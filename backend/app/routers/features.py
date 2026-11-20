"""FastAPI router for Advanced DukaanAI features:
- Household Khata (family members under one account)
- Dukaan Rules (shopkeeper-spoken policies, warnings, override)
- Promise Memory AI (future payments, reservations, supplier deliveries)
- Shopkeeper Memory (grounded recall)
- Smart Dispute Resolver (audit timeline with running balance)
- AI Daily Khata Reconciliation (cash and UPI end-of-day audit)
"""
from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from ..agent import tools
from ..config import settings
from ..db import get_session
from ..models import Customer, HouseholdMember, Promise, ShopRule, Transaction
from ..schemas import (
    HouseholdMemberIn,
    HouseholdMemberOut,
    HouseholdMemberUpdate,
    MemorySearchIn,
    PromiseIn,
    PromiseOut,
    PromisesSummaryOut,
    PromiseUpdate,
    ReconciliationIn,
    ReconciliationResolveIn,
    ShopRuleIn,
    ShopRuleOut,
    ShopRuleUpdate,
)
from ..services import household as household_service
from ..services import memory as memory_service
from ..services import promises as promises_service
from ..services import reconciliation as reconciliation_service
from ..services import rules as rules_service
from ..services import timeline as timeline_service

router = APIRouter(tags=["Advanced Features"])


async def get_shop_id(shop_id: str | None = None, s: AsyncSession = Depends(get_session)) -> str:
    """Resolve shop_id for multi-tenant isolation."""
    if shop_id:
        return shop_id
    if settings.default_shop_id and settings.default_shop_id.strip():
        return settings.default_shop_id.strip()
    row = (await s.execute(text("select id from shops limit 1"))).scalar()
    if row:
        return str(row)
    return "00000000-0000-0000-0000-000000000001"


# ====================================================================
# 1. HOUSEHOLD KHATA ENDPOINTS
# ====================================================================

@router.get("/customers/{cid}/members", response_model=list[HouseholdMemberOut])
@router.get("/customers/{cid}/household", response_model=list[HouseholdMemberOut])
async def list_customer_members(
    cid: UUID,
    s: AsyncSession = Depends(get_session),
    sid: str = Depends(get_shop_id),
):
    """List members belonging to a customer account with their credit/payment totals."""
    return await household_service.list_household_members(s=s, shop_id=sid, customer_id=str(cid))


@router.post("/customers/{cid}/members", status_code=201)
@router.post("/customers/{cid}/household", status_code=201)
async def add_customer_member(
    cid: UUID,
    body: HouseholdMemberIn,
    s: AsyncSession = Depends(get_session),
    sid: str = Depends(get_shop_id),
):
    """Add a new household member under an existing customer."""
    cust = await s.get(Customer, cid)
    if not cust or str(cust.shop_id) != sid:
        raise HTTPException(404, "Customer not found")

    res = await household_service.add_household_member(
        s=s,
        shop_id=sid,
        customer_id=str(cid),
        member_name=body.member_name,
        relationship=body.relationship,
        is_authorized=body.is_authorized,
    )
    return res


@router.patch("/members/{mid}")
async def update_member(
    mid: UUID,
    body: HouseholdMemberUpdate,
    s: AsyncSession = Depends(get_session),
    sid: str = Depends(get_shop_id),
):
    """Update household member properties or authorization status."""
    res = await household_service.update_household_member(
        s=s,
        shop_id=sid,
        member_id=str(mid),
        member_name=body.member_name,
        relationship=body.relationship,
        is_authorized=body.is_authorized,
    )
    if "error" in res:
        raise HTTPException(404, res["error"])
    return res


@router.delete("/members/{mid}", status_code=204)
async def delete_member(
    mid: UUID,
    s: AsyncSession = Depends(get_session),
    sid: str = Depends(get_shop_id),
):
    """Delete a household member. Existing transactions keep member_id null."""
    res = await household_service.delete_household_member(s=s, shop_id=sid, member_id=str(mid))
    if "error" in res:
        raise HTTPException(404, res["error"])


# ====================================================================
# 2. DUKAAN RULES ENDPOINTS
# ====================================================================

@router.get("/rules", response_model=list[ShopRuleOut])
async def list_rules(
    s: AsyncSession = Depends(get_session),
    sid: str = Depends(get_shop_id),
):
    """List all policy rules defined by the shopkeeper."""
    return await rules_service.list_shop_rules(s=s, shop_id=sid)


