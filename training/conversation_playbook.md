# Kirana Shop Talk and Money Flows: A Guide for Training DukaanAI

This guide documents the real-world conversational dynamics, money flows, and linguistic nuances of Indian kirana shops and small retail businesses. It serves as the training blueprint and evaluation standard for DukaanAI ("Hi Khata").

---

## 1. What People Talk About in a Shop

An always-listening or hands-free voice agent in a kirana counter hears continuous multi-party chatter. The primary architectural requirement is cleanly separating **Ledger Talk** (actionable accounting commands) from **Shop-Floor Talk** (ambient noise, customer boasting, and inquiries where the agent must remain strictly `[SILENT]`).

### Ledger Talk (The Agent Must Act On This)
- **Recording Udhar (Credit Sale):** "Ramesh ge 340 udhar bardu." / "Sunita ke naam 500 udhar likho."
- **Recording a Payment:** "Suresh 500 kottru." / "Ramesh ne 200 diya."
- **Asking a Balance:** "Lakshmi akka ge eshtu baaki ide?" / "Kitna baaki hai?"
- **Partial or Full Settlement:** "Sab clear kar do." / "Ella clear maadi." / "Hisaab chukta."
- **Corrections and Undo:** "Nahi nahi, 430 likho, 340 nahi." / "Last entry delete maadi."
- **Summary Questions:** "Aaj kitna udhar gaya?" / "Who owes the most?" / "Total dhanda kitna hua?"
- **Reminders:** "Ramesh ko yaad dilao." / "Payment reminder kalisi."
- **Backdated Entries:** "Kal ka 200 bhi daal do." / "Ninne du 350 haaki."

### Shop-Floor Talk (The Agent Must Stay Silent `[SILENT]`)
- **Product Requests & Price Questions:** "Ek kilo sugar kitne ka hai?" / "Ondu packet haalu eshtu?" / "Good Day biscuit hai kya?"
- **Bargaining, Greetings & Gossip:** "Bhaiya 45 mein de do na", "Namaskara sir, chennagiddira?", "Aaj bahut dhoop hai."
- **Customers Saying Their Own Amounts Aloud:** "Main 500 de raha hoon, khulla hai kya?"
  > ⚠️ **CRITICAL HAZARD:** A customer saying their own amount at the counter sounds superficially like a payment command, but it is purely ambient counter talk! If DukaanAI acts on overheard customer boasts, it creates phantom entries. Without an explicit shopkeeper instruction ("X ne diya" / "Likh lo"), DukaanAI outputs `[SILENT]`.
- **Background Music, Radio & Phone Calls:** Bollywood song lyrics ("tum hi ho"), FM radio broadcasts, cricket scores, and delivery supplier chit-chat must be sifted out cleanly.

---

## 2. Types of Money Transactions

| Type | What It Sounds Like | Effect on Customer Balance | DukaanAI Action & Tool Call | Needs Confirmation? |
| :--- | :--- | :--- | :--- | :--- |
| **Credit Sale (Udhar)** | "Ramesh ge 340 udhar bardu" | Balance increases | `create_draft(type="credit")` | **Yes** (always read back) |
| **Payment Received** | "Ramesh ne 200 PhonePe kiya" | Balance decreases | `create_draft(type="payment", payment_mode="upi")` | **Yes** (always read back) |
| **Partial Payment** | "500 mein se 300 diya, baaki baad mein" | Owes less (₹200 remains) | Propose net draft or split entry | **Yes** |
| **Full Settlement** | "Sab clear", "hisaab barabar" | Balance resets to 0 | `settle_balance(customer_id)` | **Yes** |
| **Advance / Deposit** | "1000 advance rakho" | Balance goes negative (shop owes customer) | `create_draft(type="payment", note="Advance")` | **Yes** |
| **Return of Goods** | "Wo biscuit wapas, 40 kam karo" | Balance decreases | `create_draft(type="adjustment", adjustment_reason="return")` | **Yes** |
| **Discount / Round-off** | "Chillar chhodo, 340 ki jagah 330" | Balance decreases | `create_draft(type="adjustment", adjustment_reason="discount")` | **Yes** |
| **Bad-Debt Write-Off** | "Is ka hisaab band karo" | Balance forced to 0 | `settle_balance(is_write_off=True)` (owner-only) | **Always** |
| **Paid Walk-In Sale** | "Parle liya, 10 diya. Ye lo change" | None (net cash transaction) | Output `[SILENT]` (no customer ledger entry) | No |
| **Cash Out** | Customer pays UPI, shop hands cash | Net zero | Output `[SILENT]` | No |
| **Supplier Purchase** | "Distributor ko 12,000 dena hai" | Shop payable (not customer) | Log to Payables (separate table) | Yes |
| **Supplier Payment** | "Rice wale ko 5000 diya" | Reduces shop payables | Log to Payables | Yes |
| **Shop Expenses** | "Bijli bill 1800", "Hamaal 300" | Shop cash expense | Log to Expenses | Yes |
| **Month-End Settlement**| "Mahine ka hisaab karna hai" | Multi-customer review | Trigger Reconciliation / Bulk Flow | Yes |

