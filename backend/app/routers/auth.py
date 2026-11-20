import logging
import uuid
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import settings
from ..db import get_session
from ..models import Customer, Shop
from ..schemas import AuthResponse, ShopLoginIn, ShopOut, ShopRegisterIn

log = logging.getLogger("dukaan.auth")
router = APIRouter(prefix="/auth", tags=["auth"])


def safe_uuid_val(val: Any) -> uuid.UUID:
    if isinstance(val, uuid.UUID):
        return val
    if val:
        s_val = str(val).strip()
        if "?" in s_val:
            s_val = s_val.split("?")[0].strip()
        if "&" in s_val:
            s_val = s_val.split("&")[0].strip()
        if s_val and s_val.lower() not in ("undefined", "null", "none"):
            try:
                return uuid.UUID(s_val)
            except (ValueError, TypeError):
                pass
    def_id = settings.default_shop_id or "00000000-0000-0000-0000-000000000001"
    try:
        return uuid.UUID(def_id)
    except Exception:
        return uuid.UUID("00000000-0000-0000-0000-000000000001")


async def resolve_shop_id(
    shop_id: str | None = None,
    x_shop_id: str | None = Header(None, alias="X-Shop-Id"),
    s: AsyncSession = Depends(get_session),
) -> str:
    """Helper to resolve shop ID safely from query or X-Shop-Id header."""
    candidate = shop_id or x_shop_id
    if candidate:
        s_cand = str(candidate).strip()
        if s_cand and s_cand.lower() not in ("undefined", "null", "none"):
            try:
                return str(uuid.UUID(s_cand))
            except (ValueError, TypeError):
                pass

    if settings.default_shop_id and settings.default_shop_id.strip():
        try:
            return str(uuid.UUID(settings.default_shop_id.strip()))
        except (ValueError, TypeError):
            pass

    try:
        row = (await s.execute(text("SELECT id FROM shops ORDER BY created_at ASC LIMIT 1"))).scalar()
        if row:
            return str(uuid.UUID(str(row)))
    except Exception:
        pass

    return "00000000-0000-0000-0000-000000000001"


@router.get("/shops", response_model=list[ShopOut])
async def list_available_shops(s: AsyncSession = Depends(get_session)):
    """List available virtual dukaans for 1-tap fast selection."""
    rows = (
        await s.execute(
            text(
                """
                SELECT id, name, owner_name, phone, language, pin
                FROM shops
                WHERE name NOT ILIKE 'Shop A%' AND name NOT ILIKE 'Shop B%' AND name NOT ILIKE 'Test%'
                ORDER BY CASE WHEN id = '00000000-0000-0000-0000-000000000001'::uuid THEN 0 ELSE 1 END,
                         created_at DESC
                """
            )
        )
    ).mappings().all()

    # Deduplicate display if duplicate test names exist
    seen_ids = set()
    result = []
    for r in rows:
        sid = str(r["id"])
        if sid not in seen_ids:
            seen_ids.add(sid)
            result.append(dict(r))
    return result


@router.post("/login", response_model=AuthResponse)
async def login_dukaandar(body: ShopLoginIn, s: AsyncSession = Depends(get_session)):
    """Authenticate an existing dukaandar using Shop ID or Phone Number + PIN."""
    shop_row = None

    if body.shop_id:
        shop_row = await s.get(Shop, safe_uuid_val(body.shop_id))
        if not shop_row:
            raise HTTPException(404, "Shop not found. Please verify shop ID or select from available dukaans.")

    elif body.phone:
        clean_phone = body.phone.replace(" ", "").replace("-", "").replace("+91", "").strip()
        if not clean_phone:
            raise HTTPException(400, "Please provide a valid mobile number.")

        res = await s.execute(
            text(
                """
                SELECT id FROM shops
                WHERE replace(replace(replace(phone, ' ', ''), '-', ''), '+91', '') ILIKE '%' || :p || '%'
                ORDER BY created_at ASC LIMIT 1
                """
            ),
            {"p": clean_phone},
        )
        found_id = res.scalar()
        if not found_id:
            raise HTTPException(404, "No Dukaan found registered with this phone number. Please create your virtual dukaan below.")
        shop_row = await s.get(Shop, found_id)

    else:
        # Fallback to default shop (e.g. Manjunath)
        def_id = settings.default_shop_id or "00000000-0000-0000-0000-000000000001"
        shop_row = await s.get(Shop, safe_uuid_val(def_id))

    if not shop_row:
        raise HTTPException(404, "Dukaan account not found.")

    # Validate PIN if shop has a PIN and user provided PIN
    if shop_row.pin and body.pin:
        if shop_row.pin.strip() != body.pin.strip():
            raise HTTPException(401, "Invalid PIN. Please enter the correct 4-digit PIN for this shop.")

    owner = shop_row.owner_name or "Dukaandar"
    return AuthResponse(
        token=str(shop_row.id),
        shop=ShopOut(
            id=shop_row.id,
            name=shop_row.name,
            owner_name=shop_row.owner_name,
            phone=shop_row.phone,
            language=shop_row.language,
            pin=shop_row.pin,
        ),
        message=f"Namaste {owner}! Welcome to {shop_row.name}.",
    )


