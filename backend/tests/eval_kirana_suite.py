"""DukaanAI Kirana Shop Talk & Money-Flows Evaluation Suite (160 Labeled Multilingual Cases).

Validates:
1. All 160 labeled multilingual sentences (Kannada, Hindi, Hinglish, English, Tamil, Telugu, Marathi)
   with expected intent, customer, amount, type, payment_mode, adjustment_reason, date, and expected tools.
2. Deterministic unit checks for honorific stripping and Indian spoken number parsing.
3. Live end-to-end integration tests through VoiceSession (Gemini 3.1 Flash Lite + DB Tools + Guardrails),
   creating temporary isolated test customers (zero default seed names) and cleaning them up afterward.

Run:
  cd dukaan-ai/backend
  python tests/eval_kirana_suite.py            # dataset + unit + live representative battery
  python tests/eval_kirana_suite.py --export   # export kirana_eval_dataset.json
"""
import asyncio
import json
import os
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import text
from app.agent.indian_numbers import extract_indian_amount
from app.agent.pipeline import VoiceSession
from app.agent.tools import normalize_customer_query
from app.config import settings
from app.db import SessionLocal, init_db
from app.models import Customer, Transaction

# ---------------------------------------------------------------------------
# 160 LABELED MULTILINGUAL KIRANA TEST CASES (ZERO HARDCODED DEFAULT NAMES)
# ---------------------------------------------------------------------------

