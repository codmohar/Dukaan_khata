"""Database tools exposed to the LLM agent with pg_trgm fuzzy matching, honorific stripping,
anomaly detection, full settlements, adjustments, reminders, and guarded undo.

All functions accept an open AsyncSession and return JSON-serializable dictionaries.
"""
import re
import urllib.parse
import uuid
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any

from sqlalchemy import select, text
try:
    from sqlalchemy.ext.asyncio import AsyncSession
except Exception:
    AsyncSession = Any

from ..models import Customer, DailyReconciliation, HouseholdMember, Promise, Reminder, Shop, ShopRule, Transaction
from ..services import household as household_service
from ..services import memory as memory_service
from ..services import promises as promises_service
from ..services import reconciliation as reconciliation_service
from ..services import rules as rules_service
from ..services import timeline as timeline_service

# Common Indian relationship & honorific terms stripped before customer matching
HONORIFICS_PATTERN = re.compile(
    r"\b(anna|akka|bhaiya|bhayya|bhai|didi|sir|madam|maam|uncle|aunty|auntie|"
    r"ji|garu|gaaru|saab|sahab|avare|avaru|amma|appa|dada|tai|mausi|chacha|"
    r"kaka|mama|mami|mister|mr|mrs|ms|shri|smt)\b|"
    r"(?:जी|भाई|भैया|दीदी|अंकल|आंटी|सर|मैडम|साहब|अण्णा|ಅಣ್ಣ|ಅಕ್ಕ|ಅವರು|ಅವರೇ)",
    re.IGNORECASE,
)

DEVA_TO_LATIN = {
    'क': 'k', 'ख': 'kh', 'ग': 'g', 'घ': 'gh', 'ङ': 'ng',
    'च': 'ch', 'छ': 'chh', 'ज': 'j', 'झ': 'jh', 'ञ': 'ny',
    'ट': 't', 'ठ': 'th', 'ड': 'd', 'ढ': 'dh', 'ण': 'n',
    'त': 't', 'थ': 'th', 'द': 'd', 'ध': 'dh', 'न': 'n',
    'प': 'p', 'फ': 'ph', 'ब': 'b', 'भ': 'bh', 'म': 'm',
    'य': 'y', 'र': 'r', 'ल': 'l', 'व': 'v', 'श': 'sh',
    'ष': 'sh', 'स': 's', 'ह': 'h',
    'ा': 'a', 'ि': 'i', 'ी': 'ee', 'ु': 'u', 'ू': 'oo',
    'ृ': 'ri', 'े': 'e', 'ै': 'ai', 'ो': 'o', 'ौ': 'au',
    'ं': 'n', 'ँ': 'n', 'ः': 'h', '्': '',
    'अ': 'a', 'आ': 'aa', 'इ': 'i', 'ई': 'ee', 'उ': 'u',
    'ऊ': 'oo', 'ए': 'e', 'ऐ': 'ai', 'ओ': 'o', 'औ': 'au'
}

KAN_TO_LATIN = {
    'ಕ': 'k', 'ಖ': 'kh', 'ಗ': 'g', 'ಘ': 'gh', 'ಙ': 'ng',
    'ಚ': 'ch', 'ಛ': 'chh', 'ಜ': 'j', 'ಝ': 'jh', 'ಞ': 'ny',
    'ಟ': 't', 'ಠ': 'th', 'ಡ': 'd', 'ಢ': 'dh', 'ಣ': 'n',
    'ತ': 't', 'ಥ': 'th', 'ದ': 'd', 'ಧ': 'dh', 'ನ': 'n',
    'ಪ': 'p', 'ಫ': 'ph', 'ಬ': 'b', 'ಭ': 'bh', 'ಮ': 'm',
    'ಯ': 'y', 'ರ': 'r', 'ಲ': 'l', 'ವ': 'v', 'ಶ': 'sh',
    'ಷ': 'sh', 'ಸ': 's', 'ಹ': 'h', 'ಳ': 'l',
    'ಾ': 'a', 'ಿ': 'i', 'ೀ': 'ee', 'ು': 'u', 'ೂ': 'oo',
    'ೃ': 'ri', 'ೆ': 'e', 'ೇ': 'e', 'ೈ': 'ai', 'ೊ': 'o', 'ೋ': 'o', 'ೌ': 'au',
    'ಂ': 'n', 'ಃ': 'h', '್': '',
    'ಅ': 'a', 'ಆ': 'aa', 'ಇ': 'i', 'ಈ': 'ee', 'ಉ': 'u',
    'ಊ': 'oo', 'ಎ': 'e', 'ಏ': 'e', 'ಐ': 'ai', 'ಒ': 'o', 'ಓ': 'o', 'ಔ': 'au'
}

def transliterate_indic_to_latin(text: str) -> str:
    """Deterministic phonemic transliteration for Devanagari and Kannada scripts."""
    if not text:
        return ""
    deva_c = set('कखगघङचछजझञटठडढणतथदधनपफबभमयरलवशषसह')
    deva_m = set('ािीुूृेैोौंँः्')
    kan_c = set('ಕಖಗಘಙಚಛಜಝಞಟಠಡಢಣತಥದಧನಪಫಬಭಮಯರಲವಶಷಸಹಳ')
    kan_m = set('ಾಿೀುೂೃೆೇೈೊೋೌಂಃ್')

    res = []
    chars = list(text)
    for i, c in enumerate(chars):
        if c in DEVA_TO_LATIN:
            lat = DEVA_TO_LATIN[c]
            if c in deva_c:
                next_c = chars[i+1] if i+1 < len(chars) else None
                if next_c and next_c in deva_m:
                    res.append(lat)
                elif next_c and next_c in deva_c:
                    res.append(lat + 'a')
                else:
                    res.append(lat)
            else:
                res.append(lat)
        elif c in KAN_TO_LATIN:
            lat = KAN_TO_LATIN[c]
            if c in kan_c:
                next_c = chars[i+1] if i+1 < len(chars) else None
                if next_c and next_c in kan_m:
                    res.append(lat)
                elif next_c and next_c in kan_c:
                    res.append(lat + 'a')
                else:
                    res.append(lat)
            else:
                res.append(lat)
        else:
            res.append(c)
    return ''.join(res).strip()


