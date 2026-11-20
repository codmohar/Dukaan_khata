"""Unit and integration tests for Image-Reading Agent ("Scan Book").

Covers all 8 requirements specified in the test plan:
a) a clear khata page auto-matches an existing customer
b) two similar names stay unmatched and list candidates
c) approve is refused (422) while any included line has no customer
d) approve inserts transactions exactly once (second call 409)
e) a line matching an existing same-day transaction is flagged duplicate and unchecked
f) non-image upload -> 400, >8 MB -> 413
g) same photo twice -> 409
h) supplier_bill produces no lines and a warning
"""
import asyncio
import io
import sys
import uuid
from datetime import date
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import text

from app.config import settings
from app.db import SessionLocal, init_db
from app.main import app
from app.models import Customer, Transaction
from app.services.vision import Extraction, Line


@pytest_asyncio.fixture(scope="session", autouse=True)
async def setup_db():
    await init_db()


@pytest_asyncio.fixture
async def client():
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


def _fake_png(content: bytes = b"fake-png-data") -> io.BytesIO:
    return io.BytesIO(b"\x89PNG\r\n\x1a\n" + content)


# a) A clear khata page auto-matches an existing customer
@pytest.mark.asyncio
async def test_a_auto_matches_clear_customer(client):
    tag = uuid.uuid4().hex[:6]
    cust_name = f"Vikas_{tag}"
    shop_uuid = uuid.UUID(settings.default_shop_id)

    async with SessionLocal() as s:
        c = Customer(id=uuid.uuid4(), shop_id=shop_uuid, name=cust_name, phone="9845011111", landmark="Opp Bus Stand")
        s.add(c)
        await s.commit()
        cust_id = str(c.id)

    mock_extraction = Extraction(
        doc_type="khata_page",
        total_shown=340.0,
        summary="Clear handwritten khata page",
        lines=[
            Line(
                customer_name=cust_name,
                type="credit",
                amount=340.0,
                date=date.today().isoformat(),
                note="Rice 5kg",
                confidence=0.95,
                raw_text=f"{cust_name} 340 udhar",
            )
        ],
    )

    with patch("app.routers.scans.extract", return_value=mock_extraction):
        f = _fake_png(f"test_a_{tag}".encode())
        res = await client.post("/scans", files={"file": ("page.png", f, "image/png")})
        assert res.status_code == 200, res.text
        data = res.json()
        assert data["scan"]["doc_type"] == "khata_page"
        assert len(data["lines"]) == 1
        line = data["lines"][0]
        assert line["customer_id"] == cust_id
        assert line["include"] is True
        assert line["duplicate"] is False


# b) Two similar names stay unmatched and list candidates
@pytest.mark.asyncio
async def test_b_similar_names_stay_unmatched_with_candidates(client):
    tag = uuid.uuid4().hex[:6]
    base = f"Suresh_{tag}"
    shop_uuid = uuid.UUID(settings.default_shop_id)

    async with SessionLocal() as s:
        c1 = Customer(id=uuid.uuid4(), shop_id=shop_uuid, name=f"{base} Kumar", landmark="Near Market")
        c2 = Customer(id=uuid.uuid4(), shop_id=shop_uuid, name=f"{base} Gowda", landmark="Near Temple")
        s.add_all([c1, c2])
        await s.commit()

    mock_extraction = Extraction(
        doc_type="khata_page",
        total_shown=200.0,
        summary="Khata page with ambiguous name",
        lines=[
            Line(
                customer_name=base,
                type="credit",
                amount=200.0,
                date=None,
                note=None,
                confidence=0.85,
                raw_text=f"{base} 200",
            )
        ],
    )

    with patch("app.routers.scans.extract", return_value=mock_extraction):
        f = _fake_png(f"test_b_{tag}".encode())
        res = await client.post("/scans", files={"file": ("page.png", f, "image/png")})
        assert res.status_code == 200
        data = res.json()
        line = data["lines"][0]
        assert line["customer_id"] is None
        assert len(line["candidates"]) >= 2


