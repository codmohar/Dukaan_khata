"""Shopkeeper Memory Service: grounded recall across promises, transactions, and custom rules.

Enforces:
- Hard multi-tenant isolation by shop_id.
- Exact and trigram fuzzy matching on entity names and item keywords.
- Grounded recall: if count == 0, agent reports nothing is recorded. Never guess.
"""
from __future__ import annotations

import logging
import uuid
from datetime import date, datetime
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

log = logging.getLogger("dukaan.memory")
IST = ZoneInfo("Asia/Kolkata")


async def search_shop_memory(
    s: AsyncSession,
    shop_id: str,
    entity_name: str | None = None,
    keyword: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    scope: list[str] | None = None,
    limit: int = 10,
) -> dict[str, Any]:
    """Search operational memory across promises, transactions, and rules."""
    sid = uuid.UUID(shop_id)
    active_scope = set(scope or ["promises", "transactions", "rules"])
    results: list[dict[str, Any]] = []

    # 1. Search Promises
    if "promises" in active_scope:
        query = """
            SELECT p.id, p.entity_name, p.description, p.expected_date, p.created_at, p.effective_status
            FROM promises_effective p
            WHERE p.shop_id = :sid
        """
        params: dict[str, Any] = {"sid": sid, "lim": limit}

        if entity_name:
            query += " AND (similarity(p.entity_name, :ename) > 0.35 OR p.entity_name ILIKE '%' || :ename || '%')"
            params["ename"] = entity_name.strip()

        if keyword:
            query += " AND (p.description ILIKE '%' || :kw || '%' OR similarity(p.description, :kw) > 0.3)"
            params["kw"] = keyword.strip()

        if date_from:
            query += " AND (p.expected_date >= :dfrom OR p.created_at::date >= :dfrom)"
            params["dfrom"] = date_from

        if date_to:
            query += " AND (p.expected_date <= :dto OR p.created_at::date <= :dto)"
            params["dto"] = date_to

        query += " ORDER BY p.created_at DESC LIMIT :lim"
        p_res = await s.execute(text(query), params)
        for r in p_res.mappings().all():
            when_str = r["created_at"].astimezone(IST).strftime("%b %d, %Y %I:%M %p") if r["created_at"] else ""
            results.append({
                "source": "promise",
                "id": str(r["id"]),
                "when": when_str,
                "summary": f"{r['entity_name']}: {r['description']} (target: {r['expected_date']})",
                "status": r["effective_status"],
            })

    # 2. Search Transactions (item notes & notes)
    if "transactions" in active_scope and (keyword or entity_name):
        query = """
            SELECT t.id, t.created_at, t.amount, t.type, t.payment_mode,
                   COALESCE(t.item_note, t.note) AS item_note,
                   c.name AS customer_name, hm.member_name
            FROM transactions t
            JOIN customers c ON c.id = t.customer_id
            LEFT JOIN household_members hm ON hm.id = t.member_id
            WHERE t.shop_id = :sid AND t.status = 'confirmed'
              AND (t.item_note IS NOT NULL OR t.note IS NOT NULL)
        """
        params = {"sid": sid, "lim": limit}

        if keyword:
            query += " AND (t.item_note ILIKE '%' || :kw || '%' OR t.note ILIKE '%' || :kw || '%' OR similarity(COALESCE(t.item_note, t.note, ''), :kw) > 0.25)"
            params["kw"] = keyword.strip()

        if entity_name:
            query += " AND (c.name ILIKE '%' || :ename || '%' OR similarity(c.name, :ename) > 0.35 OR (hm.member_name IS NOT NULL AND hm.member_name ILIKE '%' || :ename || '%'))"
            params["ename"] = entity_name.strip()

        if date_from:
            query += " AND t.created_at::date >= :dfrom"
            params["dfrom"] = date_from

        if date_to:
            query += " AND t.created_at::date <= :dto"
            params["dto"] = date_to

        query += " ORDER BY t.created_at DESC LIMIT :lim"
        t_res = await s.execute(text(query), params)
        for r in t_res.mappings().all():
            who = r["customer_name"] + (f" ({r['member_name']})" if r["member_name"] else "")
            when_str = r["created_at"].astimezone(IST).strftime("%b %d, %Y %I:%M %p") if r["created_at"] else ""
            results.append({
                "source": "transaction",
                "id": str(r["id"]),
                "when": when_str,
                "summary": f"{who}: {r['type'].upper()} ₹{r['amount']:,.0f} - {r['item_note']}",
                "status": "CONFIRMED",
            })

    # 3. Search Custom Rules & Policies
    if "rules" in active_scope and keyword:
        query = """
            SELECT id, rule_category, rule_text, created_at
            FROM shop_rules
            WHERE shop_id = :sid AND is_active = TRUE
              AND (rule_text ILIKE '%' || :kw || '%' OR similarity(rule_text, :kw) > 0.25)
            ORDER BY created_at DESC LIMIT :lim
        """
        r_res = await s.execute(text(query), {"sid": sid, "kw": keyword.strip(), "lim": limit})
        for r in r_res.mappings().all():
            when_str = r["created_at"].astimezone(IST).strftime("%b %d, %Y") if r["created_at"] else ""
            results.append({
                "source": "rule",
                "id": str(r["id"]),
                "when": when_str,
                "summary": f"Policy ({r['rule_category']}): {r['rule_text']}",
                "status": "ACTIVE",
            })

    # Sort combined results by most recent
    results = results[:limit]
    return {
        "results": results,
        "count": len(results),
        "note": "If count is 0, say nothing is recorded. Do not guess.",
    }