@router.post("/rules", status_code=201)
async def create_rule(
    body: ShopRuleIn,
    s: AsyncSession = Depends(get_session),
    sid: str = Depends(get_shop_id),
):
    """Save a validated credit policy rule."""
    try:
        return await rules_service.save_shop_rule(
            s=s,
            shop_id=sid,
            rule_category=body.rule_category,
            rule_text=body.rule_text,
            structured_condition=body.structured_condition,
        )
    except ValueError as e:
        raise HTTPException(422, str(e))


@router.patch("/rules/{rid}")
async def update_rule(
    rid: UUID,
    body: ShopRuleUpdate,
    s: AsyncSession = Depends(get_session),
    sid: str = Depends(get_shop_id),
):
    """Toggle rule active state or edit rule text."""
    try:
        res = await rules_service.update_shop_rule(
            s=s,
            shop_id=sid,
            rule_id=str(rid),
            is_active=body.is_active,
            rule_text=body.rule_text,
            structured_condition=body.structured_condition,
        )
        if "error" in res:
            raise HTTPException(404, res["error"])
        return res
    except ValueError as e:
        raise HTTPException(422, str(e))


@router.delete("/rules/{rid}", status_code=204)
async def delete_rule(
    rid: UUID,
    s: AsyncSession = Depends(get_session),
    sid: str = Depends(get_shop_id),
):
    """Delete a policy rule."""
    res = await rules_service.delete_shop_rule(s=s, shop_id=sid, rule_id=str(rid))
    if "error" in res:
        raise HTTPException(404, res["error"])


@router.post("/drafts/{did}/override-rules")
async def override_draft_rules(
    did: UUID,
    s: AsyncSession = Depends(get_session),
    sid: str = Depends(get_shop_id),
):
    """Explicitly mark a pending draft as overridden by the shopkeeper."""
    res = await rules_service.override_rule_warnings(s=s, shop_id=sid, draft_id=str(did))
    if "error" in res:
        raise HTTPException(404, res["error"])
    return res


# ====================================================================
# 3. PROMISE MEMORY ENDPOINTS
# ====================================================================

@router.get("/promises", response_model=list[PromiseOut])
async def list_promises(
    status: str | None = None,
    on_date: date | None = None,
    customer_name: str | None = None,
    customer_id: UUID | None = None,
    s: AsyncSession = Depends(get_session),
    sid: str = Depends(get_shop_id),
):
    """Query scheduled promises and commitments (using promises_effective view)."""
    return await promises_service.list_promises(
        s=s,
        shop_id=sid,
        status=status,
        on_date=on_date,
        customer_name=customer_name,
        customer_id=str(customer_id) if customer_id else None,
    )


@router.post("/promises", status_code=201)
async def create_promise_endpoint(
    body: PromiseIn,
    s: AsyncSession = Depends(get_session),
    sid: str = Depends(get_shop_id),
):
    """Create a promise or goods reservation (ledger untouched)."""
    try:
        return await promises_service.create_promise(
            s=s,
            shop_id=sid,
            entity_name=body.entity_name,
            promise_type=body.promise_type,
            description=body.description,
            expected_date=body.expected_date,
            promised_amount=body.promised_amount,
            customer_id=str(body.customer_id) if body.customer_id else None,
            member_id=str(body.member_id) if body.member_id else None,
        )
    except ValueError as e:
        raise HTTPException(422, str(e))


@router.patch("/promises/{pid}")
async def update_promise_endpoint(
    pid: UUID,
    body: PromiseUpdate,
    s: AsyncSession = Depends(get_session),
    sid: str = Depends(get_shop_id),
):
    """Reschedule, cancel, or manually fulfil a promise."""
    res = await promises_service.update_promise(
        s=s,
        shop_id=sid,
        promise_id=str(pid),
        action=body.action,
        new_date=body.new_date,
    )
    if "error" in res:
        raise HTTPException(404, res["error"])
    return res


@router.post("/promises/{pid}/fulfil-via-payment")
async def fulfil_promise_via_payment(
    pid: UUID,
    s: AsyncSession = Depends(get_session),
    sid: str = Depends(get_shop_id),
):
    """Create a pre-filled unconfirmed PAYMENT draft corresponding to this promise."""
    p = await s.get(Promise, pid)
    if not p or str(p.shop_id) != sid:
        raise HTTPException(404, "Promise not found")
    if not p.customer_id:
        raise HTTPException(400, "Cannot draft customer payment for non-customer commitment")
    if not p.promised_amount or p.promised_amount <= 0:
        raise HTTPException(400, "Promise does not have a valid payment amount")

    # Creates an unconfirmed payment draft; still requires confirmation to affect balance!
    draft_res = await tools.create_draft(
        s=s,
        shop_id=sid,
        customer_id=str(p.customer_id),
        type="payment",
        amount=float(p.promised_amount),
        member_id=str(p.member_id) if p.member_id else None,
        note=f"Fulfilment for promise: {p.description}",
    )
    return {"message": "Draft created for fulfilment", "draft": draft_res}


