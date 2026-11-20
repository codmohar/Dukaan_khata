# Feature 2 – Dukaan Rules

## Goal
Shopkeeper speaks policies; the system stores them as structured rules and checks them on every CREDIT draft. Rules WARN; the shopkeeper can override explicitly.

## Rule categories and `structured_condition` schemas

| Category | Example speech | structured_condition |
|---|---|---|
| NEW_CUSTOMER_CAP | "No more than 1000 credit to new customers" | `{"max_amount":1000,"new_customer_max_prior_txns":0}` |
| BALANCE_CAP | "Never let anyone's balance go above 5000" | `{"max_balance":5000}` |
| TIME_CUTOFF | "No credit after 8 PM" | `{"after":"20:00","before":null,"tz":"Asia/Kolkata"}` |
| MEMBER_AUTH | "Arjun can collect for Ramesh" / "Only Ramesh himself, not Arjun" | `{"customer_id":"...","member_id":"...","allowed":true}` |
| CUSTOM_NOTE | "Don't give credit to Manoj's brother" | `{"note":"..."}` (informational; surfaced via memory, not auto-evaluated) |

"New customer" definition (configurable constant): customer has zero confirmed prior transactions OR created < 14 days ago.

## Voice flow
Create: LLM -> `save_shop_rule(rule_text, rule_category, structured_condition)` -> backend validates JSON against schema -> reads back: "Rule saved: no credit above ₹1,000 for new customers. Correct?" -> purple card. (Rules themselves are saved after a yes; they affect policy, not money, so one confirmation is enough.)

Enforce: `upsert_draft` (CREDIT only) internally calls `evaluate_shop_rules(...)` and stores results in `draft_transactions.rule_warnings`:
```json
[{"rule_id":"...","category":"NEW_CUSTOMER_CAP","message":"Manoj is a new customer. Your rule allows up to ₹1,000.","severity":"BLOCK_UNLESS_OVERRIDE"}]
```
Agent speaks warnings and asks: "Continue anyway or change amount?"
- "Continue anyway" -> tool `override_rule_warnings(draft_id)` sets `override=true`; `confirm_draft` writes `transactions.rule_override=true`.
- "Make it 1000" -> `upsert_draft` updates amount, re-evaluates.
- `confirm_draft` REFUSES if unresolved warnings exist and no override flag.

## Evaluation order and safety
- Evaluate ALL active rules, return ALL violations (not first only).
- Deterministic Python/SQL; the LLM only *parses* rules, never *decides* violations.
- If rule JSON is malformed at runtime, skip it and log an error; never crash the confirm path.
- PAYMENT entries are never blocked by rules.

## Backend
- `save_shop_rule`, `list_shop_rules`, `toggle_shop_rule`, `evaluate_shop_rules` (internal service), `override_rule_warnings`.
- Endpoints: CRUD + toggle (see `10_api_endpoints.md`).

## UI
- Red warning banner on amber draft card with Continue / Change amount buttons.
- Memory & Rules page -> Dukaan Rules tab: list, toggle switch, delete, "Add by voice" button.

## Acceptance
- New customer + ₹1,500 credit -> warning; override -> saved with `rule_override=true`.
- After 8 PM rule -> credit at 20:30 IST warns, payment does not.
- Toggled-off rule is ignored.

