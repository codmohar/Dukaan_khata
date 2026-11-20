# Feature 3 – Promise Memory AI

## Critical rule
Promises NEVER modify `customers.outstanding_balance` and NEVER create `transactions` rows. They are reminders.

## Types
- `PAYMENT_PROMISE` – "Ramesh will pay ₹500 on Friday" (amount required)
- `GOODS_RESERVATION` – "Keep 2 packets rice for Sunita tomorrow"
- `SUPPLIER_DELIVERY` – "Sugar supplier will deliver on Monday" (customer_id null, entity_name = supplier)

## Voice flow
`create_promise(entity_name, promise_type, description, expected_date, promised_amount?, customer_name?, member_name?)`
- LLM resolves relative dates ("Friday", "kal", "naale") to ISO date using the **shop timezone Asia/Kolkata and today's date injected in the system prompt**. If ambiguous ("next Friday"), read the date back.
- Response (blue card): "Promise recorded: Ramesh • ₹500 • Friday 21 Nov — ledger balance unchanged."

## Auto-fulfilment (inside `confirm_draft`, same DB transaction)
On confirmed PAYMENT for customer C with amount A:
1. Find PENDING `PAYMENT_PROMISE` for C ordered by `expected_date ASC, created_at ASC`.
2. Prefer exact `promised_amount = A`. If none exact and A >= promised_amount of the oldest -> fulfil that one.
3. If A < promised_amount: leave PENDING (partial), add note in agent response: "Payment received, but promise of ₹500 is still pending."
4. Set `status='FULFILLED'`, `fulfilled_transaction_id`, `fulfilled_at`.
5. Fulfil at most ONE promise per payment (avoid double-consuming).

## Overdue
Use view `promises_effective` (computed), so no background job is required. Optional: `pg_cron` nightly `UPDATE promises SET status='OVERDUE' WHERE status='PENDING' AND expected_date < CURRENT_DATE`. If persisted OVERDUE is used, fulfilment must also accept OVERDUE promises.

## Tools
- `create_promise`
- `list_promises(status?, date?, customer_name?)` -> "What payments are expected tomorrow?"
- `update_promise(promise_id, action: FULFIL_MANUAL | CANCEL | RESCHEDULE, new_date?)`

## Endpoints / UI
- CRUD + manual fulfil (see `10_api_endpoints.md`).
- Dashboard card: "Today's Promises & Alerts" (due today, overdue count).
- Memory & Rules -> Promise Memory tab with Pending / Overdue / Fulfilled badges; one-tap "Mark Fulfilled via Payment" which opens the normal payment draft pre-filled (it must still go through draft + confirm; never directly mutate the ledger).

## Acceptance
- Creating a promise leaves balance and transaction count unchanged.
- Confirming a ₹500 payment fulfils the ₹500 promise and links the transaction.
- ₹200 payment against ₹500 promise leaves it PENDING.
- Promise dated yesterday appears as OVERDUE.