---

## 3. How People Actually Say It (Linguistic Matrix)

| Meaning | Kannada (Latin / Script) | Hindi / Hinglish | English / Indian English |
| :--- | :--- | :--- | :--- |
| **Credit / Write It Down** | udhar, udri, baaki, bardu, barkoli, haaki (ಉದ್ರಿ / ಬರೆದು ಹಾಕಿ) | udhaar, likh do, khate mein daal do, baaki | credit, put on tab, put on account, due |
| **Payment Received** | kottru, kottidru, bantu, jama (ಕೊಟ್ರು / ಜಮಾ) | de diya, jama, chuka diya, bhara | paid, gave, received, cleared via UPI |
| **Balance Query** | eshtu baaki ide? (ಎಷ್ಟು ಬಾಕಿ ಇದೆ?) | kitna baaki hai? / hisaab batao | what's the balance? / how much pending? |
| **Clear All / Settle** | ellaa clear maadi, settle maadi | sab clear, hisaab barabar, chukta | settle all, clear full balance |
| **Will Pay Later (Promise)**| naale kodtini, Somvaara kodtare | kal de dunga, Sunday ko dega | will pay tomorrow, paying on Saturday |
| **Cancel or Undo** | delete maadi, beda, illa | hatao, cancel, delete karo, pichla hatao | undo, delete last, cancel draft |
| **Correction** | alla, 430 antha bardu, 340 alla | nahi nahi, 430 likho, 340 nahi | no, make it 430, not 340 |

> **Regional Variants:** Kannada has distinct regional variants across Mysuru, Bengaluru, and Hubballi-Dharwad (*"haaki"*, *"barkoli"*, *"bariyiri"*, *"kottidru"*). In Hindi, Bengali, Punjabi, and Gujarati, the word **"kal"** means both yesterday and tomorrow—tense must be deduced from the auxiliary verb (*"de dunga"* = tomorrow; *"diye the"* = yesterday).

---

## 4. Spoken Amounts and Numbers

1. **Informal Indian Spoken Quantities:**
   - *dedh* = 1.5 (*dedh sau* = 150, *dedh hazaar* = 1,500)
   - *dhai* = 2.5 (*dhai sau* = 250, *dhai hazaar* = 2,500)
   - *sawa* = +0.25 (*sawa sau* = 125, *sawa hazaar* = 1,250)
   - *saade* = +0.5 (*saade teen sau* = 350, *saade chaar sau* = 450)
   - *paune* = -0.25 (*paune do sau* = 175, *paune teen sau* = 275, *paune hazaar* = 750)
   - Kannada: *innooru* (200), *mooru nooru* (300), *aidu nooru* (500), *savira* (1000), *eradu savira* (2000).
2. **Sound-Alike Numbers:**
   - Hindi *teen* (3) vs *tees* (30); English 13 vs 30.
   - **Rule:** DukaanAI must ALWAYS read back the exact numeric digits aloud with currency (*"₹30"* vs *"₹13"*).
3. **Dropped Currency Units:**
   - "Ramesh ge teen sau" has no word "rupees". In kirana context, assume Indian Rupees (₹).
