"""Comprehensive test suite for Compound Multi-Action Segregation and Promise Fulfillment."""
import asyncio
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.agent import tools
from app.agent.fast_engine import try_fast_path
from app.agent.pipeline import VoiceSession
from app.db import SessionLocal
from sqlalchemy import text as sa_text


async def run_tests():
    print("Starting run_tests...", flush=True)
    test_shop_id = "00000000-0000-0000-0000-000000000001"
    sid = tools.to_uuid(test_shop_id)

    print("Cleaning any previous test customer records...", flush=True)
    async with SessionLocal() as s:
        await s.execute(sa_text("DELETE FROM promises WHERE shop_id = :sid AND entity_name IN ('Shyam', 'Ram', 'Rhan', 'Rehan')"), {"sid": sid})
        await s.execute(sa_text("DELETE FROM transactions WHERE shop_id = :sid AND customer_id IN (SELECT id FROM customers WHERE shop_id = :sid AND name IN ('Shyam', 'Ram', 'Rhan', 'Rehan'))"), {"sid": sid})
        await s.execute(sa_text("DELETE FROM customers WHERE shop_id = :sid AND name IN ('Shyam', 'Ram', 'Rhan', 'Rehan')"), {"sid": sid})
        await s.commit()

    print("✓ Ready for test with shop", test_shop_id, flush=True)

    sess = VoiceSession(test_shop_id, language="hi-IN")

    # =========================================================================
    # TEST 1: The user's exact compound input with trailing instructional commentary
    # =========================================================================
    user_utterance = (
        "like shyam ka 50 rupee udhar and ram ka 25 udhar jama ho gaya ,rhan ne promise pura kardia ,"
        "so add udhar 50 to the shyams copy, minus 25 from the leger copy nad and do according to the promise"
    )
    print("\n--- Test 1: User's Exact Multi-Action Sentence ---")
    print("Utterance:", user_utterance)

    res = await try_fast_path(sess, user_utterance, language="hi-IN")
    print("Handled:", res.handled)
    print("Reply:", res.reply)
    print("Events count:", len(res.events))
    for ev in res.events:
        print("  Event:", ev.get("type"), ev.get("tx_type"), ev.get("customer"), ev.get("entity_name"), ev.get("amount"), ev.get("status"))

    assert res.handled, "Compound utterance must be handled by fast path!"
    draft_events = [e for e in res.events if e.get("type") == "draft"]
    promise_events = [e for e in res.events if e.get("type") == "promise_card"]

    assert len(draft_events) == 2, f"Expected exactly 2 drafts, got {len(draft_events)}"
    assert len(promise_events) == 1, f"Expected exactly 1 promise card, got {len(promise_events)}"

    # Check Shyam credit ₹50
    shyam_ev = next(e for e in draft_events if "Shyam" in e.get("customer", ""))
    assert shyam_ev["amount"] == 50.0 and shyam_ev["tx_type"] == "credit", f"Shyam draft mismatch: {shyam_ev}"

    # Check Ram payment ₹25
    ram_ev = next(e for e in draft_events if "Ram" in e.get("customer", ""))
    assert ram_ev["amount"] == 25.0 and ram_ev["tx_type"] == "payment", f"Ram draft mismatch: {ram_ev}"

    # Check Rhan promise fulfilled
    rhan_ev = promise_events[0]
    assert "Rhan" in rhan_ev.get("entity_name", "") and rhan_ev.get("status") == "FULFILLED", f"Rhan promise mismatch: {rhan_ev}"

    print("✓ Test 1 Passed: Segregated 2 drafts (Shyam +50, Ram -25) and 1 promise fulfilled (Rhan)!")

    # =========================================================================
    # TEST 1B: Confirm the drafts from Test 1
    # =========================================================================
    print("\n--- Test 1B: Confirm Drafts ---")
    conf_res = await try_fast_path(sess, "Haan confirm kar do", language="hi-IN")
    print("Confirm Handled:", conf_res.handled)
    print("Confirm Reply:", conf_res.reply)
    assert conf_res.handled, "Confirmation must be handled!"
    conf_events = [e for e in conf_res.events if e.get("type") == "confirmed"]
    assert len(conf_events) == 2, f"Expected 2 confirmed events, got {len(conf_events)}"

    # Verify balances in database
    async with SessionLocal() as s_ver:
        shyam_bal = (await s_ver.execute(
            sa_text("SELECT outstanding_balance FROM customers WHERE shop_id = :sid AND name ILIKE 'Shyam%'"),
            {"sid": sid}
        )).scalar()
        ram_bal = (await s_ver.execute(
            sa_text("SELECT outstanding_balance FROM customers WHERE shop_id = :sid AND name ILIKE 'Ram%'"),
            {"sid": sid}
        )).scalar()
        rhan_promise = (await s_ver.execute(
            sa_text("SELECT status FROM promises WHERE shop_id = :sid AND entity_name ILIKE 'Rhan%'"),
            {"sid": sid}
        )).scalar()

    print(f"Database Balances -> Shyam: ₹{shyam_bal}, Ram: ₹{ram_bal}, Rhan Promise: {rhan_promise}")
    assert float(shyam_bal) == 50.0, f"Expected Shyam balance 50.0, got {shyam_bal}"
    assert float(ram_bal) == -25.0, f"Expected Ram balance -25.0 (jama/payment advance), got {ram_bal}"
    assert rhan_promise == "FULFILLED", f"Expected Rhan promise FULFILLED, got {rhan_promise}"
    print("✓ Test 1B Passed: Balances and Promise state correctly committed in database!")

    # =========================================================================
    # TEST 2: Standalone Promise Fulfillment ("Rehan ne promise pura kar diya")
    # =========================================================================
    print("\n--- Test 2: Standalone Promise Fulfillment ---")
    res_p = await try_fast_path(sess, "Rehan ne promise pura kar diya", language="hi-IN")
    print("Handled:", res_p.handled)
    print("Reply:", res_p.reply)
    assert res_p.handled
    p_ev = next((e for e in res_p.events if e.get("type") == "promise_card"), None)
    assert p_ev and p_ev.get("status") == "FULFILLED"
    print("✓ Test 2 Passed: Standalone promise fulfillment works seamlessly!")

    # =========================================================================
    # TEST 3: Shared Amount Each ("Ramesh aur Suresh 100 each udhar")
    # =========================================================================
    print("\n--- Test 3: Shared Amount Each ---")
    sess3 = VoiceSession(test_shop_id, language="hi-IN")
    res_each = await try_fast_path(sess3, "Ramesh aur Suresh 100 each udhar likho", language="hi-IN")
    print("Handled:", res_each.handled)
    print("Reply:", res_each.reply)
    assert res_each.handled
    d_each = [e for e in res_each.events if e.get("type") == "draft"]
    assert len(d_each) == 2, f"Expected 2 drafts, got {len(d_each)}"
    assert all(d["amount"] == 100.0 and d["tx_type"] == "credit" for d in d_each)
    print("✓ Test 3 Passed: 'each' multi-customer credit drafts created!")

    # Teardown test customers only
    async with SessionLocal() as s_clean:
        await s_clean.execute(sa_text("DELETE FROM promises WHERE shop_id = :sid AND entity_name IN ('Shyam', 'Ram', 'Rhan', 'Rehan')"), {"sid": sid})
        await s_clean.execute(sa_text("DELETE FROM transactions WHERE shop_id = :sid AND customer_id IN (SELECT id FROM customers WHERE shop_id = :sid AND name IN ('Shyam', 'Ram', 'Rhan', 'Rehan'))"), {"sid": sid})
        await s_clean.execute(sa_text("DELETE FROM customers WHERE shop_id = :sid AND name IN ('Shyam', 'Ram', 'Rhan', 'Rehan')"), {"sid": sid})
        await s_clean.commit()
    print("\n✓ Cleaned up test namespace.")
    print("ALL TESTS PASSED SUCCESSFULLY!")


if __name__ == "__main__":
    asyncio.run(run_tests())
