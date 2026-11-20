"""Verification script for Song/Noise Immunity and Counter Bill Trilemma Flow."""
import asyncio
import uuid
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.agent.fast_engine import try_fast_path, clean_ambient_noise_and_songs, _extract_name_tokens, _extract_kirana_item
from app.agent.pipeline import VoiceSession
from app.db import SessionLocal
from app import models
from app.agent import tools

async def main():
    print("=== STARTING NOISE IMMUNITY & TRILEMMA TESTS ===")
    
    # Test 1: Song and Noise Cleaner Unit Tests
    print("\n--- Test 1: Song & Noise Stripping ---")
    song_text = "kyunki tum hi ho ab tum hi ho zindagi ab tum hi ho"
    cleaned, had_noise = clean_ambient_noise_and_songs(song_text)
    print(f"Original: '{song_text}'")
    print(f"Cleaned: '{cleaned}', Had Noise: {had_noise}")
    assert had_noise, "Should detect song noise"

    mixed_text = "Parle ji aapka 20 hua tum hi ho"
    cleaned_mixed, had_mixed = clean_ambient_noise_and_songs(mixed_text)
    print(f"Original: '{mixed_text}'")
    print(f"Cleaned: '{cleaned_mixed}', Had Noise: {had_mixed}")
    assert "tum hi ho" not in cleaned_mixed, "Should strip song lyrics"
    assert "20 hua" in cleaned_mixed, "Should keep counter bill speech"

    # Test 2: Kirana Item Extraction and Customer Name Disambiguation
    print("\n--- Test 2: Kirana Items Disambiguation ---")
    item = _extract_kirana_item("Parle ji aapka 20 hua")
    print(f"Detected item: {item}")
    assert item == "Parle-G", f"Expected Parle-G, got {item}"

    tokens = _extract_name_tokens("Parle ji aapka 20 hua")
    print(f"Name tokens extracted from 'Parle ji aapka 20 hua': {tokens}")
    assert len(tokens) == 0, f"Expected 0 tokens, got {tokens} (brand name Parle must not be a customer!)"

    tokens_real = _extract_name_tokens("Ramesh 500 udhar")
    print(f"Name tokens extracted from 'Ramesh 500 udhar': {tokens_real}")
    assert tokens_real == ["Ramesh"], f"Expected ['Ramesh'], got {tokens_real}"

    # Setup a fresh shop and test VoiceSession
    shop_id = "00000000-0000-0000-0000-000000000001"
    sess = VoiceSession(shop_id=shop_id, language="hi-IN")

    # Test 3: Pure song playback should return [SILENT]
    print("\n--- Test 3: Pure Background Song Immunity ---")
    res_song = await try_fast_path(sess, "kyunki tum hi ho ab tum hi ho zindagi ab tum hi ho", language="hi-IN")
    print(f"Pure Song Reply: '{res_song.reply}'")
    assert res_song.handled is True and res_song.reply == "[SILENT]", f"Expected [SILENT], got {res_song.reply}"

    # Test 4: Bill Announcement with background song ("Parle ji aapka 20 hua tum hi ho")
    print("\n--- Test 4: Counter Bill with Background Song ---")
    res_bill = await try_fast_path(sess, "Parle ji aapka 20 hua tum hi ho", language="hi-IN")
    print(f"Bill Reply: '{res_bill.reply}'")
    print(f"Session pending bill: amount={sess.pending_bill_amount}, item={sess.pending_bill_item}")
    assert res_bill.handled is True
    assert "₹20" in res_bill.reply
    assert "Parle-G" in res_bill.reply
    assert "Abhi payment" in res_bill.reply or "de rahe hain" in res_bill.reply
    assert sess.pending_bill_amount == 20.0
    assert sess.pending_bill_item == "Parle-G"

    # Test 5: Correction in next turn ("20 nahi 50")
    print("\n--- Test 5: Amount Correction ('20 nahi 50') ---")
    res_corr = await try_fast_path(sess, "20 nahi 50", language="hi-IN")
    print(f"Correction Reply: '{res_corr.reply}'")
    print(f"Session pending bill: amount={sess.pending_bill_amount}, item={sess.pending_bill_item}")
    assert res_corr.handled is True
    assert "₹50" in res_corr.reply
    assert sess.pending_bill_amount == 50.0

    # Test 6: Udhar resolution ("Udhar likh do Ramesh Kumar")
    print("\n--- Test 6: Udhar Resolution ('Udhar likh do Ramesh Kumar') ---")
    res_udhar = await try_fast_path(sess, "Udhar likh do Ramesh Kumar", language="hi-IN")
    print(f"Udhar Reply: '{res_udhar.reply}'")
    print(f"Draft Events: {res_udhar.events}")
    assert res_udhar.handled is True
    assert "Ramesh" in res_udhar.reply
    assert "₹50" in res_udhar.reply
    assert sess.pending_bill_amount is None
    assert sess.last_draft_id is not None

    # Test 7: Confirm Draft
    print("\n--- Test 7: Confirm Draft ('Haan confirm') ---")
    res_conf = await try_fast_path(sess, "Haan confirm", language="hi-IN")
    print(f"Confirm Reply: '{res_conf.reply}'")
    assert res_conf.handled is True
    assert "Confirm" in res_conf.reply

    # Test 8: Pending Promise Warning Flow
    print("\n--- Test 8: Pending Promise Warning on New Udhar ---")
    # First, record a promise for Ramesh Kumar for tomorrow
    p_res = await try_fast_path(sess, "Ramesh Kumar kal 500 dega", language="hi-IN")
    print(f"Promise Record Reply: '{p_res.reply}'")
    assert "wada" in p_res.reply.lower() or "promise" in p_res.reply.lower()

    # Now, Ramesh buys something else on bill total
    res_b2 = await try_fast_path(sess, "Maggi aapka 30 hua", language="hi-IN")
    print(f"Bill 2 Reply: '{res_b2.reply}'")
    assert "₹30" in res_b2.reply
    assert "Maggi" in res_b2.reply

    # Ramesh asks for udhar again!
    res_u2 = await try_fast_path(sess, "Udhar likh do Ramesh Kumar", language="hi-IN")
    print(f"Udhar with Promise Warning Reply: '{res_u2.reply}'")
    assert "wada pending hai" in res_u2.reply or "promise" in res_u2.reply
    assert "₹500" in res_u2.reply

    # Test 9: Kannada Trilemma Counter Flow
    print("\n--- Test 9: Kannada Trilemma Counter Flow ---")
    sess_kn = VoiceSession(shop_id=shop_id, language="kn-IN")
    res_kn1 = await try_fast_path(sess_kn, "Parle ji 20 aaythu", language="kn-IN")
    print(f"Kannada Bill Reply: '{res_kn1.reply}'")
    assert "₹20" in res_kn1.reply
    assert "aagide" in res_kn1.reply
    assert "udhar baribeka" in res_kn1.reply

    res_kn2 = await try_fast_path(sess_kn, "Suresh ge udri bariyiri", language="kn-IN")
    print(f"Kannada Udhar Reply: '{res_kn2.reply}'")
    assert "Suresh" in res_kn2.reply
    assert "₹20" in res_kn2.reply

    print("\n=== ALL TESTS PASSED SUCCESSFULLY! ===")

if __name__ == "__main__":
    asyncio.run(main())
