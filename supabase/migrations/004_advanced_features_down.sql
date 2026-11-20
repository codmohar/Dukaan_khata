-- DukaanAI Rollback Migration 004: Advanced Features

DROP TRIGGER IF EXISTS trg_tx_member_check ON transactions;
DROP FUNCTION IF EXISTS enforce_member_matches_customer();

DROP VIEW IF EXISTS draft_transactions;
DROP VIEW IF EXISTS promises_effective;

DROP TABLE IF EXISTS daily_reconciliations;
DROP TABLE IF EXISTS shop_rules;
DROP TABLE IF EXISTS promises;
DROP TABLE IF EXISTS household_members;

ALTER TABLE transactions
    DROP COLUMN IF EXISTS member_id,
    DROP COLUMN IF EXISTS item_note,
    DROP COLUMN IF EXISTS rule_warnings,
    DROP COLUMN IF EXISTS transcript_snippet,
    DROP COLUMN IF EXISTS rule_override;

ALTER TABLE customers
    DROP COLUMN IF EXISTS outstanding_balance;

