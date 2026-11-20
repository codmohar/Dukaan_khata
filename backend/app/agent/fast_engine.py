"""Fast-Path Kirana Intent Engine & Ambient Chatter Sieve with Complete Money Flows.

Implements the complete Indian Kirana money flows and conversational speech patterns:
1. Credit Sale (udhar / udri / baaki / bardu / likho / daal)
2. Payment Received (jama / kottru / diya / de diya) with Payment Mode (cash / UPI / PhonePe / GPay / Paytm)
3. Partial / Full Settlement (sab clear / ellaa clear maadi / hisaab chukta / hisaab barabar)
4. Corrections after read-back ("Nahi nahi, 430 likho, 340 nahi" / "alla, 430 antha bardu")
5. Undo / Delete last entry ("Last entry delete maadi" / "Pichla entry hatao" / "undo last")
6. Payment Reminders ("Ramesh ko yaad dilao" / "Lakshmi akka ge reminder kalsi")
7. Adjustments: Return of goods ("wapas, 40 kam karo") & Discounts ("chillar chhodo, 30 discount")
8. Advance / Deposit ("1000 advance rakho" / "mungaada")
9. Balance Inquiries ("Lakshmi akka ge eshtu baaki ide?" / "Ramesh ka balance kitna hai")
10. Shop Summary & Top Debtors ("Aaj kitna udhar gaya?" / "Who owes the most?")
11. Multi-Turn Context Tracking (Customer in Turn 1 -> Amount in Turn 2, or vice versa)
12. Disambiguation with Landmarks & Balances ("1. Ramesh (paan shop) | 2. Ramesh (auto)")
13. Suffix & Postposition stripping on names (Rameshge -> Ramesh, Lakshmige -> Lakshmi, Rameshne -> Ramesh)
14. Ambient Chatter Sieve (< 0.1ms noise immunity for product questions & payment boasting)
15. 10x Anomaly Safety Alerts ("Are you sure?" confirmation)
"""
from datetime import date, datetime, timedelta, timezone
import logging
import re
from typing import Any, Dict, List, Optional, Tuple
import uuid
from sqlalchemy import text as sa_text

from ..db import SessionLocal
from ..models import Customer, Transaction
from . import tools
from .indian_numbers import extract_indian_amount

log = logging.getLogger("dukaan.agent.fast")

# Comprehensive set of Indian Kirana products, brands, groceries, and packaged items
# Products and brand names must NEVER be mistaken for customer names!
KIRANA_ITEMS = {
    # Biscuits, Snacks & Packaged Foods
    "parle", "parle-g", "parleg", "maggi", "lays", "kurkure", "marie", "mariegold", "goodday", "britannia",
    "oreo", "monaco", "krackjack", "bourbon", "chips", "namkeen", "biscuit", "packet", "wafers", "mixture",
    "toast", "rusk", "bhujia", "sev", "chivda", "peanuts", "sing", "chana", "papad",
    # Chocolates & Confectionery
    "5star", "dairymilk", "kitkat", "munch", "perk", "eclairs", "chocolate", "toffee", "mithai", "ladoo",
    # Kitchen Staples, Grains, Pulses & Groceries
    "cheeni", "sugar", "atta", "aata", "tel", "oil", "doodh", "milk", "bread", "chawal", "rice", "dal",
    "daal", "masala", "mirchi", "haldi", "namak", "salt", "poha", "rava", "sooji", "suji", "maida",
    "besan", "ghee", "butter", "dahi", "curd", "paneer", "chai", "tea", "coffee", "patti",
    "egg", "anda", "onion", "pyaz", "alu", "aloo", "potato", "tamatar", "tomato", "adrak", "lahsun",
    # Kannada Staples
    "akki", "akkii", "bele", "sakre", "haalu", "thuppa", "enne", "uppu", "kaapi", "chaha", "mosaru",
    "baalehannu", "bannana", "savukku", "avalakki", "godhi", "hesarubele", "togaribele",
    # Personal Care, Hygiene & Cleaning
    "soap", "sabun", "shampoo", "brush", "paste", "colgate", "pepsodent", "closeup", "sensodyne",
    "surf", "tide", "rin", "vim", "harpic", "detergent", "dettol", "lifebuoy", "lux", "santoor", "godrej",
    "shaving", "blade", "cream", "lotion", "powder", "handwash", "sanitizer",
    # Tobacco, Matchbox & Pooja Items
    "cigarette", "bidi", "beedi", "gutkha", "vimal", "kamal", "matchbox", "maachis", "agarbatti",
    "dhoop", "kapoor", "supari", "paan",
    # Indic Devanagari items
    "पारले", "मैगी", "लेज", "कुरकुरे", "बिस्कुट", "चीनी", "आटा", "तेल", "दूध", "चावल", "दाल", "मसाला", "साबुन", "नमक", "चाय", "ब्रेड", "घी",
    # Indic Kannada items
    "ಅಕ್ಕಿ", "ಬೇಳೆ", "ಸಕ್ಕರೆ", "ಹಾಲು", "ತುಪ್ಪ", "ಎಣ್ಣೆ", "ಉಪ್ಪು", "ಕಾಫಿ", "ಚಹಾ", "ಮೊಸರು", "ಬಿಸ್ಕತ್", "ಸೋಪು"
}

def _extract_kirana_item(text: str) -> Optional[str]:
    """Detect if any kirana product or brand is mentioned in the utterance."""
    lower = text.lower()
    for item in [
        "parle-g", "parle", "parleg", "पारले", "maggi", "मैगी", "lays", "लेज", "kurkure", "कुरकुरे",
        "goodday", "marie", "mariegold", "oreo", "5star", "dairymilk", "kitkat", "munch",
        "cheeni", "sugar", "चीनी", "sakre", "ಸಕ್ಕರೆ", "doodh", "milk", "दूध", "haalu", "ಹಾಲು",
        "atta", "aata", "आटा", "tel", "oil", "तेल", "enne", "ಎಣ್ಣೆ", "chawal", "rice", "चावल", "akki", "ಅಕ್ಕಿ",
        "dal", "daal", "दाल", "bele", "ಬೇಳೆ", "biscuit", "बिस्कुट", "soap", "sabun", "साबुन", "soop", "ಸೋಪು",
        "bread", "ब्रेड", "ghee", "घी", "thuppa", "ತುಪ್ಪ", "tea", "chai", "चाय", "chaha", "coffee", "kaapi", "ಕಾಫಿ"
    ]:
        if re.search(r"\b" + re.escape(item) + r"\b", lower):
            if item in ("parle", "parle-g", "parleg", "पारले"):
                return "Parle-G"
            elif item in ("maggi", "मैगी"):
                return "Maggi"
            elif item in ("lays", "लेज"):
                return "Lays"
            elif item in ("kurkure", "कुरकुरे"):
                return "Kurkure"
            elif item in ("goodday", "marie", "mariegold", "oreo", "biscuit", "बिस्कुट"):
                return "Biscuit"
            elif item in ("cheeni", "sugar", "चीनी", "sakre", "ಸಕ್ಕರೆ"):
                return "Cheeni"
            elif item in ("doodh", "milk", "दूध", "haalu", "ಹಾಲು"):
                return "Doodh"
            elif item in ("atta", "aata", "आटा"):
                return "Atta"
            elif item in ("tel", "oil", "तेल", "enne", "ಎಣ್ಣೆ"):
                return "Tel"
            elif item in ("chawal", "rice", "चावल", "akki", "ಅಕ್ಕಿ"):
                return "Chawal"
            elif item in ("dal", "daal", "दाल", "bele", "ಬೇಳೆ"):
                return "Dal"
            elif item in ("soap", "sabun", "साबुन", "soop", "ಸೋಪು"):
                return "Sabun"
            return item.capitalize()
    return None

# Background music, song lyrics, radio FM, and ambient background chatter patterns
SONG_AND_NOISE_PATTERNS = [
    # Famous Bollywood & regional song refrains and lyrics
    re.compile(r"\b(?:tum\s*hi\s*ho|channa\s*mereya|dil\s*diya\s*gallan|tera\s*ban\s*jaunga|kesariya|bekhayali|deva\s*deva|apna\s*bana\s*le|lut\s*gaye|chaleya|jhoome\s*jo|senorita|raatan\s*lambiyan|pasoori|o\s*bedardeya|kalank|dheere\s*dheere|luka\s*chuppi|gerua|shayad|tere\s*hawaale|zindagi\s*do\s*pal|hasi\s*ban\s*gaye|muskurane\s*ki\s*wajah|tujh\s*mein\s*rab|jeene\s*laga\s*hoon|pehli\s*nazar\s*mein|suraj\s*hua\s*maddham|kabira|illahi|subhanallah|samjhawan|galliyan|ae\s*dil\s*hai\s*mushkil|agar\s*tum\s*saath\s*ho|kyunki\s*tum\s*hi\s*ho|ab\s*tum\s*hi\s*ho|zindagi\s*ab\s*tum\s*hi\s*ho|meri\s*aashiqui|humdard|sun\s*raha\s*hai|teri\s*galliyan)\b", re.I),
    # Kannada / South Indian song phrases
    re.compile(r"\b(?:singara\s*siriye|belakina\s*kavithe|nenapirali|sanju\s*weds\s*geetha|kannada\s*haadu|geethe|haadugalu|chinna\s*chinna\s*aasa|rowdy\s*baby|butta\s*bomma|saranga\s*dariya|jimikki\s*kammal|enjoy\s*enjaami)\b", re.I),
    # Radio, FM, DJ, and music player announcements
    re.compile(r"\b(?:radio\s*mirchi|red\s*fm|radio\s*city|big\s*fm|superhit\s*gaana|gana\s*bajao|gaana\s*lagao|music\s*play|song\s*chalao|dj\s*remix|bhajan|aarti|kirtan)\b", re.I),
    # Ambient non-accounting gossip, cricket scores, tea/weather talk
    re.compile(r"\b(?:kya\s*haal\s*chaal|kaise\s*ho|kya\s*chal\s*raha|match\s*kaun\s*jeeta|score\s*kya\s*hua|aaj\s*baarish|bahut\s*garmi|chai\s*piyenge|chai\s*banao|chai\s*lao|auto\s*auto|gaadi\s*roko|phone\s*aaya|call\s*kat\s*gaya|aur\s*batao|sab\s*badhiya)\b", re.I),
]

def clean_ambient_noise_and_songs(text: str) -> Tuple[str, bool]:
    """Isolate genuine shop accounting commands by stripping background song lyrics,
    radio chatter, and ambient gossip. Returns (cleaned_text, noise_detected)."""
    cleaned = text
    noise_detected = False
    for pat in SONG_AND_NOISE_PATTERNS:
        if pat.search(cleaned):
            noise_detected = True
            cleaned = pat.sub(" ", cleaned)

    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned, noise_detected

# Counter Bill Total / Trilemma Pattern (e.g. "Parle ji aapka 20 hua", "Aapka 50 hua", "Kul 120 bana", "Total 150 hua", "80 aaythu")
BILL_TOTAL_PATTERN = re.compile(
    r"\b(?:aapka|apka|kul|total|bill|itna\s*hua|itna\s*bana|itna\s*aaythu|hua|hue|bana|hoya|aaythu|aagide|aaitu)\b|"
    r"(?:आपका|कुल|टोटल|बिल|हुआ|हुए|बना)|"
    r"(?:ಆಯ್ತು|ಆಗಿದೆ|ಒಟ್ಟು|ಬಿಲ್)",
    re.I,
)

