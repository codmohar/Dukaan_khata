"""Promise Memory Service: commitments, payment promises, goods reservations, supplier deliveries.

Enforces:
- Promises NEVER modify customer balances or ledger transactions.
- Auto-fulfilment hooks atomically into confirm_draft during payment confirmations.
- Overdue status computed dynamically via promises_effective view.
"""
from __future__ import annotations

import logging
import uuid
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import Customer, Promise

log = logging.getLogger("dukaan.promises")
IST = ZoneInfo("Asia/Kolkata")


def today_ist() -> date:
    return datetime.now(IST).date()


async def create_promise(
    s: AsyncSession,
    shop_id: str,
    entity_name: str,
    promise_type: str,
    description: str,
    expected_date: date,
    promised_amount: Decimal | float | None = None,
    customer_id: str | None = None,
    member_id: str | None = None,
    transcript: str | None = None,
) -> dict[str, Any]:
    """Record a commitment without altering the ledger."""
    if promise_type not in ("PAYMENT_PROMISE", "GOODS_RESERVATION", "SUPPLIER_DELIVERY"):
        raise ValueError(f"Invalid promise_type: {promise_type}")

    parsed_amount: Decimal | None = None
    if promised_amount is not None:
        parsed_amount = Decimal(str(promised_amount))
        if parsed_amount <= 0:
            parsed_amount = None

    if promise_type == "PAYMENT_PROMISE" and (parsed_amount is None or parsed_amount <= 0):
        raise ValueError("Payment promise requires a positive promised_amount")

    sid = uuid.UUID(shop_id)
    cid = uuid.UUID(customer_id) if customer_id else None
    mid = uuid.UUID(member_id) if member_id else None

    # If customer_id was not provided for PAYMENT_PROMISE or GOODS_RESERVATION, attempt lookup
    if not cid and entity_name and promise_type in ("PAYMENT_PROMISE", "GOODS_RESERVATION"):
        cust_row = (
            await s.execute(
                text(
                    """
                    SELECT id FROM customers
                    WHERE shop_id = :sid AND (name ILIKE :n OR similarity(name, :n) > 0.4)
                    ORDER BY similarity(name, :n) DESC LIMIT 1
                    """
                ),
                {"sid": sid, "n": entity_name.strip()},
            )
        ).scalar()
        if cust_row:
            cid = cust_row

    promise = Promise(
        id=uuid.uuid4(),
        shop_id=sid,
        customer_id=cid,
        member_id=mid,
        entity_name=entity_name.strip(),
        promise_type=promise_type,
        promised_amount=parsed_amount,
        description=description.strip(),
        expected_date=expected_date,
        status="PENDING",
        source_transcript=transcript,
    )
    s.add(promise)
    await s.commit()

    return {
        "promise_id": str(promise.id),
        "entity_name": promise.entity_name,
        "promise_type": promise.promise_type,
        "promised_amount": float(promise.promised_amount) if promise.promised_amount else None,
        "description": promise.description,
        "expected_date": promise.expected_date.isoformat(),
        "status": "PENDING",
        "ledger_changed": False,
    }


async def auto_fulfil_promise(
    s: AsyncSession,
    shop_id: str,
    customer_id: str,
    amount: Decimal,
    tx_id: uuid.UUID,
) -> dict[str, Any] | None:
    """Invoked inside confirm_draft's atomic transaction to fulfil matching payment promise."""
    sid = uuid.UUID(shop_id)
    cid = uuid.UUID(customer_id)

    # Lock candidate pending promises for this customer
    res = await s.execute(
        text(
            """
            SELECT id, promised_amount, expected_date
            FROM promises
            WHERE shop_id = :sid AND customer_id = :cid
              AND promise_type = 'PAYMENT_PROMISE'
              AND status = 'PENDING'
            ORDER BY expected_date ASC, created_at ASC
            FOR UPDATE
            """
        ),
        {"sid": sid, "cid": cid},
    )
    rows = res.mappings().all()
    if not rows:
        return None

    # Priority 1: Exact amount match
    target = next((r for r in rows if Decimal(str(r["promised_amount"])) == amount), None)

    # Priority 2: Oldest promise where payment amount covers it
    if not target:
        target = next((r for r in rows if amount >= Decimal(str(r["promised_amount"]))), None)

    if not target:
        # Payment amount is less than any pending promise amount; keep pending (partial payment)
        return {"fulfilled": False, "pending_count": len(rows)}

    # Mark fulfilled
    await s.execute(
        text(
            """
            UPDATE promises
            SET status = 'FULFILLED',
                fulfilled_transaction_id = :txid,
                fulfilled_at = NOW()
            WHERE id = :pid
            """
        ),
        {"txid": tx_id, "pid": target["id"]},
    )

    return {
        "fulfilled": True,
        "promise_id": str(target["id"]),
        "promised_amount": float(target["promised_amount"]),
    }


