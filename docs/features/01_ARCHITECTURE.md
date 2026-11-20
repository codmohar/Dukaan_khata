# Architecture – Three Layers, One Pipeline

## Layers

| Layer | Purpose | Tables | Golden rule |
|---|---|---|---|
| 1. Ledger & Household Core | Hard financial truth | `customers`, `household_members`, `transactions`, `draft_transactions` | Only changed after explicit shopkeeper confirmation |
| 2. Operational Memory | Soft commitments & policies | `promises`, `shop_rules` | Never touches `outstanding_balance` |
| 3. Audit Engine | End-of-day comparison | `daily_reconciliations` | Flags only; never auto-adjusts balances |

## Non-negotiable invariants

1. `customers.outstanding_balance` changes ONLY inside `confirm_draft` (one DB transaction).
2. LLM never writes SQL and never invents data. Every answer comes from a tool result.
3. Promises, rules, memory and reconciliation never create ledger rows.
4. A `member_id` must belong to the same `customer_id` (enforced by DB trigger).
5. All money is `NUMERIC(12,2)`. No floats in Python (use `Decimal`).
6. Every query is scoped by `shop_id` (multi-tenant safety; add RLS).
7. Rules produce WARNINGS requiring explicit override; override is logged in `draft_transactions.rule_warnings`.

## Voice pipeline (per utterance)

```
Audio (Kannada/Hindi/English/code-mixed)
  -> STT
  -> Gemini 2.5 Flash with tool declarations
  -> Step 1 Intent: LEDGER | PROMISE | RULE | MEMORY_QUERY | DISPUTE_QUERY | RECONCILIATION
  -> Step 2 resolve_household_member(customer_name, member_name?)   [ask clarifying question if ambiguous]
  -> Step 3 (LEDGER CREDIT only) upsert_draft -> evaluate_shop_rules -> warnings spoken
  -> Step 4 spoken readback -> explicit "yes/confirm" -> confirm_draft (atomic)
       -> insert transactions, update outstanding_balance,
          auto-fulfil matching PENDING PAYMENT_PROMISE (on PAYMENT)
  -> TTS response + UI card event
```

Routing table:

| Utterance | Tool |
|---|---|
| "Add 250 credit for Ramesh's son Arjun" | `resolve_household_member` -> `upsert_draft` |
| "Ramesh will pay 500 on Friday" | `create_promise` |
| "Keep 2 bags rice for tomorrow" | `create_promise` (GOODS_RESERVATION) |
| "No credit above 1000 for new customers" | `save_shop_rule` |
| "Who asked me to keep rice?" | `search_shop_memory` |
| "Check Ramesh's last 5 transactions" | `get_dispute_timeline` |
| "Start daily khata check" | `run_daily_reconciliation` |

## UI event types (WebSocket/RTVI messages to clients)

`draft_card`, `promise_card`, `rule_card`, `timeline`, `reconciliation_prompt`, `reconciliation_result`.

