import hashlib
import json
import logging
import re
import uuid
from datetime import date
from typing import Literal

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from ..agent.tools import create_customer, search_customers
from ..config import settings
from ..db import get_session
from ..services.vision import extract

log = logging.getLogger("dukaan.scans")
router = APIRouter(prefix="/scans", tags=["scans"])
ALLOWED = {"image/jpeg", "image/png", "image/webp"}
MAX_BYTES = 8 * 1024 * 1024
MAX_LINES = 200


def _j(v):
    return json.loads(v) if isinstance(v, str) else v


async def get_shop_id(shop_id: str | None = None, s: AsyncSession | None = None) -> str:
    """Resolve shop_id safely for multi-tenancy."""
    if shop_id:
        return shop_id
    try:
        from ..main import current_shop_context
        ctx = current_shop_context.get()
        if ctx and ctx.strip() and ctx.strip().lower() not in ("undefined", "null", "none"):
            return ctx.strip()
    except Exception:
        pass
    if settings.default_shop_id and settings.default_shop_id.strip():
        return settings.default_shop_id.strip()
    if s:
        row = (await s.execute(text("select id from shops order by created_at asc limit 1"))).scalar()
        if row:
            return str(row)
    return "00000000-0000-0000-0000-000000000001"


async def _load(s: AsyncSession, scan_id: str, shop_id: str | None = None) -> dict:
    shop = shop_id or await get_shop_id(s=s)
    sc = (await s.execute(text("select * from scans where id=:i and shop_id=:shop"),
                          {"i": scan_id, "shop": shop})).mappings().first()
    if not sc:
        raise HTTPException(404, "Scan not found")
    lines = (await s.execute(text("select * from scan_lines where scan_id=:i order by row_no"),
                             {"i": scan_id})).mappings().all()
    out = dict(sc)
    out["warnings"] = _j(sc["warnings"])
    if "image_hash" in out:
        del out["image_hash"]
    return {"scan": out, "lines": [{**l, "candidates": _j(l["candidates"])} for l in lines]}