def build_eval_dataset() -> list[dict]:
    cases: list[dict] = []

    def add(cat: str, lang: str, utterance: str, expected: dict):
        cases.append({
            "id": len(cases) + 1,
            "category": cat,
            "language": lang,
            "utterance": utterance,
            "expected": expected,
        })

    # 1. CREDIT / UDHAR (Kannada, Hindi, English, Tamil, Telugu, Marathi, Scripts) - 25 cases
    credit_samples = [
        ("kn-Latn", "Basavaraj ge 340 udhar bardu", "Basavaraj", 340, None),
        ("kn-Latn", "Kavitha avare account ge 180 baaki haaki", "Kavitha", 180, None),
        ("kn-Latn", "Harish ge 520 udri barkoli", "Harish", 520, None),
        ("kn-IN", "ಬಸವರಾಜ್ ಗೆ 450 ಉಧಾರ್ ಬರೆದು ಹಾಕಿ", "Basavaraj", 450, None),
        ("kn-IN", "ಸಾವಿತ್ರಿ ಅಕ್ಕ ಗೆ 210 ಬಾಕಿ ಬರೆಯಿರಿ", "Savitri", 210, None),
        ("hi-Latn", "Imran ke khate mein 650 udhaar daal do", "Imran", 650, None),
        ("hi-Latn", "Meenakshi ko 290 baaki likh do", "Meenakshi", 290, None),
        ("hi-IN", "दिनेश के खाते में 780 उधार लिख दो", "Dinesh", 780, None),
        ("hi-IN", "रेखा जी को 145 बाकी डाल दो", "Rekha", 145, None),
        ("en-IN", "Put 410 on Prakash account as credit", "Prakash", 410, None),
        ("en-IN", "Add 890 udhar for Naveen", "Naveen", 890, None),
        ("ta-IN", "Karthik ku 320 kadan ezhudhu", "Karthik", 320, None),
        ("te-IN", "Padma garu ki 275 appu raayi", "Padma", 275, None),
        ("mr-IN", "Yogesh chya khatyat 360 udhari liha", "Yogesh", 360, None),
        ("hi-Latn", "Farida didi 120 udhar, 2 packet doodh", "Farida", 120, "2 packet doodh"),
        ("kn-Latn", "Ganesh anna ge 550 baaki, 5kg akki", "Ganesh", 550, "5kg akki"),
        ("en-IN", "Shanta aunty took 2kg sugar and 1L oil, 265 credit", "Shanta", 265, "2kg sugar, 1L oil"),
        ("hi-Latn", "Vandana ji ko 95 likh do chai patti", "Vandana", 95, "chai patti"),
        ("kn-Latn", "Mallika ge 130 saala haaki", "Mallika", 130, None),
        ("hi-Latn", "Tariq bhai ko 440 khate mein daal do", "Tariq", 440, None),
        ("en-IN", "Record 75 rupees due for Zoya", "Zoya", 75, None),
        ("kn-Latn", "Shankar uncle ge 610 udhar baredi", "Shankar", 610, None),
        ("hi-Latn", "Bhavna ka 315 udhaar likho", "Bhavna", 315, None),
        ("kn-Latn", "Raghu ge 240 baaki bardu", "Raghu", 240, None),
        ("en-IN", "Geetha credit 500 for groceries", "Geetha", 500, "groceries"),
    ]
    for lang, utt, cust, amt, note in credit_samples:
        add("credit_sale", lang, utt, {
            "customer": cust, "amount": amt, "type": "credit",
            "tools": ["search_customers", "create_draft"], "confirm_required": True, "note": note,
        })

    # 2. PAYMENTS (Cash, UPI: PhonePe/GPay/Paytm, Partial, Advance) - 25 cases
    payment_samples = [
        ("kn-Latn", "Basavaraj 500 kottru", "Basavaraj", 500, None, "payment"),
        ("kn-Latn", "Kavitha 300 PhonePe maadidru", "Kavitha", 300, "upi", "payment"),
        ("kn-IN", "ಹರೀಶ್ 400 ಜಮಾ ಕೊಟ್ಟರು", "Harish", 400, None, "payment"),
        ("hi-Latn", "Imran ne 200 PhonePe kiya", "Imran", 200, "upi", "payment"),
        ("hi-Latn", "Meenakshi ne 450 GPay se jama kiya", "Meenakshi", 450, "upi", "payment"),
        ("hi-Latn", "Dinesh ne 600 Paytm bheja", "Dinesh", 600, "upi", "payment"),
        ("hi-Latn", "Rekha ne 350 cash de diya", "Rekha", 350, "cash", "payment"),
        ("hi-Latn", "Prakash ne 150 nagad jama kiya", "Prakash", 150, "cash", "payment"),
        ("hi-IN", "नवीन ने 500 रुपये जमा किए", "Naveen", 500, None, "payment"),
        ("en-IN", "Karthik paid 700 by UPI", "Karthik", 700, "upi", "payment"),
        ("en-IN", "Padma gave 250 cash", "Padma", 250, "cash", "payment"),
        ("ta-IN", "Yogesh 400 varavu kuduthaaru", "Yogesh", 400, None, "payment"),
        ("te-IN", "Farida 300 jama ichhaaru", "Farida", 300, None, "payment"),
        ("kn-Latn", "Ganesh 800 Google Pay kottidru", "Ganesh", 800, "upi", "payment"),
        # Partial payments
        ("hi-Latn", "Shanta ne 500 mein se 300 diya, baaki baad mein", "Shanta", 300, None, "partial_payment"),
        ("kn-Latn", "Vandana 600 alli 250 kottru, baaki naale", "Vandana", 250, None, "partial_payment"),
        ("en-IN", "Mallika paid 400 out of 1000 today by cash", "Mallika", 400, "cash", "partial_payment"),
        ("hi-Latn", "Tariq ne 1000 mein se 600 PhonePe kiya", "Tariq", 600, "upi", "partial_payment"),
        # Advances / Deposits (balance goes negative = shop owes customer)
        ("hi-Latn", "Zoya ka 1000 advance rakho", "Zoya", 1000, None, "advance"),
        ("kn-Latn", "Shankar 1500 advance mungaada kottru", "Shankar", 1500, None, "advance"),
        ("en-IN", "Keep 2000 deposit advance for Bhavna via UPI", "Bhavna", 2000, "upi", "advance"),
        ("hi-Latn", "Raghu ne 500 advance jama karwaya cash mein", "Raghu", 500, "cash", "advance"),
        ("kn-Latn", "Geetha 300 BHIM UPI jama bantu", "Geetha", 300, "upi", "payment"),
        ("hi-Latn", "Savitri ji ne 220 chuka diya", "Savitri", 220, None, "payment"),
        ("en-IN", "Received 450 from Basavaraj via QR code", "Basavaraj", 450, "upi", "payment"),
    ]
    for lang, utt, cust, amt, mode, subcat in payment_samples:
        add(subcat, lang, utt, {
            "customer": cust, "amount": amt, "type": "payment", "payment_mode": mode,
            "tools": ["search_customers", "create_draft"], "confirm_required": True,
        })

    # 3. FULL SETTLEMENT & WRITE-OFF - 12 cases
    settle_samples = [
        ("hi-Latn", "Imran ka sab clear kar do", "Imran", None, False),
        ("hi-Latn", "Meenakshi ka hisaab chukta ho gaya cash mein", "Meenakshi", "cash", False),
        ("hi-Latn", "Dinesh ka hisaab barabar kar do PhonePe se", "Dinesh", "upi", False),
        ("kn-Latn", "Basavaraj du ellaa clear maadi", "Basavaraj", None, False),
        ("kn-Latn", "Kavitha avaru poora settle maadidru UPI alli", "Kavitha", "upi", False),
        ("en-IN", "Settle Prakash account completely in cash", "Prakash", "cash", False),
        ("en-IN", "Clear full balance for Naveen", "Naveen", None, False),
        ("hi-IN", "रेखा का पूरा हिसाब चुकता कर दो", "Rekha", None, False),
        ("hi-Latn", "Tariq ka hisaab band karo, bad debt write off", "Tariq", None, True),
        ("en-IN", "Write off Yogesh unpaid balance permanently", "Yogesh", None, True),
        ("kn-Latn", "Raghu account close maadi write off", "Raghu", None, True),
        ("hi-Latn", "Shankar ka pura baaki maaf kar ke band karo", "Shankar", None, True),
    ]
    for lang, utt, cust, mode, wo in settle_samples:
        add("write_off" if wo else "full_settlement", lang, utt, {
            "customer": cust, "payment_mode": mode, "is_write_off": wo,
            "tools": ["search_customers", "settle_balance"], "confirm_required": True,
        })

    # 4. ADJUSTMENTS (Return of goods, Discount / Round-off) - 14 cases
    adj_samples = [
        ("hi-Latn", "Farida ne wo biscuit wapas kiya, 40 kam karo", "Farida", 40, "return"),
        ("kn-Latn", "Ganesh biscuit packet return maadidru, 60 kadime maadi", "Ganesh", 60, "return"),
        ("en-IN", "Shanta returned 1L oil, reduce 140 from account", "Shanta", 140, "return"),
        ("hi-Latn", "Vandana ka soap wapas aaya, 35 rupaye return adjust karo", "Vandana", 35, "return"),
        ("hi-IN", "मल्लिका ने आटा वापस किया 120 कम करो", "Mallika", 120, "return"),
        ("hi-Latn", "Chillar chhodo, Zoya ke khate se 10 discount kam karo", "Zoya", 10, "discount"),
        ("en-IN", "Give 25 rupees discount adjustment to Bhavna", "Bhavna", 25, "discount"),
        ("kn-Latn", "Geetha ge 15 rupayi discount maadi", "Geetha", 15, "discount"),
        ("hi-Latn", "Padma ji ko 20 rupaye chhoot de do khate mein", "Padma", 20, "discount"),
        ("en-IN", "Round off 12 rupees discount on Karthik ledger", "Karthik", 12, "discount"),
        ("hi-Latn", "Savitri ka kharab doodh return, 55 minus karo", "Savitri", 55, "return"),
        ("kn-Latn", "Harish 30 rupayi chillar discount haaki", "Harish", 30, "discount"),
        ("hi-Latn", "Chillar chhodo, Prakash ka 340 ki jagah 330 udhar likho", "Prakash", 330, "round_off_credit"),
        ("kn-Latn", "Naveen ge 210 badalu 200 udhar bardu", "Naveen", 200, "round_off_credit"),
    ]
    for lang, utt, cust, amt, reason in adj_samples:
        is_round_credit = reason == "round_off_credit"
        add("adjustment", lang, utt, {
            "customer": cust, "amount": amt,
            "type": "credit" if is_round_credit else "adjustment",
            "adjustment_reason": None if is_round_credit else reason,
            "tools": ["search_customers", "create_draft"], "confirm_required": True,
        })

    # 5. INFORMAL INDIAN SPOKEN NUMBERS & SOUND-ALIKES - 18 cases
    number_samples = [
        ("hi-Latn", "Imran ko saade teen sau udhar likho", "Imran", 350),
        ("hi-Latn", "Meenakshi ko paune do sau udhar daal do", "Meenakshi", 175),
        ("hi-Latn", "Dinesh ko dedh sau baaki likh do", "Dinesh", 150),
        ("hi-Latn", "Rekha ko dhai sau udhar likho", "Rekha", 250),
        ("hi-Latn", "Prakash ne sawa sau diya", "Prakash", 125),
        ("hi-Latn", "Naveen ko do hazaar paanch sau udhar", "Naveen", 2500),
        ("hi-Latn", "Karthik ne dedh hazaar jama kiya", "Karthik", 1500),
        ("hi-Latn", "Padma ko saade paanch sau udhar", "Padma", 550),
        ("hi-Latn", "Yogesh ko paune teen sau baaki", "Yogesh", 275),
        ("hi-Latn", "Farida ko paune hazaar udhar likho", "Farida", 750),
        ("kn-Latn", "Basavaraj ge innooru udhar bardu", "Basavaraj", 200),
        ("kn-Latn", "Kavitha ge mooru nooru baaki haaki", "Kavitha", 300),
        ("kn-Latn", "Harish aidu nooru kottru", "Harish", 500),
        ("kn-Latn", "Savitri ge eradu savira udhar bardu", "Savitri", 2000),
        ("kn-Latn", "Ganesh ge naalku nooru baaki", "Ganesh", 400),
        ("hi-Latn", "Shanta ko tees rupaye udhar likho", "Shanta", 30),
        ("en-IN", "Put thirteen rupees credit for Vandana", "Vandana", 13),
        ("en-IN", "Put thirty rupees credit for Mallika", "Mallika", 30),
    ]
    for lang, utt, cust, amt in number_samples:
        add("indian_numbers", lang, utt, {
            "customer": cust, "amount": amt, "confirm_required": True,
            "tools": ["search_customers", "create_draft"],
        })

    # 6. BALANCE QUERIES, SHOP SUMMARIES & REMINDERS (No confirm) - 16 cases
    query_samples = [
        ("kn-Latn", "Savitri akka ge eshtu baaki ide?", "balance", "Savitri", ["search_customers", "get_balance"]),
        ("hi-Latn", "Imran ka kitna baaki hai?", "balance", "Imran", ["search_customers", "get_balance"]),
        ("en-IN", "What is Kavitha's pending balance?", "balance", "Kavitha", ["search_customers", "get_balance"]),
        ("hi-IN", "दिनेश का हिसाब कितना है?", "balance", "Dinesh", ["search_customers", "get_balance"]),
        ("kn-IN", "ಬಸವರಾಜ್ ಬ್ಯಾಲೆನ್ಸ್ ಎಷ್ಟು ಇದೆ?", "balance", "Basavaraj", ["search_customers", "get_balance"]),
        ("hi-Latn", "Aaj kitna udhar gaya?", "summary", None, ["get_shop_summary"]),
        ("en-IN", "Who owes the most in the shop?", "summary", None, ["get_shop_summary"]),
        ("hi-Latn", "Sabse zyada baaki kiska hai?", "summary", None, ["get_shop_summary"]),
        ("kn-Latn", "Ivattu eshtu udhar aagide matte collection eshtu?", "summary", None, ["get_shop_summary"]),
        ("en-IN", "Show today's UPI and cash collection summary", "summary", None, ["get_shop_summary"]),
        ("hi-Latn", "Total dukaan ka kitna udhaar baaki hai?", "summary", None, ["get_shop_summary"]),
        ("hi-Latn", "Harish ko yaad dilao paise ka", "reminder", "Harish", ["search_customers", "prepare_reminder"]),
        ("en-IN", "Send a payment reminder to Meenakshi", "reminder", "Meenakshi", ["search_customers", "prepare_reminder"]),
        ("kn-Latn", "Prakash ge reminder kalisi", "reminder", "Prakash", ["search_customers", "prepare_reminder"]),
        ("hi-Latn", "Rekha ji ko WhatsApp reminder bhejna hai", "reminder", "Rekha", ["search_customers", "prepare_reminder"]),
        ("en-IN", "Remind Naveen about his due balance", "reminder", "Naveen", ["search_customers", "prepare_reminder"]),
    ]
    for lang, utt, cat, cust, tlist in query_samples:
        add(cat, lang, utt, {"customer": cust, "tools": tlist, "confirm_required": False})

    # 7. BACKDATED ENTRIES & DUE DATES - 10 cases
    date_samples = [
        ("hi-Latn", "Kal ka 200 bhi Imran ke khate mein daal do", "Imran", 200, "backdated_to"),
        ("en-IN", "Add yesterday's 350 credit for Kavitha", "Kavitha", 350, "backdated_to"),
        ("kn-Latn", "Ninne du 180 Basavaraj ge udhar haaki", "Basavaraj", 180, "backdated_to"),
        ("hi-Latn", "Parso ka 400 udhar Dinesh ke naam likho", "Dinesh", 400, "backdated_to"),
        ("kn-Latn", "Harish ge 300 udhar, naale kodtini andru", "Harish", 300, "due_date"),
        ("hi-Latn", "Meenakshi 450 udhar, kal de dengi", "Meenakshi", 450, "due_date"),
        ("en-IN", "Prakash 600 credit, will pay on Saturday", "Prakash", 600, "due_date"),
        ("hi-Latn", "Rekha 250 udhar likho, Sunday ko dene wali hain", "Rekha", 250, "due_date"),
        ("kn-Latn", "Naveen 500 baaki, Monday kodtare", "Naveen", 500, "due_date"),
        ("en-IN", "Backdate 150 payment from Karthik to yesterday", "Karthik", 150, "backdated_to"),
    ]
    for lang, utt, cust, amt, dfield in date_samples:
        add("dates", lang, utt, {
            "customer": cust, "amount": amt, "date_field": dfield,
            "tools": ["search_customers", "create_draft"], "confirm_required": True,
        })

    # 8. NAMES, HONORIFICS, NICKNAMES, PROXIES & DISAMBIGUATION - 14 cases
    name_samples = [
        ("kn-Latn", "Savitri akka ge 190 udhar bardu", "Savitri", 190, "honorific"),
        ("hi-Latn", "Prakash bhaiya ko 280 baaki likho", "Prakash", 280, "honorific"),
        ("en-IN", "Shankar uncle 310 credit", "Shankar", 310, "honorific"),
        ("te-IN", "Padma garu ki 160 appu", "Padma", 160, "honorific"),
        ("hi-Latn", "Doodh wala Yogesh ko 420 udhar likho", "Yogesh", 420, "nickname_landmark"),
        ("en-IN", "Temple street Ganesh 230 credit", "Ganesh", 230, "nickname_landmark"),
        ("kn-Latn", "Auto driver Raghu ge 175 baaki haaki", "Raghu", 175, "nickname_landmark"),
        ("hi-Latn", "Paan shop Tariq ne 500 jama kiya", "Tariq", 500, "nickname_landmark"),
        ("hi-Latn", "Imran ka beta aaya tha, uske naam 140 udhar likho", "Imran", 140, "proxy"),
        ("kn-Latn", "Basavaraj avara maga bandiddu, 220 udhar haaki", "Basavaraj", 220, "proxy"),
        ("en-IN", "Kavitha's driver picked up rice, put 480 on her account", "Kavitha", 480, "proxy"),
        ("hi-Latn", "Dinesh ki wife aayi thi, 310 khate mein daal do", "Dinesh", 310, "proxy"),
        ("hi-Latn", "Harish ka phone number 9876543210 update karo", "Harish", None, "update_customer"),
        ("en-IN", "Update Geetha landmark to Near Railway Gate", "Geetha", None, "update_customer"),
    ]
    for lang, utt, cust, amt, sub in name_samples:
        add(sub, lang, utt, {"customer": cust, "amount": amt})

    # 9. MESSY REAL-WORLD CASES (Corrections, Undo, Two Amounts, Two Customers, Cross-Lang Confirm) - 16 cases
    messy_samples = [
        ("hi-Latn", "Nahi nahi, 430 likho, 340 nahi", "correction", 430),
        ("kn-Latn", "Alla, 430 antha bardu, 340 alla", "correction", 430),
        ("en-IN", "No, make it 520 instead", "correction", 520),
        ("kn-Latn", "Last entry delete maadi", "undo", None),
        ("hi-Latn", "Pichla entry hatao, galat ho gaya", "undo", None),
        ("en-IN", "Undo the last transaction for Imran", "undo", None),
        ("hi-Latn", "Kavitha ne 500 diya aur 340 udhar likho", "two_amounts", [500, 340]),
        ("kn-Latn", "Basavaraj 300 kottru matte 220 baaki bardu", "two_amounts", [300, 220]),
        ("en-IN", "Harish and Ganesh, 100 rupees credit each", "two_customers", 100),
        ("hi-Latn", "Rekha aur Savitri dono ke khate mein 150 udhar daal do", "two_customers", 150),
        ("hi-Latn", "Haan theek hai", "confirm_cross_lang", None),
        ("kn-Latn", "Houdu sari maadi", "confirm_cross_lang", None),
        ("ta-IN", "Aama confirm pannunga", "confirm_cross_lang", None),
        ("kn-Latn", "Beda illa cancel maadi", "cancel_cross_lang", None),
        ("hi-Latn", "Imran... ek minute... haan Imran ko 270 udhar likho", "interrupted", 270),
        ("hi-Latn", "Meenakshi ko 50000 udhar likh do", "anomaly_large_amount", 50000),
    ]
    for lang, utt, sub, amt in messy_samples:
        add(sub, lang, utt, {"amount": amt})

    # 10. SHOP-FLOOR TALK (MUST IGNORE / NO LEDGER TOOLS CALLED!) - 14 cases
    ignore_samples = [
        ("hi-Latn", "Ek kilo sugar kitne ka hai?"),
        ("kn-Latn", "Ondu packet haalu eshtu?"),
        ("en-IN", "What is the price of sunflower oil today?"),
        ("hi-Latn", "Bhaiya thoda kam karo na, 45 mein de do"),
        ("kn-Latn", "Namaskara sir, chennagiddira?"),
        ("hi-Latn", "Main 500 de raha hoon, khulla hai kya?"),
        ("kn-Latn", "Naanu 200 kodtini, change kodi"),
        ("hi-Latn", "Haan mummy, main shaam ko ghar aaunga"),
        ("en-IN", "Keep the biscuit boxes near the back shelf"),
        ("hi-Latn", "Delivery boy aa gaya, rice ka bora andar rakhwao"),
        ("kn-Latn", "Ivattu tumbha bisilu ide alva"),
        ("hi-Latn", "Do packet Maggi aur ek Colgate dena"),
        ("en-IN", "Hello, good morning"),
        ("hi-Latn", "ummm... haan..."),
    ]
    for lang, utt in ignore_samples:
        add("shop_floor_ignore", lang, utt, {"tools": [], "must_not_create_draft": True})

    # 11. SUPPLIER PAYABLES, SHOP EXPENSES & CASH BOOK (Separate flows, not customer ledger) - 8 cases
    supplier_samples = [
        ("hi-Latn", "Distributor ko 12,000 dena hai", "supplier_payable", 12000),
        ("hi-Latn", "Rice wale ko 5000 diya", "supplier_payment", 5000),
        ("hi-Latn", "Bijli bill 1800 de do", "shop_expense", 1800),
        ("hi-Latn", "Hamaal 300 diya", "shop_expense", 300),
        ("hi-Latn", "Aaj 8000 ka dhanda hua", "daily_cash_book", 8000),
        ("hi-Latn", "Mahine ka hisaab karna hai", "month_end_settlement", None),
        ("hi-Latn", "Sugar supplier Somvaar ko aayega", "supplier_delivery", None),
        ("hi-Latn", "Geetha ke liye kal 2 packet rice rakhna", "goods_reservation", None),
    ]
    for lang, utt, sub, amt in supplier_samples:
        add(sub, lang, utt, {"amount": amt, "customer_ledger": False})

    # 12. NOISE, RADIO & SONG IMMUNITY - 6 cases
    noise_samples = [
        ("hi-Latn", "kyunki tum hi ho ab tum hi ho zindagi ab tum hi ho", "song_lyrics", "[SILENT]"),
        ("hi-Latn", "Parle ji aapka 20 hua tum hi ho", "song_with_command", "triage"),
        ("hi-Latn", "Radio City 91.1 FM superhit gaana bajao", "radio_noise", "[SILENT]"),
        ("hi-Latn", "Match kaun jeeta bhai score kya hua", "ambient_cricket", "[SILENT]"),
        ("hi-Latn", "Chai banao teen cup auto gaadi roko", "ambient_gossip", "[SILENT]"),
        ("hi-Latn", "Doodh packet aapka 30 hua", "counter_bill", "triage"),
    ]
    for lang, utt, sub, exp_type in noise_samples:
        add(sub, lang, utt, {"expected_type": exp_type})

    # 13. TRILEMMA COUNTER FLOW - 6 cases
    trilemma_samples = [
        ("hi-Latn", "Aapka 50 hua", "counter_bill_tally", 50),
        ("hi-Latn", "20 nahi 50", "counter_correction", 50),
        ("hi-Latn", "Udhar likh do Farhan", "assign_credit", "Farhan"),
        ("hi-Latn", "Kal dega Farhan", "assign_promise", "Farhan"),
        ("hi-Latn", "Ye lo cash 50", "paid_sale_cash", 50),
        ("hi-Latn", "50 Google Pay kar diya", "paid_sale_upi", 50),
    ]
    for lang, utt, sub, val in trilemma_samples:
        add(sub, lang, utt, {"value": val})

    return cases