def normalize_customer_query(raw: str) -> str:
    """Strip honorifics, punctuation, and extra spaces from a spoken customer query while preserving Indic matras."""
    cleaned = re.sub(r"[^\w\s\u0900-\u097F\u0C80-\u0CFF]", " ", raw or "")
    cleaned = HONORIFICS_PATTERN.sub(" ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned or (raw or "").strip()


def _parse_iso_date(val: str | None) -> date | None:
    if not val:
        return None
    try:
        return date.fromisoformat(str(val).strip()[:10])
    except ValueError:
        return None


async def search_customers(s: AsyncSession, shop_id: str, name: str) -> dict:
    """Fuzzy-search customers by name OR landmark after stripping Indian honorifics and cross-script transliteration."""
    raw_query = (name or "").strip()
    clean_name = normalize_customer_query(raw_query)
    latin_name = transliterate_indic_to_latin(clean_name)
    shop_uuid = uuid.UUID(shop_id)

    try:
        rows = (
            await s.execute(
                text(
                    """
                    select c.id, c.name, c.landmark, c.phone,
                           greatest(
                             similarity(c.name, :q),
                             word_similarity(:q, c.name),
                             similarity(c.name, :lat),
                             word_similarity(:lat, c.name),
                             coalesce(similarity(c.landmark, :q), 0),
                             coalesce(word_similarity(:q, c.landmark), 0),
                             coalesce(similarity(c.landmark, :lat), 0),
                             coalesce(word_similarity(:lat, c.landmark), 0)
                           ) as score,
                           coalesce(b.balance, 0) as balance
                    from customers c
                    left join customer_balances b on b.customer_id = c.id
                    where c.shop_id = :shop
                      and (
                        similarity(c.name, :q) > 0.20
                        or word_similarity(:q, c.name) > 0.35
                        or similarity(c.name, :lat) > 0.20
                        or word_similarity(:lat, c.name) > 0.35
                        or c.name ilike :like
                        or c.name ilike :lat_like
                        or coalesce(c.landmark, '') ilike :like
                        or coalesce(c.landmark, '') ilike :lat_like
                        or coalesce(word_similarity(:q, c.landmark), 0) > 0.45
                        or coalesce(word_similarity(:lat, c.landmark), 0) > 0.45
                      )
                    order by score desc limit 6
                    """
                ),
                {
                    "q": clean_name,
                    "lat": latin_name or clean_name,
                    "shop": str(shop_uuid),
                    "like": f"%{clean_name}%",
                    "lat_like": f"%{latin_name}%" if latin_name else f"%{clean_name}%",
                },
            )
        ).mappings().all()

        matches = [
            {
                "customer_id": str(r["id"]),
                "name": r["name"],
                "landmark": r["landmark"],
                "phone": r["phone"],
                "balance": float(r["balance"]),
                "score": round(float(r["score"]), 2),
            }
            for r in rows
        ]
        return {"query_normalized": clean_name, "matches": matches}

    except Exception:
        await s.rollback()
        query = (
            select(Customer)
            .where(
                Customer.shop_id == shop_uuid,
                (Customer.name.ilike(f"%{clean_name}%"))
                | (Customer.landmark.ilike(f"%{clean_name}%")),
            )
            .limit(6)
        )
        res = await s.execute(query)
        custs = res.scalars().all()

        matches = []
        for c in custs:
            bal_row = (
                await s.execute(
                    text("select balance from customer_balances where customer_id = :cid"),
                    {"cid": str(c.id)},
                )
            ).scalar() or 0.0
            matches.append(
                {
                    "customer_id": str(c.id),
                    "name": c.name,
                    "landmark": c.landmark,
                    "phone": c.phone,
                    "balance": float(bal_row),
                    "score": 0.8 if clean_name.lower() in c.name.lower() else 0.5,
                }
            )
        return {"query_normalized": clean_name, "matches": matches}


async def create_customer(
    s: AsyncSession,
    shop_id: str,
    name: str,
    phone: str | None = None,
    landmark: str | None = None,
) -> dict:
    """Add a new customer to the kirana shop's ledger (stripping trailing honorifics)."""
    clean_name = normalize_customer_query(name).title()
    if not clean_name:
        return {"error": "Customer name is required"}
    c = Customer(
        id=uuid.uuid4(),
        shop_id=uuid.UUID(shop_id),
        name=clean_name,
        phone=phone.strip() if phone else None,
        landmark=landmark.strip() if landmark else None,
    )
    s.add(c)
    await s.commit()
    return {
        "customer_id": str(c.id),
        "name": c.name,
        "phone": c.phone,
        "landmark": c.landmark,
        "created": True,
    }


async def create_draft(
    s: AsyncSession,
    shop_id: str,
    customer_id: str,
    type: str,
    amount: float,
    payment_mode: str | None = None,
    adjustment_reason: str | None = None,
    due_date: str | None = None,
    backdated_to: str | None = None,
    items: list[dict[str, Any]] | None = None,
    note: str | None = None,
    transcript: str | None = None,
    language: str | None = None,
    member_id: str | None = None,
    item_note: str | None = None,
) -> dict:
    """Create an unconfirmed transaction draft with 10x anomaly detection, household attribution, and rule warnings."""
    if type not in ("credit", "payment", "adjustment"):
        return {"error": "type must be 'credit', 'payment', or 'adjustment'"}

    if payment_mode and payment_mode.lower() not in ("cash", "upi", "credit", "other"):
        payment_mode = "other"
    elif payment_mode:
        payment_mode = payment_mode.lower()

    if adjustment_reason and adjustment_reason not in ("discount", "return", "write_off", "correction"):
        adjustment_reason = "correction"

    try:
        amt = Decimal(str(amount))
    except InvalidOperation:
        return {"error": "invalid amount format"}

    if amt <= Decimal("0") or amt > Decimal("10000000"):
        return {"error": "amount must be greater than 0 and less than 1 crore"}

    cust = await s.get(Customer, uuid.UUID(customer_id))
    if not cust or str(cust.shop_id) != shop_id:
        return {"error": "customer not found in this shop"}

    member_obj = None
    if member_id:
        try:
            mid = uuid.UUID(member_id)
            member_obj = await s.get(HouseholdMember, mid)
            if not member_obj or str(member_obj.customer_id) != str(cust.id) or str(member_obj.shop_id) != shop_id:
                return {"error": "Household member does not belong to this customer"}
        except ValueError:
            return {"error": "Invalid member_id format"}

    # Check current balance & historical average for anomaly safety (10x rule)
    bal_row = (
        await s.execute(
            text("select coalesce(outstanding_balance, 0) from customers where id = :c"),
            {"c": str(cust.id)},
        )
    ).scalar()
    current_balance = float(bal_row or 0.0)

    hist_row = (
        await s.execute(
            text(
                """
                select count(*) as cnt, coalesce(avg(amount), 0) as avg_amt
                from transactions
                where customer_id = :c and status = 'confirmed'
                """
            ),
            {"c": str(cust.id)},
        )
    ).first()
    hist_count = int(hist_row[0]) if hist_row else 0
    hist_avg = float(hist_row[1]) if hist_row else 0.0

    anomaly_warning = False
    warning_message = None
    if hist_count >= 2 and hist_avg > 0 and float(amt) >= max(500.0, hist_avg * 10.0):
        anomaly_warning = True
        warning_message = (
            f"Unusually high amount: ₹{float(amt):,.0f} is more than 10x this customer's "
            f"usual entry of ₹{hist_avg:,.0f}. Ask an explicit 'Are you sure?' double-check."
        )
    elif float(amt) >= 25000.0:
        anomaly_warning = True
        warning_message = (
            f"Large amount alert: ₹{float(amt):,.0f}. Read every digit aloud and ask 'Are you sure?'."
        )

    # Evaluate shop rules deterministically for CREDIT drafts
    rule_warnings = []
    if type == "credit":
        rule_warnings = await rules_service.evaluate_shop_rules(
            s=s,
            shop_id=shop_id,
            customer_id=customer_id,
            member_id=member_id,
            amount=amt,
        )

    parsed_due = _parse_iso_date(due_date)
    parsed_backdate = _parse_iso_date(backdated_to)

    t = Transaction(
        id=uuid.uuid4(),
        shop_id=uuid.UUID(shop_id),
        customer_id=cust.id,
        member_id=member_obj.id if member_obj else None,
        item_note=item_note or note,
        rule_warnings=rule_warnings,
        rule_override=False,
        type=type,
        amount=amt,
        payment_mode=payment_mode,
        adjustment_reason=adjustment_reason,
        due_date=parsed_due,
        backdated_to=parsed_backdate,
        items=items,
        note=note,
        raw_transcript=transcript,
        language=language,
        status="draft",
    )
    s.add(t)
    await s.commit()

    projected = current_balance + float(amt) if type == "credit" else current_balance - float(amt)

    return {
        "draft_id": str(t.id),
        "customer": cust.name,
        "customer_id": str(cust.id),
        "customer_phone": cust.phone,
        "member_id": str(member_obj.id) if member_obj else None,
        "member_name": member_obj.member_name if member_obj else None,
        "relationship": member_obj.relationship_label if member_obj else None,
        "item_note": item_note or note,
        "type": type,
        "amount": float(amt),
        "payment_mode": payment_mode,
        "adjustment_reason": adjustment_reason,
        "due_date": parsed_due.isoformat() if parsed_due else None,
        "backdated_to": parsed_backdate.isoformat() if parsed_backdate else None,
        "items": items,
        "note": note,
        "current_balance": round(current_balance, 2),
        "projected_balance": round(projected, 2),
        "is_advance": projected < 0,
        "anomaly_warning": anomaly_warning,
        "warning_message": warning_message,
        "rule_warnings": rule_warnings,
        "requires_override": len(rule_warnings) > 0,
    }


async def settle_balance(
    s: AsyncSession,
    shop_id: str,
    customer_id: str,
    payment_mode: str | None = None,
    is_write_off: bool = False,
    note: str | None = None,
    transcript: str | None = None,
    language: str | None = None,
) -> dict:
    """Create a confirmation-required draft to clear a customer's entire current balance to zero."""
    bal_info = await get_balance(s, shop_id, customer_id)
    if "error" in bal_info:
        return bal_info

    bal = float(bal_info["balance"])
    if bal <= 0:
        return {
            "already_settled": True,
            "customer": bal_info["customer"],
            "balance": bal,
            "message": "Customer has no pending balance to settle.",
        }

    tx_type = "adjustment" if is_write_off else "payment"
    adj_reason = "write_off" if is_write_off else None
    default_note = "Bad-debt write-off (owner confirmed)" if is_write_off else "Full settlement (hisaab clear)"

    return await create_draft(
        s=s,
        shop_id=shop_id,
        customer_id=customer_id,
        type=tx_type,
        amount=bal,
        payment_mode=None if is_write_off else payment_mode,
        adjustment_reason=adj_reason,
        note=note or default_note,
        transcript=transcript,
        language=language,
    )


async def confirm_draft(
    s: AsyncSession,
    shop_id: str,
    draft_id: str,
    transcript_snippet: str | None = None,
) -> dict:
    """Commit a draft to confirmed status, atomically update customer balance, and auto-fulfil promises."""
    t = await s.get(Transaction, uuid.UUID(draft_id))
    if not t or str(t.shop_id) != shop_id:
        return {"error": "draft not found"}
    if t.status != "draft":
        return {"error": f"draft is already {t.status}"}

    # Hard Invariant: Rule warnings must be explicitly overridden before confirmation
    if t.rule_warnings and not t.rule_override:
        return {
            "error": "Unresolved Dukaan Rule warnings. Override or change amount.",
            "rule_warnings": t.rule_warnings,
            "draft_id": draft_id,
        }

    # Lock customer row atomically (SELECT ... FOR UPDATE)
    await s.execute(
        text("SELECT id FROM customers WHERE id = :cid AND shop_id = :sid FOR UPDATE"),
        {"cid": t.customer_id, "sid": t.shop_id},
    )
    cust = await s.get(Customer, t.customer_id)
    if not cust:
        return {"error": "Customer not found"}

    # Atomic balance update on customer row
    delta = t.amount if t.type == "credit" else -t.amount
    current_bal = cust.outstanding_balance or Decimal("0.00")
    new_bal = current_bal + delta
    cust.outstanding_balance = new_bal

    t.status = "confirmed"
    t.confirmed_at = datetime.now(timezone.utc)
    if transcript_snippet:
        t.transcript_snippet = transcript_snippet.strip()
    elif t.raw_transcript:
        t.transcript_snippet = t.raw_transcript

    # Auto-fulfil matching PAYMENT_PROMISE atomically
    promise_fulfil_res = None
    if t.type == "payment":
        promise_fulfil_res = await promises_service.auto_fulfil_promise(
            s=s,
            shop_id=shop_id,
            customer_id=str(t.customer_id),
            amount=t.amount,
            tx_id=t.id,
        )

    await s.commit()

    cname = cust.name if cust else "Customer"

    return {
        "confirmed": True,
        "draft_id": draft_id,
        "customer": cname,
        "customer_id": str(t.customer_id),
        "member_id": str(t.member_id) if t.member_id else None,
        "amount": float(t.amount or 0),
        "type": t.type,
        "new_balance": float(new_bal),
        "promise_fulfilled": promise_fulfil_res.get("fulfilled") if promise_fulfil_res else False,
        "fulfilled_promise_id": promise_fulfil_res.get("promise_id") if promise_fulfil_res else None,
    }


async def cancel_draft(s: AsyncSession, shop_id: str, draft_id: str) -> dict:
    """Discard an unconfirmed draft."""
    t = await s.get(Transaction, uuid.UUID(draft_id))
    if not t or str(t.shop_id) != shop_id:
        return {"error": "draft not found"}
    if t.status != "draft":
        return {"error": f"draft is already {t.status}"}

    t.status = "cancelled"
    await s.commit()
    return {"cancelled": True, "draft_id": draft_id}


async def undo_last_transaction(
    s: AsyncSession,
    shop_id: str,
    customer_id: str | None = None,
    confirmed_undo: bool = False,
) -> dict:
    """Undo/delete the most recent entry (draft or confirmed). Confirmed entries ALWAYS require confirmation."""
    cid_filter = "and t.customer_id = :cid" if customer_id else ""
    params: dict[str, Any] = {"shop": shop_id}
    if customer_id:
        params["cid"] = customer_id

    row = (
        await s.execute(
            text(
                f"""
                select t.id, t.customer_id, c.name as customer_name, t.type, t.amount, t.status, t.note, t.created_at
                from transactions t
                join customers c on c.id = t.customer_id
                where t.shop_id = :shop and t.status in ('draft', 'confirmed') {cid_filter}
                order by t.created_at desc
                limit 1
                """
            ),
            params,
        )
    ).mappings().first()

    if not row:
        return {"error": "No recent active transaction found to undo."}

    tid = str(row["id"])
    # Drafts can be cancelled immediately; confirmed transactions require explicit owner confirmation
    if row["status"] == "confirmed" and not confirmed_undo:
        return {
            "requires_confirmation": True,
            "transaction_id": tid,
            "customer": row["customer_name"],
            "customer_id": str(row["customer_id"]),
            "type": row["type"],
            "amount": float(row["amount"]),
            "note": row["note"],
            "message": "Read back this confirmed entry and ask the shopkeeper to confirm deletion before calling undo_last_transaction with confirmed_undo=true.",
        }

    t = await s.get(Transaction, uuid.UUID(tid))
    if t:
        t.status = "cancelled"
        await s.commit()

    bal = (
        await s.execute(
            text("select coalesce(balance, 0) from customer_balances where customer_id = :c"),
            {"c": str(row["customer_id"])},
        )
    ).scalar() or Decimal("0.00")

    return {
        "undone": True,
        "transaction_id": tid,
        "customer": row["customer_name"],
        "type": row["type"],
        "amount": float(row["amount"]),
        "new_balance": float(bal),
    }


async def get_balance(s: AsyncSession, shop_id: str, customer_id: str) -> dict:
    """Query a customer's current outstanding balance (negative means customer advance/deposit)."""
    row = (
        await s.execute(
            text(
                """
                select c.name, coalesce(b.balance, 0) as balance, c.phone, c.landmark
                from customers c
                left join customer_balances b on b.customer_id = c.id
                where c.id = :c and c.shop_id = :shop
                """
            ),
            {"c": customer_id, "shop": shop_id},
        )
    ).first()

    if not row:
        return {"error": "customer not found"}

    bal = float(row[1])
    return {
        "customer": row[0],
        "balance": bal,
        "balance_status": "advance_by_customer" if bal < 0 else ("settled" if bal == 0 else "customer_owes"),
        "phone": row[2],
        "landmark": row[3],
    }


async def prepare_reminder(s: AsyncSession, shop_id: str, customer_id: str) -> dict:
    """Prepare a polite WhatsApp payment reminder link for a customer with pending dues."""
    bal_info = await get_balance(s, shop_id, customer_id)
    if "error" in bal_info:
        return bal_info

    bal = float(bal_info["balance"])
    if bal <= 0:
        return {
            "customer": bal_info["customer"],
            "balance": bal,
            "has_due": False,
            "message": "No pending dues for this customer.",
        }

    shop = await s.get(Shop, uuid.UUID(shop_id))
    shop_name = shop.name if shop else "Kirana Store"
    digits = re.sub(r"\D", "", bal_info.get("phone") or "")
    if len(digits) == 10:
        digits = "91" + digits

    reminder_text = (
        f"Namaste {bal_info['customer']} ji, polite reminder from {shop_name}: "
        f"your pending khata balance is ₹{bal:,.0f}. Thank you!"
    )
    wa_url = (
        f"https://wa.me/{digits}?text={urllib.parse.quote(reminder_text)}"
        if digits
        else f"https://wa.me/?text={urllib.parse.quote(reminder_text)}"
    )

    # Persist reminder record to reminders table
    try:
        rem = Reminder(
            shop_id=uuid.UUID(shop_id),
            customer_id=uuid.UUID(customer_id),
            amount=Decimal(str(bal)),
            message=reminder_text,
            status="pending",
        )
        s.add(rem)
        await s.commit()
    except Exception as e:
        log.warning("Could not persist reminder record: %s", e)

    return {
        "has_due": True,
        "customer": bal_info["customer"],
        "customer_id": customer_id,
        "phone": bal_info.get("phone"),
        "balance": bal,
        "reminder_text": reminder_text,
        "whatsapp_url": wa_url,
    }


async def get_shop_summary(s: AsyncSession, shop_id: str) -> dict:
    """Query shop overview: total dues, today's credit/payments/UPI/cash, top debtors, and current date."""
    try:
        sid = uuid.UUID(shop_id)
        tot_row = (
            await s.execute(
                text(
                    """
                    select
                      coalesce(sum(greatest(b.balance, 0)), 0) as total_due,
                      coalesce(sum(abs(least(b.balance, 0))), 0) as total_advances,
                      count(distinct c.id) as cust_cnt
                    from customers c
                    left join customer_balances b on b.customer_id = c.id
                    where c.shop_id = :shop
                    """
                ),
                {"shop": str(sid)},
            )
        ).first()
        total_out = float(tot_row[0]) if tot_row else 0.0
        total_adv = float(tot_row[1]) if tot_row else 0.0
        cust_count = int(tot_row[2]) if tot_row else 0

        today_date = datetime.now(timezone.utc).date()
        today_rows = (
            await s.execute(
                text(
                    """
                    select type, coalesce(payment_mode, 'unspecified') as mode, coalesce(sum(amount), 0) as total
                    from transactions
                    where shop_id = :shop and status = 'confirmed'
                      and coalesce(backdated_to, created_at::date) = :today
                    group by type, coalesce(payment_mode, 'unspecified')
                    """
                ),
                {"shop": str(sid), "today": today_date},
            )
        ).mappings().all()

        credit_today = 0.0
        payment_today = 0.0
        adjustments_today = 0.0
        upi_today = 0.0
        cash_today = 0.0
        for r in today_rows:
            val = float(r["total"])
            if r["type"] == "credit":
                credit_today += val
            elif r["type"] == "payment":
                payment_today += val
                if r["mode"] == "upi":
                    upi_today += val
                elif r["mode"] == "cash":
                    cash_today += val
            elif r["type"] == "adjustment":
                adjustments_today += val

        top_rows = (
            await s.execute(
                text(
                    """
                    select c.name, c.landmark, b.balance
                    from customers c
                    join customer_balances b on b.customer_id = c.id
                    where c.shop_id = :shop and b.balance > 0
                    order by b.balance desc
                    limit 5
                    """
                ),
                {"shop": str(sid)},
            )
        ).mappings().all()

        return {
            "today_date": today_date.isoformat(),
            "total_outstanding": round(total_out, 2),
            "total_advances": round(total_adv, 2),
            "credit_today": round(credit_today, 2),
            "payments_today": round(payment_today, 2),
            "upi_today": round(upi_today, 2),
            "cash_today": round(cash_today, 2),
            "adjustments_today": round(adjustments_today, 2),
            "customer_count": cust_count,
            "top_debtors": [
                {"name": r["name"], "landmark": r["landmark"], "balance": float(r["balance"])}
                for r in top_rows
            ],
        }
    except Exception as e:
        return {"error": str(e)}


async def update_customer(
    s: AsyncSession,
    shop_id: str,
    customer_id: str,
    phone: str | None = None,
    landmark: str | None = None,
    name: str | None = None,
) -> dict:
    """Update existing customer details like phone number, landmark, or name."""
    try:
        cid = uuid.UUID(customer_id)
        cust = await s.get(Customer, cid)
        if not cust or str(cust.shop_id) != shop_id:
            return {"error": "customer not found in this shop"}
        if phone:
            cust.phone = phone.strip()
        if landmark:
            cust.landmark = landmark.strip()
        if name:
            cust.name = normalize_customer_query(name).title()
        await s.commit()
        return {
            "updated": True,
            "customer_id": str(cust.id),
            "name": cust.name,
            "phone": cust.phone,
            "landmark": cust.landmark,
        }
    except Exception as e:
        return {"error": str(e)}


# -------------------- ADVANCED FEATURES WRAPPERS --------------------

async def resolve_household_member(
    s: AsyncSession,
    shop_id: str,
    customer_name: str,
    member_name: str | None = None,
    relationship: str | None = None,
) -> dict:
    """Resolve customer and optional household member using fuzzy matching."""
    try:
        return await household_service.resolve_household_member(
            s=s,
            shop_id=shop_id,
            customer_name=customer_name,
            member_name=member_name,
            relationship=relationship,
        )
    except Exception as e:
        return {"error": str(e)}


async def add_household_member(
    s: AsyncSession,
    shop_id: str,
    customer_id: str,
    member_name: str,
    relationship: str | None = None,
    is_authorized: bool = True,
) -> dict:
    """Add a new member to an existing customer household."""
    try:
        return await household_service.add_household_member(
            s=s,
            shop_id=shop_id,
            customer_id=customer_id,
            member_name=member_name,
            relationship=relationship,
            is_authorized=is_authorized,
        )
    except Exception as e:
        return {"error": str(e)}


async def save_shop_rule(
    s: AsyncSession,
    shop_id: str,
    rule_category: str,
    rule_text: str,
    structured_condition: dict,
) -> dict:
    """Save a new shopkeeper policy rule."""
    try:
        return await rules_service.save_shop_rule(
            s=s,
            shop_id=shop_id,
            rule_category=rule_category,
            rule_text=rule_text,
            structured_condition=structured_condition,
        )
    except Exception as e:
        return {"error": str(e)}


async def override_rule_warnings(
    s: AsyncSession,
    shop_id: str,
    draft_id: str,
) -> dict:
    """Explicitly override policy rule warnings on a pending draft."""
    try:
        return await rules_service.override_rule_warnings(s=s, shop_id=shop_id, draft_id=draft_id)
    except Exception as e:
        return {"error": str(e)}


async def create_promise(
    s: AsyncSession,
    shop_id: str,
    entity_name: str,
    promise_type: str,
    description: str,
    expected_date: str,
    promised_amount: float | None = None,
    customer_id: str | None = None,
    member_id: str | None = None,
    transcript: str | None = None,
) -> dict:
    """Record a commitment (payment promise, goods reservation, or supplier delivery) without altering ledger."""
    try:
        exp_d = _parse_iso_date(expected_date)
        if not exp_d:
            return {"error": "Invalid expected_date, must be YYYY-MM-DD"}
        return await promises_service.create_promise(
            s=s,
            shop_id=shop_id,
            entity_name=entity_name,
            promise_type=promise_type,
            description=description,
            expected_date=exp_d,
            promised_amount=Decimal(str(promised_amount)) if promised_amount else None,
            customer_id=customer_id,
            member_id=member_id,
            transcript=transcript,
        )
    except Exception as e:
        return {"error": str(e)}


async def list_promises(
    s: AsyncSession,
    shop_id: str,
    status: str | None = None,
    on_date: str | None = None,
    customer_name: str | None = None,
    customer_id: str | None = None,
) -> list[dict]:
    """Query scheduled promises and commitments."""
    try:
        parsed_dt = _parse_iso_date(on_date)
        return await promises_service.list_promises(
            s=s,
            shop_id=shop_id,
            status=status,
            on_date=parsed_dt,
            customer_name=customer_name,
            customer_id=customer_id,
        )
    except Exception as e:
        return [{"error": str(e)}]


async def update_promise(
    s: AsyncSession,
    shop_id: str,
    promise_id: str,
    action: str,
    new_date: str | None = None,
) -> dict:
    """Reschedule, cancel, or manually mark a promise as fulfilled."""
    try:
        parsed_d = _parse_iso_date(new_date)
        return await promises_service.update_promise(
            s=s,
            shop_id=shop_id,
            promise_id=promise_id,
            action=action,
            new_date=parsed_d,
        )
    except Exception as e:
        return {"error": str(e)}


async def search_shop_memory(
    s: AsyncSession,
    shop_id: str,
    entity_name: str | None = None,
    keyword: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    scope: list[str] | None = None,
    limit: int = 10,
) -> dict:
    """Recall information across promises, transactions, and custom rules."""
    try:
        return await memory_service.search_shop_memory(
            s=s,
            shop_id=shop_id,
            entity_name=entity_name,
            keyword=keyword,
            date_from=_parse_iso_date(date_from),
            date_to=_parse_iso_date(date_to),
            scope=scope,
            limit=limit,
        )
    except Exception as e:
        return {"error": str(e)}


async def get_dispute_timeline(
    s: AsyncSession,
    shop_id: str,
    customer_id: str,
    limit: int = 5,
    member_id: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
) -> dict:
    """Audit timeline with running balance and speech evidence."""
    try:
        parsed_from = datetime.fromisoformat(date_from) if date_from else None
        parsed_to = datetime.fromisoformat(date_to) if date_to else None
        return await timeline_service.get_dispute_timeline(
            s=s,
            shop_id=shop_id,
            customer_id=customer_id,
            limit=limit,
            member_id=member_id,
            date_from=parsed_from,
            date_to=parsed_to,
        )
    except Exception as e:
        return {"error": str(e)}


async def start_reconciliation(
    s: AsyncSession,
    shop_id: str,
    on_date: str | None = None,
) -> dict:
    """Get recorded cash and UPI totals for evening khata audit."""
    try:
        return await reconciliation_service.start_reconciliation(
            s=s,
            shop_id=shop_id,
            on_date=_parse_iso_date(on_date),
        )
    except Exception as e:
        return {"error": str(e)}


async def run_daily_reconciliation(
    s: AsyncSession,
    shop_id: str,
    actual_cash: float,
    actual_upi: float,
    on_date: str | None = None,
    notes: str | None = None,
) -> dict:
    """Compare physical cash/UPI against recorded totals and flag discrepancies."""
    try:
        return await reconciliation_service.run_daily_reconciliation(
            s=s,
            shop_id=shop_id,
            actual_cash=actual_cash,
            actual_upi=actual_upi,
            on_date=_parse_iso_date(on_date),
            notes=notes,
        )
    except Exception as e:
        return {"error": str(e)}


# Gemini function tool declarations (context-based, zero hardcoded default names)
DECLARATIONS = [
    {
        "name": "search_customers",
        "description": (
            "Fuzzy-search customers in this shop by name or landmark (in Latin script). "
            "Automatically strips Indian honorifics (anna, akka, bhaiya, ji, sir, uncle). "
            "Always call this BEFORE creating a customer or drafting any transaction."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "Customer name or landmark/nickname transliterated to Latin script",
                }
            },
            "required": ["name"],
        },
    },
    {
        "name": "create_customer",
        "description": "Register a brand-new customer in the ledger ONLY when search_customers returned zero matches.",
        "parameters": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Customer name in Latin script (without honorifics)"},
                "phone": {"type": "string", "description": "Optional phone number"},
                "landmark": {"type": "string", "description": "Optional identifying landmark or shop label"},
            },
            "required": ["name"],
        },
    },
    {
        "name": "update_customer",
        "description": "Update an existing customer's phone number, landmark, or name.",
        "parameters": {
            "type": "object",
            "properties": {
                "customer_id": {"type": "string", "description": "Customer UUID"},
                "phone": {"type": "string", "description": "New phone number"},
                "landmark": {"type": "string", "description": "New landmark or nickname"},
                "name": {"type": "string", "description": "Corrected customer name"},
            },
            "required": ["customer_id"],
        },
    },
    {
        "name": "create_draft",
        "description": (
            "Create an UNCONFIRMED transaction draft. Supports credit (udhar), payment (jama/advance/partial), "
            "and adjustment (return/discount/write_off/correction). Always read back exact digits and ask confirmation."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "customer_id": {"type": "string", "description": "Customer UUID"},
                "type": {
                    "type": "string",
                    "enum": ["credit", "payment", "adjustment"],
                    "description": "'credit' = udhar/baaki; 'payment' = jama/paid/advance; 'adjustment' = discount/return/write_off",
                },
                "amount": {"type": "number", "description": "Exact numeric amount in Indian Rupees (digits)"},
                "payment_mode": {
                    "type": "string",
                    "enum": ["cash", "upi", "other"],
                    "description": "Payment mode when mentioned (PhonePe/GPay/Paytm -> 'upi', cash -> 'cash')",
                },
                "adjustment_reason": {
                    "type": "string",
                    "enum": ["discount", "return", "write_off", "correction"],
                    "description": "Reason when type='adjustment'",
                },
                "due_date": {
                    "type": "string",
                    "description": "Optional promised payment date in YYYY-MM-DD (e.g. tomorrow or Saturday)",
                },
                "backdated_to": {
                    "type": "string",
                    "description": "Optional past date in YYYY-MM-DD for backdated entries (e.g. yesterday)",
                },
                "items": {
                    "type": "array",
                    "description": "Optional itemized bill list when goods/quantities are mentioned",
                    "items": {
                        "type": "object",
                        "properties": {
                            "name": {"type": "string"},
                            "qty": {"type": "string"},
                            "amount": {"type": "number"},
                        },
                    },
                },
                "note": {"type": "string", "description": "Optional brief note or context (e.g. proxy, items, reason)"},
                "member_id": {"type": "string", "description": "Optional UUID of family member who collected or paid"},
                "item_note": {"type": "string", "description": "Optional description of goods taken on credit (e.g. '2 bags rice', 'sugar 5kg')"},
            },
            "required": ["customer_id", "type", "amount"],
        },
    },
    {
        "name": "settle_balance",
        "description": (
            "Draft a full settlement ('sab clear', 'ellaa clear maadi', 'hisaab chukta') or bad-debt write-off "
            "('hisaab band karo') equal to the customer's exact current balance. Always requires confirmation."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "customer_id": {"type": "string", "description": "Customer UUID"},
                "payment_mode": {"type": "string", "enum": ["cash", "upi", "other"]},
                "is_write_off": {
                    "type": "boolean",
                    "description": "True ONLY if owner explicitly asks to write off bad debt / close unpaid account",
                },
                "note": {"type": "string"},
            },
            "required": ["customer_id"],
        },
    },
    {
        "name": "confirm_draft",
        "description": "Commit a pending draft AFTER the shopkeeper explicitly confirms in a subsequent turn.",
        "parameters": {
            "type": "object",
            "properties": {
                "draft_id": {"type": "string", "description": "UUID of the pending draft"},
            },
            "required": ["draft_id"],
        },
    },
    {
        "name": "cancel_draft",
        "description": "Discard a pending draft when the shopkeeper cancels, says no, or gives a correction.",
        "parameters": {
            "type": "object",
            "properties": {
                "draft_id": {"type": "string", "description": "UUID of the pending draft"},
            },
            "required": ["draft_id"],
        },
    },
    {
        "name": "undo_last_transaction",
        "description": (
            "Undo/delete the last entry (for a specific customer or shop-wide). "
            "First call with confirmed_undo=false to inspect; ONLY call with confirmed_undo=true after owner confirms."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "customer_id": {"type": "string", "description": "Optional customer UUID if specified"},
                "confirmed_undo": {
                    "type": "boolean",
                    "description": "False to inspect & ask confirmation; True ONLY after explicit owner confirmation",
                },
            },
        },
    },
    {
        "name": "get_balance",
        "description": "Query a customer's current outstanding balance (or advance credit). No confirmation needed.",
        "parameters": {
            "type": "object",
            "properties": {
                "customer_id": {"type": "string", "description": "Customer UUID"},
            },
            "required": ["customer_id"],
        },
    },
    {
        "name": "prepare_reminder",
        "description": "Generate a polite WhatsApp payment reminder for a customer who owes money.",
        "parameters": {
            "type": "object",
            "properties": {
                "customer_id": {"type": "string", "description": "Customer UUID"},
            },
            "required": ["customer_id"],
        },
    },
    {
        "name": "get_shop_summary",
        "description": (
            "Query shop overview: total dues, advances, today's udhar, today's cash & UPI collections, "
            "top debtors ('who owes the most?'), and today's ISO date. No confirmation needed."
        ),
        "parameters": {
            "type": "object",
            "properties": {},
        },
    },
    {
        "name": "resolve_household_member",
        "description": (
            "Disambiguate and resolve an account holder (customer) and optional family member (e.g. Ramesh's son Arjun). "
            "Returns status: 'resolved', 'ambiguous', 'member_not_found', or 'customer_not_found'."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "customer_name": {"type": "string", "description": "Primary account holder name in Latin script"},
                "member_name": {"type": "string", "description": "Optional family member name in Latin script"},
                "relationship": {"type": "string", "description": "Optional relationship label (son, daughter, wife, brother, etc.)"},
            },
            "required": ["customer_name"],
        },
    },
    {
        "name": "add_household_member",
        "description": "Register a new family member under an existing customer account.",
        "parameters": {
            "type": "object",
            "properties": {
                "customer_id": {"type": "string", "description": "Customer UUID"},
                "member_name": {"type": "string", "description": "Member name in Latin script"},
                "relationship": {"type": "string", "description": "Relationship label (son, daughter, wife, brother, father, etc.)"},
                "is_authorized": {"type": "boolean", "description": "Whether member is allowed to take credit (default true)"},
            },
            "required": ["customer_id", "member_name"],
        },
    },
    {
        "name": "save_shop_rule",
        "description": (
            "Save a shopkeeper credit policy rule (e.g. 'no credit above 1000 for new customers', 'no credit after 8 PM'). "
            "Categories: NEW_CUSTOMER_CAP, BALANCE_CAP, TIME_CUTOFF, MEMBER_AUTH, CUSTOM_NOTE."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "rule_category": {
                    "type": "string",
                    "enum": ["NEW_CUSTOMER_CAP", "BALANCE_CAP", "TIME_CUTOFF", "MEMBER_AUTH", "CUSTOM_NOTE"],
                },
                "rule_text": {"type": "string", "description": "Natural language rule description"},
                "structured_condition": {
                    "type": "object",
                    "description": "JSON object with condition fields (e.g. max_amount, max_balance, after, etc.)",
                },
            },
            "required": ["rule_category", "rule_text", "structured_condition"],
        },
    },
    {
        "name": "override_rule_warnings",
        "description": "Explicitly override policy rule warnings on an unconfirmed draft when the shopkeeper says 'continue anyway'.",
        "parameters": {
            "type": "object",
            "properties": {
                "draft_id": {"type": "string", "description": "UUID of the unconfirmed draft"},
            },
            "required": ["draft_id"],
        },
    },
    {
        "name": "create_promise",
        "description": (
            "Record a future commitment (PAYMENT_PROMISE: 'will pay Friday', GOODS_RESERVATION: 'keep rice tomorrow', "
            "or SUPPLIER_DELIVERY: 'sugar delivery Monday'). NEVER creates a ledger entry or alters balance."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "entity_name": {"type": "string", "description": "Customer or supplier name"},
                "promise_type": {
                    "type": "string",
                    "enum": ["PAYMENT_PROMISE", "GOODS_RESERVATION", "SUPPLIER_DELIVERY"],
                },
                "description": {"type": "string", "description": "Details of the commitment or items reserved"},
                "expected_date": {"type": "string", "description": "Target date in YYYY-MM-DD"},
                "promised_amount": {"type": "number", "description": "Amount promised in Rupees (required for PAYMENT_PROMISE)"},
                "customer_id": {"type": "string", "description": "Optional customer UUID"},
                "member_id": {"type": "string", "description": "Optional member UUID"},
            },
            "required": ["entity_name", "promise_type", "description", "expected_date"],
        },
    },
    {
        "name": "list_promises",
        "description": "Query scheduled commitments, payments due, and supplier deliveries.",
        "parameters": {
            "type": "object",
            "properties": {
                "status": {"type": "string", "enum": ["PENDING", "FULFILLED", "OVERDUE", "CANCELLED"]},
                "on_date": {"type": "string", "description": "Optional target date in YYYY-MM-DD"},
                "customer_name": {"type": "string", "description": "Optional customer name to filter"},
                "customer_id": {"type": "string", "description": "Optional customer UUID"},
            },
        },
    },
    {
        "name": "update_promise",
        "description": "Reschedule, cancel, or manually mark a commitment as fulfilled.",
        "parameters": {
            "type": "object",
            "properties": {
                "promise_id": {"type": "string", "description": "Promise UUID"},
                "action": {"type": "string", "enum": ["FULFIL_MANUAL", "CANCEL", "RESCHEDULE"]},
                "new_date": {"type": "string", "description": "Required if action is RESCHEDULE (YYYY-MM-DD)"},
            },
            "required": ["promise_id", "action"],
        },
    },
    {
        "name": "search_shop_memory",
        "description": (
            "Search shop operational memory across promises, transactions, and custom rules. "
            "Use for questions like 'Who asked to keep rice?' or 'What did Ramesh promise?'."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "entity_name": {"type": "string", "description": "Optional customer or supplier name"},
                "keyword": {"type": "string", "description": "Search keyword or item name (e.g. 'rice', 'sugar')"},
                "date_from": {"type": "string", "description": "Optional start date YYYY-MM-DD"},
                "date_to": {"type": "string", "description": "Optional end date YYYY-MM-DD"},
                "scope": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Subset of ['promises', 'transactions', 'rules']",
                },
            },
        },
    },
    {
        "name": "get_dispute_timeline",
        "description": "Audit running ledger balance timeline and transcript evidence for a customer or household member.",
        "parameters": {
            "type": "object",
            "properties": {
                "customer_id": {"type": "string", "description": "Customer UUID"},
                "limit": {"type": "number", "description": "Number of recent transactions (default 5)"},
                "member_id": {"type": "string", "description": "Optional member UUID to filter"},
            },
            "required": ["customer_id"],
        },
    },
    {
        "name": "start_reconciliation",
        "description": "Begin evening khata reconciliation to check recorded cash and UPI collections for today.",
        "parameters": {
            "type": "object",
            "properties": {
                "on_date": {"type": "string", "description": "Optional audit date in YYYY-MM-DD (defaults to today)"},
            },
        },
    },
    {
        "name": "run_daily_reconciliation",
        "description": "Submit physical cash and UPI counts to compare with recorded totals and generate discrepancy diagnostics.",
        "parameters": {
            "type": "object",
            "properties": {
                "actual_cash": {"type": "number", "description": "Physical cash collected in Rupees"},
                "actual_upi": {"type": "number", "description": "Actual UPI received in Rupees"},
                "notes": {"type": "string", "description": "Optional notes or comments"},
            },
            "required": ["actual_cash", "actual_upi"],
        },
    },
]
