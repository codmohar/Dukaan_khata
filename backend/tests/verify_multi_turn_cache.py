"""Test and Verification Suite for Multi-Turn Conversation Context Cache.

Verifies natural 3-to-4 turn Kirana counter conversations:
1. Product Inquiry ("Shyam: Parle-G lena hai 15 rupaye ka") -> AI caches context silently.
2. Handover & Bill Total ("ok ye lo Parle-G, tumhara hua 15 rupae") -> AI asks Trilemma using cached customer Shyam!
3. Customer Decision:
   - Promise: "Kal de dunga wada raha" -> AI creates payment promise for Shyam for ₹15!
   - Paid sale: "Ye lo 15 cash" -> Settles silently without debt.
   - Credit: "Udhar likh do" -> Creates credit draft for Shyam for ₹15.
4. Confirmation ("Haan confirm") -> Confirmed ledger transaction.
"""
import asyncio
import os
import sys

# Ensure backend app is importable
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.agent.conversation_cache import ConversationState, ShopConversationCacheManager
from app.agent.fast_engine import try_fast_path
from app.agent.pipeline import VoiceSession
from app.db import init_db

SHOP_ID = "00000000-0000-0000-0000-000000000001"


async def run_tests():
    print("=== STARTING CONVERSATION CONTEXT CACHE & MULTI-TURN TESTS ===")

    # Clear any leftover cache for deterministic testing
    ShopConversationCacheManager.clear_cache(SHOP_ID)

    # -------------------------------------------------------------------------
    # SCENARIO 1: The Master 4-Turn Counter Flow with Credit & Confirm
    # Turn 1: Customer Shyam asks for Parle-G for ₹15.
    # Turn 2: Shopkeeper hands it over and announces bill of ₹15.
    # Turn 3: Customer asks to put on udhar (without repeating name or amount!).
    # Turn 4: Shopkeeper confirms.
    # -------------------------------------------------------------------------
    print("\n--- SCENARIO 1: Master 4-Turn Flow (Inquiry -> Bill -> Udhar -> Confirm) ---")
    sess1 = VoiceSession(SHOP_ID, language="hi-IN")

    # Turn 1: Customer asks
    t1_text = "shyam ake pucha ki parleg lena hae 15 rupae ka"
    r1, ev1 = await sess1.respond(t1_text)
    print(f"Turn 1 Input: '{t1_text}'")
    print(f"Turn 1 Reply: '{r1}'")
    cache1 = sess1.cache
    print(f"Cache State after Turn 1: customer={cache1.active_customer_name}, item={cache1.pending_bill_item}, amt={cache1.pending_bill_amount}, state={cache1.state}")
    assert r1 == "[SILENT]", f"Turn 1 should be silent inquiry, got: {r1}"
    assert cache1.active_customer_name == "Shyam", f"Expected Shyam, got: {cache1.active_customer_name}"
    assert cache1.pending_bill_amount == 15.0, f"Expected 15.0, got: {cache1.pending_bill_amount}"
    assert cache1.pending_bill_item == "Parle-G", f"Expected Parle-G, got: {cache1.pending_bill_item}"
    print("✓ Turn 1 Passed: Inquiry cleanly cached without premature ledger draft!")

    # Turn 2: Shopkeeper handover & bill announcement
    t2_text = "ok ye lo 15 the parle gi ,and tumhara hua 15 rupae"
    r2, ev2 = await sess1.respond(t2_text)
    print(f"\nTurn 2 Input: '{t2_text}'")
    print(f"Turn 2 Reply: '{r2}'")
    assert "₹15" in r2 and "Shyam" in r2, f"Turn 2 reply should address Shyam for ₹15, got: {r2}"
    assert "Abhi payment de rahe hain" in r2, f"Expected trilemma prompt, got: {r2}"
    print("✓ Turn 2 Passed: Trilemma prompted using cached customer Shyam and bill ₹15!")

    # Turn 3: Customer says "Udhar likh do" (Name & Amount NOT repeated!)
    t3_text = "udhar likh do"
    r3, ev3 = await sess1.respond(t3_text)
    print(f"\nTurn 3 Input: '{t3_text}'")
    print(f"Turn 3 Reply: '{r3}'")
    assert "Shyam" in r3 and "₹15" in r3, f"Draft reply should mention Shyam and ₹15, got: {r3}"
    assert any(e.get("type") == "draft" for e in ev3), f"Expected draft event, got: {ev3}"
    print("✓ Turn 3 Passed: Credit draft created for Shyam for ₹15 from conversation cache!")

    # Turn 4: Shopkeeper confirms
    t4_text = "Haan confirm"
    r4, ev4 = await sess1.respond(t4_text)
    print(f"\nTurn 4 Input: '{t4_text}'")
    print(f"Turn 4 Reply: '{r4}'")
    assert "Confirm ho gaya" in r4 and "₹15" in r4, f"Confirm reply failed: {r4}"
    assert cache1.pending_bill_amount is None, "Cache bill should be cleared after confirmation"
    assert cache1.state == ConversationState.IDLE, "Cache state should return to IDLE"
    print("✓ Turn 4 Passed: Transaction finalized, cache safely reset to IDLE!")

    # -------------------------------------------------------------------------
    # SCENARIO 2: 3-Turn Flow with Payment Promise ("Kal de dunga wada raha")
    # Turn 1: Inquiry ("Shyam aaya pucha Parle-G lena hai 15 ka")
    # Turn 2: Handover & Bill ("Ye lo Parle-G 15 hua")
    # Turn 3: Decision: Promise ("Kal de dunga wada raha")
    # -------------------------------------------------------------------------
    print("\n--- SCENARIO 2: 3-Turn Flow with Payment Promise ---")
    ShopConversationCacheManager.clear_cache(SHOP_ID)
    sess2 = VoiceSession(SHOP_ID, language="hi-IN")

    r2_1, _ = await sess2.respond("Shyam aaya pucha Parle-G lena hai 15 ka")
    assert r2_1 == "[SILENT]"

    r2_2, _ = await sess2.respond("Ye lo Parle-G tumhara 15 hua")
    assert "Shyam" in r2_2 and "₹15" in r2_2

    t2_3 = "kal de dunga wada raha"
    r2_3, ev2_3 = await sess2.respond(t2_3)
    print(f"Turn 3 Input: '{t2_3}'")
    print(f"Turn 3 Reply: '{r2_3}'")
    assert "Shyam" in r2_3 and "₹15" in r2_3 and "wada" in r2_3, f"Promise reply failed: {r2_3}"
    assert any(e.get("type") == "promise_card" for e in ev2_3), f"Expected promise card event: {ev2_3}"
    print("✓ Scenario 2 Passed: Multi-turn payment promise created for Shyam for ₹15!")

    # -------------------------------------------------------------------------
    # SCENARIO 3: 3-Turn Flow with Immediate Paid Sale ("Ye lo 15 cash")
    # -------------------------------------------------------------------------
    print("\n--- SCENARIO 3: 3-Turn Flow with Immediate Paid Sale ---")
    ShopConversationCacheManager.clear_cache(SHOP_ID)
    sess3 = VoiceSession(SHOP_ID, language="hi-IN")

    await sess3.respond("Shyam aaya pucha Parle-G lena hai 15 ka")
    await sess3.respond("Ye lo Parle-G 15 hua")
    r3_3, _ = await sess3.respond("abhi de raha hoon ye lo 15 cash")
    print(f"Turn 3 Paid Sale Reply: '{r3_3}'")
    assert r3_3 == "[SILENT]", f"Paid walk-in sale should be silent, got: {r3_3}"
    assert sess3.cache.pending_bill_amount is None
    print("✓ Scenario 3 Passed: Immediate cash payment settled silently without debt!")

    # -------------------------------------------------------------------------
    # SCENARIO 4: Background Song & Noise Immunity with Multi-Turn Flow
    # -------------------------------------------------------------------------
    print("\n--- SCENARIO 4: Song Immunity During Counter Multi-Turn Flow ---")
    ShopConversationCacheManager.clear_cache(SHOP_ID)
    sess4 = VoiceSession(SHOP_ID, language="hi-IN")

    # Song in Turn 1
    r4_1, _ = await sess4.respond("Shyam aaya pucha Parle-G lena hai 15 ka kyunki tum hi ho")
    assert r4_1 == "[SILENT]"
    assert sess4.cache.active_customer_name == "Shyam"

    # Song in Turn 2
    r4_2, _ = await sess4.respond("ok ye lo Parle-G tumhara hua 15 rupaye channa mereya")
    assert "Shyam" in r4_2 and "₹15" in r4_2
    print("✓ Scenario 4 Passed: Background song stripped cleanly across multi-turn cache!")

    # -------------------------------------------------------------------------
    # SCENARIO 5: Kannada Multi-Turn Counter Flow
    # -------------------------------------------------------------------------
    print("\n--- SCENARIO 5: Kannada Multi-Turn Counter Flow ---")
    ShopConversationCacheManager.clear_cache(SHOP_ID)
    sess5 = VoiceSession(SHOP_ID, language="kn-IN")

    r5_1, _ = await sess5.respond("Manjunatha bandu 1 packet biscuit kelidru 20 rupayi")
    assert r5_1 == "[SILENT]"
    assert sess5.cache.active_customer_name == "Manjunatha"
    assert sess5.cache.pending_bill_amount == 20.0

    r5_2, _ = await sess5.respond("Iga biscuit thagoli, nimmadu 20 aaythu")
    print(f"Kannada Turn 2 Reply: '{r5_2}'")
    assert "20" in r5_2 and "Manjunatha" in r5_2 and "Eega payment maadthara" in r5_2

    r5_3, ev5_3 = await sess5.respond("Udri bardu")
    print(f"Kannada Turn 3 Reply: '{r5_3}'")
    assert "Manjunath" in r5_3 and "20" in r5_3 and "Confirm maadla" in r5_3

    r5_4, _ = await sess5.respond("Houdu confirm")
    print(f"Kannada Turn 4 Reply: '{r5_4}'")
    assert "Khaatrigolislaagide" in r5_4 and "20" in r5_4
    print("✓ Scenario 5 Passed: Kannada multi-turn counter flow fully operational!")

    print("\n=== ALL CONVERSATION CONTEXT CACHE TESTS PASSED 100%! ===")


if __name__ == "__main__":
    asyncio.run(run_tests())
