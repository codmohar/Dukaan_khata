# FastAPI Endpoint Contract

All endpoints: auth required, scoped by the caller's `shop_id`, JSON, Pydantic models, money as string/Decimal. Prefix `/api/v1` or `/api`. Match existing routing/auth conventions.

## Household
| Method | Path | Notes |
|---|---|---|
| GET | `/customers/{id}/members` | list members with per-member totals (credit sum, payment sum) |
| POST | `/customers/{id}/members` | `{member_name, relationship, is_authorized}` |
| PATCH | `/members/{id}` | edit / toggle authorized |
| DELETE | `/members/{id}` | allowed; transactions keep `member_id` NULL (ON DELETE SET NULL) |
| GET | `/customers/{id}/transactions?member_id=&from=&to=` | extend existing endpoint with filters |

## Rules
| Method | Path | Notes |
|---|---|---|
| GET | `/rules` | list |
| POST | `/rules` | `{rule_text, rule_category, structured_condition}` validated |
| PATCH | `/rules/{id}` | `{is_active}` toggle / edit text |
| DELETE | `/rules/{id}` | |
| POST | `/drafts/{id}/override-rules` | marks override; logged |

## Promises
| Method | Path | Notes |
|---|---|---|
| GET | `/promises?status=&date=&customer_id=` | uses `promises_effective` |
| POST | `/promises` | creates (ledger untouched) |
| PATCH | `/promises/{id}` | reschedule / cancel |
| POST | `/promises/{id}/fulfil-via-payment` | creates a PAYMENT *draft* pre-filled; returns draft id (does not confirm) |
| GET | `/dashboard/promises-summary` | `{due_today, overdue, total_pending_amount}` |

## Memory
| Method | Path | Notes |
|---|---|---|
| POST | `/memory/search` | `{entity_name?, keyword?, date_from?, date_to?, scope?}` |

## Dispute timeline
| Method | Path | Notes |
|---|---|---|
| GET | `/customers/{id}/timeline?limit=&member_id=&from=&to=` | includes `balance_after`, `balance_mismatch` |

## Reconciliation
| Method | Path | Notes |
|---|---|---|
| GET | `/reconciliation/today` | recorded cash/UPI + counts |
| POST | `/reconciliation` | `{actual_cash, actual_upi, notes?}` -> result + findings |
| GET | `/reconciliation?from=&to=` | history |
| PATCH | `/reconciliation/{id}/resolve` | `{note}` |

## Existing endpoints to extend
- Draft and transaction schemas gain `member_id`, `payment_mode`, `item_note`, `rule_warnings`, `transcript_snippet`.
- `confirm_draft` runs the extension inside one DB transaction.

## Realtime events (WebSocket -> clients)
`draft_card` (with member + warnings), `promise_card`, `rule_card`, `timeline`, `reconciliation_prompt`, `reconciliation_result`.

