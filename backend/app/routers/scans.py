import hashlib
import json
import logging
import uuid
from datetime import date
from typing import Literal

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from ..agent.tools import search_customers
from ..config import settings
from ..db import get_session
from ..services.vision import extract

log = logging.getLogger("dukaan.scans")
router = APIRouter(prefix="/scans", tags=["scans"])
SHOP = settings.default_shop_id or "00000000-0000-0000-0000-000000000001"
ALLOWED = {"image/jpeg", "image/png", "image/webp"}
MAX_BYTES = 8 * 1024 * 1024
MAX_LINES = 200


def _j(v):
    return json.loads(v) if isinstance(v, str) else v


async def _load(s: AsyncSession, scan_id: str) -> dict:
    sc = (await s.execute(text("select * from scans where id=:i and shop_id=:shop"),
                          {"i": scan_id, "shop": SHOP})).mappings().first()
    if not sc:
        raise HTTPException(404, "Scan not found")
    lines = (await s.execute(text("select * from scan_lines where scan_id=:i order by row_no"),
                             {"i": scan_id})).mappings().all()
    out = {**sc, "warnings": _j(sc["warnings"])}
    if "image_hash" in out:
        del out["image_hash"]
    return {"scan": out, "lines": [{**l, "candidates": _j(l["candidates"])} for l in lines]}


@router.post("")
async def create_scan(file: UploadFile = File(...), hint: str | None = Form(None),
                      s: AsyncSession = Depends(get_session)):
    if file.content_type not in ALLOWED:
        raise HTTPException(400, "Upload a JPG, PNG or WebP photo")
    data = await file.read()
    if len(data) > MAX_BYTES:
        raise HTTPException(413, "Photo is larger than 8 MB")
    h = hashlib.sha256(data).hexdigest()
    if (await s.execute(text("select 1 from scans where shop_id=:s and image_hash=:h and status<>'rejected'"),
                        {"s": SHOP, "h": h})).first():
        raise HTTPException(409, "This exact photo was already scanned")

    try:
        ex = await extract(data, file.content_type, hint, date.today().isoformat())
    except Exception:
        log.exception("vision failed")
        raise HTTPException(502, "Couldn't read the photo. Try a clearer, well-lit picture.")

    warnings: list[str] = []
    scan_id = str(uuid.uuid4())
    await s.execute(text(
        "insert into scans (id,shop_id,doc_type,image_hash,total_shown,summary) "
        "values (:i,:shop,:dt,:h,:tot,:sum)"),
        {"i": scan_id, "shop": SHOP, "dt": ex.doc_type, "h": h, "tot": ex.total_shown, "sum": ex.summary[:300]})

    credit_sum = 0.0
    for n, ln in enumerate(ex.lines[:MAX_LINES], start=1):
        if not (0 < ln.amount < 10_000_000):
            warnings.append(f"Skipped row {n}: unreadable amount")
            continue
        try:
            d = date.fromisoformat(ln.date) if ln.date else None
        except ValueError:
            d = None
        cands = (await search_customers(s, SHOP, ln.customer_name))["matches"] if ln.customer_name else []
        cust = None
        if cands and cands[0]["score"] >= 0.6 and (len(cands) == 1 or cands[0]["score"] - cands[1]["score"] >= 0.2):
            cust = cands[0]["customer_id"]
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
            ), {"shop": SHOP, "c": cust, "t": ln.type, "a": ln.amount, "d": d})).first())
        if ln.type == "credit":
            credit_sum += ln.amount
        await s.execute(text(
            "insert into scan_lines (scan_id,row_no,raw_name,customer_id,type,amount,txn_date,note,confidence,"
            "raw_text,candidates,duplicate,include) values (:sc,:n,:rn,:c,:t,:a,:d,:note,:conf,:raw,"
            "cast(:cands as jsonb),:dup,:inc)"),
            {"sc": scan_id, "n": n, "rn": ln.customer_name, "c": cust, "t": ln.type, "a": ln.amount, "d": d,
             "note": ln.note, "conf": max(0, min(1, ln.confidence)), "raw": ln.raw_text[:300],
             "cands": json.dumps(cands), "dup": dup, "inc": not dup})
    if ex.total_shown and credit_sum and abs(credit_sum - ex.total_shown) > 1:
        warnings.append(f"Entries add up to ₹{credit_sum:,.0f} but the page total is ₹{ex.total_shown:,.0f}. Check for missed or misread rows.")
    if ex.doc_type == "supplier_bill":
        warnings.append("Supplier bills are kept for reference only. Payables tracking isn't built yet.")
    if ex.doc_type == "unknown":
        warnings.append("This doesn't look like a ledger document.")
    await s.execute(text("update scans set warnings=cast(:w as jsonb) where id=:i"),
                    {"w": json.dumps(warnings), "i": scan_id})
    await s.commit()
    return await _load(s, scan_id)


