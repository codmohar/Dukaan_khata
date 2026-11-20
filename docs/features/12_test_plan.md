# Test Plan (acceptance)

Run against a dev DB with seed data: shop A and shop B, customers Ramesh (household with Arjun, Sunita), Manoj (new, 0 txns), Suresh.

## Unit / service tests
| # | Test | Expected |
|---|---|---|
| H1 | Credit ₹250 for Ramesh/Arjun, confirm | household balance +250, tx.member_id=Arjun |
| H2 | Insert tx with member of another customer | DB error |
| H3 | Ambiguous "Arjun" across two households | `ambiguous` result |
| R1 | Manoj, ₹1,500 credit, rule cap 1,000 | warning; confirm blocked without override |
| R2 | Same with override | saved, `rule_override=true` |
| R3 | PAYMENT of any amount | no rule evaluated |
| R4 | TIME_CUTOFF 20:00, credit at 20:30 IST | warning |
| R5 | Rule `is_active=false` | ignored |
| R6 | Malformed structured_condition in DB | skipped, no exception |
| P1 | create_promise ₹500 | balance and tx count unchanged |
| P2 | Confirm ₹500 payment | promise FULFILLED, linked tx |
| P3 | Confirm ₹200 payment vs ₹500 promise | promise stays PENDING |
| P4 | Promise date yesterday | effective_status OVERDUE |
| P5 | Two payments, one promise | only one fulfilment |
| M1 | "who asked to keep rice" with data | correct row + IST time |
| M2 | Query with no data | count 0 and agent says nothing recorded |
| M3 | Shop B queries | never see shop A rows |
| D1 | Last 5 timeline | correct order and balance_after chain |
| D2 | Corrupt balance | `balance_mismatch=true` |
| D3 | Member filter | only that member's rows |
| C1 | Matching totals | MATCHED |
| C2 | Two identical ₹250 within 2 min | POSSIBLE_DUPLICATE |
| C3 | Pending draft today | UNCONFIRMED_DRAFT |
| C4 | Entry at 23:50 IST | counted today |
| C5 | Reconciliation run | no change in balances/transactions |
| C6 | Re-run same day | updates row (unique constraint) |

## Voice scenario tests (scripted transcripts, mixed languages)
- "Ramesh ke bete Arjun ko 250 udhaar likho"
- "Ramesh shukravaar ko 500 dega" -> promise, NOT draft
- "1000 se zyada udhaar naye customer ko mat dena" -> rule saved
- "Ramesh ke last 5 transactions dikhao" -> timeline
- "Daily khata check shuru karo" -> reconciliation flow
- Kannada equivalents for each

## Regression
- Existing draft -> confirm flow unchanged for customers without members/rules.
- Existing transactions with NULL member/payment_mode render correctly (payment_mode defaults CASH; consider backfill note: historical credit rows should be 'CREDIT').

## Done = all above pass + migration reversible on dev + no secrets/keys in repo.

