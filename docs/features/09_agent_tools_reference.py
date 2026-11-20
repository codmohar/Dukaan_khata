"""
DukaanAI advanced features - REFERENCE implementation.

Antigravity: this is a reference, not drop-in code. Adapt to the project's actual
DB layer (asyncpg / SQLAlchemy / supabase client), tool registration style for
Pipecat, naming, and error handling. Keep the logic and invariants.

Assumed: `db` is an asyncpg-like connection/pool with fetch/fetchrow/fetchval/execute,
and `conn` inside `async with db.transaction()` for atomic work.
"""
from __future__ import annotations

import json
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from typing import Any, Optional
from zoneinfo import ZoneInfo

IST = ZoneInfo("Asia/Kolkata")
NEW_CUSTOMER_DAYS = 14


def today_ist() -> date:
    return datetime.now(IST).date()


def ist_day_bounds(d: date) -> tuple[datetime, datetime]:
    start = datetime.combine(d, time.min, tzinfo=IST)
    return start, start + timedelta(days=1)


# ---------------------------------------------------------------- Feature 1
async def resolve_household_member(db, shop_id, customer_name: str,
                                   member_name: Optional[str] = None,
                                   relationship: Optional[str] = None) -> dict:
    customers = await db.fetch(
        """SELECT id, name, similarity(name, $2) AS sim
           FROM customers WHERE shop_id=$1 AND similarity(name, $2) > 0.4
           ORDER BY sim DESC LIMIT 5""", shop_id, customer_name)
    if not customers:
        return {"status": "customer_not_found"}
    if len(customers) > 1 and customers[0]["sim"] - customers[1]["sim"] < 0.15:
        return {"status": "ambiguous",
                "candidates": [{"customer_id": str(c["id"]), "name": c["name"]} for c in customers]}
    cust = customers[0]
    if not member_name:
        return {"status": "resolved", "customer_id": str(cust["id"]), "member_id": None}
    member = await db.fetchrow(
        """SELECT id, member_name FROM household_members
           WHERE customer_id=$1 AND similarity(member_name,$2) > 0.4
           ORDER BY similarity(member_name,$2) DESC LIMIT 1""", cust["id"], member_name)
    if member:
        return {"status": "resolved", "customer_id": str(cust["id"]), "member_id": str(member["id"])}
    return {"status": "member_not_found", "customer_id": str(cust["id"]),
            "suggested_member": {"name": member_name, "relationship": relationship}}


async def add_household_member(db, shop_id, customer_id, member_name, relationship=None):
    return await db.fetchval(
        """INSERT INTO household_members(shop_id, customer_id, member_name, relationship)
           VALUES ($1,$2,$3,$4)
           ON CONFLICT (customer_id, member_name) DO UPDATE SET relationship=EXCLUDED.relationship
           RETURNING id""", shop_id, customer_id, member_name, relationship)


# ---------------------------------------------------------------- Feature 2
async def save_shop_rule(db, shop_id, rule_category: str, rule_text: str, structured_condition: dict):
    validate_rule_condition(rule_category, structured_condition)
    rid = await db.fetchval(
        """INSERT INTO shop_rules(shop_id, rule_category, rule_text, structured_condition)
           VALUES ($1,$2,$3,$4::jsonb) RETURNING id""",
        shop_id, rule_category, rule_text, json.dumps(structured_condition))
    return {"rule_id": str(rid), "rule_text": rule_text}


def validate_rule_condition(category: str, cond: dict) -> None:
    required = {
        "NEW_CUSTOMER_CAP": ["max_amount"],
        "BALANCE_CAP": ["max_balance"],
        "TIME_CUTOFF": ["after"],
        "MEMBER_AUTH": ["customer_id", "member_id", "allowed"],
        "CUSTOM_NOTE": ["note"],
    }
    missing = [k for k in required.get(category, []) if k not in cond]
    if category not in required or missing:
        raise ValueError(f"Invalid rule for {category}: missing {missing}")


