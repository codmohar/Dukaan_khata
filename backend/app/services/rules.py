"""Dukaan Rules Service: shopkeeper policy enforcement engine.

Enforces:
- Deterministic credit evaluation; LLM only extracts parameters.
- Comprehensive warning collection (all violations, not just the first).
- Graceful handling of malformed rules so transactions are never blocked.
"""
from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, time
from decimal import Decimal
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import Customer, ShopRule, Transaction

log = logging.getLogger("dukaan.rules")
IST = ZoneInfo("Asia/Kolkata")
NEW_CUSTOMER_DAYS = 14


def validate_rule_condition(category: str, cond: dict[str, Any]) -> None:
    """Validate that structured condition dictionary satisfies schema requirements."""
    required = {
        "NEW_CUSTOMER_CAP": ["max_amount"],
        "BALANCE_CAP": ["max_balance"],
        "TIME_CUTOFF": ["after"],
        "MEMBER_AUTH": ["customer_id", "member_id", "allowed"],
        "CUSTOM_NOTE": ["note"],
    }
    if category not in required:
        raise ValueError(f"Unknown rule category: {category}")
    missing = [k for k in required[category] if k not in cond]
    if missing:
        raise ValueError(f"Invalid condition for {category}: missing required fields {missing}")


async def save_shop_rule(
    s: AsyncSession,
    shop_id: str,
    rule_category: str,
    rule_text: str,
    structured_condition: dict[str, Any],
) -> dict[str, Any]:
    """Validate and persist a new shopkeeper rule."""
    validate_rule_condition(rule_category, structured_condition)
    sid = uuid.UUID(shop_id)

    rule = ShopRule(
        id=uuid.uuid4(),
        shop_id=sid,
        rule_category=rule_category,
        rule_text=rule_text.strip(),
        structured_condition=structured_condition,
        is_active=True,
    )
    s.add(rule)
    await s.commit()

    return {
        "rule_id": str(rule.id),
        "rule_text": rule.rule_text,
        "rule_category": rule.rule_category,
        "is_active": rule.is_active,
    }


async def evaluate_shop_rules(
    s: AsyncSession,
    shop_id: str,
    customer_id: str,
    member_id: str | None,
    amount: Decimal,
    now: datetime | None = None,
) -> list[dict[str, Any]]:
    """Deterministically evaluate all active rules for CREDIT drafts.
    
    Returns a list of violation warnings:
    [{"rule_id": ..., "category": ..., "message": ..., "severity": "BLOCK_UNLESS_OVERRIDE"}]
    """
    now_ist = (now or datetime.now(IST)).astimezone(IST)
    sid = uuid.UUID(shop_id)
    cid = uuid.UUID(customer_id)

    # 1. Fetch active rules for this shop
    rules_res = await s.execute(
        select(ShopRule).where(ShopRule.shop_id == sid, ShopRule.is_active.is_(True))
    )
    rules = rules_res.scalars().all()
    if not rules:
        return []

    # 2. Fetch customer context
    cust_res = await s.execute(
        text(
            """
            SELECT c.name, COALESCE(c.outstanding_balance, 0.00) AS outstanding_balance, c.created_at,
                   (SELECT COUNT(*) FROM transactions t WHERE t.customer_id = c.id AND t.status = 'confirmed') AS prior_txns
            FROM customers c
            WHERE c.id = :cid AND c.shop_id = :sid
            """
        ),
        {"cid": cid, "sid": sid},
    )
    cust = cust_res.mappings().first()
    if not cust:
        return []

    warnings: list[dict[str, Any]] = []

    for r in rules:
        try:
            cond = r.structured_condition
            if isinstance(cond, str):
                cond = json.loads(cond)
            cat = r.rule_category
            msg: str | None = None

            if cat == "NEW_CUSTOMER_CAP":
                max_prior = cond.get("new_customer_max_prior_txns", 0)
                days_since_creation = (now_ist.date() - cust["created_at"].astimezone(IST).date()).days
                is_new = int(cust["prior_txns"] or 0) <= max_prior or days_since_creation < NEW_CUSTOMER_DAYS

                max_amount = Decimal(str(cond["max_amount"]))
                if is_new and amount > max_amount:
                    msg = (
                        f"{cust['name']} is a new customer. Your rule allows up to ₹{max_amount:,.0f}."
                    )

            elif cat == "BALANCE_CAP":
                current_bal = Decimal(str(cust["outstanding_balance"] or 0))
                max_bal = Decimal(str(cond["max_balance"]))
                if current_bal + amount > max_bal:
                    msg = (
                        f"This entry would take {cust['name']}'s balance to ₹{(current_bal + amount):,.0f}, "
                        f"exceeding your ₹{max_bal:,.0f} limit."
                    )

            elif cat == "TIME_CUTOFF":
                after_t = time.fromisoformat(cond["after"])
                before_t = time.fromisoformat(cond["before"]) if cond.get("before") else None
                current_t = now_ist.time()

                violates = False
                if before_t is not None:
                    # e.g. after 22:00 or before 06:00
                    if after_t > before_t:
                        violates = current_t >= after_t or current_t < before_t
                    else:
                        violates = after_t <= current_t < before_t
                else:
                    violates = current_t >= after_t

                if violates:
                    msg = f"Your rule does not allow credit after {cond['after']}."

            elif cat == "MEMBER_AUTH":
                rule_cid = str(cond.get("customer_id", ""))
                rule_mid = str(cond.get("member_id", ""))
                allowed = bool(cond.get("allowed", True))

                if rule_cid == str(cid) and member_id and rule_mid == str(member_id) and not allowed:
                    msg = "This family member is not authorized to take credit under your shop policy."

            if msg:
                warnings.append({
                    "rule_id": str(r.id),
                    "category": cat,
                    "rule_text": r.rule_text,
                    "message": msg,
                    "severity": "BLOCK_UNLESS_OVERRIDE",
                })

        except Exception as e:
            # Never crash confirmation or drafting on a corrupt or malformed rule
            log.warning("Skipped malformed rule %s: %s", r.id, e)

    return warnings


