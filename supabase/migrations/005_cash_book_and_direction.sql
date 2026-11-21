-- Migration 005: Shop Cash Book, Refund Support, and Directional Money Flows
-- 1. Cash Book Entries Table (Cash Inflow, Outflow, Shop Drawer Balances)
CREATE TABLE IF NOT EXISTS cash_book_entries (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    shop_id UUID NOT NULL REFERENCES shops(id) ON DELETE CASCADE,
    type VARCHAR(20) NOT NULL CHECK (type IN ('cash_in', 'cash_out')),
    amount NUMERIC(12, 2) NOT NULL CHECK (amount > 0),
    reason VARCHAR(100) DEFAULT 'general', -- 'deposit', 'withdrawal', 'expense', 'daily_cash', 'supplier_payment', 'change', 'other'
    description TEXT,
    payment_mode VARCHAR(20) DEFAULT 'cash',
    transaction_date DATE NOT NULL DEFAULT CURRENT_DATE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_cash_book_shop ON cash_book_entries(shop_id);
CREATE INDEX IF NOT EXISTS idx_cash_book_date ON cash_book_entries(shop_id, transaction_date);

-- 2. Extend Transaction Types to Support 'refund'
ALTER TABLE transactions DROP CONSTRAINT IF EXISTS transactions_type_check;
ALTER TABLE transactions ADD CONSTRAINT transactions_type_check
    CHECK (type IN ('credit', 'payment', 'adjustment', 'refund'));

-- 3. Extend Adjustment Reasons to Support 'round_off' and 'refund'
ALTER TABLE transactions DROP CONSTRAINT IF EXISTS transactions_adjustment_reason_check;
ALTER TABLE transactions ADD CONSTRAINT transactions_adjustment_reason_check
    CHECK (adjustment_reason IS NULL OR lower(adjustment_reason) IN ('discount', 'return', 'write_off', 'correction', 'round_off', 'refund'));

-- 4. Allow customer_id to be nullable for general shop-level transactions
ALTER TABLE transactions ALTER COLUMN customer_id DROP NOT NULL;
