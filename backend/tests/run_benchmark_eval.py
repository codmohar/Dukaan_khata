"""DukaanAI 176-Case Benchmark Evaluation Test Suite.

Evaluates the Kirana Conversational AI across all 25 operational categories:
1. Product inquiry & shop floor talk (silent immunity)
2. Walk-in cash purchase (silent immunity)
3. Credit purchase / udhar
4. Payment received (cash, UPI, PhonePe, GPay, Paytm)
5. Change calculation (no customer debt change)
6. Partial payment
7. Full settlement ("sab clear", "ella clear")
8. Bad debt write-off
9. Advance / deposit (balance goes negative/advance)
10. Product return adjustment
11. Discount & round-off adjustment
12. Corrections after read-back ("nahi 430 likho")
13. Guarded undo ("last entry delete maadi")
14. Customer balance inquiry
15. Shop daily summary & top debtors
16. Shop Cash Book: Cash In
17. Shop Cash Book: Cash Out / Expense
18. Shop Cash Book: Cash Balance Inquiry
19. Compound multi-transactions in one sentence
20. Multi-turn continuation
21. Disambiguation
22. Dynamic names (pan-Indian names)
23. Payment promise recording & query
24. Safety / Anomaly alerts
25. Background song & noise immunity
"""
import asyncio
import json
import os
from pathlib import Path
import sys
import uuid

# Ensure backend app is importable
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
os.environ["DATABASE_URL"] = os.getenv("TEST_DATABASE_URL", "postgresql+asyncpg://postgres:postgrespassword@db:5432/dukaan")

from app.agent import tools
from app.agent.conversation_cache import ShopConversationCacheManager
from app.agent.fast_engine import clean_ambient_noise_and_songs, try_fast_path
from app.agent.pipeline import VoiceSession
from app.db import SessionLocal, init_db
from app.models import Customer, Shop, Transaction

DATASET_FILE = Path(__file__).parent / "kirana_benchmark_dataset.json"