async def list_promises(
    s: AsyncSession,
    shop_id: str,
    status: str | None = None,
    on_date: date | None = None,
    customer_name: str | None = None,
    customer_id: str | None = None,
) -> list[dict[str, Any]]:
    """List promises using promises_effective view."""
    sid = uuid.UUID(shop_id)
    cid = uuid.UUID(customer_id) if customer_id else None

    query = """
        SELECT p.id, p.shop_id, p.customer_id, p.member_id, p.entity_name,
               p.promise_type, p.promised_amount, p.description, p.expected_date,
               p.status, p.effective_status, p.fulfilled_transaction_id, p.created_at, p.fulfilled_at,
               c.name AS customer_name
        FROM promises_effective p
        LEFT JOIN customers c ON c.id = p.customer_id
        WHERE p.shop_id = :sid
    """
    params: dict[str, Any] = {"sid": sid}

    if status:
        query += " AND p.effective_status = :status"
        params["status"] = status.upper()

    if on_date:
        query += " AND p.expected_date = :dt"
        params["dt"] = on_date

    if cid:
        query += " AND p.customer_id = :cid"
        params["cid"] = cid

    if customer_name:
        query += " AND (similarity(p.entity_name, :cname) > 0.35 OR p.entity_name ILIKE '%' || :cname || '%')"
        params["cname"] = customer_name.strip()

    query += " ORDER BY p.expected_date ASC, p.created_at DESC LIMIT 50"

    res = await s.execute(text(query), params)
    rows = res.mappings().all()

    return [
        {
            "id": str(r["id"]),
            "customer_id": str(r["customer_id"]) if r["customer_id"] else None,
            "customer_name": r["customer_name"] or r["entity_name"],
            "member_id": str(r["member_id"]) if r["member_id"] else None,
            "entity_name": r["entity_name"],
            "promise_type": r["promise_type"],
            "promised_amount": float(r["promised_amount"]) if r["promised_amount"] else None,
            "description": r["description"],
            "expected_date": r["expected_date"].isoformat(),
            "status": r["effective_status"],
            "fulfilled_transaction_id": str(r["fulfilled_transaction_id"]) if r["fulfilled_transaction_id"] else None,
            "created_at": r["created_at"].astimezone(IST).isoformat() if r["created_at"] else None,
            "fulfilled_at": r["fulfilled_at"].astimezone(IST).isoformat() if r["fulfilled_at"] else None,
        }
        for r in rows
    ]


async def update_promise(
    s: AsyncSession,
    shop_id: str,
    promise_id: str,
    action: str,
    new_date: date | None = None,
) -> dict[str, Any]:
    """Update promise status or reschedule date."""
    pid = uuid.UUID(promise_id)
    p = await s.get(Promise, pid)
    if not p or str(p.shop_id) != shop_id:
        return {"error": "Promise not found"}

    action_norm = action.upper().strip()
    if action_norm == "FULFIL_MANUAL":
        p.status = "FULFILLED"
        p.fulfilled_at = datetime.now(timezone.utc)
    elif action_norm == "CANCEL":
        p.status = "CANCELLED"
    elif action_norm == "RESCHEDULE":
        if not new_date:
            return {"error": "new_date is required for reschedule"}
        p.expected_date = new_date
        if p.status == "OVERDUE":
            p.status = "PENDING"
    else:
        return {"error": f"Invalid action: {action}"}

    await s.commit()
    await s.refresh(p)
    return {
        "id": str(p.id),
        "status": p.status,
        "expected_date": p.expected_date.isoformat(),
    }


async def get_promises_summary(s: AsyncSession, shop_id: str) -> dict[str, Any]:
    """Summary metrics for the dashboard 'Today's Promises & Alerts' card."""
    sid = uuid.UUID(shop_id)
    today = today_ist()

    # Query counts and totals from promises_effective
    res = await s.execute(
        text(
            """
            SELECT
                COUNT(*) FILTER (WHERE effective_status = 'PENDING' AND expected_date = :today) AS due_today,
                COUNT(*) FILTER (WHERE effective_status = 'OVERDUE') AS overdue,
                COALESCE(SUM(promised_amount) FILTER (WHERE effective_status IN ('PENDING', 'OVERDUE')), 0) AS total_pending_amount
            FROM promises_effective
            WHERE shop_id = :sid
            """
        ),
        {"sid": sid, "today": today},
    )
    counts = res.mappings().first() or {}

    # List up to 5 items due today or overdue
    today_items_res = await s.execute(
        text(
            """
            SELECT p.id, p.entity_name, p.promise_type, p.promised_amount, p.description,
                   p.expected_date, p.effective_status
            FROM promises_effective p
            WHERE p.shop_id = :sid AND p.effective_status IN ('PENDING', 'OVERDUE')
            ORDER BY (p.effective_status = 'OVERDUE') DESC, p.expected_date ASC, p.created_at ASC
            LIMIT 5
            """
        ),
        {"sid": sid},
    )
    today_list = [
        {
            "id": str(r["id"]),
            "entity_name": r["entity_name"],
            "promise_type": r["promise_type"],
            "promised_amount": float(r["promised_amount"]) if r["promised_amount"] else None,
            "description": r["description"],
            "expected_date": r["expected_date"].isoformat(),
            "status": r["effective_status"],
        }
        for r in today_items_res.mappings().all()
    ]

    return {
        "due_today": int(counts.get("due_today") or 0),
        "overdue": int(counts.get("overdue") or 0),
        "total_pending_amount": float(counts.get("total_pending_amount") or 0),
        "items": today_list,
    }