@router.post("/register", response_model=AuthResponse, status_code=201)
async def register_virtual_dukaan(body: ShopRegisterIn, s: AsyncSession = Depends(get_session)):
    """Create a new personal Virtual Dukaan for another dukaandar."""
    clean_name = body.name.strip()
    clean_owner = body.owner_name.strip()
    clean_phone = body.phone.strip()
    clean_pin = (body.pin or "1234").strip()

    # Check if a shop with this exact phone already exists
    normalized_phone = clean_phone.replace(" ", "").replace("-", "").replace("+91", "")
    existing = (
        await s.execute(
            text(
                """
                SELECT id, name FROM shops
                WHERE replace(replace(replace(phone, ' ', ''), '-', ''), '+91', '') = :p
                LIMIT 1
                """
            ),
            {"p": normalized_phone},
        )
    ).mappings().first()

    if existing:
        # If exists, log them into existing shop
        existing_shop = await s.get(Shop, existing["id"])
        if existing_shop:
            return AuthResponse(
                token=str(existing_shop.id),
                shop=ShopOut(
                    id=existing_shop.id,
                    name=existing_shop.name,
                    owner_name=existing_shop.owner_name,
                    phone=existing_shop.phone,
                    language=existing_shop.language,
                    pin=existing_shop.pin,
                ),
                message=f"Dukaan already exists for this number. Logged in to '{existing_shop.name}'.",
            )

    new_id = uuid.uuid4()
    new_shop = Shop(
        id=new_id,
        name=clean_name,
        owner_name=clean_owner,
        phone=clean_phone,
        language=body.language.strip() if body.language else "kn-IN",
        pin=clean_pin,
    )
    s.add(new_shop)
    await s.flush()

    # Add starter sample customer so new shopkeeper has an immediate live dashboard experience
    sample_customer = Customer(
        shop_id=new_id,
        name="Ramesh (Sample Customer)",
        phone="+91 98450 11111",
        landmark="Near Bus Stand",
        outstanding_balance=Decimal("0.00"),
    )
    s.add(sample_customer)
    await s.commit()
    await s.refresh(new_shop)

    log.info("Created new Virtual Dukaan: '%s' (owner: %s, id: %s)", new_shop.name, new_shop.owner_name, new_id)

    return AuthResponse(
        token=str(new_shop.id),
        shop=ShopOut(
            id=new_shop.id,
            name=new_shop.name,
            owner_name=new_shop.owner_name,
            phone=new_shop.phone,
            language=new_shop.language,
            pin=new_shop.pin,
        ),
        message=f"🎉 Virtual Dukaan '{new_shop.name}' created successfully! Welcome {new_shop.owner_name}.",
    )


@router.get("/me", response_model=ShopOut)
async def get_my_shop(
    sid: str = Depends(resolve_shop_id),
    s: AsyncSession = Depends(get_session),
):
    """Retrieve profile of the currently logged-in dukaandar."""
    shop = await s.get(Shop, safe_uuid_val(sid))
    if not shop:
        shop = await s.get(Shop, safe_uuid_val(settings.default_shop_id))
    if not shop:
        raise HTTPException(404, "Current shop not found")
    return shop