async def evaluate_shop_rules(db, shop_id, customer_id, member_id,
                              amount: Decimal, now: Optional[datetime] = None) -> list[dict]:
    """Deterministic. Called ONLY for CREDIT drafts. Returns ALL violations."""
    now = (now or datetime.now(IST)).astimezone(IST)
    rules = await db.fetch(
        "SELECT * FROM shop_rules WHERE shop_id=$1 AND is_active", shop_id)
    cust = await db.fetchrow(
        """SELECT c.name, c.outstanding_balance, c.created_at,
                  (SELECT COUNT(*) FROM transactions t WHERE t.customer_id=c.id) AS prior_txns
           FROM customers c WHERE c.id=$1""", customer_id)
    warnings: list[dict] = []
    for r in rules:
        try:
            cond = r["structured_condition"]
            cond = json.loads(cond) if isinstance(cond, str) else cond
            cat = r["rule_category"]
            msg = None
            if cat == "NEW_CUSTOMER_CAP":
                is_new = cust["prior_txns"] <= cond.get("new_customer_max_prior_txns", 0) or \
                         (now - cust["created_at"]).days < NEW_CUSTOMER_DAYS
                if is_new and amount > Decimal(str(cond["max_amount"])):
                    msg = f"{cust['name']} is a new customer. Your rule allows up to ₹{cond['max_amount']}."
            elif cat == "BALANCE_CAP":
                if cust["outstanding_balance"] + amount > Decimal(str(cond["max_balance"])):
                    msg = f"This would take {cust['name']}'s balance above your ₹{cond['max_balance']} limit."
            elif cat == "TIME_CUTOFF":
                after = time.fromisoformat(cond["after"])
                before = time.fromisoformat(cond["before"]) if cond.get("before") else None
                t = now.time()
                if t >= after or (before and t < before):
                    msg = f"Your rule says no credit after {cond['after']}."
            elif cat == "MEMBER_AUTH":
                if (str(cond["customer_id"]) == str(customer_id)
                        and member_id and str(cond["member_id"]) == str(member_id)
                        and not cond["allowed"]):
                    msg = "This family member is not allowed to take credit under your rule."
            if msg:
                warnings.append({"rule_id": str(r["id"]), "category": cat, "message": msg,
                                 "severity": "BLOCK_UNLESS_OVERRIDE"})
        except Exception as e:  # never break the confirm path on a bad rule
            print(f"[rules] skipped malformed rule {r['id']}: {e}")
    return warnings


# ---------------------------------------------------------------- upsert_draft / confirm_draft hooks
async def upsert_draft_hook(db, shop_id, draft: dict) -> dict:
    """Call at the end of the existing upsert_draft. Adds warnings for CREDIT only."""
    if draft["type"] == "CREDIT":
        draft["rule_warnings"] = await evaluate_shop_rules(
            db, shop_id, draft["customer_id"], draft.get("member_id"), Decimal(str(draft["amount"])))
    else:
        draft["rule_warnings"] = []
    return draft


async def confirm_draft_extension(conn, shop_id, draft: dict, transcript_snippet: str):
    """
    Run INSIDE the existing confirm_draft DB transaction, after locking the customer row.
    1. refuse if warnings exist and draft not overridden
    2. insert transaction with member/payment_mode/item_note/transcript_snippet/rule_override
    3. update outstanding_balance
    4. if PAYMENT: auto-fulfil promise
    """
    if draft["rule_warnings"] and not draft.get("override"):
        raise ValueError("Unresolved Dukaan Rule warnings. Override or change amount.")


# ---------------------------------------------------------------- Feature 3
async def create_promise(db, shop_id, entity_name, promise_type, description, expected_date: date,
                         promised_amount=None, customer_id=None, member_id=None, transcript=None):
    if promise_type == "PAYMENT_PROMISE" and not promised_amount:
        raise ValueError("Payment promise needs an amount")
    pid = await db.fetchval(
        """INSERT INTO promises(shop_id, customer_id, member_id, entity_name, promise_type,
                                promised_amount, description, expected_date, source_transcript)
           VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9) RETURNING id""",
        shop_id, customer_id, member_id, entity_name, promise_type,
        promised_amount, description, expected_date, transcript)
    return {"promise_id": str(pid), "ledger_changed": False}


async def auto_fulfil_promise(conn, shop_id, customer_id, amount: Decimal, tx_id) -> Optional[dict]:
    rows = await conn.fetch(
        """SELECT id, promised_amount FROM promises
           WHERE shop_id=$1 AND customer_id=$2 AND promise_type='PAYMENT_PROMISE'
             AND status='PENDING'
           ORDER BY expected_date, created_at FOR UPDATE""", shop_id, customer_id)
    target = next((r for r in rows if r["promised_amount"] == amount), None) \
        or next((r for r in rows if amount >= r["promised_amount"]), None)
    if not target:
        return {"fulfilled": False, "pending_remaining": len(rows)} if rows else None
    await conn.execute(
        """UPDATE promises SET status='FULFILLED', fulfilled_transaction_id=$2, fulfilled_at=NOW()
           WHERE id=$1""", target["id"], tx_id)
    return {"fulfilled": True, "promise_id": str(target["id"])}


async def list_promises(db, shop_id, status=None, on_date: Optional[date] = None, customer_name=None):
    return [dict(r) for r in await db.fetch(
        """SELECT p.id, p.entity_name, p.promise_type, p.promised_amount, p.description,
                  p.expected_date, p.effective_status AS status
           FROM promises_effective p
           WHERE p.shop_id=$1
             AND ($2::text IS NULL OR p.effective_status=$2)
             AND ($3::date IS NULL OR p.expected_date=$3)
             AND ($4::text IS NULL OR similarity(p.entity_name,$4) > 0.4)
           ORDER BY p.expected_date LIMIT 20""", shop_id, status, on_date, customer_name)]


