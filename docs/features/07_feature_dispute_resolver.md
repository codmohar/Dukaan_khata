# Feature 5 – Smart Dispute Resolver

## Goal
When a customer says "I already paid", show an auditable timeline with evidence.

## Tool: `get_dispute_timeline(customer_name, limit=5, member_name?, date_from?, date_to?)`
Returns, per row (newest first, but running balance computed chronologically):
```json
{"customer":{"id":"...","name":"Ramesh"},
 "current_balance":1250.00,
 "rows":[{"transaction_id":"...","at":"2026-11-18T18:42:00+05:30","type":"PAYMENT","amount":500.00,
          "member_name":null,"payment_mode":"UPI","item_note":null,
          "transcript_snippet":"Ramesh ne 500 diya UPI se","balance_after":1250.00,"rule_override":false}]}
```

## Running balance math
Compute with a window function over the household's transactions ordered by `created_at, id`:
```sql
SELECT t.*, hm.member_name,
       SUM(CASE WHEN t.type='CREDIT' THEN t.amount ELSE -t.amount END)
         OVER (PARTITION BY t.customer_id ORDER BY t.created_at, t.id) AS balance_after
FROM transactions t
LEFT JOIN household_members hm ON hm.id = t.member_id
WHERE t.customer_id = $1 AND t.shop_id = $2
```
Take last N after computing (use a subquery/CTE; do NOT limit before the window sum). If the table has an opening balance, add it. Verify `balance_after` of the newest row equals `customers.outstanding_balance`; if not, return `balance_mismatch: true` so the agent says so honestly.

## Voice response style
Short: "Ramesh's last 3 entries: Nov 18, ₹500 payment by UPI; Nov 15, ₹250 credit for Arjun, rice; ... Current balance ₹1,250." Full detail on screen.

## Evidence
- `transcript_snippet` is saved at confirmation (the confirmed utterance text). Do not store audio unless the project already does; if it does, add optional `audio_url`.
- The agent must not take sides; it presents facts only.

## UI
- Customer page "Timeline" view: rows with member badge, mode icon (Cash/UPI/Credit), item note, transcript quote, balance_after, override flag.
- Export/print as PDF (phase 2) so the shopkeeper can show the customer.

## Acceptance
- Last-5 query returns right rows and balance_after chain.
- Member filter works.
- Mismatch flag appears when balance is deliberately corrupted in test data.