@router.get("/dashboard/promises-summary", response_model=PromisesSummaryOut)
@router.get("/promises/summary", response_model=PromisesSummaryOut)
async def get_dashboard_promises_summary(
    s: AsyncSession = Depends(get_session),
    sid: str = Depends(get_shop_id),
):
    """Metrics for dashboard 'Today's Promises & Alerts' card."""
    return await promises_service.get_promises_summary(s=s, shop_id=sid)


# ====================================================================
# 4. SHOPKEEPER MEMORY ENDPOINTS
# ====================================================================

@router.get("/memory/search")
async def search_memory_get(
    q: str | None = None,
    keyword: str | None = None,
    s: AsyncSession = Depends(get_session),
    sid: str = Depends(get_shop_id),
):
    search_q = q or keyword or ""
    return await memory_service.search_shop_memory(s=s, shop_id=sid, keyword=search_q)


@router.post("/memory/search")
async def search_memory(
    body: MemorySearchIn,
    s: AsyncSession = Depends(get_session),
    sid: str = Depends(get_shop_id),
):
    """Recall information across promises, transactions, and rules."""
    return await memory_service.search_shop_memory(
        s=s,
        shop_id=sid,
        entity_name=body.entity_name,
        keyword=body.keyword,
        date_from=body.date_from,
        date_to=body.date_to,
        scope=body.scope,
        limit=body.limit,
    )


# ====================================================================
# 5. SMART DISPUTE RESOLVER TIMELINE
# ====================================================================

@router.get("/customers/{cid}/timeline")
async def get_customer_timeline(
    cid: UUID,
    limit: int = Query(10, le=100),
    member_id: UUID | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    s: AsyncSession = Depends(get_session),
    sid: str = Depends(get_shop_id),
):
    """Timeline with running balance window function and transcript evidence."""
    res = await timeline_service.get_dispute_timeline(
        s=s,
        shop_id=sid,
        customer_id=str(cid),
        limit=limit,
        member_id=str(member_id) if member_id else None,
        date_from=date_from,
        date_to=date_to,
    )
    if "error" in res:
        raise HTTPException(404, res["error"])
    return res


# ====================================================================
# 6. AI DAILY KHATA RECONCILIATION ENDPOINTS
# ====================================================================

@router.get("/reconciliation/today")
@router.get("/reconciliation/start")
@router.post("/reconciliation/start")
async def get_today_reconciliation_summary(
    s: AsyncSession = Depends(get_session),
    sid: str = Depends(get_shop_id),
):
    """Retrieve recorded cash and UPI totals for today's evening reconciliation."""
    return await reconciliation_service.start_reconciliation(s=s, shop_id=sid)


@router.post("/reconciliation")
@router.post("/reconciliation/run")
async def submit_daily_reconciliation(
    body: ReconciliationIn,
    s: AsyncSession = Depends(get_session),
    sid: str = Depends(get_shop_id),
):
    """Submit counted cash/UPI, compare with recorded totals, and generate findings."""
    return await reconciliation_service.run_daily_reconciliation(
        s=s,
        shop_id=sid,
        actual_cash=body.actual_cash,
        actual_upi=body.actual_upi,
        on_date=body.on_date,
        notes=body.notes,
    )


@router.get("/reconciliation")
async def list_reconciliations_history(
    date_from: date | None = None,
    date_to: date | None = None,
    s: AsyncSession = Depends(get_session),
    sid: str = Depends(get_shop_id),
):
    """List historical daily reconciliation audits."""
    return await reconciliation_service.list_reconciliations(
        s=s,
        shop_id=sid,
        date_from=date_from,
        date_to=date_to,
    )


@router.patch("/reconciliation/{rid}/resolve")
@router.post("/reconciliation/{rid}/resolve")
async def resolve_reconciliation_endpoint(
    rid: UUID,
    body: ReconciliationResolveIn,
    s: AsyncSession = Depends(get_session),
    sid: str = Depends(get_shop_id),
):
    """Mark an audited discrepancy as resolved with an explanation."""
    res = await reconciliation_service.resolve_reconciliation(
        s=s,
        shop_id=sid,
        rec_id=str(rid),
        note=body.note,
    )
    if "error" in res:
        raise HTTPException(404, res["error"])
    return res
