-- ============================================================
-- DukaanAI advanced features migration (idempotent)
-- Assumes existing tables: shops, customers, transactions, draft_transactions
-- Antigravity: VERIFY column names/types (esp. customers.id, shops.id, transactions.type) before applying.
-- Apply to DEV first.
-- ============================================================

CREATE EXTENSION IF NOT EXISTS pgcrypto;
CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- 1. HOUSEHOLD MEMBERS ---------------------------------------
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

-- 2. EXTEND DRAFTS & TRANSACTIONS ----------------------------
-- Note: In DukaanAI, drafts are stored in transactions (status='draft') or draft_transactions if separate table.
ALTER TABLE transactions
    ADD COLUMN IF NOT EXISTS member_id     UUID REFERENCES household_members(id) ON DELETE SET NULL,
    ADD COLUMN IF NOT EXISTS payment_mode  VARCHAR(20) DEFAULT 'CASH',
    ADD COLUMN IF NOT EXISTS item_note     TEXT,
    ADD COLUMN IF NOT EXISTS rule_warnings JSONB NOT NULL DEFAULT '[]',
    ADD COLUMN IF NOT EXISTS transcript_snippet TEXT,
    ADD COLUMN IF NOT EXISTS rule_override BOOLEAN NOT NULL DEFAULT FALSE;

DO $$ BEGIN
  ALTER TABLE transactions
    ADD CONSTRAINT chk_tx_payment_mode CHECK (payment_mode IN ('CASH','UPI','CREDIT','other'));
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

CREATE INDEX IF NOT EXISTS idx_tx_member       ON transactions(member_id);
CREATE INDEX IF NOT EXISTS idx_tx_shop_created ON transactions(shop_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_tx_item_trgm    ON transactions USING gin (item_note gin_trgm_ops);

-- Guard: member must belong to the same customer
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

-- 3. PROMISES -------------------------------------------------
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

-- Overdue = computed view (no cron needed)
CREATE OR REPLACE VIEW promises_effective AS
SELECT p.*,
       CASE WHEN p.status = 'PENDING' AND p.expected_date < CURRENT_DATE
            THEN 'OVERDUE' ELSE p.status END AS effective_status
FROM promises p;

-- 4. SHOP RULES ----------------------------------------------
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

-- 5. DAILY RECONCILIATIONS -----------------------------------
CREATE TABLE IF NOT EXISTS daily_reconciliations (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    shop_id       UUID NOT NULL REFERENCES shops(id) ON DELETE CASCADE,
    reconciliation_date DATE NOT NULL DEFAULT CURRENT_DATE,
    recorded_cash NUMERIC(12,2) NOT NULL,
    actual_cash   NUMERIC(12,2) NOT NULL,
    recorded_upi  NUMERIC(12,2) NOT NULL,
    actual_upi    NUMERIC(12,2) NOT NULL,
    cash_difference NUMERIC(12,2) NOT NULL,   -- recorded - actual
    upi_difference  NUMERIC(12,2) NOT NULL,
    status        VARCHAR(30) NOT NULL
                  CHECK (status IN ('MATCHED','NEEDS_INVESTIGATION','RESOLVED')),
    findings      JSONB NOT NULL DEFAULT '[]',   -- structured suspected causes
    audit_notes   TEXT,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (shop_id, reconciliation_date)
);