@router.post("")
async def create_scan(
    file: UploadFile = File(...),
    hint: str | None = Form(None),
    auto_commit: bool = Form(False),
    commit_now: bool = Query(False),
    s: AsyncSession = Depends(get_session),
):
    shop_id = await get_shop_id(s=s)
    should_commit = auto_commit or commit_now

    if file.content_type not in ALLOWED:
        raise HTTPException(400, "Upload a JPG, PNG or WebP photo")
    data = await file.read()
    if len(data) > MAX_BYTES:
        raise HTTPException(413, "Photo is larger than 8 MB")
    h = hashlib.sha256(data).hexdigest()

    # If already approved or reviewed, reject exact photo duplication
    if (await s.execute(text("select 1 from scans where shop_id=:s and image_hash=:h and status<>'rejected'"),
                        {"s": shop_id, "h": h})).first():
        raise HTTPException(409, "This exact photo was already scanned")

    try:
        ex = await extract(data, file.content_type, hint, date.today().isoformat())
    except Exception:
        log.exception("vision failed")
        raise HTTPException(502, "Couldn't read the photo. Try a clearer, well-lit picture.")

    warnings: list[str] = []
    scan_id = str(uuid.uuid4())
    initial_status = "approved" if should_commit else "review"
    await s.execute(text(
        "insert into scans (id,shop_id,doc_type,image_hash,total_shown,summary,status) "
        "values (:i,:shop,:dt,:h,:tot,:sum,:st)"),
        {"i": scan_id, "shop": shop_id, "dt": ex.doc_type, "h": h, "tot": ex.total_shown,
         "sum": ex.summary[:300], "st": initial_status})

    credit_sum = 0.0
    for n, ln in enumerate(ex.lines[:MAX_LINES], start=1):
        if not (0 < ln.amount < 10_000_000):
            warnings.append(f"Skipped row {n}: unreadable amount")
            continue
        try:
            d = date.fromisoformat(ln.date) if ln.date else None
        except ValueError:
            d = None

        # 1. Fuzzy search existing shop customers
        cands = (await search_customers(s, shop_id, ln.customer_name))["matches"] if ln.customer_name else []
        cust = None
        if cands:
            norm_name = ln.customer_name.strip().lower() if ln.customer_name else ""
            exact = next((c for c in cands if c["name"].strip().lower() == norm_name), None)
            if exact:
                cust = exact["customer_id"]
            elif cands[0]["score"] >= 0.6 and (len(cands) == 1 or cands[0]["score"] - cands[1]["score"] >= 0.2):
                cust = cands[0]["customer_id"]

        # 2. When should_commit is True and no clear match, auto-register customer
        if should_commit and not cust:
            target_name = (ln.customer_name or "").strip()
            if target_name:
                try:
                    res_cust = await create_customer(s, shop_id, target_name)
                    if "customer_id" in res_cust:
                        cust = res_cust["customer_id"]
                except Exception as ex_c:
                    log.warning("Failed to auto-create customer '%s': %s", target_name, ex_c)
                if not cust:
                    # Clean trailing punctuation or numbers e.g. "Kavita_123" -> "Kavita"
                    clean_alpha = re.sub(r'[^A-Za-z\u0900-\u097F\u0C80-\u0CFF\s]', '', target_name).strip().title()
                    if clean_alpha:
                        try:
                            res_cust2 = await create_customer(s, shop_id, clean_alpha)
                            if "customer_id" in res_cust2:
                                cust = res_cust2["customer_id"]
                        except Exception:
                            pass
                    if not cust:
                        new_cid = uuid.uuid4()
                        await s.execute(text(
                            "insert into customers (id, shop_id, name) values (:id, cast(:shop as uuid), :n)"
                        ), {"id": new_cid, "shop": shop_id, "n": (clean_alpha or target_name[:50])})
                        await s.commit()
                        cust = str(new_cid)
            if not cust:
                try:
                    walk_in = await create_customer(s, shop_id, "Walk-in Customer")
                    cust = walk_in.get("customer_id")
                except Exception:
                    pass

        # 3. Duplicate check for this customer, amount, type, date
        dup = False
        if cust:
            dup = bool((await s.execute(text(
                """select 1 from transactions
                   where shop_id = cast(:shop as uuid)
                     and customer_id = cast(:c as uuid)
                     and type = :t
                     and abs(amount - cast(:a as numeric)) < 0.01
                     and (
                       created_at::date = coalesce(cast(:d as date), current_date)
                       or (created_at at time zone 'Asia/Kolkata')::date = coalesce(cast(:d as date), current_date)
                       or coalesce(backdated_to, created_at::date) = coalesce(cast(:d as date), current_date)
                     )
                     and status = 'confirmed'
                   limit 1"""
            ), {"shop": shop_id, "c": cust, "t": ln.type, "a": ln.amount, "d": d})).first())

        if ln.type == "credit":
            credit_sum += ln.amount

        # 4. If should_commit is requested and not a duplicate, persist transaction immediately
        tid = None
        if should_commit and not dup and cust:
            tid = (await s.execute(text(
                """insert into transactions (
                    shop_id, customer_id, type, amount, note, raw_transcript,
                    status, confirmed_at, created_at, source, scan_id
                ) values (
                    cast(:shop as uuid), cast(:c as uuid), :t, :a, :n, :raw,
                    'confirmed', now(),
                    coalesce((cast(:d as date)::timestamp + interval '12 hours') at time zone 'Asia/Kolkata', now()),
                    'scan', cast(:sc as uuid)
                ) returning id"""
            ), {
                "shop": shop_id,
                "c": str(cust),
                "t": ln.type,
                "a": ln.amount,
                "n": ln.note or f"Scanned from {ex.doc_type}",
                "raw": ln.raw_text[:500] if ln.raw_text else None,
                "d": d,
                "sc": scan_id,
            })).scalar_one()
        elif dup and should_commit:
            warnings.append(f"Row {n} ({ln.customer_name or 'Customer'} ₹{ln.amount:,.0f}) was already recorded today; skipped auto-add to avoid duplicate.")

        await s.execute(text(
            """insert into scan_lines (
                scan_id, row_no, raw_name, customer_id, type, amount, txn_date,
                note, confidence, raw_text, candidates, duplicate, include, transaction_id
            ) values (
                cast(:sc as uuid), :n, :rn, cast(:c as uuid), :t, :a, :d,
                :note, :conf, :raw, cast(:cands as jsonb), :dup, :inc, cast(:tid as uuid)
            )"""
        ), {
            "sc": scan_id, "n": n, "rn": ln.customer_name, "c": str(cust) if cust else None,
            "t": ln.type, "a": ln.amount, "d": d, "note": ln.note,
            "conf": max(0, min(1, ln.confidence)), "raw": ln.raw_text[:300] if ln.raw_text else None,
            "cands": json.dumps(cands), "dup": dup, "inc": not dup, "tid": str(tid) if tid else None
        })

    if ex.total_shown and credit_sum and abs(credit_sum - ex.total_shown) > 1:
        warnings.append(f"Entries add up to ₹{credit_sum:,.0f} but the page total is ₹{ex.total_shown:,.0f}. Check for missed or misread rows.")
    if ex.doc_type == "supplier_bill":
        warnings.append("Supplier bills are kept for reference only. Payables tracking isn't built yet.")
    if ex.doc_type == "unknown":
        warnings.append("This doesn't look like a ledger document.")

    await s.execute(text("update scans set warnings=cast(:w as jsonb) where id=:i"),
                    {"w": json.dumps(warnings), "i": scan_id})
    await s.commit()
    return await _load(s, scan_id, shop_id)