# ---------------------------------------------------------------- Feature 4
async def search_shop_memory(db, shop_id, entity_name=None, keyword=None,
                             date_from: Optional[date] = None, date_to: Optional[date] = None,
                             scope: Optional[list[str]] = None, limit: int = 10) -> dict:
    scope = scope or ["promises", "transactions", "rules"]
    results: list[dict] = []
    if "promises" in scope:
        for r in await db.fetch(
            """SELECT id, entity_name, description, expected_date, created_at, effective_status
               FROM promises_effective WHERE shop_id=$1
                 AND ($2::text IS NULL OR similarity(entity_name,$2) > 0.4)
                 AND ($3::text IS NULL OR description ILIKE '%'||$3||'%' OR similarity(description,$3) > 0.3)
                 AND ($4::date IS NULL OR created_at::date >= $4 OR expected_date >= $4)
                 AND ($5::date IS NULL OR created_at::date <= $5 OR expected_date <= $5)
               ORDER BY created_at DESC LIMIT $6""",
                shop_id, entity_name, keyword, date_from, date_to, limit):
            results.append({"source": "promise", "id": str(r["id"]),
                            "when": r["created_at"].astimezone(IST).isoformat(),
                            "summary": f"{r['entity_name']}: {r['description']} (expected {r['expected_date']})",
                            "status": r["effective_status"]})
    if "transactions" in scope and keyword:
        for r in await db.fetch(
            """SELECT t.id, t.created_at, t.amount, t.type, t.item_note, c.name AS customer, hm.member_name
               FROM transactions t JOIN customers c ON c.id=t.customer_id
               LEFT JOIN household_members hm ON hm.id=t.member_id
               WHERE t.shop_id=$1 AND t.item_note IS NOT NULL
                 AND (t.item_note ILIKE '%'||$2||'%' OR similarity(t.item_note,$2) > 0.3)
                 AND ($3::text IS NULL OR similarity(c.name,$3) > 0.4)
               ORDER BY t.created_at DESC LIMIT $4""", shop_id, keyword, entity_name, limit):
            who = r["customer"] + (f" ({r['member_name']})" if r["member_name"] else "")
            results.append({"source": "transaction", "id": str(r["id"]),
                            "when": r["created_at"].astimezone(IST).isoformat(),
                            "summary": f"{who}: {r['type']} ₹{r['amount']} - {r['item_note']}"})
    if "rules" in scope and keyword:
        for r in await db.fetch(
            """SELECT id, rule_text, created_at FROM shop_rules
               WHERE shop_id=$1 AND rule_category='CUSTOM_NOTE'
                 AND (rule_text ILIKE '%'||$2||'%') LIMIT $3""", shop_id, keyword, limit):
            results.append({"source": "rule_note", "id": str(r["id"]),
                            "when": r["created_at"].astimezone(IST).isoformat(),
                            "summary": r["rule_text"]})
    return {"results": results[:limit], "count": len(results),
            "note": "If count is 0, say nothing is recorded. Do not guess."}


# ---------------------------------------------------------------- Feature 5
async def get_dispute_timeline(db, shop_id, customer_id, limit: int = 5, member_id=None,
                               date_from=None, date_to=None) -> dict:
    rows = await db.fetch(
        """WITH ordered AS (
             SELECT t.id, t.created_at, t.type, t.amount, t.payment_mode, t.item_note,
                    t.transcript_snippet, t.rule_override, t.member_id, hm.member_name,
                    SUM(CASE WHEN t.type='CREDIT' THEN t.amount ELSE -t.amount END)
                      OVER (ORDER BY t.created_at, t.id) AS balance_after
             FROM transactions t LEFT JOIN household_members hm ON hm.id=t.member_id
             WHERE t.customer_id=$1 AND t.shop_id=$2)
           SELECT * FROM ordered
           WHERE ($3::uuid IS NULL OR member_id=$3)
             AND ($4::timestamptz IS NULL OR created_at>=$4)
             AND ($5::timestamptz IS NULL OR created_at<$5)
           ORDER BY created_at DESC, id DESC LIMIT $6""",
        customer_id, shop_id, member_id, date_from, date_to, limit)
    bal = await db.fetchval("SELECT outstanding_balance FROM customers WHERE id=$1", customer_id)
    out = [{**dict(r), "at": r["created_at"].astimezone(IST).isoformat()} for r in rows]
    mismatch = bool(rows) and date_from is None and member_id is None and rows[0]["balance_after"] != bal
    return {"current_balance": bal, "rows": out, "balance_mismatch": mismatch}