# c) Approve is refused (422) while any included line has no customer
@pytest.mark.asyncio
async def test_c_approve_refused_when_unmatched(client):
    tag = uuid.uuid4().hex[:6]
    mock_extraction = Extraction(
        doc_type="khata_page",
        total_shown=150.0,
        summary="Page with unknown customer",
        lines=[
            Line(
                customer_name=f"CompletelyUnknown_{tag}",
                type="credit",
                amount=150.0,
                date=None,
                note=None,
                confidence=0.7,
                raw_text="Unknown 150",
            )
        ],
    )

    with patch("app.routers.scans.extract", return_value=mock_extraction):
        f = _fake_png(f"test_c_{tag}".encode())
        res = await client.post("/scans", files={"file": ("page.png", f, "image/png")})
        assert res.status_code == 200
        scan_id = res.json()["scan"]["id"]

        app_res = await client.post(f"/scans/{scan_id}/approve")
        assert app_res.status_code == 422
        detail = app_res.json()["detail"]
        assert "Pick a customer" in detail["message"]


# d) Approve inserts transactions exactly once (second call 409)
@pytest.mark.asyncio
async def test_d_approve_inserts_transactions_once_and_blocks_second(client):
    tag = uuid.uuid4().hex[:6]
    cust_name = f"Rajesh_{tag}"
    shop_uuid = uuid.UUID(settings.default_shop_id)

    async with SessionLocal() as s:
        c = Customer(id=uuid.uuid4(), shop_id=shop_uuid, name=cust_name)
        s.add(c)
        await s.commit()
        cust_id = str(c.id)

    mock_extraction = Extraction(
        doc_type="khata_page",
        total_shown=500.0,
        summary="One valid line",
        lines=[
            Line(
                customer_name=cust_name,
                type="payment",
                amount=500.0,
                date=date.today().isoformat(),
                note="UPI payment",
                confidence=0.9,
                raw_text=f"{cust_name} 500 paid",
            )
        ],
    )

    with patch("app.routers.scans.extract", return_value=mock_extraction):
        f = _fake_png(f"test_d_{tag}".encode())
        res = await client.post("/scans", files={"file": ("page.png", f, "image/png")})
        scan_id = res.json()["scan"]["id"]

        app_res = await client.post(f"/scans/{scan_id}/approve")
        assert app_res.status_code == 200
        assert app_res.json()["created"] == 1

        async with SessionLocal() as s:
            tx = (await s.execute(
                text("select * from transactions where scan_id=:sc"),
                {"sc": scan_id}
            )).mappings().first()
            assert tx is not None
            assert str(tx["customer_id"]) == cust_id
            assert tx["source"] == "scan"
            assert tx["status"] == "confirmed"

        app2 = await client.post(f"/scans/{scan_id}/approve")
        assert app2.status_code == 409


# e) A line matching an existing same-day transaction is flagged duplicate and unchecked
@pytest.mark.asyncio
async def test_e_duplicate_same_day_flagged_and_unchecked(client):
    tag = uuid.uuid4().hex[:6]
    cust_name = f"Anil_{tag}"
    shop_uuid = uuid.UUID(settings.default_shop_id)
    today = date.today()

    async with SessionLocal() as s:
        c = Customer(id=uuid.uuid4(), shop_id=shop_uuid, name=cust_name)
        s.add(c)
        await s.flush()
        tx = Transaction(
            shop_id=shop_uuid,
            customer_id=c.id,
            type="credit",
            amount=450.0,
            status="confirmed",
        )
        s.add(tx)
        await s.commit()

    mock_extraction = Extraction(
        doc_type="khata_page",
        total_shown=450.0,
        summary="Duplicate scan entry",
        lines=[
            Line(
                customer_name=cust_name,
                type="credit",
                amount=450.0,
                date=today.isoformat(),
                note=None,
                confidence=0.9,
                raw_text=f"{cust_name} 450",
            )
        ],
    )

    with patch("app.routers.scans.extract", return_value=mock_extraction):
        f = _fake_png(f"test_e_{tag}".encode())
        res = await client.post("/scans", files={"file": ("page.png", f, "image/png")})
        assert res.status_code == 200
        data = res.json()
        line = data["lines"][0]
        assert line["duplicate"] is True
        assert line["include"] is False