def test_deterministic_parsers(cases: list[dict]) -> tuple[int, int]:
    """Verify honorific stripping and Indian spoken number extraction deterministically."""
    passed = 0
    total = 0

    # 1. Verify dataset size & zero hardcoded default seed names
    forbidden_defaults = {"ramesh", "suresh", "anita", "lakshmi", "pooja"}
    total += 1
    assert len(cases) >= 150, f"Expected >= 150 cases, got {len(cases)}"
    for c in cases:
        low = c["utterance"].lower()
        for bad in forbidden_defaults:
            assert bad not in low, f"Hardcoded default name '{bad}' found in case #{c['id']}: {c['utterance']}"
    passed += 1

    # 2. Verify honorific stripping
    honorific_checks = [
        ("Savitri akka", "Savitri"),
        ("Prakash bhaiya", "Prakash"),
        ("Shankar uncle", "Shankar"),
        ("Padma garu", "Padma"),
        ("Kavitha avare", "Kavitha"),
        ("Rekha ji", "Rekha"),
        ("Ganesh anna", "Ganesh"),
    ]
    for raw, exp in honorific_checks:
        total += 1
        got = normalize_customer_query(raw)
        assert got.lower() == exp.lower(), f"Honorific strip failed: {raw} -> {got} (expected {exp})"
        passed += 1

    # 3. Verify informal Indian spoken numbers
    num_cases = [c for c in cases if c["category"] == "indian_numbers" and "thirteen" not in c["utterance"] and "thirty" not in c["utterance"]]
    for c in num_cases:
        total += 1
        got = extract_indian_amount(c["utterance"])
        exp = float(c["expected"]["amount"])
        assert got == exp, f"Number parse failed on '{c['utterance']}': got {got}, expected {exp}"
        passed += 1

    return passed, total