def generate_benchmark_dataset() -> list[dict]:
    cases = []

    def c(cat: str, lang: str, text: str, expected_intent: str, exp: dict):
        cases.append({
            "id": len(cases) + 1,
            "category": cat,
            "language": lang,
            "utterance": text,
            "expected_intent": expected_intent,
            "expected": exp,
        })

    # 1. Product Inquiries (Must be silent, no draft) - 7 cases
    inquiries = [
        ("kn-IN", "shyam ake pucha ki parleg lena hae 15 rupae ka", "inquiry", {"silent": True}),
        ("kn-Latn", "Manjunatha bandu 1 packet biscuit kelidru 20 rupayi", "inquiry", {"silent": True}),
        ("hi-IN", "एक किलो चीनी कितने का है भैया?", "inquiry", {"silent": True}),
        ("hi-Latn", "Ek kilo sugar kitne ka hai?", "inquiry", {"silent": True}),
        ("kn-Latn", "Ondu packet haalu eshtu bele?", "inquiry", {"silent": True}),
        ("en-IN", "What is the price of sunflower oil today?", "inquiry", {"silent": True}),
        ("hi-Latn", "Do packet Maggi aur ek Colgate lena hai kitne ka hua", "inquiry", {"silent": True}),
    ]
    for lang, text, intent, exp in inquiries:
        c("product_inquiry", lang, text, intent, exp)

    # 2. Walk-in cash purchase (Must be silent, no debt draft) - 7 cases
    walk_in = [
        ("hi-Latn", "Ye lo 50 cash", "paid_sale", {"silent": True}),
        ("hi-Latn", "50 Google Pay kar diya bhaiya", "paid_sale", {"silent": True}),
        ("kn-Latn", "Naanu 200 kodtini, change kodi", "paid_sale", {"silent": True}),
        ("hi-Latn", "Main 500 de raha hoon, khulla hai kya?", "paid_sale", {"silent": True}),
        ("en-IN", "Here is 100 rupees for the milk", "paid_sale", {"silent": True}),
        ("kn-Latn", "Ye lo note diya 100 rupayi", "paid_sale", {"silent": True}),
        ("hi-Latn", "Ye lo bhaiya 30 rupaye poore ho gaye", "paid_sale", {"silent": True}),
    ]
    for lang, text, intent, exp in walk_in:
        c("paid_walk_in", lang, text, intent, exp)

    # 3. Credit Purchase (Udhar) - 8 cases
    credits = [
        ("kn-Latn", "Basavaraj ge 340 udhar bardu", "credit", {"customer": "Basavaraj", "amount": 340, "tx_type": "credit"}),
        ("kn-Latn", "Kavitha avare account ge 180 baaki haaki", "credit", {"customer": "Kavitha", "amount": 180, "tx_type": "credit"}),
        ("kn-IN", "ಬಸವರಾಜ್ ಗೆ 450 ಉಧಾರ್ ಬರೆದು ಹಾಕಿ", "credit", {"customer": "Basavaraj", "amount": 450, "tx_type": "credit"}),
        ("hi-Latn", "Imran ke khate mein 650 udhaar daal do", "credit", {"customer": "Imran", "amount": 650, "tx_type": "credit"}),
        ("hi-IN", "दिनेश के खाते में 780 उधार लिख दो", "credit", {"customer": "Dinesh", "amount": 780, "tx_type": "credit"}),
        ("en-IN", "Add 890 udhar for Naveen", "credit", {"customer": "Naveen", "amount": 890, "tx_type": "credit"}),
        ("hi-Latn", "Meenakshi ko 290 baaki likh do", "credit", {"customer": "Meenakshi", "amount": 290, "tx_type": "credit"}),
        ("kn-Latn", "Harish ge 520 udri barkoli", "credit", {"customer": "Harish", "amount": 520, "tx_type": "credit"}),
    ]
    for lang, text, intent, exp in credits:
        c("credit_sale", lang, text, intent, exp)

    # 4. Payments Received (Cash / UPI) - 8 cases
    payments = [
        ("kn-Latn", "Basavaraj 500 kottru", "payment", {"customer": "Basavaraj", "amount": 500, "tx_type": "payment"}),
        ("kn-Latn", "Kavitha 300 PhonePe maadidru", "payment", {"customer": "Kavitha", "amount": 300, "tx_type": "payment", "mode": "upi"}),
        ("hi-Latn", "Imran ne 200 PhonePe kiya", "payment", {"customer": "Imran", "amount": 200, "tx_type": "payment", "mode": "upi"}),
        ("hi-Latn", "Meenakshi ne 450 GPay se jama kiya", "payment", {"customer": "Meenakshi", "amount": 450, "tx_type": "payment", "mode": "upi"}),
        ("hi-Latn", "Dinesh ne 600 Paytm bheja", "payment", {"customer": "Dinesh", "amount": 600, "tx_type": "payment", "mode": "upi"}),
        ("hi-Latn", "Rekha ne 350 cash de diya", "payment", {"customer": "Rekha", "amount": 350, "tx_type": "payment", "mode": "cash"}),
        ("en-IN", "Karthik paid 700 by UPI", "payment", {"customer": "Karthik", "amount": 700, "tx_type": "payment", "mode": "upi"}),
        ("hi-IN", "नवीन ने 500 रुपये जमा किए", "payment", {"customer": "Naveen", "amount": 500, "tx_type": "payment"}),
    ]
    for lang, text, intent, exp in payments:
        c("payment_received", lang, text, intent, exp)

    # 5. Change Calculation (No customer debt changes) - 7 cases
    change_cases = [
        ("hi-Latn", "500 diye 150 change do", "change_calc", {"change": 350, "no_debt": True}),
        ("kn-Latn", "50 change kodi", "change_calc", {"change": 50, "no_debt": True}),
        ("hi-Latn", "50 change do", "change_calc", {"change": 50, "no_debt": True}),
        ("kn-Latn", "Chillar wapas kodi 20 rupayi", "change_calc", {"change": 20, "no_debt": True}),
        ("hi-Latn", "Kitna change wapas dena hai?", "change_calc", {"no_debt": True}),
        ("kn-Latn", "Eshtu change kodbeku?", "change_calc", {"no_debt": True}),
        ("en-IN", "Give 40 rupees change return", "change_calc", {"change": 40, "no_debt": True}),
    ]
    for lang, text, intent, exp in change_cases:
        c("change_calculation", lang, text, intent, exp)

    # 6. Partial Payment - 7 cases
    partials = [
        ("hi-Latn", "Shanta ne 500 mein se 300 diya, baaki baad mein", "payment", {"customer": "Shanta", "amount": 300, "tx_type": "payment"}),
        ("kn-Latn", "Vandana 600 alli 250 kottru, baaki naale", "payment", {"customer": "Vandana", "amount": 250, "tx_type": "payment"}),
        ("en-IN", "Mallika paid 400 out of 1000 today by cash", "payment", {"customer": "Mallika", "amount": 400, "tx_type": "payment"}),
        ("hi-Latn", "Tariq ne 1000 mein se 600 PhonePe kiya", "payment", {"customer": "Tariq", "amount": 600, "tx_type": "payment"}),
        ("hi-Latn", "Deepak ne 800 mein se 400 chuka diya", "payment", {"customer": "Deepak", "amount": 400, "tx_type": "payment"}),
        ("kn-Latn", "Harish 500 alli 200 kottru", "payment", {"customer": "Harish", "amount": 200, "tx_type": "payment"}),
        ("en-IN", "Naveen gave 350 partial payment", "payment", {"customer": "Naveen", "amount": 350, "tx_type": "payment"}),
    ]
    for lang, text, intent, exp in partials:
        c("partial_payment", lang, text, intent, exp)

    # 7. Full Settlement ("Sab clear", "Ella clear") - 7 cases
    settles = [
        ("hi-Latn", "Imran ka sab clear kar do", "full_settlement", {"customer": "Imran"}),
        ("hi-Latn", "Meenakshi ka hisaab chukta ho gaya cash mein", "full_settlement", {"customer": "Meenakshi", "mode": "cash"}),
        ("hi-Latn", "Dinesh ka hisaab barabar kar do PhonePe se", "full_settlement", {"customer": "Dinesh", "mode": "upi"}),
        ("kn-Latn", "Basavaraj du ellaa clear maadi", "full_settlement", {"customer": "Basavaraj"}),
        ("kn-Latn", "Kavitha avaru poora settle maadidru", "full_settlement", {"customer": "Kavitha"}),
        ("en-IN", "Settle Prakash account completely in cash", "full_settlement", {"customer": "Prakash", "mode": "cash"}),
        ("hi-IN", "रेखा का पूरा हिसाब चुकता कर दो", "full_settlement", {"customer": "Rekha"}),
    ]
    for lang, text, intent, exp in settles:
        c("full_settlement", lang, text, intent, exp)

    # 8. Bad Debt Write-off - 7 cases
    write_offs = [
        ("hi-Latn", "Tariq ka hisaab band karo, bad debt write off", "write_off", {"customer": "Tariq", "write_off": True}),
        ("en-IN", "Write off Yogesh unpaid balance permanently", "write_off", {"customer": "Yogesh", "write_off": True}),
        ("kn-Latn", "Raghu account close maadi write off", "write_off", {"customer": "Raghu", "write_off": True}),
        ("hi-Latn", "Shankar ka pura baaki maaf kar ke band karo", "write_off", {"customer": "Shankar", "write_off": True}),
        ("hi-Latn", "Manoj ka udhar write off kar do", "write_off", {"customer": "Manoj", "write_off": True}),
        ("en-IN", "Close and write off debts for Imran", "write_off", {"customer": "Imran", "write_off": True}),
        ("kn-IN", "ರಘು ಸಾಲ ಮನ್ನಾ ಮಾಡಿ ರೈಟ್ ಆಫ್ ಮಾಡಿ", "write_off", {"customer": "Raghu", "write_off": True}),
    ]
    for lang, text, intent, exp in write_offs:
        c("bad_debt_write_off", lang, text, intent, exp)

    # 9. Advance Payment / Deposit - 7 cases
    advances = [
        ("hi-Latn", "Zoya ka 1000 advance rakho", "advance", {"customer": "Zoya", "amount": 1000, "tx_type": "payment"}),
        ("kn-Latn", "Shankar 1500 advance mungaada kottru", "advance", {"customer": "Shankar", "amount": 1500, "tx_type": "payment"}),
        ("en-IN", "Keep 2000 deposit advance for Bhavna via UPI", "advance", {"customer": "Bhavna", "amount": 2000, "tx_type": "payment", "mode": "upi"}),
        ("hi-Latn", "Raghu ne 500 advance jama karwaya cash mein", "advance", {"customer": "Raghu", "amount": 500, "tx_type": "payment", "mode": "cash"}),
        ("kn-Latn", "Ganesh 1000 advance deposit kotta", "advance", {"customer": "Ganesh", "amount": 1000, "tx_type": "payment"}),
        ("hi-Latn", "Sunil ka 2500 advance deposit likho", "advance", {"customer": "Sunil", "amount": 2500, "tx_type": "payment"}),
        ("en-IN", "Record 500 advance from Rekha", "advance", {"customer": "Rekha", "amount": 500, "tx_type": "payment"}),
    ]
    for lang, text, intent, exp in advances:
        c("advance_deposit", lang, text, intent, exp)

    # 10. Product Returns - 7 cases
    returns = [
        ("hi-Latn", "Farida ne wo biscuit wapas kiya, 40 kam karo", "return", {"customer": "Farida", "amount": 40, "tx_type": "adjustment", "reason": "return"}),
        ("kn-Latn", "Ganesh biscuit packet return maadidru, 60 kadime maadi", "return", {"customer": "Ganesh", "amount": 60, "tx_type": "adjustment", "reason": "return"}),
        ("en-IN", "Shanta returned 1L oil, reduce 140 from account", "return", {"customer": "Shanta", "amount": 140, "tx_type": "adjustment", "reason": "return"}),
        ("hi-Latn", "Vandana ka soap wapas aaya, 35 rupaye return adjust karo", "return", {"customer": "Vandana", "amount": 35, "tx_type": "adjustment", "reason": "return"}),
        ("hi-IN", "मल्लिका ने आटा वापस किया 120 कम करो", "return", {"customer": "Mallika", "amount": 120, "tx_type": "adjustment", "reason": "return"}),
        ("hi-Latn", "Savitri ka kharab doodh return, 55 minus karo", "return", {"customer": "Savitri", "amount": 55, "tx_type": "adjustment", "reason": "return"}),
        ("kn-Latn", "Harish soap packet wapas kotta 45 kadime maadi", "return", {"customer": "Harish", "amount": 45, "tx_type": "adjustment", "reason": "return"}),
    ]
    for lang, text, intent, exp in returns:
        c("product_return", lang, text, intent, exp)

    # 11. Discounts & Round-off - 7 cases
    discounts = [
        ("hi-Latn", "Chillar chhodo, Zoya ke khate se 10 discount kam karo", "discount", {"customer": "Zoya", "amount": 10, "tx_type": "adjustment", "reason": "discount"}),
        ("en-IN", "Give 25 rupees discount adjustment to Bhavna", "discount", {"customer": "Bhavna", "amount": 25, "tx_type": "adjustment", "reason": "discount"}),
        ("kn-Latn", "Geetha ge 15 rupayi discount maadi", "discount", {"customer": "Geetha", "amount": 15, "tx_type": "adjustment", "reason": "discount"}),
        ("hi-Latn", "Padma ji ko 20 rupaye chhoot de do khate mein", "discount", {"customer": "Padma", "amount": 20, "tx_type": "adjustment", "reason": "discount"}),
        ("en-IN", "Round off 12 rupees discount on Karthik ledger", "discount", {"customer": "Karthik", "amount": 12, "tx_type": "adjustment", "reason": "discount"}),
        ("kn-Latn", "Harish 30 rupayi chillar discount haaki", "discount", {"customer": "Harish", "amount": 30, "tx_type": "adjustment", "reason": "discount"}),
        ("hi-Latn", "Chillar chhodo 50 discount likho Farhan", "discount", {"customer": "Farhan", "amount": 50, "tx_type": "adjustment", "reason": "discount"}),
    ]
    for lang, text, intent, exp in discounts:
        c("discount_adjustment", lang, text, intent, exp)

    # 12. Corrections - 7 cases
    corrections = [
        ("hi-Latn", "Nahi nahi, 430 likho, 340 nahi", "correction", {"amount": 430}),
        ("kn-Latn", "Alla, 430 antha bardu, 340 alla", "correction", {"amount": 430}),
        ("en-IN", "No, make it 520 instead", "correction", {"amount": 520}),
        ("hi-Latn", "20 nahi 50", "correction", {"amount": 50}),
        ("kn-Latn", "Alla 50 rupayi", "correction", {"amount": 50}),
        ("hi-Latn", "Nahi 500 likho 200 nahi", "correction", {"amount": 500}),
        ("en-IN", "Not 100 write 250", "correction", {"amount": 250}),
    ]
    for lang, text, intent, exp in corrections:
        c("correction_readback", lang, text, intent, exp)

    # 13. Guarded Undo - 7 cases
    undos = [
        ("kn-Latn", "Last entry delete maadi", "undo", {"guard": True}),
        ("hi-Latn", "Pichla entry hatao, galat ho gaya", "undo", {"guard": True}),
        ("en-IN", "Undo the last transaction for Imran", "undo", {"guard": True}),
        ("hi-IN", "पिछली एंट्री डिलीट करो", "undo", {"guard": True}),
        ("kn-IN", "ಹಿಂದಿನ ಎಂಟ್ರಿ ಡಿಲೀಟ್ ಮಾಡಿ", "undo", {"guard": True}),
        ("hi-Latn", "Last entry delete karo", "undo", {"guard": True}),
        ("en-IN", "Undo last", "undo", {"guard": True}),
    ]
    for lang, text, intent, exp in undos:
        c("guarded_undo", lang, text, intent, exp)

    # 14. Customer Balance Inquiries - 7 cases
    bal_queries = [
        ("kn-Latn", "Savitri akka ge eshtu baaki ide?", "balance_inquiry", {"customer": "Savitri"}),
        ("hi-Latn", "Imran ka kitna baaki hai?", "balance_inquiry", {"customer": "Imran"}),
        ("en-IN", "What is Kavitha's pending balance?", "balance_inquiry", {"customer": "Kavitha"}),
        ("hi-IN", "दिनेश का हिसाब कितना है?", "balance_inquiry", {"customer": "Dinesh"}),
        ("kn-IN", "ಬಸವರಾಜ್ ಬ್ಯಾಲೆನ್ಸ್ ಎಷ್ಟು ಇದೆ?", "balance_inquiry", {"customer": "Basavaraj"}),
        ("hi-Latn", "Deepak ka balance kitna hai", "balance_inquiry", {"customer": "Deepak"}),
        ("en-IN", "Check balance for Ramesh", "balance_inquiry", {"customer": "Ramesh"}),
    ]
    for lang, text, intent, exp in bal_queries:
        c("balance_inquiry", lang, text, intent, exp)

    # 15. Shop Daily Summary - 7 cases
    summaries = [
        ("hi-Latn", "Aaj kitna udhar gaya?", "shop_summary", {}),
        ("en-IN", "Who owes the most in the shop?", "shop_summary", {}),
        ("hi-Latn", "Sabse zyada baaki kiska hai?", "shop_summary", {}),
        ("kn-Latn", "Ivattu eshtu udhar aagide matte collection eshtu?", "shop_summary", {}),
        ("en-IN", "Show today's UPI and cash collection summary", "shop_summary", {}),
        ("hi-Latn", "Total dukaan ka kitna udhaar baaki hai?", "shop_summary", {}),
        ("hi-IN", "आज का हिसाब किताब समरी दिखाओ", "shop_summary", {}),
    ]
    for lang, text, intent, exp in summaries:
        c("shop_summary", lang, text, intent, exp)

    # 16. Shop Cash Book: Cash In - 7 cases
    cash_ins = [
        ("hi-Latn", "cash box mein 2000 daalo", "cash_in", {"amount": 2000}),
        ("kn-Latn", "cash box ge 1000 haaki", "cash_in", {"amount": 1000}),
        ("hi-Latn", "galle mein 500 jama karo", "cash_in", {"amount": 500}),
        ("en-IN", "cash in 1500", "cash_in", {"amount": 1500}),
        ("kn-IN", "ಗಲ್ಲಾಪೆಟ್ಟಿಗೆಗೆ 200 ಹಾಕಿ", "cash_in", {"amount": 200}),
        ("hi-IN", "कैश बॉक्स में 1000 डालो", "cash_in", {"amount": 1000}),
        ("hi-Latn", "cash drawer mein 800 rakho", "cash_in", {"amount": 800}),
    ]
    for lang, text, intent, exp in cash_ins:
        c("cash_book_in", lang, text, intent, exp)

    # 17. Shop Cash Book: Cash Out / Expense - 7 cases
    cash_outs = [
        ("hi-Latn", "500 kharch ke liye nikala", "cash_out", {"amount": 500}),
        ("kn-Latn", "500 kharchige tegedukonde", "cash_out", {"amount": 500}),
        ("hi-Latn", "cash box se 1000 nikaalo", "cash_out", {"amount": 1000}),
        ("en-IN", "cash out 400", "cash_out", {"amount": 400}),
        ("kn-Latn", "cash box inda 300 tegiri", "cash_out", {"amount": 300}),
        ("hi-IN", "खर्च के लिए 200 निकाला", "cash_out", {"amount": 200}),
        ("hi-Latn", "galle se 600 nikalo", "cash_out", {"amount": 600}),
    ]
    for lang, text, intent, exp in cash_outs:
        c("cash_book_out", lang, text, intent, exp)

    # 18. Shop Cash Book: Cash Balance - 7 cases
    cash_bals = [
        ("hi-Latn", "cash box mein kitna hai", "cash_balance", {}),
        ("kn-Latn", "cash box nalli eshtu ide", "cash_balance", {}),
        ("en-IN", "what is cash drawer balance", "cash_balance", {}),
        ("hi-Latn", "galla mein kitna hai", "cash_balance", {}),
        ("kn-Latn", "ivattu cash eshtu ide", "cash_balance", {}),
        ("hi-IN", "कैश बॉक्स में कितना है", "cash_balance", {}),
        ("kn-IN", "ಗಲ್ಲಾಪೆಟ್ಟಿಗೆಯಲ್ಲಿ ಎಷ್ಟು ಇದೆ", "cash_balance", {}),
    ]
    for lang, text, intent, exp in cash_bals:
        c("cash_book_balance", lang, text, intent, exp)

    # 19. Compound Multi-Transactions in One Sentence - 7 cases
    compounds = [
        ("kn-Latn", "Ramesh 500 kotta, Suresh ge 300 udhar haaki", "compound_tx", {"count": 2}),
        ("hi-Latn", "Anil 1000 diya aur Sunil ko 200 udhar", "compound_tx", {"count": 2}),
        ("en-IN", "Ramesh 500 payment and Suresh 300 credit", "compound_tx", {"count": 2}),
        ("kn-Latn", "Basavaraj 400 kottru, Kavitha ge 250 udhar", "compound_tx", {"count": 2}),
        ("hi-Latn", "Imran ne 300 PhonePe kiya aur Dinesh ko 450 udhar likho", "compound_tx", {"count": 2}),
        ("kn-Latn", "Ganesh 200 kotta mattu Harish ge 150 udhar haaki", "compound_tx", {"count": 2}),
        ("hi-Latn", "Deepak 600 diya, Farhan ko 100 udhar", "compound_tx", {"count": 2}),
    ]
    for lang, text, intent, exp in compounds:
        c("compound_multi_tx", lang, text, intent, exp)

    # 20. Multi-Turn Continuation - 7 cases
    multi_turns = [
        ("hi-Latn", "Udhar likh do Farhan", "multi_turn_credit", {"customer": "Farhan"}),
        ("hi-Latn", "Kal dega Farhan", "multi_turn_promise", {"customer": "Farhan"}),
        ("kn-Latn", "Udri bardu Manjunath", "multi_turn_credit", {"customer": "Manjunath"}),
        ("hi-Latn", "450 udhar", "partial_amount", {"amount": 450}),
        ("kn-Latn", "500 kottru", "partial_amount", {"amount": 500}),
        ("hi-Latn", "Pooja", "partial_name", {"customer": "Pooja"}),
        ("kn-Latn", "Manjunatha", "partial_name", {"customer": "Manjunatha"}),
    ]
    for lang, text, intent, exp in multi_turns:
        c("multi_turn_continuation", lang, text, intent, exp)

    # 21. Disambiguation - 7 cases
    disambigs = [
        ("hi-Latn", "1", "disambig_choice", {"choice": 1}),
        ("hi-Latn", "pehla wala", "disambig_choice", {"choice": 1}),
        ("hi-Latn", "dusra wala", "disambig_choice", {"choice": 2}),
        ("kn-Latn", "ondu", "disambig_choice", {"choice": 1}),
        ("kn-Latn", "eradu", "disambig_choice", {"choice": 2}),
        ("hi-Latn", "paan shop", "disambig_landmark", {"landmark": "paan shop"}),
        ("en-IN", "second one", "disambig_choice", {"choice": 2}),
    ]
    for lang, text, intent, exp in disambigs:
        c("disambiguation", lang, text, intent, exp)

    # 22. Dynamic Names (Pan-Indian names, no hardcoding) - 7 cases
    dynamic_names = [
        ("hi-Latn", "Debashis er kach theke 600 pelam", "dynamic_name", {"customer": "Debashis", "amount": 600}),
        ("kn-Latn", "Vignesh 250 kottru", "dynamic_name", {"customer": "Vignesh", "amount": 250}),
        ("hi-Latn", "Gurpreet kal 1000 dega", "dynamic_name", {"customer": "Gurpreet", "amount": 1000}),
        ("en-IN", "Put 410 on Prakash account as credit", "dynamic_name", {"customer": "Prakash", "amount": 410}),
        ("hi-Latn", "Farhan ne 300 PhonePe kiya", "dynamic_name", {"customer": "Farhan", "amount": 300}),
        ("kn-Latn", "Basavaraj ge 450 udri bariyiri", "dynamic_name", {"customer": "Basavaraj", "amount": 450}),
        ("hi-Latn", "Deepak ko 200 cash loan diya", "dynamic_name", {"customer": "Deepak", "amount": 200}),
    ]
    for lang, text, intent, exp in dynamic_names:
        c("dynamic_names", lang, text, intent, exp)

    # 23. Payment Promises - 7 cases
    promises = [
        ("hi-Latn", "Ramesh kal 500 dega", "promise_record", {"customer": "Ramesh", "amount": 500}),
        ("kn-Latn", "Suresh naale 200 kodtini andru", "promise_record", {"customer": "Suresh", "amount": 200}),
        ("en-IN", "Prakash will pay 600 on Saturday", "promise_record", {"customer": "Prakash", "amount": 600}),
        ("hi-Latn", "Rekha Sunday ko 250 dene ka wada kiya", "promise_record", {"customer": "Rekha", "amount": 250}),
        ("hi-Latn", "Kiska promise pending hai", "promise_query", {}),
        ("kn-Latn", "Yaara promise ide", "promise_query", {}),
        ("en-IN", "Check pending promises", "promise_query", {}),
    ]
    for lang, text, intent, exp in promises:
        c("payment_promises", lang, text, intent, exp)

    # 24. Safety / 10x Anomaly Alerts - 7 cases
    anomalies = [
        ("hi-Latn", "Meenakshi ko 50000 udhar likh do", "anomaly_safety", {"amount": 50000}),
        ("en-IN", "Put 75000 credit for Ramesh", "anomaly_safety", {"amount": 75000}),
        ("kn-Latn", "Suresh ge 40000 udhar haaki", "anomaly_safety", {"amount": 40000}),
        ("hi-Latn", "Continue anyway", "rule_override", {}),
        ("kn-Latn", "Niyam meeri continue maadi", "rule_override", {}),
        ("hi-Latn", "Phir bhi karo", "rule_override", {}),
        ("en-IN", "Override and continue", "rule_override", {}),
    ]
    for lang, text, intent, exp in anomalies:
        c("anomaly_safety", lang, text, intent, exp)

    # 25. Noise and Song Immunity - 7 cases
    noise_cases = [
        ("hi-Latn", "kyunki tum hi ho ab tum hi ho zindagi ab tum hi ho", "noise_silent", {"silent": True}),
        ("hi-Latn", "Radio City 91.1 FM superhit gaana bajao", "noise_silent", {"silent": True}),
        ("hi-Latn", "Match kaun jeeta bhai score kya hua", "noise_silent", {"silent": True}),
        ("hi-Latn", "Chai banao teen cup auto gaadi roko", "noise_silent", {"silent": True}),
        ("kn-Latn", "Singara siriye belakina kavithe", "noise_silent", {"silent": True}),
        ("hi-Latn", "Parle ji aapka 20 hua tum hi ho", "noise_command", {"amount": 20}),
        ("kn-Latn", "Doodh packet aapka 30 hua rowdy baby", "noise_command", {"amount": 30}),
    ]
    for lang, text, intent, exp in noise_cases:
        c("noise_immunity", lang, text, intent, exp)

    return cases


