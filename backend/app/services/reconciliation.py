"""AI Daily Khata Reconciliation Service: physical vs recorded cash/UPI audit.

Enforces:
- Financial invariant: NEVER alters balances or transactions.
- Strictly flags discrepancies and suggests potential root causes via deterministic analyzers.
- Day boundaries computed strictly in Asia/Kolkata (IST).
"""
from __future__ import annotations

import json
import logging
import uuid
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import DailyReconciliation, Transaction

log = logging.getLogger("dukaan.reconciliation")
IST = ZoneInfo("Asia/Kolkata")


def today_ist() -> date:
    return datetime.now(IST).date()


def ist_day_bounds(d: date) -> tuple[datetime, datetime]:
    """Returns midnight to midnight boundaries in UTC for an IST calendar date."""
    start_ist = datetime.combine(d, time.min, tzinfo=IST)
    end_ist = start_ist + timedelta(days=1)
    return start_ist, end_ist


async def start_reconciliation(
    s: AsyncSession,
    shop_id: str,
    on_date: date | None = None,
) -> dict[str, Any]:
    """Compute today's recorded cash and UPI payment collections."""
    d = on_date or today_ist()
    s_dt, e_dt = ist_day_bounds(d)
    sid = uuid.UUID(shop_id)

    res = await s.execute(
        text(
            """
            SELECT LOWER(COALESCE(payment_mode, 'cash')) AS mode,
                   COALESCE(SUM(amount), 0.00) AS total,
                   COUNT(*) AS n
            FROM transactions
            WHERE shop_id = :sid AND type = 'payment' AND status = 'confirmed'
              AND created_at >= :s AND created_at < :e
            GROUP BY LOWER(COALESCE(payment_mode, 'cash'))
            """
        ),
        {"sid": sid, "s": s_dt, "e": e_dt},
    )
    rows = res.mappings().all()
    by_mode = {r["mode"]: r for r in rows}

    rec_cash = Decimal(str(by_mode.get("cash", {}).get("total", 0.00)))
    rec_upi = Decimal(str(by_mode.get("upi", {}).get("total", 0.00)))
    cash_count = int(by_mode.get("cash", {}).get("n", 0))
    upi_count = int(by_mode.get("upi", {}).get("n", 0))

    return {
        "date": d.isoformat(),
        "recorded_cash": float(rec_cash),
        "recorded_upi": float(rec_upi),
        "cash_count": cash_count,
        "upi_count": upi_count,
        "note": "Covers khata payments only unless cash sales are recorded.",
    }


async def run_daily_reconciliation(
    s: AsyncSession,
    shop_id: str,
    actual_cash: Decimal | float,
    actual_upi: Decimal | float,
    on_date: date | None = None,
    notes: str | None = None,
) -> dict[str, Any]:
    """Run reconciliation comparisons, generate diagnostic findings, and upsert record."""
    d = on_date or today_ist()
    s_dt, e_dt = ist_day_bounds(d)
    sid = uuid.UUID(shop_id)

    dec_act_cash = Decimal(str(actual_cash))
    dec_act_upi = Decimal(str(actual_upi))

    rec = await start_reconciliation(s, shop_id, d)
    rec_cash = Decimal(str(rec["recorded_cash"]))
    rec_upi = Decimal(str(rec["recorded_upi"]))

    cash_diff = rec_cash - dec_act_cash  # positive: recorded > physical (missing cash)
    upi_diff = rec_upi - dec_act_upi

    findings = await analyze_discrepancies(s, shop_id, s_dt, e_dt, cash_diff, upi_diff)

    status = (
        "MATCHED"
        if cash_diff == Decimal("0.00") and upi_diff == Decimal("0.00") and not findings
        else "NEEDS_INVESTIGATION"
    )

    # Upsert into daily_reconciliations using ORM
    existing_res = await s.execute(
        select(DailyReconciliation).where(
            DailyReconciliation.shop_id == sid,
            DailyReconciliation.reconciliation_date == d,
        )
    )
    rec_obj = existing_res.scalar_one_or_none()

    if rec_obj:
        rec_obj.recorded_cash = rec_cash
        rec_obj.actual_cash = dec_act_cash
        rec_obj.recorded_upi = rec_upi
        rec_obj.actual_upi = dec_act_upi
        rec_obj.cash_difference = cash_diff
        rec_obj.upi_difference = upi_diff
        rec_obj.status = status
        rec_obj.findings = findings
        if notes:
            rec_obj.audit_notes = notes
    else:
        rec_obj = DailyReconciliation(
            id=uuid.uuid4(),
            shop_id=sid,
            reconciliation_date=d,
            recorded_cash=rec_cash,
            actual_cash=dec_act_cash,
            recorded_upi=rec_upi,
            actual_upi=dec_act_upi,
            cash_difference=cash_diff,
            upi_difference=upi_diff,
            status=status,
            findings=findings,
            audit_notes=notes,
        )
        s.add(rec_obj)

    await s.commit()
    await s.refresh(rec_obj)

    return {
        "reconciliation_id": str(rec_obj.id),
        "date": str(rec_obj.reconciliation_date),
        "status": status,
        "recorded_cash": float(rec_cash),
        "actual_cash": float(dec_act_cash),
        "cash_difference": float(cash_diff),
        "recorded_upi": float(rec_upi),
        "actual_upi": float(dec_act_upi),
        "upi_difference": float(upi_diff),
        "findings": findings,
        "audit_notes": notes,
    }


