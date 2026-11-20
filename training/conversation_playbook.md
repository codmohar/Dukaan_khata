# DukaanAI conversation playbook

Companion to `dukaan_conversations.jsonl` (143 labeled counter conversations, 14 language tags).
**Quality warning:** I wrote these in romanized form from general knowledge. Spelling and phrasing in Tamil, Telugu, Malayalam,
Marathi, Gujarati, Bengali, Punjabi, Odia, Assamese and Urdu **must be reviewed by native speakers** before being used as ground truth.
Treat them as a seed set to extend with real recordings from shops.

## 1. How to "train" this with Gemini
You are not training Gemini's weights. Three practical levels, in order:
1. **Prompt + few-shot** (now): paste the rules in section 6 into `agent/prompts.py` and add 10 to 20 examples from the JSONL.
2. **Eval set** (now): run every JSONL row through the agent after each prompt change; compare `intent`, `entries`, `action`.
3. **Fine-tune** (later): only after you have 1,000+ *real*, human-corrected conversations.

## 2. Two modes, and the speaker problem
| Mode | Who speaks | Agent behaviour |
|---|---|---|
| **Command** | Shopkeeper to the assistant (after wake word or mic tap): `U:` | Act: draft, read back, wait for confirm |
| **Ambient** | Shopkeeper and customer at the counter (`S:` / `C:`) | Only *suggest* a draft on screen. Never commit. Shopkeeper taps or says confirm |
| **Follow-up** | Assistant asked a question (`A:`), shopkeeper answers (`U:`) | Resolve the pending draft |

- Speech-to-text gives **no speaker labels**. The LLM must infer who is speaking from the words ("mera kitna baaki hai" = customer; "likh dun?" = shopkeeper).
- Ambient listening records customers who haven't agreed. Process audio on the fly, **do not store raw audio**, show a clear "listening" indicator, and put a notice at the counter. Check local privacy law.
- Default for v1: **command mode only**, ambient as an opt-in "suggest" mode.

## 3. Intent taxonomy (labels used in the dataset)
| Intent | Ledger effect | Default action |
|---|---|---|
| CREDIT_SALE | customer owes more | draft + read back |
| PAID_SALE (cash/UPI, with or without change) | none | ignore ledger (cash book later) |
| PAYMENT_RECEIVED (old dues, cash/UPI) | owes less | draft |
| PARTIAL_PAYMENT | credit full total + payment of part | draft two entries, show net |
| SETTLE_ALL | payment = current balance from DB | draft, amount from DB |
| ADVANCE | payment above balance, goes negative | draft, flag "shop owes customer" |
| CASH_LOAN (shop hands cash) | owes more | draft, mark `cash_loan` |
| CASH_OUT (customer pays UPI, shop gives cash) | none, net zero | ignore ledger |
| ADJUSTMENT (return, discount) | owes less | draft, needs `reason` |
| WRITE_OFF | balance forced to 0 | owner only, always read back |
| BALANCE_QUERY / SUMMARY_QUERY | none | answer from DB, never from memory |
| PROMISE_TO_PAY / REMINDER | none (or due date) | suggest reminder |
| DISPUTE ("maine de diya tha") | none | flag, search past payments, never create entry |
| CORRECTION / UNDO / CONFIRM | edit or cancel the pending draft | follow guardrails |
| SUPPLIER_PURCHASE / EXPENSE / CASH_BOOK | not customer ledger | later feature |
| SMALLTALK (price, change, gossip) | none | **ignore** |
| AMBIGUOUS | none | ask one short question |

## 4. The direction rule: who gave, who took?
"Liya / diya" (took / gave) flips meaning with the speaker and the marker word. Always resolve **from the shop's point of view**:

| Customer says | Meaning for the shop |
|---|---|
| "Parle liya" | customer took goods → sale |
| "500 diya" | customer handed money → payment or paid sale |
| "Parle liya, 500 diya" | paid sale; change goes back; **no ledger entry** |
| "Likh lo / udhar / baaki" or no money handed | credit sale |

| Language | "X paid the shop" | "shop gave X" (loan) |
|---|---|---|
| Hindi/Urdu | X **ne** diya | X **ko** diya |
| Kannada | X **inda** kottru | X **ge** kottidini |
| Tamil | X **kitta irundhu** vanginen | X **ku** kuduthen |
| Telugu | X **nunchi** techukunnanu | X **ki** ichanu |
| Malayalam | X **il ninnu** vaangi | X **inu** koduthu |
| Marathi | X **kadun** milale | X **la** dile |
| Gujarati | X **pase thi** madya | X **ne** apya (note: Gujarati *ne* marks the receiver) |
| Bengali | X **er kach theke** peyechi | X **ke** diyechi |
| Punjabi | X **kolon** mile | X **nu** ditte |
| Odia | X **tharu** pali | X **ku** dili |
| English | X paid | I gave X |

