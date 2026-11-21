import asyncio
from app.agent.fast_engine import try_fast_path

async def test_multilingual_debtor_queries():
    test_cases = [
        ("कितना किसका उधार है मुझे बताओ", "hi-IN", "debtors_list"),
        ("किसका कितना उधार है", "hi-IN", "debtors_list"),
        ("किसका कितना बाकी है", "hi-IN", "debtors_list"),
        ("उधारी की लिस्ट बताओ", "hi-IN", "debtors_list"),
        ("सबका बाकी हिसाब बताओ", "hi-IN", "debtors_list"),
        ("who owes how much", "en-IN", "debtors_list"),
        ("who owes money", "en-IN", "debtors_list"),
        ("who owes the most", "en-IN", "debtors_list"),
        ("Sabse zyada baaki kiska hai?", "hi-Latn", "debtors_list"),
        ("ಯಾರದು ಎಷ್ಟು ಬಾಕಿ ಇದೆ", "kn-IN", "debtors_list"),
        ("ಯಾರಿಗೆ ಎಷ್ಟು ಉದ್ರಿ ಇದೆ", "kn-IN", "debtors_list"),
        ("ಉದ್ರಿ ಪಟ್ಟಿ ತೋರಿಸಿ", "kn-IN", "debtors_list"),
        ("ಯಾರು ಎಷ್ಟು ಕೊಡಬೇಕು ಹೇಳಿ", "kn-IN", "debtors_list"),
        ("Ramesh ka kitna baaki hai?", "hi-Latn", "balance_inquiry"),
        ("Aaj kitna udhar gaya?", "hi-Latn", "shop_summary"),
    ]
    for q, lang, expected in test_cases:
        res = await try_fast_path(
            session_or_shop_id="00000000-0000-0000-0000-000000000001",
            user_text=q,
            language=lang
        )
        assert res.handled, f"Failed to handle: {q}"
        ev_types = [e.get('type') for e in res.events]
        if expected == "debtors_list":
            assert "debtors_list" in ev_types or "Sabse zyada" in res.reply or "Top outstanding" in res.reply or "Jaasti baaki" in res.reply
        elif expected == "balance_inquiry":
            assert "Ramesh" in res.reply and any(w in res.reply.lower() for w in ["baaki", "balance", "naam", "advance", "deposit"])
        elif expected == "shop_summary":
            assert "Dukaan summary" in res.reply or "Total udhar" in res.reply

if __name__ == "__main__":
    asyncio.run(test_multilingual_debtor_queries())
    print("All debtor queries passed successfully!")
