"""Household Khata Service: multi-member khata accounts under one customer.

Enforces:
- Single household outstanding_balance on Customer row.
- Individual member attribution on transactions.
- Deterministic member disambiguation and fuzzy matching.
"""
from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import Customer, HouseholdMember, Transaction


async def resolve_household_member(
    s: AsyncSession,
    shop_id: str,
    customer_name: str,
    member_name: str | None = None,
    relationship: str | None = None,
) -> dict[str, Any]:
    """Resolve customer and optional household member using trigram similarity and name matching."""
    c_query = (customer_name or "").strip()
    if not c_query:
        return {"status": "customer_not_found"}

    # 1. Search customers in this shop
    res = await s.execute(
        text(
            """
            SELECT id, name, landmark, phone,
                   similarity(name, :q) AS sim
            FROM customers
            WHERE shop_id = :sid
              AND (similarity(name, :q) > 0.4 OR name ILIKE '%' || :q || '%')
            ORDER BY sim DESC, name ASC
            LIMIT 5
            """
        ),
        {"sid": shop_id, "q": c_query},
    )
    customers = res.mappings().all()

    if not customers:
        # Try fallback without punctuation / honorifics
        return {"status": "customer_not_found"}

    # Ambiguity check: if top 2 candidates are very close in similarity
    if len(customers) > 1 and (float(customers[0]["sim"] or 0) - float(customers[1]["sim"] or 0)) < 0.15:
        # Check if first one is an exact match
        if customers[0]["name"].strip().lower() != c_query.lower():
            return {
                "status": "ambiguous",
                "candidates": [
                    {
                        "customer_id": str(c["id"]),
                        "name": c["name"],
                        "landmark": c["landmark"],
                        "phone": c["phone"],
                    }
                    for c in customers
                ],
            }

    cust = customers[0]
    cust_id_str = str(cust["id"])

    # If no member name requested, resolve directly to the primary customer
    if not member_name or not member_name.strip():
        return {
            "status": "resolved",
            "customer_id": cust_id_str,
            "customer_name": cust["name"],
            "member_id": None,
            "member_name": None,
        }

    m_query = member_name.strip()
    # 2. Search household members for this customer
    m_res = await s.execute(
        text(
            """
            SELECT id, member_name, relationship, is_authorized,
                   similarity(member_name, :m) AS sim
            FROM household_members
            WHERE customer_id = :cid AND shop_id = :sid
              AND (similarity(member_name, :m) > 0.35 OR member_name ILIKE '%' || :m || '%')
            ORDER BY sim DESC, member_name ASC
            LIMIT 1
            """
        ),
        {"cid": cust["id"], "sid": shop_id, "m": m_query},
    )
    member = m_res.mappings().first()

    if member:
        return {
            "status": "resolved",
            "customer_id": cust_id_str,
            "customer_name": cust["name"],
            "member_id": str(member["id"]),
            "member_name": member["member_name"],
            "relationship": member["relationship"],
            "is_authorized": bool(member["is_authorized"]),
        }

    return {
        "status": "member_not_found",
        "customer_id": cust_id_str,
        "customer_name": cust["name"],
        "suggested_member": {
            "name": m_query,
            "relationship": relationship,
        },
    }


async def add_household_member(
    s: AsyncSession,
    shop_id: str,
    customer_id: str,
    member_name: str,
    relationship: str | None = None,
    is_authorized: bool = True,
) -> dict[str, Any]:
    """Add or update a household member under an existing customer."""
    cid = uuid.UUID(customer_id)
    sid = uuid.UUID(shop_id)
    m_name = member_name.strip()
    mid = uuid.uuid4()

    row = (
        await s.execute(
            text(
                """
                INSERT INTO household_members (id, shop_id, customer_id, member_name, relationship, is_authorized)
                VALUES (:mid, :sid, :cid, :mname, :rel, :auth)
                ON CONFLICT (customer_id, member_name)
                DO UPDATE SET
                    relationship = COALESCE(EXCLUDED.relationship, household_members.relationship),
                    is_authorized = EXCLUDED.is_authorized
                RETURNING id, member_name, relationship, is_authorized, created_at
                """
            ),
            {
                "mid": mid,
                "sid": sid,
                "cid": cid,
                "mname": m_name,
                "rel": relationship,
                "auth": is_authorized,
            },
        )
    ).mappings().first()
    await s.commit()

    return {
        "member_id": str(row["id"]),
        "customer_id": customer_id,
        "member_name": row["member_name"],
        "relationship": row["relationship"],
        "is_authorized": row["is_authorized"],
    }


async def list_household_members(
    s: AsyncSession,
    shop_id: str,
    customer_id: str,
) -> list[dict[str, Any]]:
    """List all household members for a customer with per-member credit/payment totals."""
    cid = uuid.UUID(customer_id)
    sid = uuid.UUID(shop_id)

    res = await s.execute(
        text(
            """
            SELECT hm.id, hm.member_name, hm.relationship, hm.is_authorized, hm.created_at,
                   COALESCE(SUM(CASE WHEN t.type = 'credit' THEN t.amount ELSE 0 END), 0) AS total_credit,
                   COALESCE(SUM(CASE WHEN t.type = 'payment' THEN t.amount ELSE 0 END), 0) AS total_payment,
                   COUNT(t.id) AS tx_count
            FROM household_members hm
            LEFT JOIN transactions t ON t.member_id = hm.id AND t.status = 'confirmed'
            WHERE hm.customer_id = :cid AND hm.shop_id = :sid
            GROUP BY hm.id
            ORDER BY hm.created_at ASC
            """
        ),
        {"cid": cid, "sid": sid},
    )
    members = []
    for r in res.mappings().all():
        members.append({
            "id": str(r["id"]),
            "member_name": r["member_name"],
            "relationship": r["relationship"],
            "is_authorized": bool(r["is_authorized"]),
            "created_at": r["created_at"].isoformat() if r["created_at"] else None,
            "total_credit": float(r["total_credit"] or 0),
            "total_payment": float(r["total_payment"] or 0),
            "tx_count": int(r["tx_count"] or 0),
        })
    return members


async def update_household_member(
    s: AsyncSession,
    shop_id: str,
    member_id: str,
    member_name: str | None = None,
    relationship: str | None = None,
    is_authorized: bool | None = None,
) -> dict[str, Any]:
    """Update household member properties."""
    mid = uuid.UUID(member_id)
    sid = uuid.UUID(shop_id)

    member = await s.get(HouseholdMember, mid)
    if not member or str(member.shop_id) != shop_id:
        return {"error": "Household member not found"}

    if member_name is not None:
        member.member_name = member_name.strip()
    if relationship is not None:
        member.relationship_label = relationship.strip()
    if is_authorized is not None:
        member.is_authorized = is_authorized

    await s.commit()
    await s.refresh(member)
    return {
        "id": str(member.id),
        "customer_id": str(member.customer_id),
        "member_name": member.member_name,
        "relationship": member.relationship_label,
        "is_authorized": member.is_authorized,
    }


async def delete_household_member(
    s: AsyncSession,
    shop_id: str,
    member_id: str,
) -> dict[str, Any]:
    """Delete a household member. Existing transactions keep member_id null via ON DELETE SET NULL."""
    mid = uuid.UUID(member_id)
    member = await s.get(HouseholdMember, mid)
    if not member or str(member.shop_id) != shop_id:
        return {"error": "Household member not found"}

    await s.delete(member)
    await s.commit()
    return {"deleted": True, "member_id": member_id}