# Shop floor chatter keywords: product requests, casual greetings, customer boasting
CHATTER_PATTERNS = [
    re.compile(r"\b(?:biscuit|packet|cheeni|sugar|atta|tel|oil|dal|doodh|milk|bread|soap|sabun|chawal|rice)\b", re.I),
    re.compile(r"\b(?:kitne\s*ka|kya\s*rate|kya\s*bhav|eshtu\s*bele|rate\s*kya|chahiye|hai\s*kya|milega\s*kya)\b", re.I),
    re.compile(r"\b(?:kaunsa|marigold|parle|maggi|lays|kurkure|shampoo|brush|paste)\b", re.I),
    re.compile(r"\b(?:change\s*hai|khulla\s*hai|chillar\s*hai|chillar\s*illa)\b", re.I),
    re.compile(r"\b(?:thoda\s*kam|kam\s*karo|discount\s*do|bargain)\b", re.I),
    re.compile(r"\b(?:main\s*\d+|maine\s*\d+|maine\s*phonepe|maine\s*gpay|maine\s*paytm|maine\s*de\s*diya|main\s*de\s*raha|maine\s*bhej|maine\s*online)\b", re.I),
]

# Core Intent Regex Patterns with strict word boundaries across 14 Indian languages
CREDIT_PATTERN = re.compile(
    r"\b(?:udhar|udhaar|udri|baaki|baki|bardu|barkoli|haaki|likho|likh|daal|khata|credit|saala|kadan|appu|kadam|ezhuthunga|ezhudhu|ezhuthikko|rayandi|raayi|liha|lakho|dhar|likha)\b|"
    r"(?:उधार|उधारी|बाकी|लिखो|लिख|डाल|खाता|क्रेडिट|साख|बकाया)|"
    r"(?:ಉದ್ರಿ|ಉಧಾರ್|ಬಾಕಿ|ಬರೆ|ಹಾಕಿ|ಖಾತೆ|ಸಾಲ)|"
    r"(?:கடன்|பாக்கி|எழுது)|(?:అప్పు|బాకీ|రాయి)|(?:കടം|ബാക്കി)|(?:उधार|लिहा)|(?:ઉધાર|લખો)|(?:ধার|বাকি|লেখ)|(?:ਉਧਾਰ|ਲਿਖ)|(?:ଉଧାର|ବାକି)|(?:باقی|ادھار)",
    re.I,
)
PAYMENT_PATTERN = re.compile(
    r"\b(?:jama|joma|kottru|kotta|kottidru|diya|de\s*diya|paid|received|vasool|chukaya|varavu|pay|payment|bantu|bithu|kuduthen|kuduthaaru|vandhuchu|ichanu|ichhaaru|ochindi|koduthu|kitti|dile|aale|apya|aavya|diyechi|diyeche|elo|ditta|dili|aasila|dilu|palu|ada\s*kiya|milale|madya|peyechi|mile|pali)\b|"
    r"(?:जमा|दिया|दे\s*दिया|पेमेंट|पेड|वसूल|चुकाया|चुका\s*दिया|भर\s*दिया|आया|मिल\s*गया)|"
    r"(?:ಜಮಾ|ಕೊಟ್ರು|ಕೊಟ್ಟ|ಪಾವತಿ|ಬಂತು|ತುಂಬಿದೆ)|"
    r"(?:வரவு|கொடுத்தேன்|ஜமா)|(?:జమా|ఇచ్చాను|వచ్చింది)|(?:ജമ|കൊടുത്തു)|(?:जमा|दिले)|(?:જમા|આપ્યા)|(?:জমা|দিয়েছি)|(?:ਜਮਾ|ਦਿੱਤਾ)|(?:ଜମା|ଦିଲି)|(?:ادا|وصول)",
    re.I,
)
CONFIRM_PATTERN = re.compile(
    r"\b(?:haan|theek|confirm|sari|houdu|haudu|karo|yes|done|maadi|ok|theek\s*hai|sahi\s*hai|right|aama|avunu|sare|athe|sheri|ho|thik\s*aahe|ha|barabar|hyan|thik\s*ache|haanji|thik\s*achhi|hoi|bhal|ji\s*haan)\b|"
    r"(?:हाँ|हां|ठीक|ठीक\s*है|सही|सही\s*है|कन्फर्म|करो|कर\s*दो|हो\s*गया|डन)|"
    r"(?:ಹೌದು|ಸರಿ|ಮಾಡಿ|ಆಯ್ತು|ಖಚಿತ)|"
    r"(?:ஆமா|சரி)|(?:అవును|సరే)|(?:അതെ|ശരി)|(?:हो|ठीक)|(?:હા|બરાબર)|(?:হ্যাঁ|ঠিক)|(?:ਹਾਂਜੀ)|(?:ହଁ)|(?:جی\s*ہاں)",
    re.I,
)
CANCEL_PATTERN = re.compile(
    r"\b(?:nahi|cancel|hatao|galat|beda|illa|no|mat\s*karo|thappu|vendam|vaddu|ledu|venda|alla|nako|rehva\s*do|rehan\s*do|nahin|nohoi)\b|"
    r"(?:नहीं|नही|हटाओ|कैंसिल|गलत|मत\s*करो|रद्द)|"
    r"(?:ಇಲ್ಲ|ಬೇಡ|ತಪ್ಪು|ರದ್ದು)|"
    r"(?:வேண்டாம்|இல்லை)|(?:వద్దు|లేదు)|(?:വേണ്ട|അല്ല)|(?:नको|नाही)|(?:ના|રહેવા\s*દો)|(?:না)|(?:ਨਹੀਂ)|(?:ନାହିଁ)|(?:نہیں)",
    re.I,
)
SUMMARY_PATTERN = re.compile(
    r"\b(?:summary|aaj\s*ka\s*hisaab|aaj\s*kitna|collection|total\s*hisaab|dukaan\s*summary|dhanda|aaj\s*ka\s*summary|who\s*owes\s*the\s*most|sabse\s*zyada\s*baaki)\b|"
    r"(?:समरी|आज\s*का\s*हिसाब|आज\s*कितना|कलेक्शन|कुल\s*हिसाब|धंधा|आज\s*का\s*समरी|सबसे\s*ज्यादा\s*बाकी)|"
    r"(?:ಸಾರಾಂಶ|ಇವತ್ತಿನ\s*ಲೆಕ್ಕ|ಕಲೆಕ್ಷನ್|ಇವತ್ತು\s*ಎಷ್ಟು)",
    re.I,
)
BALANCE_PATTERN = re.compile(
    r"\b(?:balance|kitna\s*baaki|eshtu\s*baaki|hisab|hisaab|baaki\s*ide|khata\s*batao|pending|evvalavu\s*baaki|entha\s*baaki|ethra\s*baaki|kiti\s*baaki|ketlu\s*baaki|koto\s*baki|kinna\s*baaki|kete\s*baki|koi\s*baki|kitna\s*baqi)\b|"
    r"(?:बैलेंस|कितना\s*बाकी|हिसाब|खाता\s*बताओ|पेंडिंग|बाकी\s*कितना)|"
    r"(?:ಬ್ಯಾಲೆನ್ಸ್|ಎಷ್ಟು\s*ಬಾಕಿ|ಲೆಕ್ಕ|ಬಾಕಿ\s*ಇದೆ)|"
    r"(?:எவ்வளவு\s*பாக்கி)|(?:ఎంత\s*బాకీ)|(?:എത്ര\s*ബാക്കി)|(?:किती\s*बाकी)|(?:કેટલું\s*બાકી)|(?:কত\s*বাকি)|(?:ਕਿੰਨਾ\s*ਬਾਕੀ)|(?:କେତେ\s*ବାକି)|(?:کتنا\s*باقی)",
    re.I,
)
GREETING_PATTERN = re.compile(
    r"\b(?:namaste|namaskar|namaskara|hello|hi|hi\s*khata|hey|vanakkam)\b|"
    r"(?:नमस्ते|नमस्कार|प्रणाम|हेलो|हाय)|"
    r"(?:ನಮಸ್ಕಾರ|ನಮಸ್ತೆ)",
    re.I,
)

# Direction rule & Cash Loan detection (Shop gives cash to customer -> credit / loan)
LOAN_DIRECTION_PATTERN = re.compile(
    r"\b(?:ko\s*diya|ge\s*kottidini|ku\s*kuduthen|ki\s*ichanu|inu\s*koduthu|la\s*dile|ke\s*diyechi|nu\s*ditte|ku\s*dili|gave\s*cash|cash\s*loan)\b|"
    r"(?:को\s*दिया|को\s*दे\s*दो)",
    re.I,
)

# Paid Walk-In Sale (ambient counter talk with exact cash/change handed)
PAID_SALE_PATTERN = re.compile(
    r"\b(?:ye\s*lo\s*\d+|ye\s*lo\s*bhaiya|change\s*wapas|wapas\s*ye\s*lo|note\s*diya|itna\s*bana.*de\s*diya|ye\s*lo)\b|"
    r"(?:ये\s*लो|ये\s*लीजिए|वापस\s*लो|चिल्लर\s*वापस)",
    re.I,
)

# Full Settlement Intent ("Sab clear", "Ella clear maadi", "Hisaab chukta")
SETTLE_PATTERN = re.compile(
    r"\b(?:sab\s*clear|ellaa\s*clear|ella\s*clear|hisaab\s*chukta|hisab\s*chukta|hisaab\s*barabar|settle|clear\s*kar\s*do|clear\s*maadi)\b|"
    r"(?:सब\s*क्लियर|हिसाब\s*चुकता|हिसाब\s*बराबर|पूरा\s*क्लियर|क्लियर\s*कर\s*दो)|"
    r"(?:ಎಲ್ಲಾ\s*ಕ್ಲಿಯರ್|ಲೆಕ್ಕ\s*ಚುಕ್ತಾ)",
    re.I,
)

# Undo Intent ("Last entry delete maadi", "Pichla entry hatao", "Undo last")
UNDO_PATTERN = re.compile(
    r"\b(?:undo|delete\s*maadi|pichla\s*hatao|last\s*entry\s*delete|delete\s*last|last\s*hatao|pichli\s*entry|undo\s*last)\b|"
    r"(?:पिछली\s*एंट्री\s*हटाओ|पिछला\s*हटाओ|लास्ट\s*एंट्री\s*डिलीट|अंडू)|"
    r"(?:ಹಿಂದಿನ\s*ಎಂಟ್ರಿ\s*ಡಿಲೀಟ್|ಡಿಲೀಟ್\s*ಮಾಡಿ)",
    re.I,
)

# Payment Reminders ("Ramesh ko yaad dilao", "Reminder kalsi")
REMINDER_PATTERN = re.compile(
    r"\b(?:yaad\s*dilao|reminder|kalsi|message\s*bhejo|whatsapp|bhej\s*do)\b|"
    r"(?:याद\s*दिलाओ|रिमाइंडर|मैसेज\s*भेजो|व्हाट्सएप)|"
    r"(?:ನೆನಪಿಸಿ|ಮೆಸೇಜ್\s*ಕಳಿಸಿ)",
    re.I,
)