# ---------------------------------------------------------------- Feature 6
async def start_reconciliation(db, shop_id, on_date: Optional[date] = None) -> dict:
    d = on_date or today_ist()
    s, e = ist_day_bounds(d)
    rows = await db.fetch(
        """SELECT payment_mode, COALESCE(SUM(amount),0) AS total, COUNT(*) AS n
           FROM transactions WHERE shop_id=$1 AND type='PAYMENT'
             AND created_at>=$2 AND created_at<$3 GROUP BY payment_mode""", shop_id, s, e)
    by = {r["payment_mode"]: r for r in rows}
    return {"date": str(d),
            "recorded_cash": by.get("CASH", {"total": Decimal(0)})["total"],
            "recorded_upi": by.get("UPI", {"total": Decimal(0)})["total"],
            "note": "Covers khata payments only unless cash sales are recorded."}


async def run_daily_reconciliation(db, shop_id, actual_cash: Decimal, actual_upi: Decimal,
                                   on_date: Optional[date] = None, notes: Optional[str] = None) -> dict:
    d = on_date or today_ist()
    s, e = ist_day_bounds(d)
    rec = await start_reconciliation(db, shop_id, d)
    cash_diff = rec["recorded_cash"] - actual_cash
    upi_diff = rec["recorded_upi"] - actual_upi
    findings: list[dict] = []
    if cash_diff != 0 or upi_diff != 0:
        findings = await analyze_discrepancies(db, shop_id, s, e, cash_diff, upi_diff)
    status = "MATCHED" if cash_diff == 0 and upi_diff == 0 else "NEEDS_INVESTIGATION"
    rid = await db.fetchval(
        """INSERT INTO daily_reconciliations(shop_id, reconciliation_date, recorded_cash, actual_cash,
               recorded_upi, actual_upi, cash_difference, upi_difference, status, findings, audit_notes)
           VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10::jsonb,$11)
           ON CONFLICT (shop_id, reconciliation_date) DO UPDATE SET
               recorded_cash=EXCLUDED.recorded_cash, actual_cash=EXCLUDED.actual_cash,
               recorded_upi=EXCLUDED.recorded_upi, actual_upi=EXCLUDED.actual_upi,
               cash_difference=EXCLUDED.cash_difference, upi_difference=EXCLUDED.upi_difference,
               status=EXCLUDED.status, findings=EXCLUDED.findings, audit_notes=EXCLUDED.audit_notes
           RETURNING id""",
        shop_id, d, rec["recorded_cash"], actual_cash, rec["recorded_upi"], actual_upi,
        cash_diff, upi_diff, status, json.dumps(findings, default=str), notes)
    return {"reconciliation_id": str(rid), "status": status, "cash_difference": cash_diff,
            "upi_difference": upi_diff, "findings": findings}


async def analyze_discrepancies(db, shop_id, start, end, cash_diff, upi_diff) -> list[dict]:
    findings: list[dict] = []
    for r in await db.fetch(
        """SELECT id, amount, created_at FROM draft_transactions
           WHERE shop_id=$1 AND created_at>=$2 AND created_at<$3""", shop_id, start, end):
        findings.append({"kind": "UNCONFIRMED_DRAFT", "draft_id": str(r["id"]),
                         "message": f"Unconfirmed draft of ₹{r['amount']} at "
                                    f"{r['created_at'].astimezone(IST):%I:%M %p}"})
    for r in await db.fetch(
        """SELECT a.id AS a_id, b.id AS b_id, a.amount, c.name
           FROM transactions a JOIN transactions b
             ON a.customer_id=b.customer_id AND a.amount=b.amount AND a.type=b.type
            AND a.id<b.id AND ABS(EXTRACT(EPOCH FROM (a.created_at-b.created_at)))<=300
           JOIN customers c ON c.id=a.customer_id
           WHERE a.shop_id=$1 AND a.created_at>=$2 AND a.created_at<$3""", shop_id, start, end):
        findings.append({"kind": "POSSIBLE_DUPLICATE", "transaction_ids": [str(r["a_id"]), str(r["b_id"])],
                         "message": f"Two identical ₹{r['amount']} entries for {r['name']} within 5 minutes"})
    for diff, label in ((cash_diff, "cash"), (upi_diff, "UPI")):
        if diff != 0:
            for r in await db.fetch(
                """SELECT id, type, payment_mode, amount FROM transactions
                   WHERE shop_id=$1 AND created_at>=$2 AND created_at<$3 AND amount=$4""",
                    shop_id, start, end, abs(diff)):
                findings.append({"kind": "AMOUNT_MATCHES_DIFFERENCE", "transaction_id": str(r["id"]),
                                 "message": f"A ₹{r['amount']} {r['type']} entry equals the {label} difference"})
    return findings