async def run_evaluation():
    cases = generate_benchmark_dataset()
    print(f"Generated {len(cases)} benchmark test cases across 25 operational categories.", flush=True)

    # Export to json
    with open(DATASET_FILE, "w", encoding="utf-8") as f:
        json.dump(cases, f, ensure_ascii=False, indent=2)
    print(f"Exported dataset to {DATASET_FILE}", flush=True)

    # Seed all isolated shops in shops table in 1 query
    from sqlalchemy import text as sa_text
    async with SessionLocal() as s:
        await s.execute(sa_text("""
            INSERT INTO shops (id, name)
            SELECT ('11111111-0000-0000-0000-' || LPAD(i::text, 12, '0'))::uuid, 'Benchmark Shop ' || i
            FROM generate_series(1, 200) i
            ON CONFLICT (id) DO NOTHING
        """))
        await s.commit()
    print("Seeded isolated test namespaces.", flush=True)

    passed = 0
    failed = 0
    results_by_cat = {}

    for idx, item in enumerate(cases, 1):
        cat = item["category"]
        if cat not in results_by_cat:
            results_by_cat[cat] = {"total": 0, "passed": 0}
        results_by_cat[cat]["total"] += 1

        if idx % 15 == 0 or idx == len(cases):
            print(f"Progress: [{idx}/{len(cases)}] cases evaluated...", flush=True)

        # Use clean isolated shop ID for each test case
        case_shop_id = f"11111111-0000-0000-0000-{item['id']:012d}"
        async with SessionLocal() as s_clean:
            s_u = tools.to_uuid(case_shop_id)
            await s_clean.execute(sa_text("DELETE FROM transactions WHERE shop_id = :sid"), {"sid": s_u})
            await s_clean.execute(sa_text("DELETE FROM customers WHERE shop_id = :sid"), {"sid": s_u})
            await s_clean.commit()

        sess = VoiceSession(case_shop_id, language=item["language"])
        exp = item["expected"]
        ok = True

        try:
            # ----------------------------------------------------
            # Category-Specific Turn Setups
            # ----------------------------------------------------
            if cat == "correction_readback":
                # Pre-seed initial draft
                await sess.respond("Ramesh ge 340 udhar bardu")
                reply, events = await sess.respond(item["utterance"])
                exp_amt = exp.get("amount")
                draft = next((e for e in events if e.get("type") == "draft"), None)
                if not (draft and draft.get("amount") == exp_amt):
                    ok = False

            elif cat == "guarded_undo":
                # Pre-seed confirmed transaction
                await sess.respond("Ramesh 500 kotta")
                await sess.respond("Confirm")
                reply, events = await sess.respond(item["utterance"])
                low_r = reply.lower()
                if not any(w in low_r for w in ["delete", "undo", "raddhu", "galat", "hatao", "confirm"]):
                    ok = False

            elif cat == "full_settlement":
                cname = exp.get("customer", "Customer")
                # Pre-seed customer with balance
                await sess.respond(f"{cname} ge 500 udhar bardu")
                await sess.respond("Confirm")
                reply, events = await sess.respond(item["utterance"])
                draft = next((e for e in events if e.get("type") == "draft"), None)
                low_r = reply.lower()
                if not (draft or any(w in low_r for w in ["clear", "settle", "chukta", "barabar", "0"])):
                    ok = False

            elif cat == "bad_debt_write_off":
                cname = exp.get("customer", "Customer")
                # Pre-seed customer with balance
                await sess.respond(f"{cname} ge 500 udhar bardu")
                await sess.respond("Confirm")
                reply, events = await sess.respond(item["utterance"])
                draft = next((e for e in events if e.get("type") == "draft"), None)
                low_r = reply.lower()
                if not (draft or any(w in low_r for w in ["write off", "bad-debt", "band karo", "maaf", "close"])):
                    ok = False

            elif cat == "balance_inquiry":
                cname = exp.get("customer", "Customer")
                # Pre-seed customer with balance
                await sess.respond(f"{cname} ge 400 udhar bardu")
                await sess.respond("Confirm")
                reply, events = await sess.respond(item["utterance"])
                if reply == "[SILENT]" or ("₹" not in reply and "baaki" not in reply.lower() and "balance" not in reply.lower()):
                    ok = False

            elif cat == "multi_turn_continuation":
                intent = item["expected_intent"]
                if intent == "multi_turn_credit":
                    await sess.respond("Parle-G 500 hua")
                    reply, events = await sess.respond(item["utterance"])
                    draft = next((e for e in events if e.get("type") == "draft"), None)
                    if not (draft and draft.get("amount") == 500):
                        ok = False
                elif intent == "multi_turn_promise":
                    await sess.respond("Parle-G 500 hua")
                    reply, events = await sess.respond(item["utterance"])
                    p_ev = next((e for e in events if e.get("type") == "promise_card"), None)
                    if not (p_ev or "promise" in reply.lower() or "wada" in reply.lower()):
                        ok = False
                elif intent == "partial_amount":
                    await sess.respond("Farhan")
                    reply, events = await sess.respond(item["utterance"])
                    exp_amt = exp.get("amount")
                    draft = next((e for e in events if e.get("type") == "draft"), None)
                    if not (draft and draft.get("amount") == exp_amt):
                        ok = False
                elif intent == "partial_name":
                    await sess.respond("300 udhar")
                    reply, events = await sess.respond(item["utterance"])
                    draft = next((e for e in events if e.get("type") == "draft"), None)
                    if not (draft and draft.get("amount") == 300):
                        ok = False

            elif cat == "disambiguation":
                # Pre-seed 2 customers with same name Ramesh (one tailor, one paan shop)
                async with SessionLocal() as s:
                    s_uuid = tools.to_uuid(case_shop_id)
                    c1 = Customer(id=uuid.uuid4(), shop_id=s_uuid, name="Ramesh", landmark="tailor")
                    c2 = Customer(id=uuid.uuid4(), shop_id=s_uuid, name="Ramesh", landmark="paan shop")
                    s.add_all([c1, c2])
                    await s.commit()

                # Trigger disambiguation prompt
                await sess.respond("Ramesh ge 500 udhar bardu")
                reply, events = await sess.respond(item["utterance"])
                draft = next((e for e in events if e.get("type") == "draft"), None)
                if not draft:
                    ok = False

            elif cat == "anomaly_safety":
                intent = item["expected_intent"]
                if intent == "rule_override":
                    # Turn 1: trigger anomaly
                    await sess.respond("Meenakshi ko 50000 udhar likh do")
                    # Turn 2: evaluate override
                    reply, events = await sess.respond(item["utterance"])
                    conf = next((e for e in events if e.get("type") == "confirmed"), None)
                    if not (conf or "confirm" in reply.lower() or "khaatrigolislaagide" in reply.lower()):
                        ok = False
                else:
                    reply, events = await sess.respond(item["utterance"])
                    draft = next((e for e in events if e.get("type") == "draft"), None)
                    if not (draft and draft.get("anomaly_warning")):
                        ok = False

            else:
                # Standard single-turn execution
                reply, events = await sess.respond(item["utterance"])

                if exp.get("silent") and reply != "[SILENT]":
                    ok = False
                if exp.get("no_debt") and any(e.get("type") == "draft" for e in events):
                    ok = False
                if exp.get("count") and len([e for e in events if e.get("type") == "draft"]) != exp["count"]:
                    ok = False
                if exp.get("amount"):
                    draft = next((e for e in events if e.get("type") == "draft"), None)
                    cb_ev = next((e for e in events if e.get("type") in ("cash_in", "cash_out")), None)
                    amt = (draft and draft.get("amount")) or (cb_ev and cb_ev.get("amount"))
                    if cat == "noise_immunity" and exp.get("amount"):
                        if str(exp["amount"]) not in reply and f"₹{exp['amount']}" not in reply:
                            ok = False
                    elif amt is not None and amt != exp["amount"]:
                        ok = False
                if exp.get("tx_type") and not any(e.get("tx_type") == exp["tx_type"] or e.get("type") == exp["tx_type"] for e in events):
                    ok = False

        except Exception as ex:
            ok = False
            reply = f"Exception: {ex}"
            events = []

        if ok:
            passed += 1
            results_by_cat[cat]["passed"] += 1
        else:
            failed += 1
            print(f"FAILED Case #{item['id']} ({cat}): '{item['utterance']}' -> Reply: '{reply[:60]}', Events: {events}")

    total = len(cases)
    accuracy = (passed / total) * 100
    print("\n" + "=" * 60)
    print(f"BENCHMARK EVALUATION RESULTS: {passed}/{total} Passed ({accuracy:.1f}% Accuracy)")
    print("=" * 60)
    for cat, res in sorted(results_by_cat.items()):
        cat_acc = (res["passed"] / res["total"]) * 100
        print(f" - {cat:<26}: {res['passed']}/{res['total']} ({cat_acc:.0f}%)")

    assert accuracy >= 95.0, f"Benchmark accuracy {accuracy:.1f}% below 95% requirement!"
    print("\n✓ SUCCESS: Benchmark evaluation passed (>95% threshold achieved)!")


if __name__ == "__main__":
    asyncio.run(run_evaluation())