# Adjustments: Returns & Discounts
RETURN_PATTERN = re.compile(
    r"\b(?:wapas|vaapas|return|vaapasi)\b|"
    r"(?:वापस|वापसी|रिटर्न)|"
    r"(?:ವಾಪಸ್|ರಿಟರ್ನ್)",
    re.I,
)
DISCOUNT_PATTERN = re.compile(
    r"\b(?:discount|chillar\s*chhodo|chhod\s*do|round\s*off)\b|"
    r"(?:डिस्काउंट|छूट|चिल्लर\s*छोड़ो|राउंड\s*ऑफ)|"
    r"(?:ರಿಯಾಯಿತಿ|ಡಿಸ್ಕೌಂಟ್)",
    re.I,
)

# Advance / Deposit
ADVANCE_PATTERN = re.compile(
    r"\b(?:advance|deposit|mungaada|mungada)\b|"
    r"(?:एडवांस|डिपॉजिट|अग्रिम)|"
    r"(?:ಮುಂಗಡ|ಅಡ್ವಾನ್ಸ್)",
    re.I,
)

# Override Rule Intent ("Continue anyway", "Override", "Phir bhi karo", "Niyam meeri continue")
OVERRIDE_PATTERN = re.compile(
    r"\b(?:continue\s*anyway|continue|override|phir\s*bhi|barli|niyam\s*meeri|barbadi|zarur\s*karo)\b|"
    r"(?:कंटिन्यू|ओवरराइड|फिर\s*भी|नियम\s*तोड़\s*कर|जारी\s*रखो)|"
    r"(?:ಮುಂದುವರಿಸಿ|ನಿಯಮ\s*ಮೀರಿ)",
    re.I,
)


def _format_rule_warning_msg(draft_res: Dict[str, Any], cname: str, amount: float, lang: str) -> str:
    """When a shopkeeper unconsciously breaks a rule while taking customer, tell the written rule text!"""
    rule_warnings = draft_res.get("rule_warnings") or []
    rule_texts = " aur ".join(f"\"{rw.get('rule_text') or rw.get('message')}\"" for rw in rule_warnings)
    if lang.startswith("kn"):
        return (
            f"⚠️ Gamana kodi! Nimma dukaan niyamavide: {rule_texts}. "
            f"{cname} avarige ₹{amount:,.0f} udhar draft aagide. Niyam meeri continue maadla athava amount badalayisla?"
        )
    elif lang.startswith("hi"):
        return (
            f"⚠️ Dhyan dein! Aapka dukaan niyam hai: {rule_texts}. "
            f"{cname} ke liye ₹{amount:,.0f} udhar draft ban gaya hai. Kya niyam override karke continue karna chahte hain ya amount change karein?"
        )
    else:
        return (
            f"⚠️ Warning! Your shop rule states: {rule_texts}. "
            f"A draft of ₹{amount:,.0f} credit has been prepared for {cname}. Do you want to continue anyway or change the amount?"
        )


def _format_promise_warning_msg(draft_res: Dict[str, Any], cname: str, amount: float, lang: str) -> str:
    """When a customer with a pending payment promise asks for more credit, immediately warn the shopkeeper!"""
    p = draft_res.get("pending_promise") or {}
    p_amt = float(p.get("promised_amount") or 0)
    p_date = p.get("expected_date") or "jald"
    amt_str = f"₹{p_amt:,.0f}" if p_amt > 0 else "purana amount"

    if lang.startswith("kn"):
        return (
            f"⚠️ Gamanisi: {cname} avarige igaagale {amt_str} koduvudagi promise ide ({p_date}). "
            f"Innu ₹{amount:,.0f} udhar baribeka athava purana clear maadbeka? Khaathri maadi."
        )
    elif lang.startswith("hi"):
        return (
            f"⚠️ Dhyan dein: {cname} ji ka pehle se {amt_str} dene ka wada pending hai ({p_date}). "
            f"Kya naya ₹{amount:,.0f} udhar likhna hai ya pehle purana hisaab clear karwayein? Confirm karein?"
        )
    else:
        return (
            f"⚠️ Alert: {cname} already has a pending promise to pay {amt_str} by {p_date}. "
            f"Give more credit of ₹{amount:,.0f} anyway? Please confirm."
        )


def _parse_relative_promise_date(text: str) -> date:
    lower = text.lower()
    today = datetime.now(timezone(timedelta(hours=5, minutes=30))).date()

    if any(w in lower for w in ["parso", "naadiddu", "erandu naal", "ellundi"]):
        return today + timedelta(days=2)

    if any(w in lower for w in ["kal", "naale", "tomorrow", "udya", "repu", "naalaiku", "kali"]):
        return today + timedelta(days=1)

    weekday_map = {
        "somwar": 0, "somvaar": 0, "monday": 0, "tingalavara": 0,
        "mangalwar": 1, "mangalvaar": 1, "tuesday": 1, "mangalavara": 1,
        "budhwar": 2, "budhwaar": 2, "wednesday": 2, "budhavara": 2,
        "guruwar": 3, "guruwaar": 3, "thursday": 3, "guruvara": 3,
        "shukrawar": 4, "shukrawaar": 4, "friday": 4, "shukravara": 4,
        "shaniwar": 5, "shaniwaar": 5, "saturday": 5, "shanivara": 5,
        "itwar": 6, "ravivar": 6, "sunday": 6, "bhanuvara": 6,
    }
    for day_word, target_wd in weekday_map.items():
        if re.search(r"\b" + day_word + r"\b", lower):
            days_ahead = target_wd - today.weekday()
            if days_ahead <= 0:
                days_ahead += 7
            return today + timedelta(days=days_ahead)

    return today + timedelta(days=1)


# Promise Recording Intent ("Ramesh kal 500 dega", "Suresh naale 200 kodtini")
PROMISE_RECORD_PATTERN = re.compile(
    r"\b(?:dega|degi|denge|de\s*dunga|dene\s*ka\s*wada|wada\s*kiya|wada\s*hai|kodtini|kodtane|kodtare|kodthini|tharen|isthanu|tharaam|deto|aapis|debo|devanga|debi|dim|dunga|will\s*pay|promised|promise\s*kiya)\b|"
    r"(?:देगा|देगी|देंगे|दे\s*दूंगा|वादा|प्रॉमिस)|"
    r"(?:ಕೊಡ್ತೀನಿ|ಕೊಡ್ತಾರೆ|ಕೊಡುತ್ತೇನೆ|ಪ್ರಾಮಿಸ್)",
    re.I,
)

# Promise Query Intent ("Kiska promise pending hai", "Ramesh ka promise kya tha")
PROMISE_QUERY_PATTERN = re.compile(
    r"\b(?:promises|promise\s*kya|promise\s*list|wada|pending\s*promise|promises\s*dikhao|yaara\s*promise|kiska\s*wada|kiska\s*promise|promise\s*check)\b|"
    r"(?:प्रॉमिस|वादा|पेंडिंग\s*प्रॉमिस)",
    re.I,
)

# Payment Mode Regex
UPI_PATTERN = re.compile(
    r"\b(?:phonepe|gpay|google\s*pay|paytm|upi|bhim|qr|online)\b|"
    r"(?:फोनपे|जीपे|गूगल\s*पे|पेटीएम|यूपीआई|भीम|ऑनलाइन)|"
    r"(?:ಫೋನ್‌ಪೇ|ಗೂಗಲ್‌ಪೇ|ಪೇಟಿಎಂ|ಯುಪಿಐ)",
    re.I,
)
CASH_PATTERN = re.compile(
    r"\b(?:cash|nagad|rokda)\b|"
    r"(?:कैश|नकद|रोकड़ा|रोकड)|"
    r"(?:ನಗದು|ಕ್ಯಾಶ್)",
    re.I,
)

# Indian honorifics stripped from names
HONORIFICS = {
    "anna", "akka", "bhaiya", "bhayya", "bhai", "didi", "sir", "madam", "maam",
    "uncle", "aunty", "ji", "saab", "sahab", "avare", "avaru", "avar", "amma", "appa",
    "babu", "shetr", "seth", "sethji", "bhaiji",
    # Devanagari honorifics
    "जी", "भाई", "भैया", "दीदी", "अंकल", "आंटी", "सर", "मैडम", "साहब", "अण्णा", "बाबू",
    # Kannada honorifics
    "ಅಣ್ಣ", "ಅಕ್ಕ", "ಅವರು", "ಅವರೇ", "ಅಮ್ಮ", "ಅಪ್ಪ"
}

STOPWORDS = {
    "ge", "ka", "ki", "ko", "ne", "rupayi", "rupaye", "rupees", "rs", "inr",
    "udhar", "udri", "jama", "bardu", "barkoli", "haaki", "likho", "likh", "kotta",
    "kottru", "diya", "paid", "add", "credit", "bantu", "daal", "do", "kadan", "appu",
    "se", "mein", "par", "saade", "sau", "hazaar", "hazar", "nooru", "savira", "dedh",
    "dhai", "paune", "aur", "karo", "kar", "de", "le", "lo", "batao", "dekhna", "bhi",
    "ek", "do", "teen", "chaar", "paanch", "pehla", "second", "wala", "wali", "naam",
    "customer", "graahaka", "please", "kripya", "dayavittu", "innomme", "heli", "bolo",
    "bataiye", "boliye", "chahiye", "hai", "kya", "tha", "thi", "the", "aaya", "aayi",
    "aaye", "gaya", "gayi", "gaye", "hua", "hui", "hue", "khata", "ledger", "entry",
    "record", "karna", "sab", "clear", "ella", "ellaa", "maadi", "chukta", "barabar",
    "kal", "naale", "parso", "naadiddu", "today", "tomorrow", "yesterday", "dega", "degi", "denge", "dunga", "wada", "kodtini", "kodtane", "kodtare",
    "aapka", "apka", "kul", "total", "bill", "bana", "itna", "hoya", "aaythu", "aagide", "aaitu", "tum", "hi", "ho",
    "nahi", "nahin", "alla", "beda", "nako", "no", "mat", "cancel", "hatao",
    "bariyiri", "bari", "bariyiro", "haakri", "haakiro",
    "sell", "becho", "bechna", "kharido", "kharid", "buy", "liya", "liye", "diye", "packet", "piece", "kilo", "kg", "gm", "litre", "ltr", "rate", "bhav", "price", "cost",
    "phonepe", "gpay", "paytm", "upi", "bhim", "cash", "online", "qr", "cheque", "pelam", "loan", "cashloan", "er",
    # 14 languages markers & postpositions
    "kitta", "irundhu", "ku", "roobai", "vanginen", "kuduthen", "podunga", "ezhudhu",
    "nunchi", "ki", "rupayalu", "techukunnanu", "ichanu", "rayandi", "ochindi",
    "il", "ninnu", "inu", "roopa", "vaangi", "koduthu", "ezhuthikko", "kitti",
    "kadun", "la", "milale", "dile", "liha", "aale",
    "pase", "thi", "rupiya", "madya", "apya", "lakho", "aavya",
    "kach", "theke", "ke", "taka", "peyechi", "diyechi", "lekho", "elo",
    "kolon", "nu", "mile", "ditte", "likh", "ditta",
    "tharu", "tanka", "pali", "dili", "likhi", "aasila",
    "naamot", "toka", "palu", "dilu", "likha",
    "khaate", "rupay", "ada", "kiya", "likhiye",
    # Devanagari stopwords
    "का", "की", "के", "को", "ने", "से", "में", "पर", "रुपये", "रुपए", "रुपया", "रु",
    "उधार", "उधारी", "जमा", "लिखो", "लिख", "डाल", "डालो", "दिया", "दिए", "दे", "लिया",
    "लिए", "ले", "करो", "कर", "दो", "दी", "हो", "गया", "गई", "गए", "है", "हैं", "था",
    "थी", "थे", "खाता", "हिसाब", "सब", "क्लियर", "फोनपे", "कैश", "नकद", "कृपया", "बोलो", "बताओ",
    # Kannada stopwords
    "ಗೆ", "ಇಂದ", "ರೂಪಾಯಿ", "ರೂ", "ಉದ್ರಿ", "ಉಧಾರ್", "ಜಮಾ", "ಬರೆ", "ಹಾಕಿ", "ಕೊಟ್ರು",
    "ಕೊಟ್ಟ", "ಆಗಿದೆ", "ಆಯ್ತು", "ಇದೆ", "ಮಾಡಿದೆ", "ಖಾತೆ", "ಲೆಕ್ಕ"
}


