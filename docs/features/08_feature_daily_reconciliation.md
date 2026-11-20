# Feature 6 – AI Daily Khata Reconciliation

## Goal
End-of-day check: physical cash and UPI received vs what the khata recorded. Flags discrepancies; NEVER auto-adjusts balances or books a "loss".

## What "recorded" means (important)
Recorded cash/UPI = SUM of confirmed `PAYMENT` transactions today (IST) grouped by `payment_mode` (`CASH`, `UPI`). CREDIT entries are not money received. If the shop also records cash sales (non-khata), include that type too; **Antigravity must check whether such sales exist in the schema** and, if not, show a clear note: "Reconciliation covers khata payments only; cash sales not recorded in DukaanAI are excluded." Otherwise the shopkeeper will see false mismatches.
"Today" = `[00:00, 24:00)` in Asia/Kolkata, not UTC.

## Flow (voice or tap)
1. "Start daily khata check" -> tool `start_reconciliation()` returns recorded_cash, recorded_upi, counts.
2. Agent asks "How much cash payment did you collect today?" -> shopkeeper answers -> confirm number by readback.
3. Agent asks for UPI -> readback.
4. `run_daily_reconciliation(actual_cash, actual_upi)` computes differences (`recorded - actual`), runs analyzers, upserts `daily_reconciliations` (unique per shop/day; re-run overwrites and keeps history in audit_notes).
5. Status `MATCHED` if both diffs are 0, else `NEEDS_INVESTIGATION`. Shopkeeper can later mark `RESOLVED` with a note.

## Analyzers (deterministic SQL, return structured `findings`)
- Unconfirmed drafts today: `draft_transactions` still pending -> "1 unconfirmed draft ₹500 at 4:15 PM".
- Possible duplicates: same customer, same amount, same type, within 5 minutes.
- Amount equals difference: any transaction/draft equal to |difference| (possible missed or extra entry).
- Wrong mode suspicion: a CASH entry whose amount equals the UPI shortfall or vice versa (swap).
- Large single entries, entries with `rule_override=true` (informational).
- Payments recorded but deleted/edited today, if audit tables exist.
Each finding: `{"kind":"POSSIBLE_DUPLICATE","transaction_ids":[...],"message":"..."}`

The LLM only *narrates* findings; it must not invent causes beyond `findings`.

## Tools
`start_reconciliation`, `run_daily_reconciliation(actual_cash, actual_upi, notes?)`, `resolve_reconciliation(id, note)`.

## UI
- Dashboard "Start Evening Reconciliation" button.
- 3-step modal: Recorded vs Actual cash -> Recorded vs Actual UPI -> Result with findings and links to the suspicious transactions.
- Memory & Rules -> Daily Reconciliations tab: history list with status badge and difference.

## Acceptance
- Matching totals -> MATCHED, no findings.
- Seed 2 identical ₹250 entries 2 min apart -> duplicate finding.
- Leaving a draft unconfirmed -> appears in findings.
- No change to any `outstanding_balance` or `transactions` row after reconciliation.
- IST day boundary tested (entry at 23:50 IST belongs to today).

