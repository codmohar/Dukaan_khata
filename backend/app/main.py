import base64
import json
import logging
from contextlib import asynccontextmanager
from contextvars import ContextVar
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Any
from uuid import UUID

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from .agent import tools
from .agent.pipeline import VoiceSession
from .config import settings
from .db import get_session, init_db
from .models import Customer, Shop, Transaction
from .routers.auth import router as auth_router
from .routers.features import router as features_router
from .routers.scans import router as scans_router
from .schemas import (
    CustomerIn,
    CustomerOut,
    CustomerUpdate,
    DashboardStats,
    DraftActionResponse,
    FinalizeDraftIn,
    ShopOut,
    ShopUpdate,
    TransactionIn,
    TransactionOut,
    VoiceTurnResponse,
)
from .services import rules as rules_service
from .services import speech

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
log = logging.getLogger("dukaan.api")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize database tables and seed defaults on startup
    log.info("Starting DukaanAI Backend...")
    await init_db()
    yield
    log.info("Shutting down DukaanAI Backend...")


app = FastAPI(title="DukaanAI", description="Voice Khata for Indian Kirana Shopkeepers", lifespan=lifespan)

# Setup CORS
cors_list = [o.strip() for o in settings.cors_origins.split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_list or ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

current_shop_context: ContextVar[str | None] = ContextVar("current_shop_context", default=None)


@app.middleware("http")
async def shop_context_middleware(request: Request, call_next):
    raw_header = request.headers.get("x-shop-id") or request.query_params.get("shop_id")
    if raw_header and raw_header.strip() and raw_header.strip().lower() not in ("undefined", "null", "none"):
        token = current_shop_context.set(raw_header.strip())
    else:
        token = current_shop_context.set(None)
    try:
        response = await call_next(request)
        return response
    finally:
        current_shop_context.reset(token)

app.include_router(auth_router)
app.include_router(scans_router)
app.include_router(features_router)

MAX_UTTERANCE_BYTES = 16000 * 2 * 30  # 30 seconds of 16 kHz mono PCM16


def safe_uuid_str(val: Any) -> str | None:
    if not val:
        return None
    s = str(val).strip()
    if "?" in s:
        s = s.split("?")[0].strip()
    if "&" in s:
        s = s.split("&")[0].strip()
    if not s or s.lower() in ("undefined", "null", "none"):
        return None
    try:
        return str(UUID(s))
    except (ValueError, TypeError):
        return None


async def get_current_shop_id(
    shop_id: Any = None,
    s: AsyncSession | None = None,
    x_shop_id: str | None = None,
) -> str:
    """Resolve shop_id safely: provided param -> X-Shop-Id header/ctx -> config -> first DB shop."""
    # Handle cases where s was passed positionally or shop_id was an AsyncSession
    if isinstance(shop_id, AsyncSession):
        s, shop_id = shop_id, None
    if isinstance(s, str):
        x_shop_id, s = s, None

    # Check explicit argument
    valid_sid = safe_uuid_str(shop_id) or safe_uuid_str(x_shop_id)
    if valid_sid:
        return valid_sid

    # Check request context (from header X-Shop-Id or query param)
    ctx_val = safe_uuid_str(current_shop_context.get())
    if ctx_val:
        return ctx_val

    # Check environment/config default_shop_id
    def_sid = safe_uuid_str(settings.default_shop_id)
    if def_sid:
        return def_sid

    # Fallback to first shop in DB
    if s and isinstance(s, AsyncSession):
        try:
            row = (await s.execute(text("select id from shops order by created_at asc limit 1"))).scalar()
            if row:
                row_sid = safe_uuid_str(row)
                if row_sid:
                    return row_sid
        except Exception:
            pass

    return "00000000-0000-0000-0000-000000000001"


# -------------------- HEALTH & SHOP --------------------

@app.get("/health")
async def health(s: AsyncSession = Depends(get_session)):
    db_ok = False
    try:
        await s.execute(text("select 1"))
        db_ok = True
    except Exception as e:
        log.warning("Healthcheck DB ping failed: %s", e)
    return {
        "ok": True,
        "database": db_ok,
        "default_shop_id": settings.default_shop_id,
        "speech_provider": settings.speech_provider,
        "model": settings.gemini_model,
    }


@app.get("/shop", response_model=ShopOut)
async def get_shop(s: AsyncSession = Depends(get_session)):
    sid = await get_current_shop_id(None, s)
    row = (await s.execute(
        text("select id, name, owner_name, phone, language from shops where id = :s"),
        {"s": sid}
    )).mappings().first()
    if not row:
        raise HTTPException(404, "Shop not found")
    return dict(row)


@app.put("/shop", response_model=ShopOut)
async def update_shop(body: ShopUpdate, s: AsyncSession = Depends(get_session)):
    sid = await get_current_shop_id(None, s)
    shop = await s.get(Shop, UUID(sid))
    if not shop:
        raise HTTPException(404, "Shop not found")
    if body.name is not None:
        shop.name = body.name
    if body.owner_name is not None:
        shop.owner_name = body.owner_name
    if body.phone is not None:
        shop.phone = body.phone
    if body.language is not None:
        shop.language = body.language
    await s.commit()
    await s.refresh(shop)
    return shop


# -------------------- CUSTOMERS CRUD --------------------

@app.get("/customers", response_model=list[CustomerOut])
async def list_customers(
    q: str | None = None,
    s: AsyncSession = Depends(get_session),
):
    sid = await get_current_shop_id(None, s)
    rows = (
        await s.execute(
            text(
                """
                select c.id, c.name, c.phone, c.landmark, c.created_at,
                       coalesce(b.balance, 0) as balance
                from customers c
                left join customer_balances b on b.customer_id = c.id
                where c.shop_id = :shop
                  and (cast(:q as text) is null or c.name ilike '%' || :q || '%' or c.landmark ilike '%' || :q || '%')
                order by c.name asc
                """
            ),
            {"shop": sid, "q": q.strip() if q else None},
        )
    ).mappings().all()
    return [dict(r) for r in rows]


@app.post("/customers", response_model=CustomerOut, status_code=201)
async def create_customer_endpoint(body: CustomerIn, s: AsyncSession = Depends(get_session)):
    sid = await get_current_shop_id(None, s)
    from app.agent.tools import transliterate_indic_to_latin, normalize_customer_query
    raw_name = normalize_customer_query(body.name.strip())
    lat = transliterate_indic_to_latin(raw_name)
    clean_name = (lat or raw_name).strip().title()
    row = (
        await s.execute(
            text(
                """
                insert into customers (shop_id, name, phone, landmark)
                values (:shop, :n, :p, :l)
                returning id, name, phone, landmark, created_at
                """
            ),
            {"shop": sid, "n": clean_name, "p": body.phone, "l": body.landmark},
        )
    ).mappings().one()
    await s.commit()
    return {**row, "balance": Decimal("0.00")}


@app.get("/customers/{cid}")
async def get_customer_detail(cid: UUID, s: AsyncSession = Depends(get_session)):
    sid = await get_current_shop_id(None, s)
    cust = (
        await s.execute(
            text(
                """
                select c.id, c.name, c.phone, c.landmark, c.created_at,
                       coalesce(b.balance, 0) as balance
                from customers c
                left join customer_balances b on b.customer_id = c.id
                where c.id = :cid and c.shop_id = :shop
                """
            ),
            {"cid": str(cid), "shop": sid},
        )
    ).mappings().first()
    if not cust:
        raise HTTPException(404, "Customer not found")

    recent_txns = (
        await s.execute(
            text(
                """
                select id, type, amount, note, status, created_at
                from transactions
                where customer_id = :cid and shop_id = :shop
                order by created_at desc limit 20
                """
            ),
            {"cid": str(cid), "shop": sid},
        )
    ).mappings().all()

    return {**cust, "recent_transactions": [dict(t) for t in recent_txns]}


@app.put("/customers/{cid}", response_model=CustomerOut)
async def update_customer(cid: UUID, body: CustomerUpdate, s: AsyncSession = Depends(get_session)):
    sid = await get_current_shop_id(None, s)
    cust = await s.get(Customer, cid)
    if not cust or str(cust.shop_id) != sid:
        raise HTTPException(404, "Customer not found")
    if body.name is not None:
        cust.name = body.name.strip()
    if body.phone is not None:
        cust.phone = body.phone.strip() if body.phone else None
    if body.landmark is not None:
        cust.landmark = body.landmark.strip() if body.landmark else None
    await s.commit()

    bal = (
        await s.execute(
            text("select balance from customer_balances where customer_id = :cid"),
            {"cid": str(cid)},
        )
    ).scalar() or Decimal("0.00")

    return {
        "id": cust.id,
        "name": cust.name,
        "phone": cust.phone,
        "landmark": cust.landmark,
        "created_at": cust.created_at,
        "balance": bal,
    }


@app.delete("/customers/{cid}", status_code=204)
async def delete_customer_endpoint(cid: UUID, s: AsyncSession = Depends(get_session)):
    sid = await get_current_shop_id(None, s)
    res = await s.execute(
        text("delete from customers where id = :c and shop_id = :shop"),
        {"c": str(cid), "shop": sid},
    )
    await s.commit()
    if res.rowcount == 0:
        raise HTTPException(404, "Customer not found")


# -------------------- TRANSACTIONS (LEDGER) --------------------

@app.get("/transactions", response_model=list[TransactionOut])
async def list_transactions(
    customer_id: UUID | None = None,
    member_id: UUID | None = None,
    type: str | None = None,
    status: str | None = None,
    start: date | None = None,
    end: date | None = None,
    limit: int = Query(100, le=500),
    s: AsyncSession = Depends(get_session),
):
    sid = await get_current_shop_id(None, s)
    rows = (
        await s.execute(
            text(
                """
                select t.id, t.customer_id, t.member_id, hm.member_name, c.name as customer_name, c.phone as customer_phone,
                       t.type, t.amount, t.payment_mode, t.adjustment_reason, t.due_date, t.backdated_to, t.items,
                       t.item_note, t.note, t.rule_warnings, t.rule_override, t.transcript_snippet,
                       t.status, t.created_at, t.confirmed_at
                from transactions t
                join customers c on c.id = t.customer_id
                left join household_members hm on hm.id = t.member_id
                where t.shop_id = :shop
                  and (cast(:cid as uuid) is null or t.customer_id = cast(:cid as uuid))
                  and (cast(:mid as uuid) is null or t.member_id = cast(:mid as uuid))
                  and (cast(:type as text) is null or t.type = :type)
                  and (cast(:status as text) is null or t.status = :status)
                  and (cast(:start as date) is null or t.created_at::date >= :start)
                  and (cast(:end as date) is null or t.created_at::date <= :end)
                order by t.created_at desc
                limit :lim
                """
            ),
            {
                "shop": sid,
                "cid": str(customer_id) if customer_id else None,
                "mid": str(member_id) if member_id else None,
                "type": type,
                "status": status,
                "start": start,
                "end": end,
                "lim": limit,
            },
        )
    ).mappings().all()
    return [dict(r) for r in rows]


@app.get("/customers/{cid}/transactions", response_model=list[TransactionOut])
async def list_customer_transactions(
    cid: UUID,
    member_id: UUID | None = None,
    type: str | None = None,
    start: date | None = None,
    end: date | None = None,
    limit: int = Query(100, le=500),
    s: AsyncSession = Depends(get_session),
):
    """Convenience alias for listing transactions of a specific customer with member/date filters."""
    return await list_transactions(
        customer_id=cid,
        member_id=member_id,
        type=type,
        status="confirmed",
        start=start,
        end=end,
        limit=limit,
        s=s,
    )


@app.post("/transactions", response_model=TransactionOut, status_code=201)
async def create_transaction_manual(body: TransactionIn, s: AsyncSession = Depends(get_session)):
    sid = await get_current_shop_id(None, s)
    cust = await s.get(Customer, body.customer_id)
    if not cust or str(cust.shop_id) != sid:
        raise HTTPException(404, "Customer not found in this shop")

    confirmed_at = datetime.now(timezone.utc) if body.status == "confirmed" else None
    t = Transaction(
        shop_id=UUID(sid),
        customer_id=body.customer_id,
        type=body.type,
        amount=body.amount,
        payment_mode=body.payment_mode,
        adjustment_reason=body.adjustment_reason,
        due_date=body.due_date,
        backdated_to=body.backdated_to,
        items=body.items,
        note=body.note,
        status=body.status,
        confirmed_at=confirmed_at,
    )
    s.add(t)
    await s.commit()
    await s.refresh(t)

    return {
        "id": t.id,
        "customer_id": t.customer_id,
        "customer_name": cust.name,
        "customer_phone": cust.phone,
        "type": t.type,
        "amount": t.amount,
        "payment_mode": t.payment_mode,
        "adjustment_reason": t.adjustment_reason,
        "due_date": t.due_date,
        "backdated_to": t.backdated_to,
        "items": t.items,
        "note": t.note,
        "status": t.status,
        "created_at": t.created_at,
        "confirmed_at": t.confirmed_at,
    }


@app.get("/transactions/{tid}", response_model=TransactionOut)
async def get_transaction(tid: UUID, s: AsyncSession = Depends(get_session)):
    sid = await get_current_shop_id(None, s)
    row = (
        await s.execute(
            text(
                """
                select t.id, t.customer_id, c.name as customer_name, c.phone as customer_phone,
                       t.type, t.amount, t.payment_mode, t.adjustment_reason, t.due_date, t.backdated_to, t.items,
                       t.note, t.status, t.created_at, t.confirmed_at
                from transactions t
                join customers c on c.id = t.customer_id
                where t.id = :tid and t.shop_id = :shop
                """
            ),
            {"tid": str(tid), "shop": sid},
        )
    ).mappings().first()
    if not row:
        raise HTTPException(404, "Transaction not found")
    return dict(row)


@app.post("/transactions/{tid}/{action}", response_model=DraftActionResponse)
async def finalize_transaction(
    tid: UUID,
    action: str,
    body: FinalizeDraftIn | None = None,
    s: AsyncSession = Depends(get_session),
):
    if action not in ("confirm", "cancel"):
        raise HTTPException(400, "Action must be 'confirm' or 'cancel'")
    sid = await get_current_shop_id(None, s)

    if action == "confirm":
        if body and body.override_warnings:
            await rules_service.override_rule_warnings(s, sid, str(tid))
        out = await tools.confirm_draft(s, sid, str(tid))
        if "error" in out:
            raise HTTPException(400, out["error"])
        return DraftActionResponse(
            status="confirmed",
            draft_id=str(tid),
            new_balance=float(out["new_balance"]),
        )
    else:
        out = await tools.cancel_draft(s, sid, str(tid))
        if "error" in out:
            raise HTTPException(404, out["error"])
        return DraftActionResponse(
            status="cancelled",
            draft_id=str(tid),
            new_balance=float(out.get("new_balance", 0.0)),
        )


# -------------------- DASHBOARD & REPORTS --------------------

@app.get("/dashboard/stats", response_model=DashboardStats)
async def get_dashboard_stats(s: AsyncSession = Depends(get_session)):
    sid = await get_current_shop_id(None, s)
    since_date = date.today() - timedelta(days=6)
    since_ts = datetime.combine(since_date, datetime.min.time(), tzinfo=timezone.utc)
    today_ts = datetime.combine(date.today(), datetime.min.time(), tzinfo=timezone.utc)

    # 1. Total outstanding across all customers
    tot_out = (await s.execute(
        text("SELECT coalesce(sum(balance), 0) FROM customer_balances WHERE shop_id = :shop"),
        {"shop": sid}
    )).scalar() or Decimal("0.00")

    # 2. Today's credit, today's payment, customer count, pending drafts
    stats_row = (await s.execute(
        text("""
            SELECT
                coalesce(sum(amount) filter (where type = 'credit' and status = 'confirmed' and created_at >= :today_ts), 0) as cr,
                coalesce(sum(amount) filter (where type = 'payment' and status = 'confirmed' and created_at >= :today_ts), 0) as pay,
                (SELECT count(*) FROM customers WHERE shop_id = :shop) as cnt,
                count(*) filter (where status = 'draft') as drafts
            FROM transactions
            WHERE shop_id = :shop
        """),
        {"shop": sid, "today_ts": today_ts}
    )).mappings().one()

    # 3. Last 7 days breakdown
    daily_rows = (await s.execute(
        text("""
            SELECT
                created_at::date as d,
                coalesce(sum(amount) filter (where type = 'credit'), 0) as credit,
                coalesce(sum(amount) filter (where type = 'payment'), 0) as payment
            FROM transactions
            WHERE shop_id = :shop and status = 'confirmed' and created_at >= :since_ts
            GROUP BY created_at::date
        """),
        {"shop": sid, "since_ts": since_ts}
    )).mappings().all()

    daily_map = {r["d"]: r for r in daily_rows}
    series = []
    for i in range(7):
        d = since_date + timedelta(days=i)
        r = daily_map.get(d)
        series.append({
            "date": d.isoformat(),
            "credit": float(r["credit"]) if r else 0.0,
            "payment": float(r["payment"]) if r else 0.0,
        })

    return DashboardStats(
        total_outstanding=tot_out,
        credit_today=stats_row["cr"],
        payments_today=stats_row["pay"],
        customer_count=stats_row["cnt"],
        pending_drafts=stats_row["drafts"],
        last_7_days=series,
    )


@app.get("/reports/summary")
async def get_reports_summary(s: AsyncSession = Depends(get_session)):
    sid = await get_current_shop_id(None, s)

    # Debtors list (customers who owe > 0)
    debtors = (
        await s.execute(
            text(
                """
                select c.id, c.name, c.phone, c.landmark, coalesce(b.balance, 0) as balance
                from customers c
                join customer_balances b on b.customer_id = c.id
                where c.shop_id = :shop and b.balance > 0
                order by b.balance desc
                """
            ),
            {"shop": sid},
        )
    ).mappings().all()

    # 30-day totals
    since_30 = date.today() - timedelta(days=30)
    month_stats = (
        await s.execute(
            text(
                """
                select 
                  coalesce(sum(amount) filter (where type = 'credit' and status = 'confirmed'), 0) as credit_30d,
                  coalesce(sum(amount) filter (where type = 'payment' and status = 'confirmed'), 0) as payment_30d
                from transactions
                where shop_id = :shop and created_at::date >= :since
                """
            ),
            {"shop": sid, "since": since_30},
        )
    ).mappings().one()

    return {
        "debtors": [dict(d) for d in debtors],
        "total_outstanding": sum(float(d["balance"]) for d in debtors),
        "debtors_count": len(debtors),
        "credit_30d": float(month_stats["credit_30d"]),
        "payment_30d": float(month_stats["payment_30d"]),
    }


from pydantic import BaseModel

class VoiceProcessRequest(BaseModel):
    audio_base64: str | None = None
    text: str | None = None
    language: str = "kn-IN"
    shop_id: str | None = None

# -------------------- VOICE PROCESS REST ENDPOINT --------------------

@app.post("/voice/process", response_model=VoiceTurnResponse)
async def process_voice_turn(
    body: VoiceProcessRequest,
    s: AsyncSession = Depends(get_session),
):
    """Direct REST endpoint for processing voice audio (base64) or text input."""
    sid = await get_current_shop_id(body.shop_id, s)
    sess = VoiceSession(sid, body.language)

    user_text = ""
    if body.audio_base64:
        try:
            pcm = base64.b64decode(body.audio_base64)
            user_text = await sess.transcribe(pcm)
        except Exception as e:
            log.warning("Audio decode error: %s", e)
    elif body.text:
        user_text = body.text.strip()

    if not user_text:
        raise HTTPException(400, "Provide either audio_base64 or text in request body")

    reply, events = await sess.respond(user_text)

    # Synthesize audio response (skip if silent ambient context)
    audio_b64 = None
    if reply != "[SILENT]":
        try:
            wav_bytes = await sess.synthesize(reply)
            if wav_bytes:
                audio_b64 = base64.b64encode(wav_bytes).decode()
        except Exception as e:
            log.warning("Audio synthesis failed: %s", e)

    return VoiceTurnResponse(
        transcript=user_text,
        reply=reply,
        audio_base64=audio_b64,
        events=events,
        cache_state=sess.cache.to_dict() if hasattr(sess, "cache") else None,
    )


# -------------------- VOICE WEBSOCKET --------------------

@app.websocket("/ws/voice")
async def ws_voice_endpoint(
    ws: WebSocket,
    language: str = "kn-IN",
    shop_id: str | None = None,
):
    """WebSocket voice Khata session streaming 16kHz PCM audio."""
    await ws.accept()
    resolved_shop = safe_uuid_str(shop_id) or safe_uuid_str(settings.default_shop_id) or "00000000-0000-0000-0000-000000000001"
    sess = VoiceSession(resolved_shop, language)
    buf = bytearray()

    async def send_json(obj: dict):
        try:
            await ws.send_text(json.dumps(obj, ensure_ascii=False))
        except Exception:
            pass

    try:
        while True:
            msg = await ws.receive()
            if msg.get("type") == "websocket.disconnect":
                break

            # Binary audio frame: 16 kHz mono PCM16
            if msg.get("bytes"):
                buf += msg["bytes"]
                if len(buf) > MAX_UTTERANCE_BYTES:
                    buf.clear()
                    await send_json({"type": "error", "message": "Utterance exceeded maximum length"})
                continue

            # JSON text frame (control commands or typed text)
            if not msg.get("text"):
                continue

            try:
                ctl = json.loads(msg["text"])
            except Exception:
                continue

            kind = ctl.get("type")

            try:
                if kind == "ping":
                    await send_json({"type": "pong"})
                    continue

                if kind == "reset":
                    sess = VoiceSession(sess.shop_id, language)
                    buf.clear()
                    await send_json({"type": "reset_ack"})
                    continue

                if kind == "set_language":
                    new_lang = ctl.get("language", "kn-IN")
                    sess.language = new_lang
                    await send_json({"type": "language_changed", "language": new_lang})
                    continue

                if kind == "end_utterance":
                    client_text = str(ctl.get("text", "")).strip()
                    pcm = bytes(buf)
                    buf.clear()
                    if client_text:
                        user_text = client_text
                    else:
                        if len(pcm) < 3200:  # < 100 ms of audio: ignore noise
                            await send_json({"type": "noop"})
                            continue
                        user_text = await sess.transcribe(pcm)

                elif kind == "audio_file":
                    client_text = str(ctl.get("text", "")).strip()
                    if client_text:
                        user_text = client_text
                    else:
                        raw_b64 = ctl.get("data", "")
                        if not raw_b64:
                            await send_json({"type": "noop"})
                            continue
                        audio_bytes = base64.b64decode(raw_b64)
                        if len(audio_bytes) < 1000:
                            await send_json({"type": "noop"})
                            continue
                        user_text = await sess.transcribe(audio_bytes)

                elif kind == "text":
                    user_text = str(ctl.get("text", "")).strip()

                else:
                    continue

                if not user_text:
                    await send_json({"type": "error", "message": "Could not recognize any speech. Please repeat."})
                    continue

                # Echo transcript to client
                await send_json({"type": "transcript", "text": user_text})

                # Run conversation turn with LLM and DB tools
                reply, events = await sess.respond(user_text)
                log.info("Voice Turn [shop=%s, lang=%s]: '%s' -> reply: '%s' (events: %d)", sess.shop_id, sess.language, user_text, reply, len(events))

                # If ambient pre-transaction talk (e.g. item browsing), stay silent and keep context!
                if reply == "[SILENT]" and not events:
                    await send_json({"type": "silent_context"})
                    continue

                # Emit ledger draft / confirmation events
                for ev in events:
                    await send_json(ev)

                # Emit final assistant textual reply with conversation cache context
                await send_json({
                    "type": "reply",
                    "text": reply,
                    "cache_state": sess.cache.to_dict() if hasattr(sess, "cache") else None,
                })

                # Synthesize and stream speech audio WAV
                try:
                    wav_data = await sess.synthesize(reply)
                    if wav_data:
                        await send_json({
                            "type": "audio",
                            "format": "wav",
                            "data": base64.b64encode(wav_data).decode(),
                        })
                except Exception as tts_err:
                    log.warning("TTS audio synthesis error: %s", tts_err)

            except Exception as turn_err:
                log.exception("Voice turn failed: %s", turn_err)
                await send_json({"type": "error", "message": str(turn_err)[:200]})

    except WebSocketDisconnect:
        log.info("WebSocket voice client disconnected")
    except Exception as e:
        log.warning("WebSocket error: %s", e)