@router.get("/{scan_id}")
async def get_scan(scan_id: uuid.UUID, s: AsyncSession = Depends(get_session)):
    shop_id = await get_shop_id(s=s)
    return await _load(s, str(scan_id), shop_id)


class LineEdit(BaseModel):
    customer_id: uuid.UUID | None = None
    create_customer_name: str | None = None
    type: Literal["credit", "payment"] | None = None
    amount: float | None = None
    txn_date: date | None = None
    note: str | None = None
    include: bool | None = None


@router.patch("/lines/{line_id}")
async def edit_line(line_id: uuid.UUID, body: LineEdit, s: AsyncSession = Depends(get_session)):
    shop_id = await get_shop_id(s=s)
    row = (await s.execute(text(
        "select l.id, l.scan_id, l.transaction_id, l.type, l.amount, l.customer_id, l.note, l.txn_date, l.include "
        "from scan_lines l join scans sc on sc.id=l.scan_id "
        "where l.id=:l and sc.shop_id=:shop and sc.status<>'rejected'"), {"l": str(line_id), "shop": shop_id})).first()
    if not row:
        raise HTTPException(404, "Line not found or scan already finalized")

    sets: dict = {}
    f = body.model_fields_set

    # 1. Resolve Customer if changed or new customer requested
    if body.create_customer_name and body.create_customer_name.strip():
        res_c = await create_customer(s, shop_id, body.create_customer_name.strip())
        if "customer_id" in res_c:
            sets["customer_id"] = res_c["customer_id"]
    elif "customer_id" in f:
        if body.customer_id:
            cid_str = str(body.customer_id)
            if not (await s.execute(text("select 1 from customers where id=:c and shop_id=:shop"),
                                    {"c": cid_str, "shop": shop_id})).first():
                raise HTTPException(400, "Unknown customer")
            sets["customer_id"] = cid_str
        else:
            sets["customer_id"] = None

    if body.type:
        sets["type"] = body.type
    if body.amount is not None:
        if not (0 < body.amount < 10_000_000):
            raise HTTPException(400, "Amount out of range")
        sets["amount"] = body.amount
    if "txn_date" in f:
        sets["txn_date"] = body.txn_date
    if "note" in f:
        sets["note"] = body.note
    if body.include is not None:
        sets["include"] = body.include

    # Calculate effective updated values
    eff_cust = sets.get("customer_id", str(row.customer_id) if row.customer_id else None)
    eff_type = sets.get("type", row.type)
    eff_amount = sets.get("amount", row.amount)
    eff_note = sets.get("note", row.note)
    eff_date = sets.get("txn_date", row.txn_date)
    eff_inc = sets.get("include", row.include)
    current_tid = row.transaction_id

    # Sync to transactions table if transaction already exists or should exist
    if eff_inc:
        if current_tid:
            await s.execute(text(
                """update transactions set
                    customer_id = cast(:c as uuid),
                    type = :t,
                    amount = :a,
                    note = :n,
                    created_at = coalesce((cast(:d as date)::timestamp + interval '12 hours') at time zone 'Asia/Kolkata', created_at)
                   where id = cast(:tid as uuid) and shop_id = cast(:shop as uuid)"""
            ), {
                "c": str(eff_cust) if eff_cust else None,
                "t": eff_type,
                "a": eff_amount,
                "n": eff_note,
                "d": eff_date,
                "tid": str(current_tid),
                "shop": shop_id
            })
        elif eff_cust:
            # Check if parent scan was approved
            scan_row = (await s.execute(text("select status from scans where id=:sc"), {"sc": str(row.scan_id)})).first()
            if scan_row and scan_row[0] == "approved":
                new_tid = (await s.execute(text(
                    """insert into transactions (
                        shop_id, customer_id, type, amount, note,
                        status, confirmed_at, created_at, source, scan_id
                    ) values (
                        cast(:shop as uuid), cast(:c as uuid), :t, :a, :n,
                        'confirmed', now(),
                        coalesce((cast(:d as date)::timestamp + interval '12 hours') at time zone 'Asia/Kolkata', now()),
                        'scan', cast(:sc as uuid)
                    ) returning id"""
                ), {
                    "shop": shop_id,
                    "c": str(eff_cust),
                    "t": eff_type,
                    "a": eff_amount,
                    "n": eff_note or "Scanned line",
                    "d": eff_date,
                    "sc": str(row.scan_id)
                })).scalar_one()
                sets["transaction_id"] = str(new_tid)
    else:
        # If toggled off / excluded, remove from transactions table
        if current_tid:
            await s.execute(text("delete from transactions where id = cast(:tid as uuid)"), {"tid": str(current_tid)})
            sets["transaction_id"] = None

    if sets:
        cols = ", ".join(f"{k}=:{k}" for k in sets)
        await s.execute(text(f"update scan_lines set {cols} where id=:id"), {**sets, "id": str(line_id)})
    await s.commit()
    r = (await s.execute(text("select * from scan_lines where id=:i"), {"i": str(line_id)})).mappings().one()
    return {**r, "candidates": _j(r["candidates"])}