@router.get("/{scan_id}")
async def get_scan(scan_id: uuid.UUID, s: AsyncSession = Depends(get_session)):
    return await _load(s, str(scan_id))


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
    row = (await s.execute(text(
        "select l.id, l.scan_id from scan_lines l join scans sc on sc.id=l.scan_id "
        "where l.id=:l and sc.shop_id=:shop and sc.status='review'"), {"l": str(line_id), "shop": SHOP})).first()
    if not row:
        raise HTTPException(404, "Line not found or scan already finalized")
    sets: dict = {}
    f = body.model_fields_set
    if body.create_customer_name and body.create_customer_name.strip():
        new = (await s.execute(text("insert into customers (shop_id,name) values (:shop,:n) returning id"),
                               {"shop": SHOP, "n": body.create_customer_name.strip()})).scalar_one()
        sets["customer_id"] = str(new)
    elif "customer_id" in f:
        if body.customer_id and not (await s.execute(text("select 1 from customers where id=:c and shop_id=:shop"),
                                                     {"c": str(body.customer_id), "shop": SHOP})).first():
            raise HTTPException(400, "Unknown customer")
        sets["customer_id"] = str(body.customer_id) if body.customer_id else None
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
    if sets:
        cols = ", ".join(f"{k}=:{k}" for k in sets)
        await s.execute(text(f"update scan_lines set {cols} where id=:id"), {**sets, "id": str(line_id)})
    await s.commit()
    r = (await s.execute(text("select * from scan_lines where id=:i"), {"i": str(line_id)})).mappings().one()
    return {**r, "candidates": _j(r["candidates"])}


@router.post("/{scan_id}/approve")
async def approve(scan_id: uuid.UUID, s: AsyncSession = Depends(get_session)):
    sc = (await s.execute(text("select status from scans where id=:i and shop_id=:shop for update"),
                          {"i": str(scan_id), "shop": SHOP})).first()
    if not sc:
        raise HTTPException(404, "Scan not found")
    if sc[0] != "review":
        raise HTTPException(409, "Scan already finalized")
    lines = (await s.execute(text(
        "select id, customer_id, raw_name, type, amount, txn_date, note, raw_text from scan_lines "
        "where scan_id=:i and include and transaction_id is null order by row_no"), {"i": str(scan_id)})).mappings().all()
    missing = [l["raw_name"] or "(no name)" for l in lines if not l["customer_id"]]
    if missing:
        raise HTTPException(422, {"message": "Pick a customer for every included line", "lines": missing})
    for l in lines:
        tid = (await s.execute(text(
            "insert into transactions (shop_id,customer_id,type,amount,note,raw_transcript,status,confirmed_at,"
            "created_at,source,scan_id) values (:shop,:c,:t,:a,:n,:raw,'confirmed',now(),"
            "coalesce((cast(:d as date)::timestamp + interval '12 hours') at time zone 'Asia/Kolkata', now()),"
            "'scan',:sc) returning id"),
            {"shop": SHOP, "c": str(l["customer_id"]), "t": l["type"], "a": l["amount"], "n": l["note"],
             "raw": l["raw_text"], "d": l["txn_date"], "sc": str(scan_id)})).scalar_one()
        await s.execute(text("update scan_lines set transaction_id=:t where id=:l"), {"t": str(tid), "l": str(l["id"])})
    await s.execute(text("update scans set status='approved' where id=:i"), {"i": str(scan_id)})
    await s.commit()
    return {"created": len(lines)}


@router.post("/{scan_id}/reject")
async def reject(scan_id: uuid.UUID, s: AsyncSession = Depends(get_session)):
    res = await s.execute(text("update scans set status='rejected' where id=:i and shop_id=:shop and status='review'"),
                          {"i": str(scan_id), "shop": SHOP})
    await s.commit()
    if res.rowcount == 0:
        raise HTTPException(409, "Scan not found or already finalized")
    return {"status": "rejected"}
