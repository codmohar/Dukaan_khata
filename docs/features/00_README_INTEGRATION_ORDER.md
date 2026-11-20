# DukaanAI – Advanced Features Integration Pack

Six features, one system:

1. Household Khata (family members under one account)
2. Dukaan Rules (shopkeeper-spoken policies)
3. Promise Memory AI (future payments / reservations)
4. Shopkeeper Memory (grounded Q&A)
5. Smart Dispute Resolver (audit timeline)
6. AI Daily Khata Reconciliation (cash/UPI end-of-day audit)

## Files in this pack

| File | Purpose |
|---|---|
| `ANTIGRAVITY_PROMPT.md` | The prompt to paste into Antigravity |
| `01_ARCHITECTURE.md` | Layers, golden rules, voice pipeline flow |
| `02_migration_dukaan_features.sql` | Single idempotent migration |
| `03_feature_household_khata.md` | Feature spec |
| `04_feature_dukaan_rules.md` | Feature spec |
| `05_feature_promise_memory.md` | Feature spec |
| `06_feature_shopkeeper_memory.md` | Feature spec |
| `07_feature_dispute_resolver.md` | Feature spec |
| `08_feature_daily_reconciliation.md` | Feature spec |
| `09_agent_tools_reference.py` | Reference implementation of the 8 LLM tools + services |
| `10_api_endpoints.md` | FastAPI endpoint contract |
| `11_ui_spec.md` | Web + mobile screens |
| `12_test_plan.md` | Acceptance tests |

## Recommended integration order

1. Run **audit** of the existing repo (Phase 0, no edits to existing code).
2. Apply `02_migration_dukaan_features.sql` to Supabase / PostgreSQL.
3. Feature 1 – Household (everything else depends on `member_id`).
4. Feature 2 – Rules (hooks into `upsert_draft`).
5. Feature 3 – Promises (hooks into `confirm_draft`).
6. Feature 4 – Memory (read-only, depends on 1–3 tables).
7. Feature 5 – Dispute timeline (read-only).
8. Feature 6 – Reconciliation.
9. UI: web, then mobile.
10. Run `12_test_plan.md`.