class FastPathResult:
    def __init__(self, handled: bool, reply: str = "", events: Optional[List[Dict[str, Any]]] = None):
        self.handled = handled
        self.reply = reply
        self.events = events or []


def _extract_name_tokens(text: str) -> List[str]:
    """Dynamically extract any customer name: strips punctuation, numbers, honorifics,
    transaction verbs (dena, lena, udhar, sell, buy), and attached postpositions.
    Supports ALL names across all Indian languages without hardcoding selected names.
    """
    cleaned_punct = re.sub(r"[\u0964\u0965.,?!;:\"'()\[\]{}\-—_]", " ", text)
    words = cleaned_punct.split()
    tokens = []
    for raw in words:
        w = raw.strip()
        lower = w.lower()

        # Skip stopwords (transaction verbs, buy/sell context), honorifics, kirana items, and numbers
        if (
            lower in STOPWORDS
            or lower in HONORIFICS
            or lower in KIRANA_ITEMS
            or w.isdigit()
            or len(w) <= 1
        ):
            continue

        # Strip attached postpositions/suffixes (e.g. Rameshge -> Ramesh, Lakshmige -> Lakshmi, Manjunathavarige -> Manjunath, Deepakko -> Deepak)
        cleaned = w
        if len(cleaned) > 4:
            for suf in ["avarige", "inda", "ige", "ge", "ne", "ko", "ka", "ki", "ke", "er"]:
                if cleaned.lower().endswith(suf) and len(cleaned) > len(suf) + 2:
                    cleaned = cleaned[:-len(suf)]
                    break

        if (
            cleaned.lower() not in STOPWORDS
            and cleaned.lower() not in HONORIFICS
            and cleaned.lower() not in KIRANA_ITEMS
            and len(cleaned) > 1
        ):
            tokens.append(cleaned)

    return tokens


def _detect_payment_mode(text: str) -> Optional[str]:
    if UPI_PATTERN.search(text):
        return "upi"
    if CASH_PATTERN.search(text):
        return "cash"
    return None


def _pick_best_match(matches: List[Dict[str, Any]], query_name: str) -> Tuple[Optional[Dict[str, Any]], List[Dict[str, Any]]]:
    """Filter candidate customers for genuine name matches.
    If no candidate genuinely matches query_name, returns (None, []) so a new customer is created dynamically.
    Does not assume selected names or force unrelated database matches onto new customers.
    """
    if not matches or not query_name:
        return None, []

    clean_q = query_name.strip().lower()
    q_words = clean_q.split()

    genuine_matches: List[Dict[str, Any]] = []
    exact_matches: List[Dict[str, Any]] = []

    for m in matches:
        m_name = (m.get("name") or "").strip().lower()
        m_words = m_name.split()
        m_score = float(m.get("score") or 0.0)

        # 1. Exact match (case-insensitive)
        if m_name == clean_q:
            exact_matches.append(m)
            genuine_matches.append(m)
            continue

        # 2. First name match (e.g. query "Ramesh" -> candidate "Ramesh Kumar" or "Ramesh Gowda")
        if m_words and m_words[0] == clean_q:
            genuine_matches.append(m)
            continue

        # 3. Query is multi-word and matches candidate prefix or candidate starts with query
        if len(q_words) > 1 and (m_name.startswith(clean_q) or clean_q.startswith(m_name)):
            genuine_matches.append(m)
            continue

        # 4. Word boundary match
        if clean_q in m_words:
            genuine_matches.append(m)
            continue

        # 5. High fuzzy score (at least 0.65 similarity for minor spelling/transliteration differences)
        if m_score >= 0.65:
            genuine_matches.append(m)
            continue

    if len(exact_matches) == 1:
        return exact_matches[0], []
    if len(exact_matches) > 1:
        return None, exact_matches

    if not genuine_matches:
        # No existing customer genuinely matches this name! It is a NEW customer!
        return None, []

    if len(genuine_matches) == 1:
        return genuine_matches[0], []

    # Multiple genuine matches (e.g. query "Ramesh" matched both "Ramesh Kumar" and "Ramesh Gowda")
    return None, genuine_matches


def extract_corrected_amount(text: str) -> Optional[float]:
    """If utterance has correction like '20 nahi 50' or '50 likho 20 nahi' or 'alla 50', extract the intended target amount."""
    lower = text.lower()
    match_corr = re.search(r"(\d+(?:\.\d+)?)\s*(?:nahi|nahin|alla|not)\s*(\d+(?:\.\d+)?)", lower)
    if match_corr:
        return float(match_corr.group(2))

    match_corr_rev = re.search(r"(\d+(?:\.\d+)?)\s*(?:likho|likh|bardu|karo|bana|hua|aaythu)\s*[,]?\s*(\d+(?:\.\d+)?)\s*(?:nahi|nahin|alla|not)", lower)
    if match_corr_rev:
        return float(match_corr_rev.group(1))

    match_after_nahi = re.search(r"(?:nahi|nahin|alla|not)\s*[,]?\s*(\d+(?:\.\d+)?)", lower)
    if match_after_nahi:
        return float(match_after_nahi.group(1))

    return None