async def override_rule_warnings(
    s: AsyncSession,
    shop_id: str,
    draft_id: str,
) -> dict[str, Any]:
    """Mark a draft transaction as explicitly overridden by the shopkeeper."""
    did = uuid.UUID(draft_id)
    t = await s.get(Transaction, did)
    if not t or str(t.shop_id) != shop_id:
        return {"error": "Draft transaction not found"}
    if t.status != "draft":
        return {"error": f"Cannot override {t.status} transaction"}

    t.rule_override = True
    await s.commit()
    return {"overridden": True, "draft_id": draft_id}


async def list_shop_rules(s: AsyncSession, shop_id: str) -> list[dict[str, Any]]:
    """List all rules for this shop."""
    sid = uuid.UUID(shop_id)
    res = await s.execute(
        select(ShopRule).where(ShopRule.shop_id == sid).order_by(ShopRule.created_at.desc())
    )
    rules = res.scalars().all()
    return [
        {
            "id": str(r.id),
            "rule_category": r.rule_category,
            "rule_text": r.rule_text,
            "structured_condition": r.structured_condition,
            "is_active": r.is_active,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in rules
    ]


async def update_shop_rule(
    s: AsyncSession,
    shop_id: str,
    rule_id: str,
    is_active: bool | None = None,
    rule_text: str | None = None,
    structured_condition: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Toggle active status or edit rule properties."""
    rid = uuid.UUID(rule_id)
    rule = await s.get(ShopRule, rid)
    if not rule or str(rule.shop_id) != shop_id:
        return {"error": "Rule not found"}

    if is_active is not None:
        rule.is_active = is_active
    if rule_text is not None:
        rule.rule_text = rule_text.strip()
    if structured_condition is not None:
        validate_rule_condition(rule.rule_category, structured_condition)
        rule.structured_condition = structured_condition

    await s.commit()
    await s.refresh(rule)
    return {
        "id": str(rule.id),
        "rule_category": rule.rule_category,
        "rule_text": rule.rule_text,
        "structured_condition": rule.structured_condition,
        "is_active": rule.is_active,
    }


async def delete_shop_rule(s: AsyncSession, shop_id: str, rule_id: str) -> dict[str, Any]:
    """Delete a shopkeeper rule."""
    rid = uuid.UUID(rule_id)
    rule = await s.get(ShopRule, rid)
    if not rule or str(rule.shop_id) != shop_id:
        return {"error": "Rule not found"}

    await s.delete(rule)
    await s.commit()
    return {"deleted": True, "rule_id": rule_id}

