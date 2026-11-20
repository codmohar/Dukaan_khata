"""Smart Dispute Resolver Service: verifiable timeline with chronological running balances and transcript evidence.

Enforces:
- Window function running balance computed chronologically over all customer transactions.
- Exact audit verification: newest row balance_after checked against customer.outstanding_balance.
- Member filtering preserves running balance accuracy.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

log = logging.getLogger("dukaan.timeline")
IST = ZoneInfo("Asia/Kolkata")


async def get_dispute_timeline(
    s: AsyncSession,
    shop_id: str,
    customer_id: str,
    limit: int = 5,
    member_id: str | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
) -> dict[str, Any]:
    """Calculate running ledger balance chain with speech transcript evidence."""
    sid = uuid.UUID(shop_id)
    cid = uuid.UUID(customer_id)
    mid = uuid.UUID(member_id) if member_id else None

    # 1. Fetch customer details and current recorded balance
    cust_res = await s.execute(
        text(
            """
            SELECT id, name, phone, COALESCE(outstanding_balance, 0.00) AS outstanding_balance
            FROM customers
            WHERE id = :cid AND shop_id = :sid
            """
        ),
        {"cid": cid, "sid": sid},
    )
    cust = cust_res.mappings().first()
    if not cust:
        return {"error": "Customer not found"}

    current_balance = Decimal(str(cust["outstanding_balance"] or 0))

    # 2. Compute running balance chronologically using window sum, then filter and order by newest
    query = """
        WITH ordered AS (
            SELECT t.id, t.created_at, t.type, t.amount, t.payment_mode,
                   COALESCE(t.item_note, t.note) AS item_note,
                   t.transcript_snippet, t.rule_override, t.member_id, hm.member_name,
                   SUM(CASE WHEN t.type = 'credit' THEN t.amount ELSE -t.amount END)
                       OVER (ORDER BY t.created_at ASC, t.id ASC) AS balance_after
            FROM transactions t
            LEFT JOIN household_members hm ON hm.id = t.member_id
            WHERE t.customer_id = :cid AND t.shop_id = :sid AND t.status = 'confirmed'
        )
        SELECT * FROM ordered
        WHERE 1 = 1
    """
    params: dict[str, Any] = {"cid": cid, "sid": sid, "lim": limit}

    if mid:
        query += " AND member_id = :mid"
        params["mid"] = mid

    if date_from:
        query += " AND created_at >= :dfrom"
        params["dfrom"] = date_from

    if date_to:
        query += " AND created_at < :dto"
        params["dto"] = date_to

    query += " ORDER BY created_at DESC, id DESC LIMIT :lim"

    res = await s.execute(text(query), params)
    rows = res.mappings().all()

    # 3. Check for balance mismatch (unfiltered query top row vs customer.outstanding_balance)
    balance_mismatch = False
    if member_id is None and date_from is None and date_to is None:
        newest_running = Decimal(str(rows[0]["balance_after"])) if rows else Decimal("0.00")
        if newest_running != current_balance:
            balance_mismatch = True
            log.warning(
                "Dispute Resolver: balance mismatch detected for customer %s (table: ₹%s, computed: ₹%s)",
                cid, current_balance, newest_running
            )

    timeline_rows = [
        {
            "transaction_id": str(r["id"]),
            "at": r["created_at"].astimezone(IST).isoformat(),
            "display_date": r["created_at"].astimezone(IST).strftime("%d %b %Y, %I:%M %p"),
            "type": r["type"],
            "amount": float(r["amount"]),
            "payment_mode": r["payment_mode"],
            "member_id": str(r["member_id"]) if r["member_id"] else None,
            "member_name": r["member_name"],
            "item_note": r["item_note"],
            "transcript_snippet": r["transcript_snippet"],
            "rule_override": bool(r["rule_override"]),
            "balance_after": float(r["balance_after"]),
        }
        for r in rows
    ]

    return {
        "customer": {
            "id": str(cust["id"]),
            "name": cust["name"],
            "phone": cust["phone"],
        },
        "current_balance": float(current_balance),
        "balance_mismatch": balance_mismatch,
        "rows": timeline_rows,
    }