# f) Non-image upload -> 400, >8 MB -> 413
@pytest.mark.asyncio
async def test_f_non_image_and_oversized_rejected(client):
    res1 = await client.post("/scans", files={"file": ("test.pdf", b"%PDF-1.4", "application/pdf")})
    assert res1.status_code == 400

    big = b"X" * (8 * 1024 * 1024 + 10)
    res2 = await client.post("/scans", files={"file": ("big.png", big, "image/png")})
    assert res2.status_code == 413


# g) Same photo twice -> 409
@pytest.mark.asyncio
async def test_g_same_photo_twice_returns_409(client):
    tag = uuid.uuid4().hex[:6]
    photo_bytes = f"identical_photo_{tag}".encode()

    mock_extraction = Extraction(
        doc_type="payment_proof",
        total_shown=100.0,
        summary="UPI payment proof",
        lines=[],
    )

    with patch("app.routers.scans.extract", return_value=mock_extraction):
        f1 = _fake_png(photo_bytes)
        res1 = await client.post("/scans", files={"file": ("img.png", f1, "image/png")})
        assert res1.status_code == 200

        f2 = _fake_png(photo_bytes)
        res2 = await client.post("/scans", files={"file": ("img.png", f2, "image/png")})
        assert res2.status_code == 409
        assert "already scanned" in res2.text


# h) supplier_bill produces no lines and a warning
@pytest.mark.asyncio
async def test_h_supplier_bill_produces_no_lines_and_warning(client):
    tag = uuid.uuid4().hex[:6]
    mock_extraction = Extraction(
        doc_type="supplier_bill",
        total_shown=12500.0,
        summary="Bill from Sri Balaji Traders for 10 bags sugar",
        lines=[],
    )

    with patch("app.routers.scans.extract", return_value=mock_extraction):
        f = _fake_png(f"test_h_{tag}".encode())
        res = await client.post("/scans", files={"file": ("bill.png", f, "image/png")})
        assert res.status_code == 200
        data = res.json()
        assert data["scan"]["doc_type"] == "supplier_bill"
        assert len(data["lines"]) == 0
        warnings = data["scan"]["warnings"]
        assert any("Supplier bills" in w for w in warnings)


async def _run_all_direct():
    print("Running test_scans.py directly...")
    await init_db()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        tests = [
            ("test_a_auto_matches_clear_customer", test_a_auto_matches_clear_customer),
            ("test_b_similar_names_stay_unmatched_with_candidates", test_b_similar_names_stay_unmatched_with_candidates),
            ("test_c_approve_refused_when_unmatched", test_c_approve_refused_when_unmatched),
            ("test_d_approve_inserts_transactions_once_and_blocks_second", test_d_approve_inserts_transactions_once_and_blocks_second),
            ("test_e_duplicate_same_day_flagged_and_unchecked", test_e_duplicate_same_day_flagged_and_unchecked),
            ("test_f_non_image_and_oversized_rejected", test_f_non_image_and_oversized_rejected),
            ("test_g_same_photo_twice_returns_409", test_g_same_photo_twice_returns_409),
            ("test_h_supplier_bill_produces_no_lines_and_warning", test_h_supplier_bill_produces_no_lines_and_warning),
        ]
        passed = 0
        for name, fn in tests:
            try:
                await fn(c)
                print(f"  [PASS] {name}")
                passed += 1
            except Exception as e:
                print(f"  [FAIL] {name}: {e}")
        print(f"\nResult: {passed}/{len(tests)} PASSED")


if __name__ == "__main__":
    asyncio.run(_run_all_direct())