@router.post("/{scan_id}/approve")
async def approve(
    scan_id: uuid.UUID,
    auto_create_customers: bool = Query(False),
    s: AsyncSession = Depends(get_session),
):
    shop_id = await get_shop_id(s=s)
    sc = (await s.execute(text("select status from scans where id=:i and shop_id=:shop for update"),
                          {"i": str(scan_id), "shop": shop_id})).first()
    if not sc:
        raise HTTPException(404, "Scan not found")
    if sc[0] != "review":
        raise HTTPException(409, "Scan already finalized")

    lines = (await s.execute(text(
        "select id, customer_id, raw_name, type, amount, txn_date, note, raw_text, transaction_id from scan_lines "
        "where scan_id=:i and include and transaction_id is null order by row_no"), {"i": str(scan_id)})).mappings().all()

    missing = [l["raw_name"] or "(no name)" for l in lines if not l["customer_id"]]
    if missing:
        if auto_create_customers:
            resolved_lines = []
            for l in lines:
                cid = l["customer_id"]
                if not cid:
                    target_name = (l["raw_name"] or "").strip()
                    if target_name:
                        res_c = await create_customer(s, shop_id, target_name)
                        cid = res_c.get("customer_id")
                    if not cid:
                        walk_in = await create_customer(s, shop_id, "Walk-in Customer")
                        cid = walk_in.get("customer_id")
                    await s.execute(text("update scan_lines set customer_id=:c where id=:l"), {"c": str(cid), "l": str(l["id"])})
                resolved_lines.append({**dict(l), "customer_id": cid})
            lines = resolved_lines
        else:
            raise HTTPException(422, {"message": "Pick a customer for every included line", "lines": missing})

    for l in lines:
        tid = (await s.execute(text(
            "insert into transactions (shop_id,customer_id,type,amount,note,raw_transcript,status,confirmed_at,"
            "created_at,source,scan_id) values (:shop,:c,:t,:a,:n,:raw,'confirmed',now(),"
            "coalesce((cast(:d as date)::timestamp + interval '12 hours') at time zone 'Asia/Kolkata', now()),"
            "'scan',:sc) returning id"),
            {"shop": shop_id, "c": str(l["customer_id"]), "t": l["type"], "a": l["amount"], "n": l["note"],
             "raw": l["raw_text"], "d": l["txn_date"], "sc": str(scan_id)})).scalar_one()
        await s.execute(text("update scan_lines set transaction_id=:t where id=:l"), {"t": str(tid), "l": str(l["id"])})

    await s.execute(text("update scans set status='approved' where id=:i"), {"i": str(scan_id)})
    await s.commit()
    return {"created": len(lines)}


@router.post("/{scan_id}/reject")
async def reject(scan_id: uuid.UUID, s: AsyncSession = Depends(get_session)):
    shop_id = await get_shop_id(s=s)
    # Remove any transactions that were committed by this scan
    await s.execute(text("delete from transactions where scan_id = cast(:i as uuid) and shop_id = cast(:shop as uuid)"),
                    {"i": str(scan_id), "shop": shop_id})
    await s.execute(text("update scan_lines set transaction_id = null where scan_id = cast(:i as uuid)"),
                    {"i": str(scan_id)})
    res = await s.execute(text("update scans set status='rejected' where id=:i and shop_id=:shop and status<>'rejected'"),
                          {"i": str(scan_id), "shop": shop_id})
    await s.commit()
    if res.rowcount == 0:
        raise HTTPException(409, "Scan not found or already finalized")
    return {"status": "rejected"}
