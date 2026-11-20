-- DukaanAI Migration 004: Advanced Features
-- 1. Household Khata
-- 2. Dukaan Rules
-- 3. Promise Memory AI
-- 4. Shopkeeper Memory
-- 5. Smart Dispute Resolver
-- 6. AI Daily Khata Reconciliation

CREATE EXTENSION IF NOT EXISTS pgcrypto;
CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- 1. CUSTOMERS.OUTSTANDING_BALANCE --------------------------------------
ALTER TABLE customers ADD COLUMN IF NOT EXISTS outstanding_balance NUMERIC(12,2) NOT NULL DEFAULT 0.00;

-- Backfill from customer_balances view if balance view exists
UPDATE customers c
SET outstanding_balance = COALESCE(b.balance, 0.00)
FROM customer_balances b
WHERE b.customer_id = c.id;

-- 2. HOUSEHOLD MEMBERS --------------------------------------------------
CREATE TABLE IF NOT EXISTS household_members (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    customer_id   UUID NOT NULL REFERENCES customers(id) ON DELETE CASCADE,
    shop_id       UUID NOT NULL REFERENCES shops(id)     ON DELETE CASCADE,
    member_name   VARCHAR(120) NOT NULL,
    relationship  VARCHAR(60),
    is_authorized BOOLEAN NOT NULL DEFAULT TRUE,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (customer_id, member_name)
);

CREATE INDEX IF NOT EXISTS idx_hm_customer ON household_members(customer_id);
CREATE INDEX IF NOT EXISTS idx_hm_shop     ON household_members(shop_id);
CREATE INDEX IF NOT EXISTS idx_hm_name_trgm ON household_members USING gin (member_name gin_trgm_ops);

-- 3. EXTEND TRANSACTIONS ------------------------------------------------
ALTER TABLE transactions
    ADD COLUMN IF NOT EXISTS member_id          UUID REFERENCES household_members(id) ON DELETE SET NULL,
    ADD COLUMN IF NOT EXISTS item_note          TEXT,
    ADD COLUMN IF NOT EXISTS rule_warnings      JSONB NOT NULL DEFAULT '[]',
    ADD COLUMN IF NOT EXISTS transcript_snippet TEXT,
    ADD COLUMN IF NOT EXISTS rule_override      BOOLEAN NOT NULL DEFAULT FALSE;

-- Ensure payment_mode supports cash, upi, credit, other (case-insensitive)
ALTER TABLE transactions DROP CONSTRAINT IF EXISTS chk_tx_payment_mode;
ALTER TABLE transactions DROP CONSTRAINT IF EXISTS transactions_payment_mode_check;
ALTER TABLE transactions ADD CONSTRAINT transactions_payment_mode_check
    CHECK (payment_mode IS NULL OR lower(payment_mode) IN ('cash', 'upi', 'credit', 'other'));

-- Backfill payment_mode on historical rows
UPDATE transactions SET payment_mode = 'credit' WHERE type = 'credit' AND payment_mode IS NULL;
UPDATE transactions SET payment_mode = 'cash' WHERE type = 'payment' AND payment_mode IS NULL;

CREATE INDEX IF NOT EXISTS idx_tx_member ON transactions(member_id);
CREATE INDEX IF NOT EXISTS idx_tx_item_trgm ON transactions USING gin (item_note gin_trgm_ops);

-- Guard trigger: member_id must belong to the same customer_id
CREATE OR REPLACE FUNCTION enforce_member_matches_customer() RETURNS trigger AS $$
BEGIN
  IF NEW.member_id IS NOT NULL THEN
    IF NOT EXISTS (SELECT 1 FROM household_members hm
                   WHERE hm.id = NEW.member_id AND hm.customer_id = NEW.customer_id) THEN
      RAISE EXCEPTION 'member_id % does not belong to customer_id %', NEW.member_id, NEW.customer_id;
    END IF;
  END IF;
  RETURN NEW;
END $$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_tx_member_check ON transactions;
CREATE TRIGGER trg_tx_member_check BEFORE INSERT OR UPDATE ON transactions
  FOR EACH ROW EXECUTE FUNCTION enforce_member_matches_customer();

-- Compatibility view for draft_transactions
CREATE OR REPLACE VIEW draft_transactions AS
SELECT * FROM transactions WHERE status = 'draft';

