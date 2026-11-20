# Feature 4 – Shopkeeper Memory (grounded recall)

## Goal
Answer open questions strictly from database rows. Never guess.

## Tool: `search_shop_memory(query_text, entity_name?, date_from?, date_to?, scope?)`
`scope` optional subset of: `promises`, `transactions`, `rules`.

Implementation (hybrid, deterministic):
1. LLM extracts structured filters (entity, date range, item keyword, promise type) and passes them in.
2. Backend queries:
   - `promises_effective`: filter by entity (trigram on `entity_name`/customer name), `expected_date`/`created_at` range, `description ILIKE` / trigram on item keywords.
   - `transactions.item_note` trigram match joined with customer/member names, date range.
   - `shop_rules` where `rule_category='CUSTOM_NOTE'` and `rule_text` trigram match.
3. Returns normalized list:
```json
{"results":[{"source":"promise","id":"...","when":"2026-11-19T16:20:00+05:30","summary":"Ramesh asked to keep 5 kg rice for 2026-11-20","status":"PENDING"}],
 "count":1}
```
4. If `count == 0` the agent must say "I found nothing recorded about that." Never infer.

## Example mapping
| Question | Filters |
|---|---|
| "What did Ramesh promise yesterday?" | promises, entity=Ramesh, created_at=yesterday |
| "Who asked me to keep 5 kg rice?" | promises GOODS_RESERVATION, keyword=rice |
| "Which supplier delivers sugar today?" | promises SUPPLIER_DELIVERY, expected_date=today, keyword=sugar |
| "What did Arjun take this month?" | route to `get_dispute_timeline` with member filter + date range (ledger facts) |

## Rules
- Cap results (default 10) and say "and N more" if truncated.
- Always include timestamps in IST in responses.
- Semantic embeddings are OPTIONAL phase 2 (pgvector). Phase 1 uses trigram + structured filters, which is more reliable for ledger-adjacent data.

## UI
- Search box in Memory & Rules page and a "Ask memory" mic button; results list with source badges.

## Acceptance
- Query with matching promise returns it with date.
- Query with no matches returns the "nothing recorded" response, no fabricated rows.
- Cross-shop data never appears (shop_id filter test).

