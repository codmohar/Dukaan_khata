"""Comprehensive Verification for Dynamic Customer Names (No Hardcoding)."""
import asyncio
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.agent.fast_engine import try_fast_path, _extract_name_tokens, _pick_best_match
from app.agent.pipeline import VoiceSession

async def main():
    print("=== STARTING DYNAMIC NAMES & GENERAL CONTEXT TESTS ===")
    
    # Test 1: Diverse Indian Names Token Extraction
    print("\n--- Test 1: Name Extraction Across Diverse Backgrounds ---")
    test_phrases = [
        ("Deepak 500 udhar", ["Deepak"]),
        ("Farhan ne 300 PhonePe kiya", ["Farhan"]),
        ("Anita ko 200 cash loan diya", ["Anita"]),
        ("Gurpreet kal 1000 dega", ["Gurpreet"]),
        ("Basavaraj ge 450 udri bariyiri", ["Basavaraj"]),
        ("Vignesh 250 kottru", ["Vignesh"]),
        ("Debashis er kach theke 600 pelam", ["Debashis"]),
        ("1 kilo cheeni liya, 50 diya", []),  # buy/sell/lena/dena words ignored as names
        ("Parle biscuit 20 hua", []),          # products ignored as names
    ]
    for phrase, expected in test_phrases:
        tokens = _extract_name_tokens(phrase)
        print(f"Phrase: '{phrase}' -> Extracted tokens: {tokens}")
        assert tokens == expected, f"Expected {expected}, got {tokens} for '{phrase}'"

    shop_id = "00000000-0000-0000-0000-000000000001"
    sess = VoiceSession(shop_id=shop_id, language="hi-IN")

    # Test 2: One-shot transaction for completely new customer (Farhan)
    print("\n--- Test 2: Dynamic New Customer One-Shot (Farhan) ---")
    res_f = await try_fast_path(sess, "Farhan 400 udhar", language="hi-IN")
    print(f"Farhan Reply: '{res_f.reply}'")
    assert res_f.handled is True
    assert "Farhan" in res_f.reply
    assert "₹400" in res_f.reply

    # Test 3: One-shot payment for another new customer (Anita)
    print("\n--- Test 3: Dynamic New Customer Payment (Anita) ---")
    res_a = await try_fast_path(sess, "Anita ne 1000 PhonePe kiya", language="hi-IN")
    print(f"Anita Reply: '{res_a.reply}'")
    assert res_a.handled is True
    assert "Anita" in res_a.reply
    assert "₹1,000" in res_a.reply

    # Test 4: Multi-turn for new customer without magical 'naya' keyword
    print("\n--- Test 4: Multi-Turn for New Customer (Gurpreet) ---")
    # Turn 1: Just name
    res_g1 = await try_fast_path(sess, "Gurpreet", language="hi-IN")
    print(f"Gurpreet Turn 1 Reply: '{res_g1.reply}'")
    assert res_g1.handled is True
    assert "Gurpreet" in res_g1.reply
    assert sess.active_customer_name == "Gurpreet"

    # Turn 2: Amount & Type
    res_g2 = await try_fast_path(sess, "350 udhar", language="hi-IN")
    print(f"Gurpreet Turn 2 Reply: '{res_g2.reply}'")
    assert res_g2.handled is True
    assert "Gurpreet" in res_g2.reply
    assert "₹350" in res_g2.reply

    # Test 5: Payment Promise for new customer (Basavaraj)
    print("\n--- Test 5: Dynamic Promise for Basavaraj ---")
    res_b = await try_fast_path(sess, "Basavaraj kal 600 dega", language="hi-IN")
    print(f"Basavaraj Promise Reply: '{res_b.reply}'")
    assert res_b.handled is True
    assert "Basavaraj" in res_b.reply
    assert "₹600" in res_b.reply

    # Test 6: Kannada New Customer (Manjunath)
    print("\n--- Test 6: Kannada New Customer (Manjunath) ---")
    sess_kn = VoiceSession(shop_id=shop_id, language="kn-IN")
    res_m = await try_fast_path(sess_kn, "Manjunath avarige 750 udri bariyiri", language="kn-IN")
    print(f"Manjunath Reply: '{res_m.reply}'")
    assert res_m.handled is True
    assert "Manjunath" in res_m.reply
    assert "₹750" in res_m.reply

    print("\n=== ALL DYNAMIC NAME TESTS PASSED! ===")

if __name__ == "__main__":
    asyncio.run(main())
