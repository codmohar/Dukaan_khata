"""Verification Suite for Cash Book, Change Calculation, Compound Multi-Transactions, and Advance Formatting.
"""
import asyncio
import os
import sys

# Ensure backend app is importable
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
os.environ["DATABASE_URL"] = os.getenv("TEST_DATABASE_URL", "postgresql+asyncpg://postgres:postgrespassword@db:5432/dukaan")

from app.agent.conversation_cache import ShopConversationCacheManager
from app.agent.fast_engine import try_fast_path
from app.agent.pipeline import VoiceSession
from app.db import init_db

SHOP_ID = "00000000-0000-0000-0000-000000000001"


async def run_tests():
    print("=== STARTING CASH BOOK, CHANGE CALC, AND COMPOUND TX TESTS ===")
    ShopConversationCacheManager.clear_cache(SHOP_ID)

    # -------------------------------------------------------------------------
    # TEST 1: Cash Book Inflow ("Cash box mein 2000 daalo")
    # -------------------------------------------------------------------------
    print("\n--- TEST 1: Cash Inflow into Drawer ---")
    sess1 = VoiceSession(SHOP_ID, language="hi-IN")
    t1 = "cash box mein 2000 daalo"
    r1, ev1 = await sess1.respond(t1)
    print(f"Input: '{t1}'")
    print(f"Reply: '{r1}'")
    print(f"Events: {ev1}")
    assert any(e.get("type") == "cash_in" for e in ev1), f"Expected cash_in event, got: {ev1}"
    assert "2,000" in r1 and "jama" in r1
    print("✓ Test 1 Passed: Cash in recorded into physical drawer!")

    # -------------------------------------------------------------------------
    # TEST 2: Cash Book Outflow / Expense ("500 kharch ke liye nikala")
    # -------------------------------------------------------------------------
    print("\n--- TEST 2: Cash Outflow / Expense from Drawer ---")
    sess2 = VoiceSession(SHOP_ID, language="hi-IN")
    t2 = "500 kharch ke liye nikala"
    r2, ev2 = await sess2.respond(t2)
    print(f"Input: '{t2}'")
    print(f"Reply: '{r2}'")
    print(f"Events: {ev2}")
    assert any(e.get("type") == "cash_out" for e in ev2), f"Expected cash_out event, got: {ev2}"
    assert "500" in r2 and ("kharch" in r2 or "nikaal" in r2)
    print("✓ Test 2 Passed: Cash out recorded from physical drawer!")

    # -------------------------------------------------------------------------
    # TEST 3: Cash Book Balance Inquiry ("Cash box mein kitna hai")
    # -------------------------------------------------------------------------
    print("\n--- TEST 3: Cash Book Balance Inquiry ---")
    sess3 = VoiceSession(SHOP_ID, language="hi-IN")
    t3 = "cash box mein kitna hai"
    r3, ev3 = await sess3.respond(t3)
    print(f"Input: '{t3}'")
    print(f"Reply: '{r3}'")
    assert any(e.get("type") == "cash_balance" for e in ev3), f"Expected cash_balance event, got: {ev3}"
    assert "balance" in r3.lower() or "baaki" in r3.lower()
    print("✓ Test 3 Passed: Cash drawer balance queried!")

    # -------------------------------------------------------------------------
    # TEST 4: Cash Change Calculation ("500 diye 150 change do")
    # -------------------------------------------------------------------------
    print("\n--- TEST 4: Change Calculation (No debt modification) ---")
    sess4 = VoiceSession(SHOP_ID, language="hi-IN")
    t4 = "500 diye 150 change do"
    r4, ev4 = await sess4.respond(t4)
    print(f"Input: '{t4}'")
    print(f"Reply: '{r4}'")
    print(f"Events: {ev4}")
    assert any(e.get("type") == "change_calc" for e in ev4), f"Expected change_calc event, got: {ev4}"
    assert not any(e.get("type") == "draft" for e in ev4), f"Must NOT create credit ledger draft!"
    assert "change" in r4.lower() or "wapas" in r4.lower()
    print("✓ Test 4 Passed: Change calculated without touching customer ledger!")

    # -------------------------------------------------------------------------
    # TEST 5: Kannada Change Calculation ("50 change kodi")
    # -------------------------------------------------------------------------
    print("\n--- TEST 5: Kannada Change Calculation ---")
    sess5 = VoiceSession(SHOP_ID, language="kn-IN")
    t5 = "50 change kodi"
    r5, ev5 = await sess5.respond(t5)
    print(f"Input: '{t5}'")
    print(f"Reply: '{r5}'")
    assert any(e.get("type") == "change_calc" for e in ev5)
    assert not any(e.get("type") == "draft" for e in ev5)
    assert "50" in r5 and "change" in r5.lower()
    print("✓ Test 5 Passed: Kannada change command cleanly answered!")

    # -------------------------------------------------------------------------
    # TEST 6: Compound Multi-Transaction Splitting & Atomic Confirmation
    # ("Ramesh 500 kotta, Suresh ge 300 udhar haaki")
    # -------------------------------------------------------------------------
    print("\n--- TEST 6: Compound Multi-Transaction Splitting ---")
    sess6 = VoiceSession(SHOP_ID, language="kn-IN")
    t6a = "Ramesh 500 kotta, Suresh ge 300 udhar haaki"
    r6a, ev6a = await sess6.respond(t6a)
    print(f"Input: '{t6a}'")
    print(f"Reply: '{r6a}'")
    print(f"Draft Events Count: {len([e for e in ev6a if e.get('type') == 'draft'])}")
    drafts6 = [e for e in ev6a if e.get("type") == "draft"]
    assert len(drafts6) == 2, f"Expected 2 drafts, got: {len(drafts6)}"
    assert sess6.pending_draft_ids and len(sess6.pending_draft_ids) == 2
    print("✓ Turn 6A Passed: 2 separate drafts created for Ramesh and Suresh in one shot!")

    # Turn 6B: Confirm both drafts atomically
    t6b = "Haan confirm"
    r6b, ev6b = await sess6.respond(t6b)
    print(f"Turn 6B Input: '{t6b}'")
    print(f"Turn 6B Reply: '{r6b}'")
    confirmed6 = [e for e in ev6b if e.get("type") == "confirmed"]
    print(f"Confirmed Events Count: {len(confirmed6)}")
    assert len(confirmed6) == 2, f"Expected 2 confirmed events, got: {len(confirmed6)}"
    assert sess6.pending_draft_ids is None
    print("✓ Turn 6B Passed: Both compound drafts confirmed atomically!")

    # -------------------------------------------------------------------------
    # TEST 7: Hindi Compound Multi-Transaction Splitting
    # ("Anil 1000 diya aur Sunil ko 200 udhar")
    # -------------------------------------------------------------------------
    print("\n--- TEST 7: Hindi Compound Multi-Transaction Splitting ---")
    sess7 = VoiceSession(SHOP_ID, language="hi-IN")
    t7a = "Anil 1000 diya aur Sunil ko 200 udhar"
    r7a, ev7a = await sess7.respond(t7a)
    print(f"Input: '{t7a}'")
    print(f"Reply: '{r7a}'")
    drafts7 = [e for e in ev7a if e.get("type") == "draft"]
    assert len(drafts7) == 2, f"Expected 2 drafts, got: {len(drafts7)}"
    print("✓ Turn 7A Passed: 2 drafts created from Hindi compound sentence!")

    t7b = "Nahi cancel"
    r7b, ev7b = await sess7.respond(t7b)
    print(f"Turn 7B Input: '{t7b}'")
    print(f"Turn 7B Reply: '{r7b}'")
    cancelled7 = [e for e in ev7b if e.get("type") == "cancelled"]
    assert len(cancelled7) == 2, f"Expected 2 cancelled events, got: {len(cancelled7)}"
    assert sess7.pending_draft_ids is None
    print("✓ Turn 7B Passed: Both drafts cancelled cleanly!")

    print("\n=== ALL CASH BOOK, CHANGE CALC, AND COMPOUND TX TESTS PASSED 100%! ===")


if __name__ == "__main__":
    asyncio.run(run_tests())