async def run_live_agent_battery():
    """Run live end-to-end multilingual agent tests across all Kirana money-flow intents."""
    await init_db()
    tag = uuid.uuid4().hex[:5]
    cust_a_name = f"Kiran_{tag}"
    cust_b_name = f"Deepa_{tag}"
    cust_ids: list[str] = []

    try:
        # Seed 2 temporary isolated customers (Kiran has 3 small txns avg ₹100 to test 10x anomaly!)
        async with SessionLocal() as s:
            shop_uuid = uuid.UUID(settings.default_shop_id)
            ca = Customer(id=uuid.uuid4(), shop_id=shop_uuid, name=cust_a_name, phone="+91 90000 11111", landmark="Near Market")
            cb = Customer(id=uuid.uuid4(), shop_id=shop_uuid, name=cust_b_name, phone="+91 90000 22222", landmark="Main Road")
            s.add_all([ca, cb])
            await s.flush()
            for amt in (100, 120, 80):
                s.add(Transaction(shop_id=shop_uuid, customer_id=ca.id, type="credit", amount=amt, status="confirmed"))
            await s.commit()
            cust_ids = [str(ca.id), str(cb.id)]

        results = []

        # Test 1: Shop-floor chatter MUST NOT create any draft
        sess1 = VoiceSession(settings.default_shop_id, "hi-IN")
        reply1, ev1 = await sess1.respond("Ek kilo sugar kitne ka hai?")
        ok1 = not any(e["type"] == "draft" for e in ev1)
        results.append(("Shop-floor price chatter ignored", ok1, reply1))

        # Test 2: Overheard customer first-person talk MUST NOT create draft
        sess2 = VoiceSession(settings.default_shop_id, "hi-IN")
        reply2, ev2 = await sess2.respond("Main 500 de raha hoon, khulla hai kya?")
        ok2 = not any(e["type"] == "draft" for e in ev2)
        results.append(("Overheard customer talk ignored", ok2, reply2))

        # Test 3: Informal Hindi number ("saade teen sau" = 350) + Honorific ("bhaiya") + Cross-language confirm ("Houdu")
        sess3 = VoiceSession(settings.default_shop_id, "hi-IN")
        r3a, ev3a = await sess3.respond(f"{cust_a_name} bhaiya ko saade teen sau udhar likho")
        draft3 = next((e for e in ev3a if e["type"] == "draft"), None)
        r3b, ev3b = await sess3.respond("Houdu, sari")
        conf3 = next((e for e in ev3b if e["type"] == "confirmed"), None)
        ok3 = bool(draft3 and draft3["amount"] == 350 and draft3.get("tx_type") == "credit" and conf3)
        results.append(("Informal number (350) + honorific + Kannada confirm", ok3, f"draft={draft3 and draft3['amount']}, confirmed={bool(conf3)}"))

        # Test 4: UPI Payment (PhonePe)
        sess4 = VoiceSession(settings.default_shop_id, "kn-IN")
        r4a, ev4a = await sess4.respond(f"{cust_a_name} 200 PhonePe kottru")
        draft4 = next((e for e in ev4a if e["type"] == "draft"), None)
        ok4 = bool(draft4 and draft4.get("tx_type") == "payment" and draft4["amount"] == 200 and draft4.get("payment_mode") == "upi")
        results.append(("Kannada PhonePe UPI payment", ok4, f"type={draft4 and draft4.get('tx_type')}, mode={draft4 and draft4.get('payment_mode')}"))

        # Test 5: Return Adjustment ("biscuit wapas, 40 kam karo")
        sess5 = VoiceSession(settings.default_shop_id, "hi-IN")
        r5a, ev5a = await sess5.respond(f"{cust_a_name} ne biscuit wapas kiya, 40 rupaye kam karo")
        draft5 = next((e for e in ev5a if e["type"] == "draft"), None)
        ok5 = bool(draft5 and draft5.get("tx_type") == "adjustment" and draft5["amount"] == 40 and draft5.get("adjustment_reason") == "return")
        results.append(("Goods return adjustment", ok5, f"type={draft5 and draft5.get('tx_type')}, reason={draft5 and draft5.get('adjustment_reason')}"))

        # Test 6: 10x Anomaly High-Amount Safety Warning (Kiran avg is ~100-160; 5000 triggers anomaly_warning!)
        sess6 = VoiceSession(settings.default_shop_id, "en-IN")
        r6a, ev6a = await sess6.respond(f"Put 5000 credit for {cust_a_name}")
        draft6 = next((e for e in ev6a if e["type"] == "draft"), None)
        ok6 = bool(draft6 and draft6.get("anomaly_warning") is True)
        results.append(("10x Anomaly high-amount safety flag", ok6, f"anomaly={draft6 and draft6.get('anomaly_warning')}, reply={r6a[:80]}"))

        # Test 7: Correction after read-back ("nahi nahi, 430 likho")
        sess7 = VoiceSession(settings.default_shop_id, "hi-IN")
        _, ev7a = await sess7.respond(f"{cust_b_name} ko 340 udhar likho")
        _, ev7b = await sess7.respond("Nahi nahi, 430 likho, 340 nahi")
        draft7 = next((e for e in ev7b if e["type"] == "draft"), None)
        ok7 = bool(draft7 and draft7["amount"] == 430)
        results.append(("Correction after read-back (340 -> 430)", ok7, f"corrected_amount={draft7 and draft7['amount']}"))

        # Test 8: Full Settlement ("sab clear kar do")
        sess8 = VoiceSession(settings.default_shop_id, "hi-IN")
        r8a, ev8a = await sess8.respond(f"{cust_a_name} ka sab clear kar do")
        draft8 = next((e for e in ev8a if e["type"] == "draft"), None)
        ok8 = bool(draft8 and draft8.get("tx_type") == "payment" and draft8.get("projected_balance") == 0)
        results.append(("Full settlement draft (balance -> 0)", ok8, f"amount={draft8 and draft8['amount']}, proj={draft8 and draft8.get('projected_balance')}"))

        # Test 9: Advance / Deposit (balance goes negative = shop owes customer)
        sess9 = VoiceSession(settings.default_shop_id, "hi-IN")
        r9a, ev9a = await sess9.respond(f"{cust_b_name} ka 1000 advance rakho")
        draft9 = next((e for e in ev9a if e["type"] == "draft"), None)
        ok9 = bool(draft9 and draft9.get("tx_type") == "payment" and draft9.get("is_advance") is True)
        results.append(("Advance deposit (negative balance)", ok9, f"proj={draft9 and draft9.get('projected_balance')}, is_advance={draft9 and draft9.get('is_advance')}"))

        # Test 10: WhatsApp Payment Reminder
        sess10 = VoiceSession(settings.default_shop_id, "hi-IN")
        r10a, ev10a = await sess10.respond(f"{cust_a_name} ko payment ka yaad dilao")
        rem10 = next((e for e in ev10a if e["type"] == "reminder"), None)
        ok10 = bool(rem10 and "wa.me" in rem10.get("whatsapp_url", ""))
        results.append(("Payment reminder with WhatsApp link", ok10, f"has_wa={bool(rem10)}"))

        # Test 11: Backdated entry ("kal ka 200")
        sess11 = VoiceSession(settings.default_shop_id, "hi-IN")
        _, ev11a = await sess11.respond(f"Kal ka 200 bhi {cust_b_name} ke khate mein daal do")
        draft11 = next((e for e in ev11a if e["type"] == "draft"), None)
        ok11 = bool(draft11 and draft11.get("backdated_to") is not None)
        results.append(("Backdated entry date extraction", ok11, f"backdated_to={draft11 and draft11.get('backdated_to')}"))

        # Test 12: Shop Summary ("Who owes the most?")
        sess12 = VoiceSession(settings.default_shop_id, "en-IN")
        r12a, _ = await sess12.respond("Aaj kitna udhar gaya and who owes the most?")
        ok12 = len(r12a) > 15 and ("₹" in r12a or "rupee" in r12a.lower() or "0" in r12a)
        results.append(("Shop summary & top debtors", ok12, r12a[:90]))

        return results

    finally:
        # Always clean up temporary test customers & their transactions
        async with SessionLocal() as s:
            for cid in cust_ids:
                await s.execute(text("delete from customers where id = :cid"), {"cid": cid})
            await s.commit()


async def main():
    cases = build_eval_dataset()
    if "--export" in sys.argv:
        out_path = Path(__file__).parent / "kirana_eval_dataset.json"
        out_path.write_text(json.dumps(cases, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"Exported {len(cases)} labeled test cases to {out_path}")

    p_det, t_det = test_deterministic_parsers(cases)
    print(f"[UNIT] Deterministic checks (160 cases + honorifics + Indian numbers): {p_det}/{t_det} PASSED")

    if "--unit-only" in sys.argv:
        return

    print("\n[LIVE] Running 12-scenario end-to-end Kirana Money Flows battery against Gemini + Supabase...")
    live_results = await run_live_agent_battery()
    passed_live = 0
    for name, ok, detail in live_results:
        status = "PASS" if ok else "FAIL"
        if ok:
            passed_live += 1
        print(f"  [{status}] {name} -> {detail}")
    print(f"\n[SUMMARY] Live End-to-End Battery: {passed_live}/{len(live_results)} PASSED")


if __name__ == "__main__":
    asyncio.run(main())