async def try_fast_path(
    session_or_shop_id: Any,
    user_text: str,
    language: str = "kn-IN",
    last_draft_id: Optional[str] = None,
) -> FastPathResult:
    """Attempt deterministic, instantaneous execution of Kirana voice turns with multi-turn memory."""
    raw_text = (user_text or "").strip()
    if not raw_text:
        return FastPathResult(handled=True, reply="[SILENT]")

    # Strip background song lyrics, radio announcements, and non-accounting chatter
    cleaned_text, had_song_or_noise = clean_ambient_noise_and_songs(raw_text)
    if not cleaned_text:
        return FastPathResult(handled=True, reply="[SILENT]")

    text = cleaned_text

    # Resolve session attributes whether passed as VoiceSession or legacy parameters
    sess = session_or_shop_id if hasattr(session_or_shop_id, "shop_id") else None
    shop_id = sess.shop_id if sess else session_or_shop_id
    lang = sess.language if sess else language
    active_draft_id = sess.last_draft_id if sess else last_draft_id
    if not active_draft_id:
        try:
            async with SessionLocal() as s_lookup:
                last_d_row = (await s_lookup.execute(
                    sa_text("SELECT id FROM transactions WHERE shop_id = :sid AND status = 'draft' ORDER BY created_at DESC LIMIT 1"),
                    {"sid": tools.to_uuid(shop_id)}
                )).scalar()
                if last_d_row:
                    active_draft_id = str(last_d_row)
                    if sess:
                        sess.last_draft_id = active_draft_id
        except Exception as ex:
            log.warning("Fast engine draft fallback lookup error: %s", ex)

    lower = text.lower()
    corrected_amt = extract_corrected_amount(text)
    amount = corrected_amt or extract_indian_amount(text)
    name_tokens = _extract_name_tokens(text)
    detected_item = _extract_kirana_item(text)
    payment_mode = _detect_payment_mode(text)
    is_loan = bool(LOAN_DIRECTION_PATTERN.search(text))
    is_credit = bool(CREDIT_PATTERN.search(text)) or is_loan
    is_payment = (bool(PAYMENT_PATTERN.search(text)) and not is_loan) or bool(payment_mode and not is_credit)
    is_return = bool(RETURN_PATTERN.search(text))
    is_discount = bool(DISCOUNT_PATTERN.search(text))
    is_advance = bool(ADVANCE_PATTERN.search(text))
    is_promise_rec = bool(PROMISE_RECORD_PATTERN.search(text))
    is_promise_query = bool(PROMISE_QUERY_PATTERN.search(text))
    is_bill_total = bool(BILL_TOTAL_PATTERN.search(text)) or bool(detected_item and amount and not (is_credit or is_payment))

    # Anti-Hallucination Guard: If background song or radio chatter was heard and no explicit ledger command or bill is present:
    if had_song_or_noise and not (is_credit or is_payment or is_bill_total or is_promise_rec or is_promise_query or (amount and name_tokens)):
        return FastPathResult(handled=True, reply="[SILENT]")

    # ---------------------------------------------------------
    # 0A. MULTI-TURN COUNTER FLOW: PENDING BILL CORRECTION (e.g. "20 nahi 50" / "alla 50")
    # ---------------------------------------------------------
    if sess and getattr(sess, "pending_bill_amount", None) and (corrected_amt or (amount and not name_tokens and (CANCEL_PATTERN.search(text) or any(w in lower for w in ["nahi", "alla", "kar", "hua", "bana", "rakho", "sudhar", "change"])))):
        target_amt = corrected_amt or amount
        sess.pending_bill_amount = target_amt
        item_str = f" ({sess.pending_bill_item})" if getattr(sess, "pending_bill_item", None) else ""
        if lang.startswith("kn"):
            msg = f"Tiddupaadi maadlaagide: ₹{target_amt:,.0f}{item_str} aagide. Eega payment maadthara, nantara promise maadthara, athava udhar baribeka?"
        elif lang.startswith("hi"):
            msg = f"Sudhaar diya: ₹{target_amt:,.0f}{item_str} hue. Abhi payment de rahe hain, wada kar rahe hain kab denge, ya udhar khate mein likh loon?"
        else:
            msg = f"Updated: ₹{target_amt:,.0f}{item_str}. Paying now, making a payment promise, or adding to credit khata?"
        return FastPathResult(handled=True, reply=msg)

    # ---------------------------------------------------------
    # 0B. MULTI-TURN COUNTER FLOW: PENDING BILL PAID IN CASH / UPI (Paid Sale -> Ambient [SILENT])
    # ---------------------------------------------------------
    if sess and getattr(sess, "pending_bill_amount", None) and (PAID_SALE_PATTERN.search(text) or any(w in lower for w in ["abhi de", "cash", "phonepe", "gpay", "paytm", "online", "ye lo", "diya", "de diya", "kotru", "kottu", "le lo"])):
        sess.pending_bill_amount = None
        sess.pending_bill_item = None
        return FastPathResult(handled=True, reply="[SILENT]")

    # ---------------------------------------------------------
    # 0C. MULTI-TURN COUNTER FLOW: PENDING BILL ASSIGNED TO CREDIT KHATA (e.g. "Udhar likh do Ramesh" / "Ramesh ke naam udhar")
    # ---------------------------------------------------------
    if sess and getattr(sess, "pending_bill_amount", None) and is_credit and name_tokens:
        bill_amt = sess.pending_bill_amount
        bill_item = getattr(sess, "pending_bill_item", None)
        sess.pending_bill_amount = None
        sess.pending_bill_item = None

        cust_name = " ".join(t.capitalize() for t in name_tokens[:2])
        async with SessionLocal() as s:
            search_res = await tools.search_customers(s, shop_id, cust_name)
            matches = search_res.get("matches", [])
            best, ambig = _pick_best_match(matches, cust_name)
            if not best and not ambig:
                new_c = await tools.create_customer(s, shop_id, name=cust_name)
                target_cid = new_c["customer_id"]
                c_display = cust_name
                cur_bal = 0.0
            elif best:
                target_cid = best["customer_id"]
                c_display = best["name"]
                cur_bal = float(best.get("balance", 0))
            else:
                sess.active_disambiguation = ambig
                sess.active_amount = bill_amt
                sess.active_tx_type = "credit"
                items = [f"{i}. {m['name']} ({m.get('landmark') or 'main'})" for i, m in enumerate(ambig[:3], 1)]
                msg = f"{cust_name} naam ke multiple customers hain: {' | '.join(items)}. Kiske naam ₹{bill_amt:,.0f} likhun?"
                return FastPathResult(handled=True, reply=msg)

            note_str = f"Bill: {bill_item}" if bill_item else "Counter bill"
            draft_res = await tools.create_draft(
                s,
                shop_id,
                customer_id=target_cid,
                type="credit",
                amount=bill_amt,
                note=note_str,
                transcript=raw_text,
                language=lang,
            )
            sess.last_draft_id = draft_res.get("draft_id")
            proj_bal = cur_bal + bill_amt

            draft_events = [{**draft_res, "tx_type": "credit", "type": "draft"}]
            if draft_res.get("pending_promise"):
                p_info = draft_res["pending_promise"]
                draft_events.append({
                    "type": "promise_card",
                    "alert": True,
                    "entity_name": c_display,
                    "customer_name": c_display,
                    "amount": p_info.get("promised_amount"),
                    "expected_date": p_info.get("expected_date"),
                    "description": p_info.get("description"),
                    "status": p_info.get("status"),
                    "new_amount": bill_amt,
                    "draft_id": draft_res.get("draft_id"),
                })

            if draft_res.get("rule_warnings") and draft_res.get("pending_promise"):
                msg = f"{_format_promise_warning_msg(draft_res, c_display, bill_amt, lang)} {_format_rule_warning_msg(draft_res, c_display, bill_amt, lang)}"
            elif draft_res.get("pending_promise"):
                msg = _format_promise_warning_msg(draft_res, c_display, bill_amt, lang)
            elif draft_res.get("rule_warnings"):
                msg = _format_rule_warning_msg(draft_res, c_display, bill_amt, lang)
            elif lang.startswith("kn"):
                msg = f"{c_display} avarige ₹{bill_amt:,.0f} udhar draft aagide (naya baaki ₹{proj_bal:,.0f}). Confirm maadla?"
            else:
                msg = f"{c_display} ke naam ₹{bill_amt:,.0f} udhar draft ban gaya hai (naya balance ₹{proj_bal:,.0f}). Confirm karein?"

            return FastPathResult(handled=True, reply=msg, events=draft_events)

    # ---------------------------------------------------------
    # 0D. MULTI-TURN COUNTER FLOW: PENDING BILL ASSIGNED TO PAYMENT PROMISE (e.g. "Kal dega Ramesh" / "Naale kodtini Ramesh")
    # ---------------------------------------------------------
    if sess and getattr(sess, "pending_bill_amount", None) and is_promise_rec:
        bill_amt = sess.pending_bill_amount
        sess.pending_bill_amount = None
        sess.pending_bill_item = None
        cust_name = " ".join(t.capitalize() for t in name_tokens[:2]) if name_tokens else (sess.active_customer_name or "Customer")
        exp_date = _parse_relative_promise_date(text)
        async with SessionLocal() as s:
            p_res = await tools.create_promise(
                s,
                shop_id,
                entity_name=cust_name,
                promise_type="PAYMENT_PROMISE",
                description=f"Counter bill payment promise of ₹{bill_amt:,.0f}",
                expected_date=exp_date.isoformat(),
                promised_amount=bill_amt,
                transcript=raw_text,
            )
            date_str = exp_date.isoformat()
            if lang.startswith("kn"):
                msg = f"{cust_name} avaru ₹{bill_amt:,.0f} koduvudagi promise record aagide ({date_str})."
            elif lang.startswith("hi"):
                msg = f"{cust_name} ji ka ₹{bill_amt:,.0f} dene ka wada ({date_str}) record kar liya hai."
            else:
                msg = f"Payment promise of ₹{bill_amt:,.0f} from {cust_name} recorded for {date_str}."
            return FastPathResult(
                handled=True,
                reply=msg,
                events=[{
                    "type": "promise_card",
                    "entity_name": cust_name,
                    "amount": bill_amt,
                    "expected_date": date_str,
                    "description": f"Counter bill payment promise of ₹{bill_amt:,.0f}",
                    "status": "PENDING",
                    "promise_id": p_res.get("promise_id"),
                }],
            )

    # ---------------------------------------------------------
    # 0E. INITIAL COUNTER BILL TOTAL / THE KIRANA TRILEMMA TRIGGER
    # (e.g. "Parle ji aapka 20 hua", "Aapka 50 hua", "Kul 120 bana", "Total 150 hua")
    # ---------------------------------------------------------
    if amount and is_bill_total and not name_tokens and not (is_credit or is_payment or is_return or is_discount or is_advance):
        if sess:
            sess.pending_bill_amount = amount
            sess.pending_bill_item = detected_item

        item_str = f" ({detected_item})" if detected_item else ""
        if lang.startswith("kn"):
            msg = f"₹{amount:,.0f}{item_str} aagide. Eega payment maadthara, nantara promise maadthara, athava udhar baribeka?"
        elif lang.startswith("hi"):
            msg = f"₹{amount:,.0f}{item_str} hue. Abhi payment de rahe hain, wada kar rahe hain kab denge, ya udhar khate mein likh loon?"
        else:
            msg = f"Bill is ₹{amount:,.0f}{item_str}. Paying now, making a payment promise, or adding to credit khata?"

        return FastPathResult(handled=True, reply=msg)

    # ---------------------------------------------------------
    # 1. AMBIENT SHOP CHATTER FILTER (< 0.1ms)
    # Customers talking about items, prices, claiming payments, or paying exact cash (PAID_SALE):
    # ---------------------------------------------------------
    if PAID_SALE_PATTERN.search(text) and not (CREDIT_PATTERN.search(text) or LOAN_DIRECTION_PATTERN.search(text)):
        return FastPathResult(handled=True, reply="[SILENT]")

    for pat in CHATTER_PATTERNS:
        if pat.search(text):
            if "maine" in lower or "main " in lower or "bhaiya" in lower or not amount:
                return FastPathResult(handled=True, reply="[SILENT]")

    # ---------------------------------------------------------
    # 2. CONFIRM PENDING UNDO TRANSACTION
    # ---------------------------------------------------------
    if sess and getattr(sess, "pending_undo_tid", None) and CONFIRM_PATTERN.search(text):
        async with SessionLocal() as s:
            out = await tools.undo_last_transaction(s, shop_id, confirmed_undo=True)
            sess.pending_undo_tid = None
            if lang.startswith("kn"):
                msg = "Hindina entry safalavaagi raddhugolislaagide."
            else:
                msg = "Pichli entry safalta-purvak delete kar di gayi hai."
            return FastPathResult(handled=True, reply=msg)

    # ---------------------------------------------------------
    # 3. CORRECTION AFTER READ-BACK (e.g. "Nahi 430 likho, 340 nahi" / "alla 430 bardu")
    # ---------------------------------------------------------
    if active_draft_id and amount and not name_tokens and (CANCEL_PATTERN.search(text) or any(w in lower for w in ["likho", "bardu", "karo", "maadi"])):
        async with SessionLocal() as s:
            old_t = await s.get(Transaction, uuid.UUID(active_draft_id))
            if old_t and str(old_t.shop_id) == shop_id:
                target_cid = str(old_t.customer_id)
                old_tx_type = old_t.type
                old_t.status = "cancelled"
                await s.commit()

                tx_type = "payment" if PAYMENT_PATTERN.search(text) else ("credit" if CREDIT_PATTERN.search(text) else old_tx_type)
                new_draft = await tools.create_draft(
                    s,
                    shop_id,
                    customer_id=target_cid,
                    type=tx_type,
                    amount=amount,
                    payment_mode=payment_mode,
                    transcript=text,
                    language=lang,
                )
                if sess:
                    sess.last_draft_id = new_draft.get("draft_id")

                cname = new_draft.get("customer", "Customer")
                bal = float(new_draft.get("projected_balance", 0))

                if new_draft.get("rule_warnings"):
                    msg = _format_rule_warning_msg(new_draft, cname, amount, lang)
                elif lang.startswith("kn"):
                    msg = f"Tiddupaadi maadlaagide: {cname} avarige ₹{amount:,.0f} {tx_type} draft aagide (naya baaki ₹{bal:,.0f}). Confirm maadla?"
                else:
                    msg = f"Sudhaar diya gaya hai: {cname} ke naam ₹{amount:,.0f} {tx_type} draft ban gaya hai (naya balance ₹{bal:,.0f}). Confirm karein?"

                return FastPathResult(
                    handled=True,
                    reply=msg,
                    events=[{**new_draft, "tx_type": tx_type, "type": "draft"}],
                )

    # ---------------------------------------------------------
    # 4. OVERRIDE OR CONFIRM ACTIVE DRAFT
    # ---------------------------------------------------------
    is_override_speech = bool(OVERRIDE_PATTERN.search(text)) or "continue" in lower
    if active_draft_id and (CONFIRM_PATTERN.search(text) or is_override_speech):
        async with SessionLocal() as s:
            if is_override_speech:
                # Explicitly override any shop rule warnings first
                await tools.override_rule_warnings(s, shop_id, active_draft_id)

            out = await tools.confirm_draft(s, shop_id, active_draft_id)
            if out.get("confirmed"):
                cname = out.get("customer", "Customer")
                bal = out.get("new_balance", 0)
                amt = out.get("amount", 0)
                ttype = out.get("type", "transaction")
                if sess:
                    sess.last_draft_id = None
                    sess.active_customer_id = None
                    sess.active_customer_name = None
                    sess.active_amount = None
                    sess.active_disambiguation = None

                override_note = " (niyam override karke)" if is_override_speech else ""
                if lang.startswith("kn"):
                    msg = f"Khaatrigolislaagide! ₹{amt:,.0f} {ttype} {cname} avarige daakhalagide. Naya baaki ₹{bal:,.0f}."
                else:
                    msg = f"Confirm ho gaya{override_note}! ₹{amt:,.0f} {ttype} record ho gaya. {cname} ka naya balance ₹{bal:,.0f} hai."

                return FastPathResult(
                    handled=True,
                    reply=msg,
                    events=[{**out, "type": "confirmed"}],
                )
            elif "Unresolved Dukaan Rule warnings" in out.get("error", ""):
                # Unresolved rule warning reminder: tell the written rule text!
                draft_tx = await s.get(Transaction, uuid.UUID(active_draft_id))
                r_warns = draft_tx.rule_warnings if draft_tx else []
                r_text = " aur ".join(f"\"{w.get('rule_text') or w.get('message')}\"" for w in r_warns) if r_warns else "dukaan rule"
                if lang.startswith("kn"):
                    msg = f"⚠️ Niyam meeirsalilla: {r_text}. Khaatrigolisalu 'Continue anyway' antha heli athava amount badalisi."
                else:
                    msg = f"⚠️ Entry par aapka dukaan niyam laga hai: {r_text}. Confirm karne ke liye 'Continue anyway' boliye ya amount change kijiye."
                return FastPathResult(handled=True, reply=msg)

    # ---------------------------------------------------------
    # 5. CANCEL ACTIVE DRAFT
    # ---------------------------------------------------------
    if active_draft_id and CANCEL_PATTERN.search(text):
        async with SessionLocal() as s:
            out = await tools.cancel_draft(s, shop_id, active_draft_id)
            if sess:
                sess.last_draft_id = None
                sess.active_customer_id = None
                sess.active_customer_name = None
                sess.active_amount = None
                sess.active_disambiguation = None

            if lang.startswith("kn"):
                msg = "Draft raddhugolislaagide."
            else:
                msg = "Draft cancel kar diya gaya hai."

            return FastPathResult(
                handled=True,
                reply=msg,
                events=[{**out, "type": "cancelled"}],
            )

    # ---------------------------------------------------------
    # 6. UNDO / DELETE LAST ENTRY ("Last entry delete maadi", "Pichla entry hatao")
    # ---------------------------------------------------------
    if UNDO_PATTERN.search(text):
        async with SessionLocal() as s:
            out = await tools.undo_last_transaction(s, shop_id, confirmed_undo=False)
            if "error" in out:
                return FastPathResult(handled=True, reply=out["error"])

            tid = out.get("transaction_id")
            cname = out.get("customer", "Customer")
            amt = float(out.get("amount", 0))
            ttype = out.get("type", "transaction")

            if sess:
                sess.pending_undo_tid = tid

            if lang.startswith("kn"):
                msg = f"Hindina entry: {cname} avara ₹{amt:,.0f} {ttype}. Idannu raddhugolisabekaa? (Haan / Beda heli)."
            else:
                msg = f"Pichli entry: {cname} ke ₹{amt:,.0f} {ttype}. Kya aap ise sach me delete karna chahte hain?"

            return FastPathResult(handled=True, reply=msg)

    # ---------------------------------------------------------
    # 7. PAYMENT REMINDER ("Ramesh ko yaad dilao", "Lakshmi akka ge reminder kalsi")
    # ---------------------------------------------------------
    if REMINDER_PATTERN.search(text):
        target_name = " ".join(t.capitalize() for t in name_tokens[:2]) if name_tokens else None
        if not target_name and sess and sess.active_customer_name:
            target_name = sess.active_customer_name

        if target_name:
            async with SessionLocal() as s:
                search_res = await tools.search_customers(s, shop_id, target_name)
                matches = search_res.get("matches", [])
                best, ambig = _pick_best_match(matches, target_name)
                if best:
                    rem_res = await tools.prepare_reminder(s, shop_id, customer_id=best["customer_id"])
                    bal = rem_res.get("balance", 0)
                    if lang.startswith("kn"):
                        msg = f"{best['name']} avara ₹{bal:,.0f} baaki reminder tayaride. WhatsApp link kalsabahudu."
                    else:
                        msg = f"{best['name']} ke ₹{bal:,.0f} baaki ka WhatsApp reminder ready hai."

                    return FastPathResult(
                        handled=True,
                        reply=msg,
                        events=[{**rem_res, "type": "reminder"}],
                    )

    # ---------------------------------------------------------
    # 8. FULL SETTLEMENT ("Sab clear", "Ella clear maadi", "Hisaab chukta")
    # ---------------------------------------------------------
    if SETTLE_PATTERN.search(text) and not active_draft_id:
        target_name = " ".join(t.capitalize() for t in name_tokens[:2]) if name_tokens else None
        if not target_name and sess and sess.active_customer_name:
            target_name = sess.active_customer_name

        if target_name:
            async with SessionLocal() as s:
                search_res = await tools.search_customers(s, shop_id, target_name)
                matches = search_res.get("matches", [])
                best, ambig = _pick_best_match(matches, target_name)

                if best:
                    settle_res = await tools.settle_balance(
                        s,
                        shop_id,
                        customer_id=best["customer_id"],
                        payment_mode=payment_mode,
                        language=lang,
                    )
                    if settle_res.get("already_settled"):
                        if lang.startswith("kn"):
                            msg = f"{best['name']} avarinda yaavude baaki illa."
                        else:
                            msg = f"{best['name']} ka koi baaki hisaab nahi hai (already settled)."
                        return FastPathResult(handled=True, reply=msg)

                    if sess:
                        sess.last_draft_id = settle_res.get("draft_id")

                    s_amt = settle_res.get("amount", 0)
                    if lang.startswith("kn"):
                        msg = f"{best['name']} avara kul baaki ₹{s_amt:,.0f} clear maaduva draft tayaride. Confirm maadla?"
                    else:
                        msg = f"{best['name']} ka poora hisaab ₹{s_amt:,.0f} clear karne ka draft ban gaya hai. Confirm karein?"

                    return FastPathResult(
                        handled=True,
                        reply=msg,
                        events=[{**settle_res, "tx_type": "payment", "type": "draft"}],
                    )

    # ---------------------------------------------------------
    # 8A. RECORD PAYMENT PROMISE ("Ramesh kal 500 dega", "Suresh naale 200 kodtini")
    # ---------------------------------------------------------
    if amount and name_tokens and PROMISE_RECORD_PATTERN.search(text) and not (is_payment or is_return or is_discount):
        cust_name = " ".join(t.capitalize() for t in name_tokens[:2])
        exp_date = _parse_relative_promise_date(text)

        async with SessionLocal() as s:
            p_res = await tools.create_promise(
                s,
                shop_id,
                entity_name=cust_name,
                promise_type="PAYMENT_PROMISE",
                description=f"Payment promise of ₹{amount:,.0f}",
                expected_date=exp_date.isoformat(),
                promised_amount=amount,
                transcript=text,
            )

            date_str = exp_date.isoformat()
            if lang.startswith("kn"):
                msg = f"{cust_name} avaru ₹{amount:,.0f} koduvudagi promise record aagide ({date_str}). Ledger baaki badalaagilla."
            elif lang.startswith("hi"):
                msg = f"{cust_name} ji ka ₹{amount:,.0f} dene ka wada ({date_str}) record kar liya hai. Ledger balance change nahi hua hai."
            else:
                msg = f"Payment promise of ₹{amount:,.0f} from {cust_name} recorded for {date_str}. Ledger balance unchanged."

            return FastPathResult(
                handled=True,
                reply=msg,
                events=[{
                    "type": "promise_card",
                    "entity_name": cust_name,
                    "amount": amount,
                    "expected_date": date_str,
                    "description": f"Payment promise of ₹{amount:,.0f}",
                    "status": "PENDING",
                    "promise_id": p_res.get("promise_id"),
                }],
            )

    # ---------------------------------------------------------
    # 8B. PROMISE INQUIRY ("Kiska promise pending hai", "Ramesh ka promise kya tha")
    # ---------------------------------------------------------
    if PROMISE_QUERY_PATTERN.search(text) and not amount:
        cust_name = " ".join(t.capitalize() for t in name_tokens[:2]) if name_tokens else None
        if not cust_name and sess and sess.active_customer_name:
            cust_name = sess.active_customer_name

        async with SessionLocal() as s:
            p_list = await tools.list_promises(s, shop_id, status="PENDING", customer_name=cust_name)
            if not p_list and cust_name:
                p_list = await tools.list_promises(s, shop_id, status="PENDING")

            if not p_list:
                if lang.startswith("kn"):
                    msg = "Yaavude pending promises illa."
                elif lang.startswith("hi"):
                    msg = "Koi pending payment promise nahi hai."
                else:
                    msg = "No pending promises found."
                return FastPathResult(handled=True, reply=msg)

            lines = []
            for p in p_list[:3]:
                p_amt = float(p.get("promised_amount") or 0)
                lines.append(f"{p['entity_name']} (₹{p_amt:,.0f}, {p['expected_date']})")
            summary = ", ".join(lines)

            if lang.startswith("kn"):
                msg = f"Pending promises: {summary}."
            elif lang.startswith("hi"):
                msg = f"Pending promises: {summary}."
            else:
                msg = f"Pending promises: {summary}."

            return FastPathResult(
                handled=True,
                reply=msg,
                events=[{
                    "type": "promise_card",
                    "entity_name": p_list[0]["entity_name"],
                    "amount": p_list[0].get("promised_amount"),
                    "expected_date": p_list[0].get("expected_date"),
                    "description": p_list[0].get("description"),
                    "status": p_list[0].get("status"),
                }],
            )

    # ---------------------------------------------------------
    # 9. DISAMBIGUATION RESOLUTION (e.g. "1", "pehla wala", landmark)
    # ---------------------------------------------------------
    if sess and sess.active_disambiguation:
        matches = sess.active_disambiguation
        chosen_match = None

        if re.search(r"\b(?:1|pehla|first|one|ondu)\b", lower):
            chosen_match = matches[0] if len(matches) >= 1 else None
        elif re.search(r"\b(?:2|dusra|second|two|eradu)\b", lower):
            chosen_match = matches[1] if len(matches) >= 2 else None
        elif re.search(r"\b(?:3|teesra|third|three|mooru)\b", lower):
            chosen_match = matches[2] if len(matches) >= 3 else None
        else:
            for m in matches:
                lm = (m.get("landmark") or "").lower()
                if lm and re.search(r"\b" + re.escape(lm) + r"\b", lower):
                    chosen_match = m
                    break

        if chosen_match:
            sess.active_disambiguation = None
            sess.active_customer_id = chosen_match["customer_id"]
            sess.active_customer_name = chosen_match["name"]

            # If an amount was already waiting, create the draft immediately!
            if sess.active_amount:
                tx_amt = sess.active_amount
                tx_t = sess.active_tx_type or "credit"
                p_mode = sess.active_payment_mode
                sess.active_amount = None
                sess.active_tx_type = None
                sess.active_payment_mode = None

                async with SessionLocal() as s:
                    draft_res = await tools.create_draft(
                        s,
                        shop_id,
                        customer_id=chosen_match["customer_id"],
                        type=tx_t,
                        amount=tx_amt,
                        payment_mode=p_mode,
                        transcript=text,
                        language=lang,
                    )
                    sess.last_draft_id = draft_res.get("draft_id")
                    cur_bal = float(chosen_match.get("balance", 0))
                    proj_bal = cur_bal + tx_amt if tx_t == "credit" else cur_bal - tx_amt

                    lm_str = f" ({chosen_match.get('landmark')})" if chosen_match.get("landmark") else ""
                    mode_str = f" {p_mode.upper()}" if p_mode else ""
                    if lang.startswith("kn"):
                        msg = f"{chosen_match['name']}{lm_str} avarige ₹{tx_amt:,.0f}{mode_str} {tx_t} draft aagide (naya baaki ₹{proj_bal:,.0f}). Confirm maadla?"
                    else:
                        msg = f"{chosen_match['name']}{lm_str} ke naam ₹{tx_amt:,.0f}{mode_str} {tx_t} draft ban gaya hai (naya balance ₹{proj_bal:,.0f}). Confirm karein?"

                    return FastPathResult(
                        handled=True,
                        reply=msg,
                        events=[{**draft_res, "tx_type": tx_t, "type": "draft"}],
                    )
            else:
                lm_str = f" ({chosen_match.get('landmark')})" if chosen_match.get("landmark") else ""
                if lang.startswith("kn"):
                    msg = f"{chosen_match['name']}{lm_str} avarige eshtu udhar athava jama baribeku?"
                else:
                    msg = f"{chosen_match['name']}{lm_str} ke naam kitna udhar ya payment likhna hai?"
                return FastPathResult(handled=True, reply=msg)

    # ---------------------------------------------------------
    # 10. SHOP SUMMARY QUERY ("Aaj kitna udhar gaya", "Total collection")
    # ---------------------------------------------------------
    if SUMMARY_PATTERN.search(text):
        async with SessionLocal() as s:
            res = await tools.get_shop_summary(s, shop_id)
            tot = res.get("total_outstanding", 0)
            cr = res.get("credit_today", 0)
            pay = res.get("payments_today", 0)
            cnt = res.get("customer_count", 0)
            top_debts = res.get("top_debtors", [])

            if "who owes the most" in lower or "sabse zyada" in lower:
                if top_debts:
                    top_list = ", ".join(f"{d['name']} (₹{d['balance']:,.0f})" for d in top_debts[:3])
                    msg = f"Sabse zyada baaki: {top_list}."
                else:
                    msg = "Sabhi customers ka hisaab clear hai."
                return FastPathResult(handled=True, reply=msg)

            if lang.startswith("kn"):
                msg = f"Dukaan summary: Kul baaki ₹{tot:,.0f} ({cnt} graahakaru). Indina udhar ₹{cr:,.0f}, jama ₹{pay:,.0f}."
            else:
                msg = f"Dukaan summary: Total udhar ₹{tot:,.0f} hai {cnt} customers par. Aaj ₹{cr:,.0f} udhar gaya, aur ₹{pay:,.0f} collection hua."
            return FastPathResult(handled=True, reply=msg)

    # ---------------------------------------------------------
    # 11. BALANCE INQUIRY ("Lakshmi akka ge eshtu baaki ide?", "Ramesh balance")
    # ---------------------------------------------------------
    if BALANCE_PATTERN.search(text) and not amount:
        target_name = " ".join(t.capitalize() for t in name_tokens[:2]) if name_tokens else None
        if not target_name and sess and sess.active_customer_name:
            target_name = sess.active_customer_name

        if target_name:
            async with SessionLocal() as s:
                search_res = await tools.search_customers(s, shop_id, target_name)
                matches = search_res.get("matches", [])
                best, ambig = _pick_best_match(matches, target_name)
                if best:
                    bal = float(best.get("balance", 0))
                    if lang.startswith("kn"):
                        msg = f"{best['name']} avarinda kul ₹{bal:,.0f} baaki ide."
                    else:
                        msg = f"{best['name']} ka balance ₹{bal:,.0f} baaki hai."
                    return FastPathResult(handled=True, reply=msg)
                elif ambig:
                    if sess:
                        sess.active_disambiguation = ambig
                    opts = " ya ".join(f"{m['name']} ({m.get('landmark') or 'main'})" for m in ambig[:2])
                    msg = f"{target_name} naam ke multiple log hain: {opts}. Kiska hisaab dekhna hai?"
                    return FastPathResult(handled=True, reply=msg)
                else:
                    if lang.startswith("kn"):
                        msg = f"{target_name} hesarina graahakaru sigalilla."
                    else:
                        msg = f"{target_name} naam ke koi customer nahi mile."
                    return FastPathResult(handled=True, reply=msg)

    # ---------------------------------------------------------
    # 12. MULTI-TURN CONTINUATION: Amount & Type provided with active customer in session
    # (e.g. Turn 1: "Ramesh" -> Turn 2: "450 udhar")
    # ---------------------------------------------------------
    if amount and sess and (sess.active_customer_id or sess.active_customer_name) and not name_tokens:
        tx_type = "adjustment" if (is_return or is_discount) else ("payment" if (is_payment or is_advance) else "credit")
        adj_reason = "return" if is_return else ("discount" if is_discount else None)
        note = "Cash Loan" if is_loan else ("Advance / Deposit" if is_advance else None)

        async with SessionLocal() as s:
            target_cid = sess.active_customer_id
            target_name = sess.active_customer_name

            if not target_cid and target_name:
                new_c = await tools.create_customer(s, shop_id, name=target_name)
                target_cid = new_c.get("customer_id")

            if target_cid:
                draft_res = await tools.create_draft(
                    s,
                    shop_id,
                    customer_id=target_cid,
                    type=tx_type,
                    amount=amount,
                    payment_mode=payment_mode,
                    adjustment_reason=adj_reason,
                    note=note,
                    transcript=text,
                    language=lang,
                )
                sess.last_draft_id = draft_res.get("draft_id")
                c_display = target_name or draft_res.get("customer", "Customer")
                sess.active_customer_id = None
                sess.active_customer_name = None

                mode_str = f" {payment_mode.upper()}" if payment_mode else ""
                proj_bal = float(draft_res.get("projected_balance", 0))
                tx_label = adj_reason if (tx_type == "adjustment" and adj_reason) else tx_type

                draft_events = [{**draft_res, "tx_type": tx_type, "type": "draft"}]
                if draft_res.get("pending_promise"):
                    p_info = draft_res["pending_promise"]
                    draft_events.append({
                        "type": "promise_card",
                        "alert": True,
                        "entity_name": c_display,
                        "customer_name": c_display,
                        "amount": p_info.get("promised_amount"),
                        "expected_date": p_info.get("expected_date"),
                        "description": p_info.get("description"),
                        "status": p_info.get("status"),
                        "new_amount": amount,
                        "draft_id": draft_res.get("draft_id"),
                    })

                # Promise warning & Rule warning check
                if draft_res.get("rule_warnings") and draft_res.get("pending_promise"):
                    msg = f"{_format_promise_warning_msg(draft_res, c_display, amount, lang)} {_format_rule_warning_msg(draft_res, c_display, amount, lang)}"
                elif draft_res.get("pending_promise"):
                    msg = _format_promise_warning_msg(draft_res, c_display, amount, lang)
                elif draft_res.get("rule_warnings"):
                    msg = _format_rule_warning_msg(draft_res, c_display, amount, lang)
                elif draft_res.get("anomaly_warning"):
                    if lang.startswith("kn"):
                        msg = f"⚠️ Gamana kodi: ₹{amount:,.0f} mottha saamaanyakkinta hecchide! {c_display} avarige khaathri maadlaa?"
                    else:
                        msg = f"⚠️ Alert: ₹{amount:,.0f} amount customer ke normal entry se 10 guna zyada hai! Confirm karein?"
                elif lang.startswith("kn"):
                    msg = f"{c_display} avarige ₹{amount:,.0f}{mode_str} {tx_label} draft aagide (naya baaki ₹{proj_bal:,.0f}). Confirm maadla?"
                else:
                    msg = f"{c_display} ke naam ₹{amount:,.0f}{mode_str} {tx_label} draft ban gaya hai (naya balance ₹{proj_bal:,.0f}). Confirm karein?"

                return FastPathResult(
                    handled=True,
                    reply=msg,
                    events=draft_events,
                )

    # ---------------------------------------------------------
    # 13. MULTI-TURN CONTINUATION: Customer name provided with active amount waiting in session
    # (e.g. Turn 1: "500 udhar" -> Turn 2: "Pooja")
    # ---------------------------------------------------------
    if not amount and sess and sess.active_amount and name_tokens:
        tx_amt = sess.active_amount
        tx_type = sess.active_tx_type or "credit"
        p_mode = sess.active_payment_mode
        cust_name = " ".join(t.capitalize() for t in name_tokens[:2])

        async with SessionLocal() as s:
            search_res = await tools.search_customers(s, shop_id, cust_name)
            matches = search_res.get("matches", [])
            best, ambig = _pick_best_match(matches, cust_name)

            if best:
                draft_res = await tools.create_draft(
                    s,
                    shop_id,
                    customer_id=best["customer_id"],
                    type=tx_type,
                    amount=tx_amt,
                    payment_mode=p_mode,
                    transcript=text,
                    language=lang,
                )
                sess.last_draft_id = draft_res.get("draft_id")
                sess.active_amount = None
                sess.active_tx_type = None
                sess.active_payment_mode = None

                cur_bal = float(best.get("balance", 0))
                proj_bal = cur_bal + tx_amt if tx_type == "credit" else cur_bal - tx_amt
                mode_str = f" {p_mode.upper()}" if p_mode else ""

                draft_events = [{**draft_res, "tx_type": tx_type, "type": "draft"}]
                if draft_res.get("pending_promise"):
                    p_info = draft_res["pending_promise"]
                    draft_events.append({
                        "type": "promise_card",
                        "alert": True,
                        "entity_name": best["name"],
                        "customer_name": best["name"],
                        "amount": p_info.get("promised_amount"),
                        "expected_date": p_info.get("expected_date"),
                        "description": p_info.get("description"),
                        "status": p_info.get("status"),
                        "new_amount": tx_amt,
                        "draft_id": draft_res.get("draft_id"),
                    })

                if draft_res.get("rule_warnings") and draft_res.get("pending_promise"):
                    msg = f"{_format_promise_warning_msg(draft_res, best['name'], tx_amt, lang)} {_format_rule_warning_msg(draft_res, best['name'], tx_amt, lang)}"
                elif draft_res.get("pending_promise"):
                    msg = _format_promise_warning_msg(draft_res, best["name"], tx_amt, lang)
                elif draft_res.get("rule_warnings"):
                    msg = _format_rule_warning_msg(draft_res, best["name"], tx_amt, lang)
                elif lang.startswith("kn"):
                    msg = f"{best['name']} avarige ₹{tx_amt:,.0f}{mode_str} {tx_type} draft aagide (naya baaki ₹{proj_bal:,.0f}). Confirm maadla?"
                else:
                    msg = f"{best['name']} ke naam ₹{tx_amt:,.0f}{mode_str} {tx_type} draft ban gaya hai (naya balance ₹{proj_bal:,.0f}). Confirm karein?"

                return FastPathResult(
                    handled=True,
                    reply=msg,
                    events=draft_events,
                )

            elif ambig:
                sess.active_disambiguation = ambig
                items = [f"{i}. {m['name']} ({m.get('landmark') or 'main'})" for i, m in enumerate(ambig[:3], 1)]
                msg = f"{cust_name} naam ke multiple customers hain: {' | '.join(items)}. Kiske naam likhun?"
                return FastPathResult(handled=True, reply=msg)

            else:
                new_c = await tools.create_customer(s, shop_id, name=cust_name)
                draft_res = await tools.create_draft(
                    s,
                    shop_id,
                    customer_id=new_c["customer_id"],
                    type=tx_type,
                    amount=tx_amt,
                    payment_mode=p_mode,
                    transcript=text,
                    language=lang,
                )
                sess.last_draft_id = draft_res.get("draft_id")
                sess.active_amount = None
                sess.active_tx_type = None
                sess.active_payment_mode = None

                if draft_res.get("rule_warnings"):
                    msg = _format_rule_warning_msg(draft_res, cust_name, tx_amt, lang)
                elif lang.startswith("kn"):
                    msg = f"Hosa graahaka {cust_name} serislaagide mattu ₹{tx_amt:,.0f} {tx_type} draft aagide. Confirm maadla?"
                else:
                    msg = f"Naye customer {cust_name} ke naam ₹{tx_amt:,.0f} {tx_type} draft bana diya hai. Confirm karein?"

                return FastPathResult(
                    handled=True,
                    reply=msg,
                    events=[{**draft_res, "tx_type": tx_type, "type": "draft"}],
                )

    # ---------------------------------------------------------
    # 14. COMPLETE ONE-SHOT TRANSACTION (Customer + Amount + Type + Mode)
    # (e.g. "Ramesh ge 340 udhar bardu", "Suresh 500 kottru", "Pooja ne 200 PhonePe kiya", "Ramesh 500")
    # ---------------------------------------------------------
    if amount and name_tokens:
        tx_type = "adjustment" if (is_return or is_discount) else ("payment" if (is_payment or is_advance) else "credit")
        adj_reason = "return" if is_return else ("discount" if is_discount else None)
        note = "Cash Loan" if is_loan else ("Advance / Deposit" if is_advance else None)
        cust_name = " ".join(t.capitalize() for t in name_tokens[:2])

        async with SessionLocal() as s:
            search_res = await tools.search_customers(s, shop_id, cust_name)
            matches = search_res.get("matches", [])
            best, ambig = _pick_best_match(matches, cust_name)

            if best:
                draft_res = await tools.create_draft(
                    s,
                    shop_id,
                    customer_id=best["customer_id"],
                    type=tx_type,
                    amount=amount,
                    payment_mode=payment_mode,
                    adjustment_reason=adj_reason,
                    note=note,
                    transcript=text,
                    language=lang,
                )
                if sess:
                    sess.last_draft_id = draft_res.get("draft_id")
                    sess.active_customer_id = None
                    sess.active_customer_name = None

                cname = best["name"]
                cur_bal = float(best.get("balance", 0))
                proj_bal = cur_bal + amount if tx_type == "credit" else cur_bal - amount
                mode_str = f" {payment_mode.upper()}" if payment_mode else ""
                tx_label = "advance" if is_advance else (adj_reason if (tx_type == "adjustment" and adj_reason) else tx_type)

                draft_events = [{**draft_res, "tx_type": tx_type, "type": "draft"}]
                if draft_res.get("pending_promise"):
                    p_info = draft_res["pending_promise"]
                    draft_events.append({
                        "type": "promise_card",
                        "alert": True,
                        "entity_name": cname,
                        "customer_name": cname,
                        "amount": p_info.get("promised_amount"),
                        "expected_date": p_info.get("expected_date"),
                        "description": p_info.get("description"),
                        "status": p_info.get("status"),
                        "new_amount": amount,
                        "draft_id": draft_res.get("draft_id"),
                    })

                # Promise warning & Rule warning check
                if draft_res.get("rule_warnings") and draft_res.get("pending_promise"):
                    msg = f"{_format_promise_warning_msg(draft_res, cname, amount, lang)} {_format_rule_warning_msg(draft_res, cname, amount, lang)}"
                elif draft_res.get("pending_promise"):
                    msg = _format_promise_warning_msg(draft_res, cname, amount, lang)
                elif draft_res.get("rule_warnings"):
                    msg = _format_rule_warning_msg(draft_res, cname, amount, lang)
                elif draft_res.get("anomaly_warning"):
                    if lang.startswith("kn"):
                        msg = f"⚠️ Alert: ₹{amount:,.0f} mottha saamaanyakkinta hecchide! {cname} avarige khaathri maadlaa?"
                    else:
                        msg = f"⚠️ Alert: ₹{amount:,.0f} normal se 10x zyada hai! Confirm karein?"
                elif lang.startswith("kn"):
                    msg = f"{cname} avarige ₹{amount:,.0f}{mode_str} {tx_label} draft aagide (naya baaki ₹{proj_bal:,.0f}). Confirm maadla?"
                else:
                    msg = f"{cname} ke naam ₹{amount:,.0f}{mode_str} {tx_label} draft ban gaya hai (naya balance ₹{proj_bal:,.0f}). Confirm karein?"

                return FastPathResult(
                    handled=True,
                    reply=msg,
                    events=draft_events,
                )

            elif ambig:
                if sess:
                    sess.active_disambiguation = ambig
                    sess.active_amount = amount
                    sess.active_tx_type = tx_type
                    sess.active_payment_mode = payment_mode

                items = []
                for i, m in enumerate(ambig[:3], 1):
                    lm = f" ({m.get('landmark')})" if m.get("landmark") else ""
                    bal = f"₹{float(m.get('balance', 0)):,.0f}"
                    items.append(f"{i}. {m['name']}{lm}, balance {bal}")
                summary_str = " | ".join(items)
                msg = f"{cust_name} naam ke multiple customers hain: {summary_str}. Kiske naam ₹{amount:,.0f} likhun?"
                return FastPathResult(handled=True, reply=msg)

            else:
                new_c = await tools.create_customer(s, shop_id, name=cust_name)
                if "customer_id" in new_c:
                    draft_res = await tools.create_draft(
                        s,
                        shop_id,
                        customer_id=new_c["customer_id"],
                        type=tx_type,
                        amount=amount,
                        payment_mode=payment_mode,
                        adjustment_reason=adj_reason,
                        note=note,
                        transcript=text,
                        language=lang,
                    )
                    if sess:
                        sess.last_draft_id = draft_res.get("draft_id")
                        sess.active_customer_id = None
                        sess.active_customer_name = None

                    mode_str = f" {payment_mode.upper()}" if payment_mode else ""
                    if draft_res.get("rule_warnings"):
                        msg = _format_rule_warning_msg(draft_res, cust_name, amount, lang)
                    elif lang.startswith("kn"):
                        msg = f"Hosa graahaka {cust_name} serislaagide mattu ₹{amount:,.0f}{mode_str} {tx_type} draft aagide. Confirm maadla?"
                    else:
                        msg = f"Naye customer {cust_name} ko register karke ₹{amount:,.0f}{mode_str} {tx_type} draft bana diya hai. Confirm karein?"

                    return FastPathResult(
                        handled=True,
                        reply=msg,
                        events=[{**draft_res, "tx_type": tx_type, "type": "draft"}],
                    )

    # ---------------------------------------------------------
    # 15. PARTIAL INPUT: Customer Name only (No Amount)
    # (e.g. "Ramesh", "Lakshmi akka", "Suresh ka khata")
    # ---------------------------------------------------------
    if not amount and name_tokens and not GREETING_PATTERN.search(text):
        cust_name = " ".join(t.capitalize() for t in name_tokens[:2])
        async with SessionLocal() as s:
            search_res = await tools.search_customers(s, shop_id, cust_name)
            matches = search_res.get("matches", [])
            best, ambig = _pick_best_match(matches, cust_name)

            if best:
                if sess:
                    sess.active_customer_id = best["customer_id"]
                    sess.active_customer_name = best["name"]

                if lang.startswith("kn"):
                    msg = f"{best['name']} avarige eshtu udhar athava jama baribeku?"
                else:
                    msg = f"{best['name']} ke naam kitna udhar ya payment likhna hai?"
                return FastPathResult(handled=True, reply=msg)

            elif ambig:
                if sess:
                    sess.active_disambiguation = ambig
                items = [f"{i}. {m['name']} ({m.get('landmark') or 'main'})" for i, m in enumerate(ambig[:3], 1)]
                msg = f"{cust_name} naam ke multiple customers hain: {' | '.join(items)}. Kiska hisaab dekhna hai?"
                return FastPathResult(handled=True, reply=msg)

            else:
                # Dynamic New Customer: Any name spoken is accepted and tracked in session
                if sess:
                    sess.active_customer_name = cust_name
                    sess.active_customer_id = None

                if lang.startswith("kn"):
                    msg = f"Hosa graahaka {cust_name} avarige eshtu udhar athava jama baribeku?"
                else:
                    msg = f"Naye customer {cust_name} ke naam kitna udhar ya payment likhna hai?"
                return FastPathResult(handled=True, reply=msg)

    # ---------------------------------------------------------
    # 16. PARTIAL INPUT: Amount & Type only (No Customer Name)
    # (e.g. "450 udhar", "500 jama", "200 PhonePe")
    # ---------------------------------------------------------
    if amount and not name_tokens:
        tx_type = "payment" if is_payment else "credit"
        if sess:
            sess.active_amount = amount
            sess.active_tx_type = tx_type
            sess.active_payment_mode = payment_mode

        mode_str = f" {payment_mode.upper()}" if payment_mode else ""
        if lang.startswith("kn"):
            msg = f"₹{amount:,.0f}{mode_str} {tx_type} yaarige baribeku? Graahakara hesaru heli."
        else:
            msg = f"₹{amount:,.0f}{mode_str} {tx_type} kiske naam likhna hai? Kripya customer ka naam batayein."
        return FastPathResult(handled=True, reply=msg)

    # ---------------------------------------------------------
    # 17. EXPLICIT GREETINGS: Respond once, never repeat boilerplate
    # ---------------------------------------------------------
    if GREETING_PATTERN.search(text) and not amount:
        if sess and not sess.greeting_given:
            sess.greeting_given = True
            if lang.startswith("kn"):
                msg = "Namaskara! Dukaan Khata tayaride. Yaara hisaab baribeku?"
            else:
                msg = "Namaste! Dukaan Khata active hai. Kiska hisaab likhna hai?"
            return FastPathResult(handled=True, reply=msg)
        else:
            return FastPathResult(handled=True, reply="[SILENT]")

    # ---------------------------------------------------------
    # 18. UNCLEAR / UNRECOGNIZED INPUT: Forward to Gemini Flash LLM
    # Never block or emit repeated 'Samajh nahi aaya' without LLM analysis!
    # ---------------------------------------------------------
    return FastPathResult(handled=False)
