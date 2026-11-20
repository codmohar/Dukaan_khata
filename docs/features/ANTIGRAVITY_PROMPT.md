# Prompt to paste into Antigravity

(Attach/place all pack files in the repo under `docs/features/` first: `00_README_INTEGRATION_ORDER.md`, `01_ARCHITECTURE.md`, `02_migration_dukaan_features.sql`, `03`–`08` feature specs, `09_agent_tools_reference.py`, `10_api_endpoints.md`, `11_ui_spec.md`, `12_test_plan.md`.)

---

You are a senior full-stack engineer working inside my existing project **DukaanAI**, a voice-first digital khata for kirana shops (Pipecat + Gemini 2.5 Flash voice agent, FastAPI backend, Supabase PostgreSQL, Next.js web app, mobile app). I want you to integrate six new features into the EXISTING codebase without breaking existing behaviour.

## Source of truth
Read every file in `docs/features/` first, starting with `00_README_INTEGRATION_ORDER.md` and `01_ARCHITECTURE.md`. They define the features, invariants, schema, tool contracts, endpoints, UI and tests:
1. Household Khata  2. Dukaan Rules  3. Promise Memory AI  4. Shopkeeper Memory  5. Smart Dispute Resolver  6. AI Daily Khata Reconciliation.

`09_agent_tools_reference.py` and `02_migration_dukaan_features.sql` are REFERENCE material. Adapt them to my real stack (DB client, naming, tool registration, auth, i18n, styling). Do not copy blindly. If the docs conflict with the real code, trust the real code, adapt, and tell me.

## Phase 0 – Audit (NO edits yet)
Explore the repo and produce a short written report: real table/column names (`shops`, `customers`, `transactions`, `draft_transactions`, balance column), how `upsert_draft`/`confirm_draft` work and whether they are atomic, where agent tools are registered, system prompt location, WebSocket/RTVI event mechanism, web routes, mobile navigation, auth/RLS approach, i18n, existing tests, whether cash sales (non-khata) are recorded. List every mismatch with the docs and your planned adaptation. Then proceed unless a decision is destructive or ambiguous (in which case ask me).

## Hard invariants (never violate)
1. `customers.outstanding_balance` changes only inside `confirm_draft`, in one DB transaction, with the customer row locked.
2. Promises, rules, memory and reconciliation NEVER write to `transactions` or change balances. Reconciliation never auto-adjusts anything.
3. The LLM never writes SQL or invents data; it only calls tools and narrates tool results. Empty results -> "nothing recorded".
4. Rule evaluation is deterministic backend code; the LLM only parses rules into JSON.
5. Money uses Decimal/NUMERIC, never float. All times are handled in Asia/Kolkata; DB stores timestamptz.
6. Every query is scoped by `shop_id`; add/verify RLS and test cross-shop isolation.
7. `member_id` must belong to the `customer_id` (DB trigger).
8. Existing flows (draft -> readback -> confirm) keep working for customers with no members/rules/promises.

## Implementation order (one commit/PR-sized step per feature, run tests after each)
1. Migration: create a proper migration file in my migrations system (adapt `02_...sql`), backward compatible, with a down/rollback script. Backfill note: historical rows get payment_mode sensibly (credit -> 'CREDIT', payments -> 'CASH' unless known).
2. Household Khata -> `resolve_household_member`, extend `upsert_draft`/`confirm_draft`, endpoints, UI pills.
3. Dukaan Rules -> `save_shop_rule`, `evaluate_shop_rules` hooked into `upsert_draft` (CREDIT only), override flow, confirm guard, endpoints, UI.
4. Promise Memory -> `create_promise`, `list_promises`, `update_promise`, auto-fulfil inside `confirm_draft`, `promises_effective` view, endpoints, dashboard card.
5. Shopkeeper Memory -> `search_shop_memory` (structured filters + trigram; embeddings out of scope), endpoint, UI search.
6. Dispute Resolver -> `get_dispute_timeline` (window-function running balance, mismatch flag), endpoint, timeline UI with transcript evidence (save `transcript_snippet` on confirm).
7. Daily Reconciliation -> `start_reconciliation`, `run_daily_reconciliation`, analyzers, endpoints, 3-step modal, history tab.
8. Agent wiring: register all new tools with declarations, add the system-prompt addendum from `09_agent_tools_reference.py` (inject today's date + timezone), add UI event types (`promise_card`, `rule_card`, `timeline`, `reconciliation_*`).
9. Web UI: dashboard card, customer page pills + Timeline tab, new `/memory` page with 3 tabs, voice cards with the colour scheme in `11_ui_spec.md`. Reuse existing components and design system.
10. Mobile UI: equivalent screens/cards.
11. i18n: add English/Hindi/Kannada strings through the existing mechanism.
12. Tests: implement everything in `12_test_plan.md` (unit/service + scripted voice scenarios where feasible). Run the full suite, lint and type checks.

## Working rules
- Make the smallest necessary changes to existing files; prefer new modules (e.g. `app/services/rules.py`, `promises.py`, `reconciliation.py`, `memory.py`).
- Don't rename or remove existing columns/endpoints. Additive changes only.
- No new heavy dependencies without telling me. Don't commit secrets.
- Apply migrations to DEV only. Do not touch production.
- If something is unclear or the docs are unsafe for my schema, stop and ask a concise question rather than guessing on financial logic.

## Deliverable at the end
A summary containing: files changed/created per feature, the migration and rollback, how to run the tests, test results, any deviations from the docs and why, and a manual QA checklist I can run by voice (Hindi/Kannada/English examples).

Start with Phase 0 now.

