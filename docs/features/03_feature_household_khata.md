# Feature 1 – Household Khata

## Goal
One `customer` row = one household account and one `outstanding_balance`. Individual `household_members` (Arjun, Sunita...) are attributed on each transaction for per-person history.

## Data
- `household_members(customer_id, member_name, relationship, is_authorized)`
- `transactions.member_id`, `draft_transactions.member_id` (nullable; null = account holder / unspecified)
- DB trigger blocks member/customer mismatch.

## Voice behaviour
| Utterance | Result |
|---|---|
| "Add 250 credit for Ramesh's son Arjun" | Draft: customer=Ramesh, member=Arjun(Son), 250 CREDIT |
| "Arjun took 2 packets rice" | If only one Arjun exists in shop, resolve; else ask "Which Arjun – Ramesh's son or Suresh's son?" |
| New member name for existing household | Agent asks: "Arjun is not in Ramesh's family. Add him as Son?" -> create on yes |
| "What did Arjun take this month?" | `SUM(amount) WHERE member_id=... AND type='CREDIT' AND created_at >= month_start` via `get_member_summary` or `get_dispute_timeline` filters |

## Tool: `resolve_household_member(customer_name, member_name=None, relationship=None)`
Returns one of:
- `{status:"resolved", customer_id, member_id|null}`
- `{status:"ambiguous", candidates:[{customer_id, name, landmark?}]}` -> agent asks clarifying question
- `{status:"member_not_found", customer_id, suggested_member:{name, relationship}}` -> agent asks to add
- `{status:"customer_not_found"}` -> existing new-customer flow

Matching: normalised name + pg_trgm similarity (threshold ~0.4), handle Kannada/Hindi transliteration via the LLM before the call (LLM passes Latin-script best guess plus original).

## Backend changes
1. Add migration tables/columns.
2. Extend `upsert_draft` params: `member_id`, `payment_mode`, `item_note`.
3. Extend `confirm_draft` to copy `member_id`, `payment_mode`, `item_note`, `transcript_snippet`.
4. Endpoints: see `10_api_endpoints.md` (members CRUD, member summary).

## UI
- Customer page: member filter pills (All / each member) with per-member totals + single household balance.
- Draft card shows `Ramesh • Son: Arjun`.
- Add/edit member modal (name, relationship, authorized toggle).

## Acceptance
- Credit for member increases household balance once, member total reflects only their rows.
- Mismatched member_id insert fails at DB level.
- Existing transactions with null member_id still render ("Household").