If the marker is missing or unclear ("Ramesh 200"), **ask**. Never guess direction.

## 5. Language cheat-sheet (romanized; verify with locals)
| Lang | Credit / write it | Paid | Balance? | Tomorrow | Yes | No |
|---|---|---|---|---|---|---|
| Hindi | udhaar, likh do, baaki | diya, jama | kitna baaki hai | kal | haan, theek hai, kar do | nahi, ruko, mat karo |
| Kannada | udhar, bardu, baaki | kottru, jama | eshtu baaki ide | naale | houdu, sari, maadi | illa, beda |
| Tamil | kadan, baaki, ezhuthunga | kuduthen, jama | evvalavu baaki | naalaiku | aama, sari | illa, vendam |
| Telugu | appu, baki, rayandi | ichanu, jama | entha baaki undi | repu | avunu, sare | ledu, vaddu |
| Malayalam | kadam, baaki, ezhuthikko | koduthu | ethra baaki | naale | athe, sheri | alla, venda |
| Marathi | udhar, liha, baki | dile, jama | kiti baaki aahe | udya | ho, thik aahe | nahi, nako |
| Gujarati | udhar, lakho, baki | apya, jama | ketlu baaki che | kal | ha, barabar | na, rehva do |
| Bengali | dhar, baki, likho | diyechi, joma | koto baki | kal | hyan, thik ache | na |
| Punjabi | udhaar, likh lo | ditta, jama | kinna baaki | kal | haanji, theek hai | nahi, rehan do |
| Odia | udhaar, baki, likhi dia | dili, jama | kete baki | kali | haan, thik achhi | na, nahin |
| Assamese | baki, dhar | dilu, jama | koi baki | kali | hoi, bhal | nohoi |
| Urdu | udhaar, khaate mein likhiye | ada kiya | kitna baqi | kal | ji haan, theek hai | nahi |

**"Kal" trap:** in Hindi, Gujarati, Bengali and Punjabi *kal* means both yesterday and tomorrow. Decide by verb tense
(*de dunga* = future/tomorrow, *diye the* = past/yesterday).

## 6. Prompt addendum (paste into `agent/prompts.py`)
```
Direction: always interpret from the SHOP's point of view. "X ne/inda/kitta irundhu/nunchi ... diya/kottru/vanginen" = X paid the shop.
"X ko/ge/ku/ki ... diya/kottidini/kuduthen" = the shop gave X cash (cash_loan, adds to what X owes). If direction is unclear, ask.
A sale where the customer hands money at the counter (with or without change) is NOT a ledger entry. Only create entries for credit,
payments against dues, partial payments (credit full total + payment of the part), advances, cash loans and adjustments.
Never turn amounts heard in price talk, change talk or gossip into entries. Never guess a total from item names: ask the amount.
"kal/naale/repu/udya" next to a future verb is a due date, not a backdate. Past tense + kal = yesterday.
If the customer disputes a past payment, create nothing and offer to search past entries.
Amounts above 10x the customer's usual entry need a second "are you sure?". Read every amount back in digits.
Ambient (customer + shopkeeper) speech may only produce a suggestion; commit only after the shopkeeper's explicit confirm.
```

## 7. What to build next
1. DB: add `adjustment` type + `reason`, `payment_mode`, `due_date`, `entry_date`; `reminders` table. (Current schema only has credit/payment, and
   `shops.language` only allows kn/hi/en. The web/mobile language chips are also limited to those three.)
2. STT: confirm which of these languages your speech provider actually supports. Odia, Assamese and Urdu may be weaker or unsupported.
3. Eval harness: `eval_agent.py` that replays the JSONL and reports per-language intent/amount/action accuracy.
4. Real data: record 5 to 10 shops (with consent), have native speakers transcribe and label, and add 500+ rows per language.
5. Missing languages/dialects: Tulu, Konkani, Kodava, Rajasthani, Bhojpuri, Maithili, Haryanvi, Nepali, Kashmiri, Sindhi.
6. Mixed-language turns inside one conversation (shopkeeper in Kannada, customer in Hindi) are common; add many of them.