4. **Lakh & Thousand Conversion:**
   - "Do hazaar paanch sau" -> automatically converted to numeric digits `2500`.
5. **10x Anomaly Safety Shield:**
   - Any transaction $\ge 10\times$ a customer's typical historical entry or $\ge ₹25,000$ triggers an explicit verbal confirmation step: *"Yeh amount customer ke normal entry se bohot zyada hai, kya aap sure hain?"*.

---

## 5. Handling Names & Disambiguation

1. **Disambiguation by Landmark & Balance:**
   - If "Ramesh" matches multiple records (e.g. "Ramesh (Paan Shop)" and "Ramesh (Auto Driver)"), DukaanAI never guesses. It prompts:
     *"Ramesh naam ke multiple customers hain: 1. Ramesh (Paan Shop, balance ₹400) | 2. Ramesh (Auto Driver, balance ₹1,200). Kiske naam likhun?"*.
2. **Relationship Suffixes:**
   - *anna, akka, bhaiya, didi, sir, uncle, aunty, garu, avare, ji*.
   - These are automatically stripped before customer matching (e.g. *"Lakshmi akka"* -> query *"Lakshmi"*).
3. **Nicknames & Shop Labels:**
   - *"Doodh wala Ramesh"*, *"Temple street Suresh"*, *"Mechanic Harish"*.
   - Mapped using full-text and trigram fuzzy matching against customer notes and landmarks.
4. **Household & Proxies:**
   - *"Ramesh ka beta aaya tha, uske naam likho."*
   - Handled via Household Khata resolving the family member while attributing the liability to the primary account.
5. **Cross-Script Transliteration:**
   - Speech-to-text engines may output Kannada or Devanagari script, while databases often store Latin characters. DukaanAI transparently normalizes and transliterates names across scripts.

---

## 6. The 184 Labeled Test Cases Evaluation Suite

The evaluation suite (`backend/tests/kirana_eval_dataset.json` and `backend/tests/eval_kirana_suite.py`) contains **184 labeled test sentences** across 13 core categories:

1. **Credit / Udhar (25 cases):** Kannada, Hindi, English, Tamil, Telugu, Marathi, Devanagari, and Kannada scripts.
2. **Payments & Payment Modes (25 cases):** Cash, PhonePe, GPay, Paytm, BHIM UPI, QR code, partial payments, advances.
3. **Full Settlement & Write-Off (12 cases):** "Sab clear", "ella clear maadi", bad-debt write-offs.
4. **Adjustments (14 cases):** Returns of damaged goods, price discounts, round-offs.
5. **Informal Indian Spoken Numbers (18 cases):** dedh, dhai, sawa, saade, paune, innooru, mooru nooru, sound-alikes.
6. **Balance Queries & Shop Summaries (16 cases):** Balance lookups, top debtors, today's collection summaries, WhatsApp reminders.
7. **Backdated Entries & Due Dates (10 cases):** "Kal ka 200", yesterday's credit, future payment promises.
8. **Names, Nicknames, Proxies & Honorifics (14 cases):** Household members, auto driver labels, phone updates.
9. **Messy Real-World Cases (16 cases):** Corrections after read-back ("nahi 430 likho 340 nahi"), two amounts in one sentence, two customers in one sentence, cross-language confirms.
10. **Shop-Floor Chatter (Must Ignore) (14 cases):** Price inquiries, customer boasts ("Main 500 de raha hoon"), phone chatter.
11. **Supplier Payables & Expenses (8 cases):** Distributor payables, electricity bills, hamaal expenses, daily cash book.
12. **Noise & Song Immunity (6 cases):** Sifting Bollywood song lyrics, radio chatter, and ambient market noise.
13. **Counter Bill Trilemma Flow (6 cases):** Bill total announcement, 3-way triage prompt, amount corrections, assign to credit/promise/cash.

### Running the Test Suite
```bash
# Run deterministic parser & entity extraction checks
python dukaan-ai/backend/tests/eval_kirana_suite.py --unit-only

# Run live 12-scenario battery against Gemini + Supabase
python dukaan-ai/backend/tests/eval_kirana_suite.py

# Export / refresh JSON dataset
python dukaan-ai/backend/tests/eval_kirana_suite.py --export
```