-- 4. PROMISES -----------------------------------------------------------
CREATE TABLE IF NOT EXISTS promises (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    shop_id       UUID NOT NULL REFERENCES shops(id) ON DELETE CASCADE,
    customer_id   UUID REFERENCES customers(id) ON DELETE SET NULL,
    member_id     UUID REFERENCES household_members(id) ON DELETE SET NULL,
    entity_name   VARCHAR(120) NOT NULL,
    promise_type  VARCHAR(30) NOT NULL
                  CHECK (promise_type IN ('PAYMENT_PROMISE','GOODS_RESERVATION','SUPPLIER_DELIVERY')),
    promised_amount NUMERIC(12,2) CHECK (promised_amount IS NULL OR promised_amount > 0),
    description   TEXT NOT NULL,
    expected_date DATE NOT NULL,
    status        VARCHAR(20) NOT NULL DEFAULT 'PENDING'
                  CHECK (status IN ('PENDING','FULFILLED','OVERDUE','CANCELLED')),
    fulfilled_transaction_id UUID REFERENCES transactions(id) ON DELETE SET NULL,
    source_transcript TEXT,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    fulfilled_at  TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_prom_shop_status_date ON promises(shop_id, status, expected_date);
CREATE INDEX IF NOT EXISTS idx_prom_customer         ON promises(customer_id);
CREATE INDEX IF NOT EXISTS idx_prom_desc_trgm        ON promises USING gin (description gin_trgm_ops);

CREATE OR REPLACE VIEW promises_effective AS
SELECT p.*,
       CASE WHEN p.status = 'PENDING' AND p.expected_date < CURRENT_DATE
            THEN 'OVERDUE' ELSE p.status END AS effective_status
FROM promises p;

-- 5. SHOP RULES ---------------------------------------------------------
CREATE TABLE IF NOT EXISTS shop_rules (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    shop_id       UUID NOT NULL REFERENCES shops(id) ON DELETE CASCADE,
    rule_category VARCHAR(40) NOT NULL
                  CHECK (rule_category IN ('NEW_CUSTOMER_CAP','BALANCE_CAP','TIME_CUTOFF','MEMBER_AUTH','CUSTOM_NOTE')),
    rule_text     TEXT NOT NULL,
    structured_condition JSONB NOT NULL,
    is_active     BOOLEAN NOT NULL DEFAULT TRUE,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_rules_shop_active ON shop_rules(shop_id, is_active);

-- 6. DAILY RECONCILIATIONS ----------------------------------------------
CREATE TABLE IF NOT EXISTS daily_reconciliations (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    shop_id       UUID NOT NULL REFERENCES shops(id) ON DELETE CASCADE,
    reconciliation_date DATE NOT NULL DEFAULT CURRENT_DATE,
    recorded_cash NUMERIC(12,2) NOT NULL,
    actual_cash   NUMERIC(12,2) NOT NULL,
    recorded_upi  NUMERIC(12,2) NOT NULL,
    actual_upi    NUMERIC(12,2) NOT NULL,
    cash_difference NUMERIC(12,2) NOT NULL,
    upi_difference  NUMERIC(12,2) NOT NULL,
    status        VARCHAR(30) NOT NULL
                  CHECK (status IN ('MATCHED','NEEDS_INVESTIGATION','RESOLVED')),
    findings      JSONB NOT NULL DEFAULT '[]',
    audit_notes   TEXT,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (shop_id, reconciliation_date)
);

CREATE INDEX IF NOT EXISTS idx_recon_shop_date ON daily_reconciliations(shop_id, reconciliation_date DESC);

-- 7. ROW LEVEL SECURITY & REPLICATION -----------------------------------
ALTER TABLE household_members ENABLE ROW LEVEL SECURITY;
ALTER TABLE promises ENABLE ROW LEVEL SECURITY;
ALTER TABLE shop_rules ENABLE ROW LEVEL SECURITY;
ALTER TABLE daily_reconciliations ENABLE ROW LEVEL SECURITY;

DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE policyname = 'Allow public read and write on household_members') THEN
    CREATE POLICY "Allow public read and write on household_members" ON household_members FOR ALL USING (true) WITH CHECK (true);
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE policyname = 'Allow public read and write on promises') THEN
    CREATE POLICY "Allow public read and write on promises" ON promises FOR ALL USING (true) WITH CHECK (true);
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE policyname = 'Allow public read and write on shop_rules') THEN
    CREATE POLICY "Allow public read and write on shop_rules" ON shop_rules FOR ALL USING (true) WITH CHECK (true);
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE policyname = 'Allow public read and write on daily_reconciliations') THEN
    CREATE POLICY "Allow public read and write on daily_reconciliations" ON daily_reconciliations FOR ALL USING (true) WITH CHECK (true);
  END IF;
END $$;