async def analyze_discrepancies(
    s: AsyncSession,
    shop_id: str,
    start: datetime,
    end: datetime,
    cash_diff: Decimal,
    upi_diff: Decimal,
) -> list[dict[str, Any]]:
    """Deterministic discrepancy analyzer identifying probable human error patterns."""
    sid = uuid.UUID(shop_id)
    findings: list[dict[str, Any]] = []

    # 1. Unconfirmed Drafts: drafts started but not confirmed
    drafts_res = await s.execute(
        text(
            """
            SELECT id, amount, type, created_at
            FROM transactions
            WHERE shop_id = :sid AND status = 'draft'
              AND created_at >= :s AND created_at < :e
            ORDER BY created_at DESC
            """
        ),
        {"sid": sid, "s": start, "e": end},
    )
    for r in drafts_res.mappings().all():
        time_str = r["created_at"].astimezone(IST).strftime("%I:%M %p")
        findings.append({
            "kind": "UNCONFIRMED_DRAFT",
            "draft_id": str(r["id"]),
            "message": f"Unconfirmed draft of ₹{r['amount']:,.0f} at {time_str} ({r['type']})",
        })

    # 2. Possible Duplicate Entries: same customer, amount, and type within 5 minutes
    dups_res = await s.execute(
        text(
            """
            SELECT a.id AS a_id, b.id AS b_id, a.amount, c.name, a.type
            FROM transactions a
            JOIN transactions b
              ON a.customer_id = b.customer_id
             AND a.amount = b.amount
             AND a.type = b.type
             AND a.id < b.id
             AND ABS(EXTRACT(EPOCH FROM (a.created_at - b.created_at))) <= 300
            JOIN customers c ON c.id = a.customer_id
            WHERE a.shop_id = :sid AND a.status = 'confirmed'
              AND a.created_at >= :s AND a.created_at < :e
            """
        ),
        {"sid": sid, "s": start, "e": end},
    )
    for r in dups_res.mappings().all():
        findings.append({
            "kind": "POSSIBLE_DUPLICATE",
            "transaction_ids": [str(r["a_id"]), str(r["b_id"])],
            "message": f"Two identical ₹{r['amount']:,.0f} {r['type']} entries for {r['name']} within 5 minutes",
        })

    # 3. Exact Difference Match: an individual entry matching the difference amount
    for diff, label in ((cash_diff, "cash"), (upi_diff, "UPI")):
        if diff != Decimal("0.00"):
            amt_target = abs(diff)
            match_res = await s.execute(
                text(
                    """
                    SELECT t.id, t.type, t.payment_mode, t.amount, c.name
                    FROM transactions t
                    JOIN customers c ON c.id = t.customer_id
                    WHERE t.shop_id = :sid AND t.status = 'confirmed'
                      AND t.created_at >= :s AND t.created_at < :e
                      AND t.amount = :target
                    """
                ),
                {"sid": sid, "s": start, "e": end, "target": amt_target},
            )
            for r in match_res.mappings().all():
                findings.append({
                    "kind": "AMOUNT_MATCHES_DIFFERENCE",
                    "transaction_id": str(r["id"]),
                    "message": f"A ₹{r['amount']:,.0f} {r['type']} entry for {r['name']} matches the {label} difference",
                })

    # 4. Mode Swap Suspicion: cash shortfall equals UPI excess or vice versa
    if cash_diff != Decimal("0.00") and cash_diff == -upi_diff:
        findings.append({
            "kind": "MODE_SWAP_SUSPECTED",
            "message": f"Cash and UPI differences match inversely (₹{abs(cash_diff):,.0f}). An entry may have the wrong payment mode (Cash vs UPI).",
        })

    return findings


async def list_reconciliations(
    s: AsyncSession,
    shop_id: str,
    date_from: date | None = None,
    date_to: date | None = None,
) -> list[dict[str, Any]]:
    """List historical daily reconciliations."""
    sid = uuid.UUID(shop_id)
    query = """
        SELECT id, reconciliation_date, recorded_cash, actual_cash,
               recorded_upi, actual_upi, cash_difference, upi_difference,
               status, findings, audit_notes, created_at
        FROM daily_reconciliations
        WHERE shop_id = :sid
    """
    params: dict[str, Any] = {"sid": sid}

    if date_from:
        query += " AND reconciliation_date >= :dfrom"
        params["dfrom"] = date_from
    if date_to:
        query += " AND reconciliation_date <= :dto"
        params["dto"] = date_to

    query += " ORDER BY reconciliation_date DESC LIMIT 30"
    res = await s.execute(text(query), params)

    return [
        {
            "id": str(r["id"]),
            "reconciliation_date": r["reconciliation_date"].isoformat(),
            "recorded_cash": float(r["recorded_cash"]),
            "actual_cash": float(r["actual_cash"]),
            "cash_difference": float(r["cash_difference"]),
            "recorded_upi": float(r["recorded_upi"]),
            "actual_upi": float(r["actual_upi"]),
            "upi_difference": float(r["upi_difference"]),
            "status": r["status"],
            "findings": r["findings"] or [],
            "audit_notes": r["audit_notes"],
            "created_at": r["created_at"].astimezone(IST).isoformat() if r["created_at"] else None,
        }
        for r in res.mappings().all()
    ]


async def resolve_reconciliation(
    s: AsyncSession,
    shop_id: str,
    rec_id: str,
    note: str | None = None,
) -> dict[str, Any]:
    """Mark an audited day as RESOLVED with explanation."""
    rid = uuid.UUID(rec_id)
    rec = await s.get(DailyReconciliation, rid)
    if not rec or str(rec.shop_id) != shop_id:
        return {"error": "Reconciliation record not found"}

    rec.status = "RESOLVED"
    if note:
        existing = rec.audit_notes or ""
        rec.audit_notes = f"{existing}\n[Resolved]: {note.strip()}".strip()

    await s.commit()
    return {"resolved": True, "reconciliation_id": rec_id, "status": "RESOLVED"}
