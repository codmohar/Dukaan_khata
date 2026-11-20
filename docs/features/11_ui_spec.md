# UI Spec (Web + Mobile)

Principle: busy kirana counter. Big touch targets, minimal text, voice-first, colour-coded.

## Card colours (Voice Khata, `/voice` + mobile home)
| Card | Colour | Content |
|---|---|---|
| Draft transaction | Amber | `Ramesh • Son: Arjun`, amount, mode badge (Cash/UPI/Credit), item note, Confirm / Edit / Cancel |
| Rule warning (on draft) | Red banner | Rule message, buttons "Continue anyway" / "Change amount" |
| Promise recorded | Blue | `Ramesh • ₹500 • Fri 21 Nov — Ledger balance unchanged` |
| Rule saved | Purple | Rule text, Undo |
| Reconciliation | Green/Orange | MATCHED green, NEEDS_INVESTIGATION orange |

## Dashboard `/`
- New card "Today's Promises & Alerts": due today list (max 5), overdue count (red), button "Start Evening Reconciliation" (becomes "Reconciled ✓" after today's run).

## Customer page `/customers/[id]`
- Household balance header (single number).
- Member filter pills: All | Ramesh | Arjun (Son) ... each with spend total; "+ Add member".
- Tabs: Ledger | Timeline.
- Timeline row: date/time (IST), type, amount, member badge, mode icon, item note, transcript quote, balance_after, "override" flag. Red banner if `balance_mismatch`.

## New page `/memory` (sidebar: "Memory & Rules")
Tabs:
1. **Promise Memory** – Pending / Overdue / Fulfilled filters; each row: entity, type icon, amount/description, date, actions (Reschedule, Cancel, "Mark Fulfilled via Payment" -> opens payment draft).
2. **Dukaan Rules** – list with toggle switch, rule text, category chip, delete, "Add by voice" mic.
3. **Daily Reconciliations** – history table (date, cash diff, UPI diff, status), row click -> findings detail with links to transactions, "Mark Resolved".
Plus a search box "Ask memory" (text + mic) -> results with source badges.

## Reconciliation modal (3 steps)
1. Cash: Recorded ₹X vs Actual (numeric input / voice) 
2. UPI: Recorded ₹Y vs Actual
3. Result: differences, findings list, "Save", link to review items.
Show the note "Covers khata payments only" when cash sales aren't tracked.

## Mobile app
- Same cards on home voice screen; bottom tab "Memory" (Promises/Rules/Reconciliation segmented control); customer screen with member pills and timeline list.

## Accessibility & i18n
- All new strings go through the existing i18n mechanism (English, Hindi, Kannada). Large fonts, high contrast, ₹ formatting with `Intl.NumberFormat('en-IN')`.
- Loading/empty/error states for every list.

