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
from .conversation_cache import (
    ConversationContextCache,
    ConversationState,
    ShopConversationCacheManager,
)
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
        "parle-g", "parle gi", "parle", "parleg", "पारले", "maggi", "मैगी", "lays", "लेज", "kurkure", "कुरकुरे",
        "goodday", "marie", "mariegold", "oreo", "5star", "dairymilk", "kitkat", "munch",
        "cheeni", "sugar", "चीनी", "sakre", "ಸಕ್ಕರೆ", "doodh", "milk", "दूध", "haalu", "ಹಾಲು",
        "atta", "aata", "आटा", "tel", "oil", "तेल", "enne", "ಎಣ್ಣೆ", "chawal", "rice", "चावल", "akki", "ಅಕ್ಕಿ",
        "dal", "daal", "दाल", "bele", "ಬೇಳೆ", "biscuit", "बिस्कुट", "soap", "sabun", "साबुन", "soop", "ಸೋಪು",
        "bread", "ब्रेड", "ghee", "घी", "thuppa", "ತುಪ್ಪ", "tea", "chai", "चाय", "chaha", "coffee", "kaapi", "ಕಾಫಿ"
    ]:
        if re.search(r"\b" + re.escape(item) + r"\b", lower):
            if item in ("parle", "parle-g", "parle gi", "parleg", "पारले"):
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
    re.compile(r"\b(?:(?:radio\s*city|radio\s*mirchi|red\s*fm|big\s*fm)(?:\s*\d+(?:\.\d+)?\s*(?:fm)?)?|superhit\s*gaana|gana\s*bajao|gaana\s*bajao|gaana\s*lagao|music\s*play|song\s*chalao|dj\s*remix|bhajan|aarti|kirtan)\b", re.I),
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

# Counter Bill Total / Trilemma Pattern (e.g. "Parle ji aapka 20 hua", "Aapka 50 hua", "Kul 120 bana", "Total 150 hua", "80 aaythu", "ok ye lo parle-g tumhara hua 15")
BILL_TOTAL_PATTERN = re.compile(
    r"\b(?:aapka|apka|tumhara|tumara|kul|total|bill|itna\s*hua|itna\s*bana|itna\s*aaythu|hua|hue|bana|hoya|aaythu|aagide|aaitu)\b|"
    r"(?:आपका|तुम्हारा|कुल|टोटल|बिल|हुआ|हुए|बना)|"
    r"(?:ಆಯ್ತು|ಆಗಿದೆ|ನಿಮ್ಮದು|ಒಟ್ಟು|ಬಿಲ್)",
    re.I,
)

# Counter Product Inquiry Pattern (e.g. "shyam ake pucha ki parleg lena hae 15 rupae ka", "Parle-G lena hai 15 rupaye ka")
INQUIRY_PATTERN = re.compile(
    r"\b(?:lena\s*hai|chahiye|chahiye\s*tha|beku|bekittu|pucha|puch\s*raha|puchi|puche|pucho|aaya|aayi|aake|ake|kitne\s*ka|kya\s*rate|packet\s*dena|dena\s*bhaiya|kya\s*bhav|rate\s*kya|eshtu\s*bele|kelida|kelidru)\b|"
    r"(?:लेना\s*है|चाहिए|पूछा|पूछ\s*रहा|आया|कितने\s*का|क्या\s*रेट|देना)|"
    r"(?:ಬೇಕು|ಕೇಳಿದ|ಬಂದ|ಎಷ್ಟು\s*ಬೆಲೆ)",
    re.I,
)

# Shop floor chatter keywords: product requests, casual greetings, customer boasting
CHATTER_PATTERNS = [
    re.compile(r"\b(?:biscuit|packet|cheeni|sugar|atta|tel|oil|dal|doodh|milk|bread|soap|sabun|chawal|rice)\b", re.I),
    re.compile(r"\b(?:kitne\s*ka|kya\s*rate|kya\s*bhav|eshtu\s*bele|rate\s*kya|chahiye|hai\s*kya|milega\s*kya)\b", re.I),
    re.compile(r"\b(?:kaunsa|marigold|parle|maggi|lays|kurkure|shampoo|brush|paste)\b", re.I),
    re.compile(r"\b(?:change\s*hai|khulla\s*hai|chillar\s*hai|chillar\s*illa)\b", re.I),
    re.compile(r"\b(?:thoda\s*kam|kam\s*karo|discount\s*do|bargain)\b", re.I),
    re.compile(r"\b(?:main\s*\d+|maine\s*\d+|maine\s*phonepe|maine\s*gpay|maine\s*paytm|maine\s*de\s*diya|main\s*de\s*raha|maine\s*bhej|maine\s*online|naanu\s*\d+|naanu\s*kodtini)\b", re.I),
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
    r"\b(?:haan|theek|confirm|sari|houdu|haudu|karo|yes|done|maadi|ok|theek\s*hai|sahi\s*hai|right|aama|avunu|sare|athe|sheri|ho|thik\s*aahe|ha|barabar|hyan|thik\s*ache|haanji|thik\s*achhi|hoi|bhal|ji\s*haan|ho\s*gaya|ho\s*gayi|kar\s*do|bhejo|save)\b|"
    r"(?:हाँ|हां|ठीक|ठीक\s*है|सही|सही\s*है|कन्फर्म|करो|कर\s*दो|हो\s*गया|डन|हुआ)|"
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
DEBTORS_QUERY_PATTERN = re.compile(
    r"\b(?:"
    r"kiska\s*kitna|kitna\s*kiska|kis\s*kis\s*ka|kis\s*ka\s*kitna|kaun\s*kitna|kiske\s*kitne|"
    r"kiska\s*(?:udhar|baaki|bakaya)|kitna\s*(?:udhar|baaki)\s*kiska|udhar\s*kiska|udhar\s*list|udhari\s*list|baaki\s*list|"
    r"who\s*owes(?:\s*(?:how\s*much|money|what|the\s*most|the\s*shop))?|debtor[s]?\s*list|list\s*(?:all\s*)?(?:pending\s*)?balances?|"
    r"sabka\s*(?:baaki|hisaab|udhar)|sabke\s*baaki|sabse\s*zyada\s*baaki|"
    r"yaara\s*du\s*eshtu|yaaradu\s*eshtu|yaarige\s*eshtu|yaaru\s*eshtu|yaara\s*baaki|yaarige\s*udri|"
    r"udri\s*patti|baaki\s*patti|ellara\s*baaki|ellara\s*lekka|"
    r"yaarukku\s*evvalavu|yaar\s*evvalavu|evariki\s*entha|evaru\s*entha"
    r")\b|"
    r"(?:"
    r"किसका\s*कितना|कितना\s*किसका|किस-किस\s*का|किस\s*का\s*कितना|कौन\s*कितना|किसके\s*कितने|"
    r"किसका\s*उधार|किसका\s*बाकी|सबका\s*बाकी|सबका\s*उधार|सबका\s*हिसाब|उधारी\s*की\s*लिस्ट|उधार\s*की\s*लिस्ट|उधार\s*लिस्ट|उधारी\s*लिस्ट|बाकी\s*लिस्ट|"
    r"ಯಾರದು\s*ಎಷ್ಟು|ಯಾರಿಗೆ\s*ಎಷ್ಟು|ಯಾರು\s*ಎಷ್ಟು|ಯಾರಾರಿಗೆ|ಎಲ್ಲರ\s*ಬಾಕಿ|ಎಲ್ಲರ\s*ಲೆಕ್ಕ|ಉದ್ರಿ\s*ಪಟ್ಟಿ|ಬಾಕಿ\s*ಪಟ್ಟಿ|"
    r"யாருக்கு\s*எவ்வளவு|யார்\s*எவ்வளவு|ఎవరికి\s*ఎంత|ఎవరు\s*ఎంత"
    r")",
    re.I,
)
BALANCE_PATTERN = re.compile(
    r"\b(?:balance|kitna\s*baaki|eshtu\s*baaki|hisab|hisaab|baaki\s*ide|khata\s*batao|pending|evvalavu\s*baaki|entha\s*baaki|ethra\s*baaki|kiti\s*baaki|ketlu\s*baaki|koto\s*baki|kinna\s*baaki|kete\s*baki|koi\s*baki|kitna\s*baqi|"
    r"kitna\s*hua|kitna\s*bana|eshtu\s*aaythu|eshtu\s*aagide|entha\s*aindi|evvalavu\s*aachu|kitna\s*hua\s*hai|eshtu\s*aaytu)\b|"
    r"(?:बैलेंस|कितना\s*बाकी|हिसाब|खाता\s*बताओ|पेंडिंग|बाकी\s*कितना|कितना\s*हुआ|कितना\s*बना)|"
    r"(?:ಬ್ಯಾಲೆನ್ಸ್|ಎಷ್ಟು\s*ಬಾಕಿ|ಲೆಕ್ಕ|ಬಾಕಿ\s*ಇದೆ|ಎಷ್ಟು\s*ಆಯ್ತು|ಎಷ್ಟು\s*ಆಗಿದೆ)|"
    r"(?:எவ்வளவு\s*பாக்கி)|(?:ఎంత\s*బాకీ)|(?:ఎത്ര\s*ബാക്കി)|(?:किती\s*बाकी)|(?:કેટલું\s*બાકી)|(?:কত\s*বাকি)|(?:ਕਿੰਨਾ\s*ਬਾਕੀ)|(?:କେତେ\s*ବାକି)|(?:کتنا\s*باقی)",
    re.I,
)

# Named Customer Bill / Udhar Entry in Customer's Khata (e.g. 'Ram ka hua 25', 'Ram ka 25 hua', 'Ramesh ge 50 aaythu', 'Suresh du 100 aagide', 'Ram ka bana 25')
NAMED_BILL_CREDIT_PATTERN = re.compile(
    r"(?:\b(?:ka|ki|ke|ge|du|ku|de|da|la|er|hesaralli|khathage|khate|copy|kopi|account|naam)\b|(?:का|की|के|गे|ದು|ಹೆಸರಲ್ಲಿ|ಖಾತೆಗೆ|खाते|कॉपी|नाम)).*?"
    r"(?:\b(?:hua|hue|hui|bana|bane|bani|hoya|aaythu|aagide|aaitu|aaytu|agide|zhala|holo|aindi|aachu)\b|(?:हुआ|हुए|हुई|बना|बने|ಹೋಯಾ|ಆಯ್ತು|ಆಗಿದೆ))|"
    r"(?:\b(?:hua|hue|hui|bana|bane|bani|hoya|aaythu|aagide|aaitu|aaytu|agide|zhala|holo|aindi|aachu)\b|(?:हुआ|हुए|हुई|बना|बने|ಹೋಯಾ|ಆಯ್ತು|ಆಗಿದೆ)).*?"
    r"(?:\b(?:ka|ki|ke|ge|du|ku|de|da|la|er|hesaralli|khathage|khate|copy|kopi|account|naam)\b|(?:का|की|के|गे|ದು|ಹೆಸರಲ್ಲಿ|ಖಾತೆಗೆ|खाते|कॉपी|नाम))",
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
    r"\b(?:ye\s*lo\s*\d+|ye\s*lo\s*bhaiya|change\s*wapas|wapas\s*ye\s*lo|note\s*diya|itna\s*bana.*de\s*diya|ye\s*lo|here\s*is|google\s*pay\s*kar\s*diya|gpay\s*kar\s*diya|phonepe\s*kar\s*diya|paytm\s*kar\s*diya|poore\s*ho\s*gaye)\b|"
    r"(?:ये\s*लो|ये\s*लीजिए|वापस\s*लो|चिल्लर\s*वापस|पूरे\s*हो\s*गए)",
    re.I,
)

# Full Settlement Intent ("Sab clear", "Ella clear maadi", "Hisaab chukta")
SETTLE_PATTERN = re.compile(
    r"\b(?:sab\s*clear|ellaa\s*clear|ella\s*clear|hisaab\s*chukta|hisab\s*chukta|hisaab\s*barabar|settle|clear\s*kar\s*do|clear\s*maadi|write\s*off|bad\s*debt|baaki\s*maaf|band\s*karo|saala\s*manna)\b|"
    r"(?:सब\s*क्लियर|हिसाब\s*चुकता|हिसाब\s*बराबर|पूरा\s*क्लियर|क्लियर\s*कर\s*दो|राइट\s*ऑफ|माफ)|"
    r"(?:ಎಲ್ಲಾ\s*ಕ್ಲಿಯರ್|ಲೆಕ್ಕ\s*ಚುಕ್ತಾ|ಸಾಲ\s*ಮನ್ನಾ|ರೈಟ್\s*ಆಫ್)",
    re.I,
)

# Undo Intent ("Last entry delete maadi", "Pichla entry hatao", "Undo last")
UNDO_PATTERN = re.compile(
    r"\b(?:undo|delete\s*maadi|pichla\s*hatao|last\s*entry\s*delete|delete\s*last|last\s*hatao|pichli\s*entry|undo\s*last|last\s*entry|delete\s*karo)\b|"
    r"(?:पिछली\s*एंट्री|पिछली\s*एंट्री\s*हटाओ|पिछली\s*एंट्री\s*डिलीट|पिछला\s*हटाओ|लास्ट\s*एंट्री\s*डिलीट|अंडू|डिलीट\s*करो)|"
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
    r"\b(?:wapas|vaapas|return|returned|returns|vaapasi|reduce|minus)\b|"
    r"(?:वापस|वापसी|रिटर्न)|"
    r"(?:ವಾಪಸ್|ರಿಟರ್ನ್)",
    re.I,
)
DISCOUNT_PATTERN = re.compile(
    r"\b(?:discount|chillar\s*chhodo|chhod\s*do|round\s*off|chhoot|chhut|chut|choot)\b|"
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

# Cash Drawer / Galla / Cash Book Patterns
CASH_BALANCE_PATTERN = re.compile(
    r"\b(?:cash\s*balance|drawer\s*balance|today'?s\s*cash|aaj\s*ka\s*cash|ivattu\s*cash)\b|"
    r"(?:\b(?:cash\s*box|drawer|galla|petti)\b.*?\b(?:kitna|eshtu|entha|balance|baaki)\b)|"
    r"(?:\b(?:kitna|eshtu|entha|balance|baaki)\b.*?\b(?:cash\s*box|drawer|galla|petti)\b)|"
    r"(?:कैश\s*बैलेंस|गल्ले\s*में\s*कितना|कैश\s*बॉक्स\s*में\s*कितना|आज\s*का\s*कैश)|"
    r"(?:ಕ್ಯಾಶ್\s*ಬ್ಯಾಲೆನ್ಸ್|ಗಲ್ಲಾಪೆಟ್ಟಿಗೆಯಲ್ಲಿ\s*ಎಷ್ಟು|ಕ್ಯಾಶ್\s*ಬಾಕ್ಸ್\s*ಬ್ಯಾಲೆನ್ಸ್)",
    re.I,
)

CASH_IN_PATTERN = re.compile(
    r"\b(?:cash\s*in|cash\s*deposit)\b|"
    r"(?:\b(?:cash\s*box|drawer|galla|petti)\b.*?\b(?:daal|daalo|jama|rakh|rakho|haaki|haaku)\b)|"
    r"(?:\b(?:daal|daalo|jama|rakh|rakho|haaki|haaku)\b.*?\b(?:cash\s*box|drawer|galla|petti)\b)|"
    r"(?:कैश\s*इन|कैश\s*बॉक्स\s*में\s*डालो|गल्ले\s*में\s*डालो|कैश\s*जमा\s*बॉक्स)|"
    r"(?:ಕ್ಯಾಶ್\s*ಇನ್|ಕ್ಯಾಶ್\s*ಬಾಕ್ಸ್‌ಗೆ\s*ಹಾಕಿ|ಗಲ್ಲಾಪೆಟ್ಟಿಗೆಗೆ\s*ಹಾಕಿ)",
    re.I,
)

CASH_OUT_PATTERN = re.compile(
    r"\b(?:cash\s*out|cash\s*withdraw(?:al)?)\b|"
    r"(?:\b(?:cash\s*box|drawer|galla|petti)\b.*?\b(?:nikaal|nikaalo|nikal|nikala|tegiri|tegedu|tegedukonde|kharch|kharchu|kharchige)\b)|"
    r"(?:\b(?:nikaal|nikaalo|nikal|nikala|tegiri|tegedu|tegedukonde|kharch|kharchu|kharchige)\b.*?\b(?:cash\s*box|drawer|galla|petti)\b)|"
    r"(?:\b\d+\s*(?:kharch|expense|kharchige)\b.*?\b(?:nikal|nikaal|nikaalo|nikala|tegedu|tegedukonde)\b)|"
    r"(?:\b(?:nikal|nikaal|nikaalo|nikala|tegedu|tegedukonde)\b.*?\b(?:kharch|expense|kharchige)\b)|"
    r"(?:कैश\s*आउट|कैश\s*बॉक्स\s*से\s*निकालो|गल्ले\s*से\s*निकालो|खर्च\s*के\s*लिए\s*निकाला)|"
    r"(?:ಕ್ಯಾಶ್\s*ಔಟ್|ಕ್ಯಾಶ್\s*ಬಾಕ್ಸ್\s*ಇಂದ\s*ತೆಗೆಯಿರಿ|ಖರ್ಚಿಗೆ\s*ತೆಗೆದೆ)",
    re.I,
)

# Cash Change Calculation (explicit change given, NOT ledger payment)
CHANGE_CALC_PATTERN = re.compile(
    r"\b(?:change\s*(?:do|kodi|wapas|karo|banta|de\s*do|kitna|eshtu)|"
    r"wapas\s*(?:kitna|do|karo|dena|kodi)|"
    r"chillar\s*(?:wapas|kodi|do)|"
    r"kitna\s*wapas\s*(?:dena|karna|hoga)|"
    r"eshtu\s*wapas\s*kodbeku)\b|"
    r"(?:चेंज\s*दो|वापस\s*दो|कितना\s*वापस|चिल्लर\s*दो)|"
    r"(?:ಚೇಂಜ್\s*ಕೊಡಿ|ವಾಪಸ್\s*ಕೊಡಿ|ಎಷ್ಟು\s*ವಾಪಸ್)",
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

# Promise Fulfillment Intent ("Rehan ne promise pura kar diya", "Rhan ne promise pura kardia", "Wada pura kiya")
PROMISE_FULFIL_PATTERN = re.compile(
    r"\b(?:"
    r"promise\s*(?:pura|poora|complete|fulfilled|clear|chukta|settle|ho\s*gaya|nibhaya|paalana)|"
    r"(?:pura|poora|complete|fulfilled|clear|chukta|settle|nibhaya)\s*(?:kar\s*diya|kardia|ho\s*gaya|aaythu|maadi|kiya)?\s*(?:promise|wada)|"
    r"wada\s*(?:pura|poora|complete|fulfilled|clear|chukta|settle|nibhaya)|"
    r"(?:wada|promise)\s*(?:pura\s*kardia|pura\s*kar\s*diya|pura\s*kiya|pura\s*ho\s*gaya|poora\s*maadi|poora\s*aaythu)|"
    r"fulfilled\s*(?:the\s*)?promise|mark\s*promise\s*(?:as\s*)?fulfilled"
    r")\b|"
    r"(?:वादा\s*पूरा|प्रॉमिस\s*पूरा|प्रॉमिस\s*क्लियर|वादा\s*निभाया)|"
    r"(?:ಪ್ರಾಮಿಸ್\s*ಪೂರ್ಣ|ಪ್ರಾಮಿಸ್\s*ಕ್ಲಿಯರ್|ಭರವಸೆ\s*ಈಡೇರಿಸಿದೆ)",
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
    "ge", "ka", "ki", "ko", "ne", "rupayi", "rupaye", "rupae", "rupai", "rupiya", "rupya", "rupay", "rupayya", "roopayi", "roopaye", "rupee", "rupees", "rs", "inr",
    "udhar", "udri", "jama", "bardu", "barkoli", "haaki", "likho", "likh", "kotta",
    "kottru", "diya", "paid", "add", "credit", "bantu", "daal", "do", "kadan", "appu",
    "se", "mein", "par", "saade", "sau", "hazaar", "hazar", "nooru", "savira", "dedh",
    "dhai", "paune", "aur", "karo", "kar", "de", "le", "lo", "batao", "dekhna", "bhi",
    "ek", "do", "teen", "chaar", "paanch", "pehla", "second", "wala", "wali", "naam",
    "customer", "graahaka", "please", "kripya", "dayavittu", "innomme", "heli", "bolo",
    "bataiye", "boliye", "chahiye", "hai", "kya", "tha", "thi", "the", "aaya", "aayi",
    "aaye", "gaya", "gayi", "gaye", "hua", "hui", "hue", "raha", "rahe", "rahi", "raho", "khata", "ledger", "entry",
    "record", "karna", "sab", "clear", "ella", "ellaa", "maadi", "chukta", "barabar",
    "kal", "naale", "parso", "naadiddu", "today", "tomorrow", "yesterday", "dega", "degi", "denge", "dunga", "wada", "kodtini", "kodtane", "kodtare",
    "aapka", "apka", "aapke", "apke", "aapki", "apki", "aap", "tum", "hi", "ho", "tumhara", "tumara", "tumhare", "tumhari", "tere", "teri", "tera", "unka", "unki", "unke", "inka", "inki", "inke", "kiska", "kiski", "kiske", "apna", "apni", "apne", "mera", "meri", "mere", "hamara", "hamari", "hamare", "kul", "total", "bill", "bana", "itna", "hoya", "aaythu", "aagide", "aaitu",
    "nahi", "nahin", "alla", "beda", "nako", "no", "mat", "cancel", "hatao",
    "bariyiri", "bari", "bariyiro", "haakri", "haakiro",
    "sell", "becho", "bechna", "kharido", "kharid", "buy", "liya", "liye", "diye", "packet", "piece", "kilo", "kg", "gm", "litre", "ltr", "rate", "bhav", "price", "cost",
    "phonepe", "gpay", "paytm", "upi", "bhim", "cash", "online", "qr", "cheque", "pelam", "loan", "cashloan", "er",
    "galla", "petti", "box", "drawer", "kharch", "kharcha", "kharchu", "chillar", "change",
    "daalo", "rakh", "rakho", "haaku", "tegiri", "tegedu", "tegedukonde", "nikal", "nikalo", "nikaalo", "nikala", "wapas", "vaapas", "return", "discount",
    "give", "here", "is", "keep", "put", "take", "google", "pay", "rupee", "rupees", "for", "the", "from", "with",
    "alli", "chuka", "chukaya", "baad", "bad", "baaki", "baki", "chhoot", "chhut", "chut", "choot", "du", "de", "di", "kitna", "kitne", "eshtu", "entha", "evvalavu", "khate", "khaate", "khatege", "khathage", "udar", "pandrah", "pandra", "pandhrah", "bees", "pachees", "pachis", "tees", "chaalis", "pachaas", "saath", "sattar", "assi", "nabbe", "cashbox", "counter", "kounter",
    "not", "make", "it", "instead", "write", "anta", "antha", "pichla", "pichli", "pichle",
    "what", "pending", "balance", "fm", "radio", "city", "superhit", "gaana", "bajao", "match", "score", "saala", "saal",
    "out", "of", "today", "by", "check", "show", "list", "find", "kadime", "kam", "kharab", "adjust", "permanently", "unpaid", "close", "off", "debts", "debt",
    # Conversational filler, instructional & promise words
    "like", "so", "to", "nad", "from", "the", "according", "then", "fir", "each", "dono", "donho", "pratyek",
    "promise", "pura", "poora", "kardia", "kardiya", "nibhaya", "complete", "fulfilled", "clear", "settle",
    "leger", "ledger", "minus", "plus", "sub", "waada", "wada",
    # Kirana conversational shop talk stopwords
    "ake", "aake", "aakar", "pucha", "puchi", "puche", "pucho", "bol", "bola", "boli", "bole", "bolo",
    "lena", "lene", "dena", "dene", "hae", "hain", "and", "ok", "the", "tumhara", "tumara",
    "ye", "yeh", "wo", "woh", "lo", "gi", "yelo", "lelo",
    "nimma", "nimmadu", "nimmage", "nimmanna", "nimdu", "namma", "nammad", "nanna", "nannadu", "avara", "avardu", "avargella", "ivara", "ivardu", "ivargella", "yaara", "yaardu", "thamma", "copy", "kopi", "bahi", "chopdi", "chotha", "account", "galat", "galti", "thappu", "tappu", "sahi", "tago", "thago", "tagoli", "thagoli", "kodbeku", "barbeku", "kelida", "kelidru", "kelidare",
    "iga", "eega", "ivaga", "nantara", "aamele",
    "banda", "bandu", "bandru", "bandidare", "parle", "parleg", "parle-g",
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
    # Pronouns, Question markers & Inquiry tokens
    "mujhe", "mujhko", "mujhse", "hume", "humein", "humko", "kaun", "kise", "kisko", "kiske", "kisne", "kis", "sabka", "sabki", "sabke", "sabko", "kisi", "kisika", "dikhao", "dikhaiye", "bataiye", "bakaya", "bata", "dikha", "patti", "thorisi", "nanage", "namage", "yaaru", "yaarige", "yaaradu", "yaaraadru", "yaaraarige", "ellaru", "ellara", "ellarigu",
    # Devanagari stopwords
    "का", "की", "के", "को", "ने", "से", "में", "पर", "रुपये", "रुपए", "रुपया", "रु",
    "उधार", "उधारी", "जमा", "लिखो", "लिख", "डाल", "डालो", "दिया", "दिए", "दे", "लिया",
    "लिए", "ले", "करो", "कर", "दो", "दी", "हो", "गया", "गई", "गए", "है", "हैं", "था",
    "थी", "थे", "खाता", "खाते", "खातों", "हिसाब", "पंद्रह", "पन्द्रह", "बीस", "पच्चीस", "तीस", "चालीस", "पचास", "साठ", "सत्तर", "अस्सी", "नब्बे", "गल्ला", "गल्ले", "बॉक्स", "पेटी", "काउंटर", "सब", "क्लियर", "फोनपे", "कैश", "नकद", "कृपया", "बोलो", "बताओ",
    "पिछली", "पिछला", "एंट्री", "डिलीट", "हटाओ", "कितना", "कितने", "बैलेंस", "छूट", "हुआ", "हुए", "हुई", "बना", "बने", "बनी", "रुपये", "रुपए", "रुपया", "पैसा", "पैसे", "ಆಯ್ತು", "ಆಗಿದೆ", "ಆಯಿತು", "ರೂಪಾಯಿ", "आपके", "आपकी", "तुम्हारा", "तुम्हारी", "तुम्हारे", "तेरे", "तेरी", "तेरा", "उनका", "उनकी", "उनके", "इनका", "इनकी", "इनके", "किसका", "किसकी", "किसके", "कॉपी", "ಖಾತೆ", "ನಿಮಗೆ",
    "मुझे", "मुझको", "मुझसे", "हमें", "हमको", "हमारा", "हमारी", "हमारे", "मैं", "तू", "तुम", "आप", "कौन", "किसे", "किसको", "किसने", "किस", "सबका", "सबकी", "सबके", "सबको", "किसी", "किसिका", "दिखाओ", "दिखाइए", "बताइए", "बता", "दिखा", "लिस्ट", "बकाया", "देगा", "देंगे", "वादा", "प्रॉमिस", "पूरा", "निभाया",
    # Kannada stopwords
    "ಗೆ", "ಇಂದ", "ರೂಪಾಯಿ", "ರೂ", "ಉದ್ರಿ", "ಉಧಾರ್", "ಜಮಾ", "ಬರೆ", "ಹಾಕಿ", "ಕೊಟ್ರು",
    "ಕೊಟ್ಟ", "ಆಗಿದೆ", "ಆಯ್ತು", "ಇದೆ", "ಮಾಡಿದೆ", "ಖಾತೆ", "ಖಾತೆಗೆ", "ಖಾತೆಯಲ್ಲಿ", "ಲೆಕ್ಕ", "ಬ್ಯಾಲೆನ್ಸ್", "ಎಷ್ಟು", "ಸಾಲ", "ಮನ್ನಾ", "ರೈಟ್", "ಆಫ್", "ಹಿಂದಿನ", "ಮಾಡಿ", "ಪ್ರಾಮಿಸ್", "ಪೂರ್ಣ", "ಪೂರ್ತಿ",
    "ನನಗೆ", "ನಮಗೆ", "ನಮ್ಮ", "ನನ್ನ", "ಯಾರು", "ಯಾರಿಗೆ", "ಯಾರದು", "ಯಾರಾದ್ರೂ", "ಯಾರಾರಿಗೆ", "ಎಲ್ಲರ", "ಎಲ್ಲರಿಗೂ", "ಹೇಳಿ", "ತೋರಿಸಿ", "ಪಟ್ಟಿ", "ಕೊಡಬೇಕು"
}


class FastPathResult:
    def __init__(self, handled: bool, reply: str = "", events: Optional[List[Dict[str, Any]]] = None):
        self.handled = handled
        self.reply = reply
        self.events = events or []


def _extract_name_tokens(text: str) -> List[str]:
    """Dynamically extract any customer name: strips punctuation, currency symbols, numbers,
    honorifics, transaction verbs (dena, lena, udhar, sell, buy), and attached postpositions.
    Always returns normalized English/Latin tokens for uniform database storage and recall.
    """
    cleaned_punct = re.sub(r'''[₹$€£।॥.,?!;:"'()\[\]{}\-—_/\\]''', ' ', text)
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
            or any(ch.isdigit() for ch in w)
            or len(w) <= 1
        ):
            continue

        # Strip attached postpositions/suffixes (e.g. Rameshge -> Ramesh, Robinudar -> Robin, Robinudhar -> Robin, Deepakko -> Deepak, Ramka -> Ram, Sureshdu -> Suresh, Shyams -> Shyam)
        cleaned = w
        if len(cleaned) > 4:
            for suf in ["avarige", "inda", "ige", "ge", "udhar", "udhaar", "udar", "udri", "khate", "khaate", "khata", "ka", "ke", "ki", "ko", "du", "ku", "er", "'s"]:
                if cleaned.lower().endswith(suf) and len(cleaned) > len(suf) + 2:
                    cleaned = cleaned[:-len(suf)]
                    break
        if len(cleaned) > 4 and cleaned.lower().endswith("s") and not cleaned.lower().endswith(("sh", "as", "is", "us", "ss")):
            cleaned = cleaned[:-1]

        if (
            cleaned.lower() not in STOPWORDS
            and cleaned.lower() not in HONORIFICS
            and cleaned.lower() not in KIRANA_ITEMS
            and not any(ch.isdigit() for ch in cleaned)
            and len(cleaned) > 1
        ):
            lat = tools.transliterate_indic_to_latin(cleaned).strip()
            final_token = lat.title() if lat else cleaned.title()
            if final_token.lower() not in STOPWORDS and len(final_token) > 1:
                tokens.append(final_token)

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

        # 5. High fuzzy score (at least 0.80 similarity for minor spelling/transliteration differences)
        if m_score >= 0.80 and abs(len(m_name) - len(clean_q)) <= 2:
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
    """If utterance has correction like '20 nahi 50' or '50 likho 20 nahi' or 'alla 50' or 'Not 100 write 250' or 'No, make it 520 instead', extract the intended target amount."""
    lower = text.lower()
    # Pattern: "Not 100 write 250"
    match_not_write = re.search(r"\bnot\s*(\d+(?:\.\d+)?).*?\b(?:write|bardu|likho|make\s*it|instead)?\s*(\d+(?:\.\d+)?)\b", lower)
    if match_not_write and match_not_write.group(2):
        return float(match_not_write.group(2))

    # Pattern: "No, make it 520 instead" or "520 instead"
    match_instead = re.search(r"\b(?:make\s*it|likho|bardu)?\s*(\d+(?:\.\d+)?)\s*instead\b", lower)
    if match_instead:
        return float(match_instead.group(1))

    match_corr = re.search(r"(\d+(?:\.\d+)?)\s*(?:nahi|nahin|alla|not)\s*(\d+(?:\.\d+)?)", lower)
    if match_corr:
        return float(match_corr.group(2))

    match_corr_rev = re.search(r"(\d+(?:\.\d+)?).*?(?:likho|likh|bardu|karo|bana|hua|aaythu|antha).*?(\d+(?:\.\d+)?)\s*(?:nahi|nahin|alla|not)", lower)
    if match_corr_rev:
        return float(match_corr_rev.group(1))

    match_after_nahi = re.search(r"(?:nahi|nahin|alla|not)\s*[,]?\s*(\d+(?:\.\d+)?)", lower)
    if match_after_nahi:
        return float(match_after_nahi.group(1))

    return None


def _parse_compound_actions(text: str) -> List[Dict[str, Any]]:
    """Detect and segregate multiple accounting actions in a single compound utterance:
    - Multiple customer drafts (credit, payment, adjustment, loan)
    - Mixed drafts and promise fulfillments (e.g. 'shyam ka 50 udhar, ram ka 25 jama, rhan ne promise pura kardia')
    - Shared amount with 'each' / 'dono' (e.g. 'Ramesh and Suresh 100 each udhar')
    - Filter and deduplicate meta-commentary or redundant repeat instructions
    """
    # 1. Pattern: "X and Y <amount> each <type>"
    each_match = re.search(
        r"([a-zA-Z\s\u0900-\u097F\u0C80-\u0CFF]+?)\s*(?:and|aur|mattu)\s*([a-zA-Z\s\u0900-\u097F\u0C80-\u0CFF]+?)\s+(\d+(?:\.\d+)?)\s*(?:each|pratyek|dono)\s*(?:ka\s*)?(udhar|jama|credit|payment|bardu)?",
        text,
        re.I,
    )
    if each_match:
        n1 = _extract_name_tokens(each_match.group(1))
        n2 = _extract_name_tokens(each_match.group(2))
        amt = float(each_match.group(3))
        ttype = "payment" if each_match.group(4) and any(w in each_match.group(4).lower() for w in ["jama", "payment"]) else "credit"
        if n1 and n2 and amt:
            return [
                {"action": "draft", "customer": n1[0], "amount": amt, "tx_type": ttype, "payment_mode": None, "transcript": text},
                {"action": "draft", "customer": n2[0], "amount": amt, "tx_type": ttype, "payment_mode": None, "transcript": text},
            ]

    raw_clauses = [c.strip() for c in re.split(r"[,;]|\b(?:aur|mattu|and|hagu)\b", text, flags=re.I) if c.strip()]
    if len(raw_clauses) < 2:
        return []

    actions: List[Dict[str, Any]] = []
    seen = set()

    for c in raw_clauses:
        # Check promise fulfillment first
        if PROMISE_FULFIL_PATTERN.search(c):
            names = _extract_name_tokens(c)
            cname = names[0] if names else "Customer"
            key = (cname.lower(), "promise_fulfil", 0.0)
            if key not in seen:
                seen.add(key)
                actions.append({
                    "action": "promise_fulfil",
                    "customer": cname,
                    "transcript": c,
                })
            continue

        amt = extract_indian_amount(c)
        names = _extract_name_tokens(c)
        if not amt or not names:
            continue

        cname = names[0]
        if cname.lower().endswith("s") and len(cname) > 3 and not cname.lower().endswith(("sh", "as", "is", "us")):
            cname = cname[:-1]

        cl_loan = bool(LOAN_DIRECTION_PATTERN.search(c))
        cl_return = bool(RETURN_PATTERN.search(c))
        cl_discount = bool(DISCOUNT_PATTERN.search(c))
        cl_advance = bool(ADVANCE_PATTERN.search(c))
        cl_mode = _detect_payment_mode(c)

        is_payment_clause = bool(
            PAYMENT_PATTERN.search(c)
            or cl_mode
            or any(w in c.lower() for w in ["jama", "chuka", "minus", "diya", "kotta", "kottru"])
        ) and not cl_loan

        if cl_return or cl_discount:
            tx_type = "adjustment"
            adj_reason = "return" if cl_return else "discount"
        elif is_payment_clause or cl_advance:
            tx_type = "payment"
            adj_reason = None
        else:
            tx_type = "credit"
            adj_reason = None

        key = (cname.lower(), tx_type, amt)
        if key not in seen:
            seen.add(key)
            actions.append({
                "action": "draft",
                "customer": cname,
                "amount": amt,
                "tx_type": tx_type,
                "payment_mode": cl_mode,
                "adjustment_reason": adj_reason,
                "note": "Cash Loan" if cl_loan else ("Advance / Deposit" if cl_advance else None),
                "transcript": c,
            })

    return actions if len(actions) >= 2 else []


def _detect_compound_clauses(text: str) -> List[str]:
    """Compatibility wrapper returning clause strings for compound utterances."""
    acts = _parse_compound_actions(text)
    return [a.get("transcript", "") for a in acts if a.get("transcript")]


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
                    sa_text("SELECT id FROM transactions WHERE shop_id = :sid AND status = 'draft' AND created_at > (now() - interval '10 minutes') ORDER BY created_at DESC LIMIT 1"),
                    {"sid": tools.to_uuid(shop_id)}
                )).scalar()
                if last_d_row:
                    active_draft_id = str(last_d_row)
                    if sess:
                        sess.last_draft_id = active_draft_id
        except Exception as ex:
            log.warning("Fast engine draft fallback lookup error: %s", ex)

    # Active conversation context cache for shop
    cache = ShopConversationCacheManager.get_cache(shop_id)
    if sess:
        sess.cache = cache
        if not getattr(sess, "active_customer_name", None) and cache.active_customer_name:
            sess.active_customer_name = cache.active_customer_name
        if not getattr(sess, "pending_bill_amount", None) and cache.pending_bill_amount:
            sess.pending_bill_amount = cache.pending_bill_amount
        if not getattr(sess, "pending_bill_item", None) and cache.pending_bill_item:
            sess.pending_bill_item = cache.pending_bill_item

    lower = text.lower()
    corrected_amt = extract_corrected_amount(text)
    amount = corrected_amt or extract_indian_amount(text)
    name_tokens = _extract_name_tokens(text)
    detected_item = _extract_kirana_item(text)
    payment_mode = _detect_payment_mode(text)
    is_loan = bool(LOAN_DIRECTION_PATTERN.search(text))
    is_return = bool(RETURN_PATTERN.search(text))
    is_discount = bool(DISCOUNT_PATTERN.search(text))
    is_advance = bool(ADVANCE_PATTERN.search(text))
    is_promise_rec = bool(PROMISE_RECORD_PATTERN.search(text))
    is_promise_query = bool(PROMISE_QUERY_PATTERN.search(text))
    is_inquiry = bool(INQUIRY_PATTERN.search(text))
    is_payment = (bool(PAYMENT_PATTERN.search(text)) and not is_loan) or bool(payment_mode and not (bool(CREDIT_PATTERN.search(text)) or is_loan))

    # Named Customer Bill / Udhar Entry in Customer Khata (e.g. "Ram ka hua 25", "Ram ka 25 hua", "Ramesh ge 50 aaythu", "Suresh du 100 aagide")
    # In Indian Kirana shopkeeping, when a customer name is stated with "hua/bana/aaythu/aagide" and an amount,
    # it means in the copy/khata of that customer, the amount is UDHAR (credit sale)!
    is_named_bill_credit = bool(
        name_tokens
        and amount
        and NAMED_BILL_CREDIT_PATTERN.search(text)
        and not (is_payment or is_return or is_discount or is_advance or is_promise_rec or is_inquiry or PAID_SALE_PATTERN.search(text))
    )
    is_credit = bool(CREDIT_PATTERN.search(text)) or is_loan or is_named_bill_credit

    # General / Walk-in Bill total:
    is_bill_total = bool(BILL_TOTAL_PATTERN.search(text)) or bool(detected_item and amount and not (is_credit or is_payment or is_inquiry or PAID_SALE_PATTERN.search(text)))

    # Anti-Hallucination Guard: If background song or radio chatter was heard and no explicit ledger command or bill is present:
    if had_song_or_noise and not (is_credit or is_payment or is_bill_total or is_promise_rec or is_promise_query or (amount and name_tokens)):
        return FastPathResult(handled=True, reply="[SILENT]")

    active_bill_amt = (cache and cache.pending_bill_amount) or (sess and getattr(sess, "pending_bill_amount", None))

    # ---------------------------------------------------------
    # 0A. MULTI-TURN COUNTER FLOW: PENDING BILL CORRECTION (e.g. "20 nahi 50" / "alla 50")
    # ---------------------------------------------------------
    if active_bill_amt and (corrected_amt or (amount and not name_tokens and (CANCEL_PATTERN.search(text) or any(w in lower for w in ["nahi", "alla", "kar", "hua", "bana", "rakho", "sudhar", "change"])))):
        target_amt = corrected_amt or amount
        if cache:
            cache.pending_bill_amount = target_amt
        if sess:
            sess.pending_bill_amount = target_amt

        target_item = (cache and cache.pending_bill_item) or (sess and getattr(sess, "pending_bill_item", None))
        item_str = f" ({target_item})" if target_item else ""
        target_cname = (cache and cache.active_customer_name) or (sess and getattr(sess, "active_customer_name", None))
        name_str = f" ({target_cname})" if target_cname else ""

        if lang.startswith("kn"):
            msg = f"Tiddupaadi maadlaagide: ₹{target_amt:,.0f}{item_str} aagide{name_str}. Eega payment maadthara, nantara promise maadthara, athava udhar baribeka?"
        elif lang.startswith("hi"):
            msg = f"Sudhaar diya: ₹{target_amt:,.0f}{item_str} hue{name_str}. Abhi payment de rahe hain, wada kar rahe hain kab denge, ya udhar khate mein likh loon?"
        else:
            msg = f"Updated: ₹{target_amt:,.0f}{item_str}{name_str}. Paying now, making a payment promise, or adding to credit khata?"
        return FastPathResult(handled=True, reply=msg)

    # ---------------------------------------------------------
    # 0B. MULTI-TURN COUNTER FLOW: PENDING BILL PAID IN CASH / UPI (Paid Sale -> Record Cash & Acknowledge!)
    # ---------------------------------------------------------
    is_bill_announcement = bool(BILL_TOTAL_PATTERN.search(text)) or any(w in lower for w in ["hua", "hue", "bana", "total", "bill", "aaythu", "aagide", "tumhara", "aapka"])
    if active_bill_amt and not is_bill_announcement and (PAID_SALE_PATTERN.search(text) or any(w in lower for w in ["abhi de", "cash", "phonepe", "gpay", "paytm", "online", "ye lo", "diya", "de diya", "kotru", "kottu", "le lo"])):
        target_amt = float(active_bill_amt)
        target_item = (cache and cache.pending_bill_item) or (sess and getattr(sess, "pending_bill_item", None)) or "Counter Sale"
        if cache:
            cache.reset_active_transaction()
        if sess:
            sess.pending_bill_amount = None
            sess.pending_bill_item = None

        async with SessionLocal() as s:
            cb_res = await tools.record_cash_in(
                s,
                shop_id,
                amount=target_amt,
                reason=f"{target_item} (Counter Cash Sale)",
            )
            new_bal = cb_res.get("new_balance")

        if lang.startswith("kn"):
            msg = f"₹{target_amt:,.0f} cash bantu. Galla ge jama aaythu."
        elif lang.startswith("hi"):
            msg = f"₹{target_amt:,.0f} prapt hue. Galle mein jama kar liya."
        else:
            msg = f"₹{target_amt:,.0f} cash received. Added to cash drawer."

        return FastPathResult(
            handled=True,
            reply=msg,
            events=[{
                "type": "cash_in",
                "amount": target_amt,
                "reason": f"{target_item} (Counter Cash Sale)",
                "new_balance": new_bal,
            }],
        )

    # ---------------------------------------------------------
    # 0C. MULTI-TURN COUNTER FLOW: PENDING BILL ASSIGNED TO CREDIT KHATA
    # (e.g. "Udhar likh do" [customer from cache], or "Udhar likh do Ramesh")
    # ---------------------------------------------------------
    if active_bill_amt and is_credit:
        bill_amt = active_bill_amt
        bill_item = (cache and cache.pending_bill_item) or (sess and getattr(sess, "pending_bill_item", None))

        target_cname = None
        if name_tokens:
            target_cname = " ".join(t.capitalize() for t in name_tokens[:2])
        elif cache and cache.active_customer_name:
            target_cname = cache.active_customer_name
        elif sess and getattr(sess, "active_customer_name", None):
            target_cname = sess.active_customer_name

        if target_cname:
            if cache:
                cache.pending_bill_amount = None
                cache.pending_bill_item = None
            if sess:
                sess.pending_bill_amount = None
                sess.pending_bill_item = None

            cust_name = target_cname
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
                    if sess:
                        sess.active_disambiguation = ambig
                        sess.active_amount = bill_amt
                        sess.active_tx_type = "credit"
                    if cache:
                        cache.active_disambiguation = ambig
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
                draft_id = draft_res.get("draft_id")
                if sess:
                    sess.last_draft_id = draft_id
                if cache:
                    cache.last_draft_id = draft_id
                    cache.state = ConversationState.DRAFT_PENDING
                    cache.active_customer_name = c_display
                    cache.active_customer_id = target_cid

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
                        "draft_id": draft_id,
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
        else:
            if lang.startswith("kn"):
                msg = f"Yaara hesaralli ₹{bill_amt:,.0f} udhar baribeku?"
            elif lang.startswith("hi"):
                msg = f"Kiske naam ₹{bill_amt:,.0f} ka udhar likhna hai?"
            else:
                msg = f"Whose name should I record the ₹{bill_amt:,.0f} credit under?"
            return FastPathResult(handled=True, reply=msg)

    # ---------------------------------------------------------
    # 0D. MULTI-TURN COUNTER FLOW: PENDING BILL ASSIGNED TO PAYMENT PROMISE
    # (e.g. "Kal de dunga wada raha" [customer from cache], or "Kal dega Ramesh")
    # ---------------------------------------------------------
    if active_bill_amt and is_promise_rec:
        bill_amt = amount or active_bill_amt
        if cache:
            cache.pending_bill_amount = None
            cache.pending_bill_item = None
        if sess:
            sess.pending_bill_amount = None
            sess.pending_bill_item = None

        cust_name = None
        if name_tokens:
            cust_name = " ".join(t.capitalize() for t in name_tokens[:2])
        elif cache and cache.active_customer_name:
            cust_name = cache.active_customer_name
        elif sess and getattr(sess, "active_customer_name", None):
            cust_name = sess.active_customer_name
        else:
            cust_name = "Customer"

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
            if cache:
                cache.state = ConversationState.PROMISE_RECORDED
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
    # (e.g. "Parle ji aapka 20 hua", "Aapka 50 hua", "Kul 120 bana", "Total 150 hua", "ye lo Parle-G tumhara hua 15")
    # ---------------------------------------------------------
    if (amount or (active_bill_amt and not (name_tokens or is_inquiry or BALANCE_PATTERN.search(text)))) and (is_bill_total or any(w in lower for w in ["hua", "hue", "bana", "aaythu", "bill", "total", "kul"])) and not (is_credit or is_payment or is_return or is_discount or is_advance or is_promise_rec or is_inquiry or PAID_SALE_PATTERN.search(text) or BALANCE_PATTERN.search(text)):
        target_amt = amount or active_bill_amt
        target_item = detected_item or (cache and cache.pending_bill_item) or (sess and getattr(sess, "pending_bill_item", None))

        target_cname = None
        if name_tokens:
            target_cname = " ".join(t.capitalize() for t in name_tokens[:2])
        else:
            # If no customer name is spoken in this bill announcement (e.g. "25 hua", "Aapke hue 15", "50 aaythu"),
            # NEVER inherit a previously active customer name from cache! Reset active customer name to prevent cross-customer leakage.
            if cache:
                cache.active_customer_name = None
            if sess:
                sess.active_customer_name = None

        if sess:
            sess.pending_bill_amount = target_amt
            sess.pending_bill_item = target_item
            sess.active_customer_name = target_cname
        if cache:
            cache.set_bill_tally(amount=target_amt, product=target_item, customer_name=target_cname)

        name_str = f" ({target_cname})" if target_cname else ""
        item_str = f" ({target_item})" if (target_item and not target_cname) else ""

        if lang.startswith("kn"):
            msg = f"₹{target_amt:,.0f}{item_str} aagide{name_str}. Eega payment maadthara, nantara promise maadthara, athava udhar baribeka?"
        elif lang.startswith("hi"):
            msg = f"₹{target_amt:,.0f}{item_str} hue{name_str}. Abhi payment de rahe hain, wada kar rahe hain kab denge, ya udhar khate mein likh loon?"
        else:
            msg = f"Bill is ₹{target_amt:,.0f}{item_str}{name_str}. Paying now, making a payment promise, or adding to credit khata?"

        return FastPathResult(handled=True, reply=msg)

    # ---------------------------------------------------------
    # 0F. PRODUCT INQUIRY & SHOP-FLOOR COUNTER ASK
    # (e.g. "shyam ake pucha ki parleg lena hae 15 rupae ka", "Parle-G lena hai 15 ka")
    # Captures context into conversation cache and stays silent without premature drafting!
    # ---------------------------------------------------------
    if is_inquiry and not (is_credit or is_payment or is_return or is_discount or is_advance or is_promise_rec or is_promise_query or DEBTORS_QUERY_PATTERN.search(text) or SUMMARY_PATTERN.search(text) or BALANCE_PATTERN.search(text) or CONFIRM_PATTERN.search(text)):
        c_name = " ".join(t.capitalize() for t in name_tokens[:2]) if name_tokens else None
        if cache:
            cache.set_inquiry(customer_name=c_name, product=detected_item, amount=amount)
        if sess:
            if c_name:
                sess.active_customer_name = c_name
            if detected_item:
                sess.pending_bill_item = detected_item
            if amount:
                sess.pending_bill_amount = amount

        return FastPathResult(handled=True, reply="[SILENT]")

    # ---------------------------------------------------------
    # 1. AMBIENT SHOP CHATTER FILTER (< 0.1ms)
    # Customers talking about items, prices, claiming payments, or paying exact cash (PAID_SALE):
    # ---------------------------------------------------------
    if PAID_SALE_PATTERN.search(text) and not (CREDIT_PATTERN.search(text) or LOAN_DIRECTION_PATTERN.search(text)):
        if cache:
            cache.reset_active_transaction()
        if sess:
            sess.pending_bill_amount = None
            sess.pending_bill_item = None
        return FastPathResult(handled=True, reply="[SILENT]")

    for pat in CHATTER_PATTERNS:
        if pat.search(text):
            if "maine" in lower or "main " in lower or "naanu" in lower or "bhaiya" in lower or not amount:
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
    # 2A. CHANGE CALCULATION (Explicit cash change handed back at counter)
    # (e.g. "50 change kodi", "500 diye 150 change do", "50 change do", "chillar wapas do")
    # Must NOT create or alter customer credit/payment ledger!
    # ---------------------------------------------------------
    if CHANGE_CALC_PATTERN.search(text) and not is_inquiry:
        all_amts = re.findall(r"\b\d+(?:\.\d+)?\b", text)
        calc_change = None
        if len(all_amts) >= 2:
            try:
                a1, a2 = float(all_amts[0]), float(all_amts[1])
                calc_change = abs(a1 - a2) if max(a1, a2) > min(a1, a2) else min(a1, a2)
            except Exception:
                calc_change = amount
        elif amount:
            calc_change = amount

        ch_amt_str = f"₹{calc_change:,.0f}" if calc_change else "change"
        if lang.startswith("kn"):
            msg = f"{ch_amt_str} change wapas kodbeku (Nagadu chillar lekka, graahakara khate badalaagilla)."
        elif lang.startswith("hi"):
            msg = f"{ch_amt_str} change wapas dena hai (Nagad change calculation, customer credit khate mein koi badlav nahi hua hai)."
        else:
            msg = f"Return {ch_amt_str} change (Cash change calculation, customer credit ledger unchanged)."
        return FastPathResult(handled=True, reply=msg, events=[{"type": "change_calc", "change_amount": calc_change}])

    # ---------------------------------------------------------
    # 2B. CASH BOOK: CASH BALANCE INQUIRY
    # (e.g. "Cash box mein kitna hai", "Ivattu cash eshtu ide", "drawer balance")
    # ---------------------------------------------------------
    if CASH_BALANCE_PATTERN.search(text) and not (CREDIT_PATTERN.search(text) or PAYMENT_PATTERN.search(text)):
        async with SessionLocal() as s:
            res = await tools.get_cash_balance(s, shop_id)
            bal = res.get("cash_balance", 0.0)
            c_in = res.get("today_cash_in", 0.0)
            c_out = res.get("today_cash_out", 0.0)
            if lang.startswith("kn"):
                msg = f"Dukaan cash box baaki: ₹{bal:,.0f} (Indina jama: ₹{c_in:,.0f}, Kharchu: ₹{c_out:,.0f})."
            elif lang.startswith("hi"):
                msg = f"Shop cash box balance: ₹{bal:,.0f} (Aaj jama: ₹{c_in:,.0f}, Aaj kharch: ₹{c_out:,.0f})."
            else:
                msg = f"Cash drawer balance: ₹{bal:,.0f} (Today in: ₹{c_in:,.0f}, Today out: ₹{c_out:,.0f})."
            return FastPathResult(handled=True, reply=msg, events=[{**res, "type": "cash_balance"}])

    # ---------------------------------------------------------
    # 2C. CASH BOOK: CASH INFLOW (DEPOSIT TO DRAWER)
    # (e.g. "Cash box mein 1000 daalo", "Cash in 500", "Galla petti ge 200 haaki")
    # ---------------------------------------------------------
    if amount and CASH_IN_PATTERN.search(text):
        async with SessionLocal() as s:
            res = await tools.record_cash_in(
                s,
                shop_id,
                amount=amount,
                reason="deposit",
                description=text,
                payment_mode="cash",
            )
            new_bal = res.get("cash_balance", 0.0)
            if lang.startswith("kn"):
                msg = f"Cash box ge ₹{amount:,.0f} jama aagide. Hosa cash balance: ₹{new_bal:,.0f}."
            elif lang.startswith("hi"):
                msg = f"Shop cash box mein ₹{amount:,.0f} jama ho gaya. Naya cash balance: ₹{new_bal:,.0f}."
            else:
                msg = f"Recorded ₹{amount:,.0f} cash-in. New cash drawer balance: ₹{new_bal:,.0f}."
            return FastPathResult(handled=True, reply=msg, events=[{**res, "type": "cash_in"}])

    # ---------------------------------------------------------
    # 2D. CASH BOOK: CASH OUTFLOW (EXPENSE / WITHDRAWAL)
    # (e.g. "Cash box se 500 nikaalo", "500 kharch ke liye nikala", "Cash out 1000")
    # ---------------------------------------------------------
    if amount and CASH_OUT_PATTERN.search(text):
        async with SessionLocal() as s:
            res = await tools.record_cash_out(
                s,
                shop_id,
                amount=amount,
                reason="expense",
                description=text,
                payment_mode="cash",
            )
            new_bal = res.get("cash_balance", 0.0)
            if lang.startswith("kn"):
                msg = f"Cash box inda ₹{amount:,.0f} kharchige tegedukollalaagide. Hosa cash balance: ₹{new_bal:,.0f}."
            elif lang.startswith("hi"):
                msg = f"Shop cash box se ₹{amount:,.0f} kharch ke liye nikaal liya gaya. Naya cash balance: ₹{new_bal:,.0f}."
            else:
                msg = f"Recorded ₹{amount:,.0f} cash-out. New cash drawer balance: ₹{new_bal:,.0f}."
            return FastPathResult(handled=True, reply=msg, events=[{**res, "type": "cash_out"}])

    # ---------------------------------------------------------
    # 2E. COMPOUND MULTI-TRANSACTION & ACTION SEGREGATION
    # (e.g. "Ramesh 500 kotta, Suresh ge 300 udhar haaki", "Anil 1000 diya aur Sunil ko 200 udhar",
    #       "shyam ka 50 rupee udhar and ram ka 25 udhar jama ho gaya ,rhan ne promise pura kardia")
    # ---------------------------------------------------------
    compound_actions = _parse_compound_actions(text)
    if compound_actions:
        async with SessionLocal() as s:
            created_drafts = []
            clause_summaries = []
            all_events = []
            for act in compound_actions:
                act_type = act.get("action")
                c_name = act.get("customer") or "Customer"

                if act_type == "promise_fulfil":
                    p_res = await tools.fulfil_entity_promise(s, shop_id, entity_name=c_name, transcript=act.get("transcript"))
                    p_entity = p_res.get("entity_name") or c_name
                    clause_summaries.append(f"{p_entity} ka promise pura")
                    all_events.append({
                        "type": "promise_card",
                        "status": "FULFILLED",
                        "entity_name": p_entity,
                        "customer_name": p_entity,
                        "amount": p_res.get("promised_amount"),
                        "promise_id": p_res.get("promise_id"),
                    })

                elif act_type == "draft":
                    cl_amt = act["amount"]
                    tx_t = act["tx_type"]
                    cl_mode = act.get("payment_mode")
                    adj_r = act.get("adjustment_reason")
                    cl_note = act.get("note")

                    # Search or create customer
                    search_res = await tools.search_customers(s, shop_id, c_name)
                    matches = search_res.get("matches", [])
                    best, _ = _pick_best_match(matches, c_name)
                    if best:
                        target_cid = best["customer_id"]
                        display_name = best["name"]
                        cur_b = float(best.get("balance", 0))
                    else:
                        new_c = await tools.create_customer(s, shop_id, name=c_name)
                        target_cid = new_c["customer_id"]
                        display_name = c_name
                        cur_b = 0.0

                    d_res = await tools.create_draft(
                        s,
                        shop_id,
                        customer_id=target_cid,
                        type=tx_t,
                        amount=cl_amt,
                        payment_mode=cl_mode,
                        adjustment_reason=adj_r,
                        note=cl_note,
                        transcript=act.get("transcript"),
                        language=lang,
                    )
                    draft_id = d_res.get("draft_id")
                    if draft_id:
                        created_drafts.append(draft_id)
                        all_events.append({**d_res, "tx_type": tx_t, "type": "draft"})
                        mode_s = f" ({cl_mode.upper()})" if cl_mode else ""
                        clause_summaries.append(f"{display_name} ke ₹{cl_amt:,.0f} {tx_t}{mode_s}")

            if created_drafts:
                if sess:
                    sess.pending_draft_ids = created_drafts
                    sess.last_draft_id = created_drafts[-1]
                if cache:
                    cache.last_draft_id = created_drafts[-1]

            summary_str = " aur ".join(clause_summaries)
            if lang.startswith("kn"):
                msg = f"{len(clause_summaries)} actions process aagide: {' mattu '.join(clause_summaries)}. Confirm maadla?"
            elif lang.startswith("hi"):
                msg = f"{len(clause_summaries)} actions process ho gaye hain: {summary_str}. Confirm karein?"
            else:
                msg = f"{len(clause_summaries)} actions processed: {summary_str}. Please confirm."

            return FastPathResult(handled=True, reply=msg, events=all_events)

    # ---------------------------------------------------------
    # 3. CORRECTION AFTER READ-BACK (e.g. "Nahi 430 likho, 340 nahi" / "alla 430 bardu")
    # ---------------------------------------------------------
    target_corr_amt = corrected_amt or amount
    if active_draft_id and target_corr_amt and not name_tokens and (CANCEL_PATTERN.search(text) or corrected_amt or any(w in lower for w in ["likho", "bardu", "karo", "maadi", "instead", "write", "make"])):
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
                    amount=target_corr_amt,
                    payment_mode=payment_mode,
                    transcript=text,
                    language=lang,
                )
                if sess:
                    sess.last_draft_id = new_draft.get("draft_id")

                cname = new_draft.get("customer", "Customer")
                bal = float(new_draft.get("projected_balance", 0))

                if new_draft.get("rule_warnings"):
                    msg = _format_rule_warning_msg(new_draft, cname, target_corr_amt, lang)
                elif lang.startswith("kn"):
                    msg = f"Tiddupaadi maadlaagide: {cname} avarige ₹{target_corr_amt:,.0f} {tx_type} draft aagide (naya baaki ₹{bal:,.0f}). Confirm maadla?"
                else:
                    msg = f"Sudhaar diya gaya hai: {cname} ke naam ₹{target_corr_amt:,.0f} {tx_type} draft ban gaya hai (naya balance ₹{bal:,.0f}). Confirm karein?"

                return FastPathResult(
                    handled=True,
                    reply=msg,
                    events=[{**new_draft, "tx_type": tx_type, "type": "draft"}],
                )

    # ---------------------------------------------------------
    # 4. OVERRIDE OR CONFIRM ACTIVE DRAFT(S)
    # ---------------------------------------------------------
    is_override_speech = bool(OVERRIDE_PATTERN.search(text)) or "continue" in lower
    has_pending_multi = bool(sess and getattr(sess, "pending_draft_ids", None))
    if (active_draft_id or has_pending_multi) and (CONFIRM_PATTERN.search(text) or is_override_speech) and not (amount and name_tokens) and not BALANCE_PATTERN.search(text) and not (is_return or is_discount):
        async with SessionLocal() as s:
            d_ids = (sess and sess.pending_draft_ids) or ([active_draft_id] if active_draft_id else [])
            confirmed_events = []
            conf_msgs = []
            unresolved_err = None

            for d_id in d_ids:
                if is_override_speech:
                    await tools.override_rule_warnings(s, shop_id, d_id)
                out = await tools.confirm_draft(s, shop_id, d_id)
                if out.get("confirmed"):
                    cname = out.get("customer", "Customer")
                    bal = out.get("new_balance", 0)
                    amt = out.get("amount", 0)
                    ttype = out.get("type", "transaction")
                    confirmed_events.append({**out, "type": "confirmed"})
                    conf_msgs.append(f"{cname} (₹{amt:,.0f} {ttype}, baaki ₹{bal:,.0f})")
                elif "Unresolved Dukaan Rule warnings" in out.get("error", ""):
                    unresolved_err = out

            if unresolved_err and not confirmed_events:
                draft_tx = await s.get(Transaction, uuid.UUID(d_ids[0]))
                r_warns = draft_tx.rule_warnings if draft_tx else []
                r_text = " aur ".join(f"\"{w.get('rule_text') or w.get('message')}\"" for w in r_warns) if r_warns else "dukaan rule"
                if lang.startswith("kn"):
                    msg = f"⚠️ Niyam meeirsalilla: {r_text}. Khaatrigolisalu 'Continue anyway' antha heli athava amount badalisi."
                else:
                    msg = f"⚠️ Entry par aapka dukaan niyam laga hai: {r_text}. Confirm karne ke liye 'Continue anyway' boliye ya amount change kijiye."
                return FastPathResult(handled=True, reply=msg)

            if confirmed_events:
                if sess:
                    sess.pending_draft_ids = None
                    sess.last_draft_id = None
                    sess.active_customer_id = None
                    sess.active_customer_name = None
                    sess.active_amount = None
                    sess.active_disambiguation = None
                if cache:
                    cache.reset_active_transaction()

                override_note = " (niyam override karke)" if is_override_speech else ""
                if len(confirmed_events) > 1:
                    if lang.startswith("kn"):
                        msg = f"Khaatrigolislaagide! Sabhi {len(confirmed_events)} transactions daakhalagide: {', '.join(conf_msgs)}."
                    else:
                        msg = f"Confirm ho gaya{override_note}! Sabhi {len(confirmed_events)} transactions record ho gaye: {', '.join(conf_msgs)}."
                else:
                    ev0 = confirmed_events[0]
                    cname = ev0.get("customer", "Customer")
                    bal = ev0.get("new_balance", 0)
                    amt = ev0.get("amount", 0)
                    ttype = ev0.get("type", "transaction")
                    if lang.startswith("kn"):
                        msg = f"Khaatrigolislaagide! ₹{amt:,.0f} {ttype} {cname} avarige daakhalagide. Naya baaki ₹{bal:,.0f}."
                    else:
                        msg = f"Confirm ho gaya{override_note}! ₹{amt:,.0f} {ttype} record ho gaya. {cname} ka naya balance ₹{bal:,.0f} hai."

                return FastPathResult(
                    handled=True,
                    reply=msg,
                    events=confirmed_events,
                )

    # ---------------------------------------------------------
    # 5. CANCEL ACTIVE DRAFT(S)
    # ---------------------------------------------------------
    has_pending_multi = bool(sess and getattr(sess, "pending_draft_ids", None))
    if (active_draft_id or has_pending_multi) and CANCEL_PATTERN.search(text):
        async with SessionLocal() as s:
            d_ids = (sess and sess.pending_draft_ids) or ([active_draft_id] if active_draft_id else [])
            cancelled_events = []
            for d_id in d_ids:
                out = await tools.cancel_draft(s, shop_id, d_id)
                cancelled_events.append({**out, "type": "cancelled"})

            if sess:
                sess.pending_draft_ids = None
                sess.last_draft_id = None
                sess.active_customer_id = None
                sess.active_customer_name = None
                sess.active_amount = None
                sess.active_disambiguation = None
            if cache:
                cache.reset_active_transaction()

            if lang.startswith("kn"):
                msg = f"{len(cancelled_events)} draft(s) raddhugolislaagide."
            else:
                msg = f"{len(cancelled_events)} draft(s) cancel kar diye gaye hain."

            return FastPathResult(
                handled=True,
                reply=msg,
                events=cancelled_events,
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
    if SETTLE_PATTERN.search(text):
        target_name = " ".join(t.capitalize() for t in name_tokens[:2]) if name_tokens else None
        if not target_name and sess and sess.active_customer_name:
            target_name = sess.active_customer_name

        if target_name:
            async with SessionLocal() as s:
                search_res = await tools.search_customers(s, shop_id, target_name)
                matches = search_res.get("matches", [])
                best, ambig = _pick_best_match(matches, target_name)

                if not best and not ambig:
                    new_c = await tools.create_customer(s, shop_id, name=target_name)
                    best = {"customer_id": new_c["customer_id"], "name": target_name, "balance": 0.0}

                if best:
                    is_wo = bool(re.search(r"\b(?:write\s*off|bad\s*debt|maaf)\b", lower))
                    settle_res = await tools.settle_balance(
                        s,
                        shop_id,
                        customer_id=best["customer_id"],
                        payment_mode=payment_mode,
                        is_write_off=is_wo,
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
                    action_label = "bad-debt write off" if is_wo else "clear"
                    if lang.startswith("kn"):
                        msg = f"{best['name']} avara kul baaki ₹{s_amt:,.0f} {action_label} maaduva draft tayaride. Confirm maadla?"
                    else:
                        msg = f"{best['name']} ka poora hisaab ₹{s_amt:,.0f} {action_label} karne ka draft ban gaya hai. Confirm karein?"

                    tx_t = "adjustment" if is_wo else "payment"
                    return FastPathResult(
                        handled=True,
                        reply=msg,
                        events=[{**settle_res, "tx_type": tx_t, "type": "draft"}],
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
    # 8C. PROMISE FULFILLMENT ("Rehan ne promise pura kar diya", "Rhan ne promise pura kardia", "Wada pura kiya")
    # ---------------------------------------------------------
    if PROMISE_FULFIL_PATTERN.search(text) and not amount:
        cust_name = " ".join(t.capitalize() for t in name_tokens[:2]) if name_tokens else None
        if not cust_name and sess and sess.active_customer_name:
            cust_name = sess.active_customer_name
        if not cust_name and cache and cache.active_customer_name:
            cust_name = cache.active_customer_name
        if not cust_name:
            cust_name = "Customer"

        async with SessionLocal() as s:
            f_res = await tools.fulfil_entity_promise(s, shop_id, entity_name=cust_name, transcript=text)
            p_entity = f_res.get("entity_name") or cust_name
            if lang.startswith("kn"):
                msg = f"{p_entity} avara promise poorthi (fulfilled) daakhalagide."
            elif lang.startswith("hi"):
                msg = f"{p_entity} ji ka promise pura (fulfilled) mark kar diya hai."
            else:
                msg = f"Marked {p_entity}'s promise as fulfilled."

            return FastPathResult(
                handled=True,
                reply=msg,
                events=[{
                    "type": "promise_card",
                    "status": "FULFILLED",
                    "entity_name": p_entity,
                    "customer_name": p_entity,
                    "amount": f_res.get("promised_amount"),
                    "promise_id": f_res.get("promise_id"),
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
    # 10.A DEBTORS & OUTSTANDING UDHAR QUERY ("Kitna kiska udhar hai", "Who owes how much", "Sabka baaki hisaab")
    # ---------------------------------------------------------
    if DEBTORS_QUERY_PATTERN.search(text):
        async with SessionLocal() as s:
            res = await tools.get_shop_summary(s, shop_id)
            tot = res.get("total_outstanding", 0)
            top_debts = res.get("top_debtors", [])
            cnt = res.get("customer_count", 0)

            ev = [{"type": "debtors_list", "total_outstanding": tot, "debtors": top_debts}]

            if not top_debts or tot <= 0:
                if lang.startswith("kn"):
                    msg = "Dukaan-nalli yaaradu udhar baaki illa. Ella graahakara khate clear aagide."
                elif lang.startswith("en"):
                    msg = "No pending udhar. All customer accounts are completely clear."
                else:
                    msg = "Dukaan mein kisi ka bhi udhar baaki nahi hai. Sabhi customers ka hisaab clear hai."
                return FastPathResult(handled=True, reply=msg, events=ev)

            # Check if asking specifically who owes the most
            if "the most" in lower or "sabse zyada" in lower or "jaasti" in lower or "सबसे ज्यादा" in text or "ಜಾಸ್ತಿ" in text:
                top_3 = ", ".join(f"{d['name']} (₹{d['balance']:,.0f})" for d in top_debts[:3])
                if lang.startswith("kn"):
                    msg = f"Jaasti baaki: {top_3}."
                elif lang.startswith("en"):
                    msg = f"Top outstanding: {top_3}."
                else:
                    msg = f"Sabse zyada baaki: {top_3}."
                return FastPathResult(handled=True, reply=msg, events=ev)

            debtor_items = [f"{i}. {d['name']} (₹{d['balance']:,.0f})" for i, d in enumerate(top_debts[:5], 1)]
            items_str = ", ".join(debtor_items)

            if lang.startswith("kn"):
                msg = f"Dukaan-nalli ottu ₹{tot:,.0f} udhar baaki ide. Baaki patti: {items_str}."
            elif lang.startswith("en"):
                msg = f"Total shop udhar is ₹{tot:,.0f} across {len(top_debts)} debtors. Top balances: {items_str}."
            else:
                msg = f"Dukaan mein kul ₹{tot:,.0f} udhar baaki hai. Udhari list: {items_str}."
            return FastPathResult(handled=True, reply=msg, events=ev)

    # ---------------------------------------------------------
    # 10.B SHOP SUMMARY QUERY ("Aaj kitna udhar gaya", "Total collection")
    # ---------------------------------------------------------
    if SUMMARY_PATTERN.search(text):
        async with SessionLocal() as s:
            res = await tools.get_shop_summary(s, shop_id)
            tot = res.get("total_outstanding", 0)
            cr = res.get("credit_today", 0)
            pay = res.get("payments_today", 0)
            cnt = res.get("customer_count", 0)
            top_debts = res.get("top_debtors", [])

            if "who owes the most" in lower or "sabse zyada" in lower or "सबसे ज्यादा" in text:
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
                    if bal < 0:
                        adv = abs(bal)
                        if lang.startswith("kn"):
                            msg = f"{best['name']} avarinda ₹{adv:,.0f} mungada (advance / deposit) jama ide."
                        else:
                            msg = f"{best['name']} ka ₹{adv:,.0f} advance / deposit jama hai."
                    else:
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
                proj_bal_str_kn = f"naya baaki ₹{proj_bal:,.0f}" if proj_bal >= 0 else f"naya balance ₹{abs(proj_bal):,.0f} mungada (advance)"
                proj_bal_str_hi = f"naya balance ₹{proj_bal:,.0f}" if proj_bal >= 0 else f"naya balance ₹{abs(proj_bal):,.0f} advance deposit"

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
                    msg = f"{c_display} avarige ₹{amount:,.0f}{mode_str} {tx_label} draft aagide ({proj_bal_str_kn}). Confirm maadla?"
                else:
                    msg = f"{c_display} ke naam ₹{amount:,.0f}{mode_str} {tx_label} draft ban gaya hai ({proj_bal_str_hi}). Confirm karein?"

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

                proj_bal_str_kn = f"naya baaki ₹{proj_bal:,.0f}" if proj_bal >= 0 else f"naya balance ₹{abs(proj_bal):,.0f} mungada (advance)"
                proj_bal_str_hi = f"naya balance ₹{proj_bal:,.0f}" if proj_bal >= 0 else f"naya balance ₹{abs(proj_bal):,.0f} advance deposit"

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
                    msg = f"{cname} avarige ₹{amount:,.0f}{mode_str} {tx_label} draft aagide ({proj_bal_str_kn}). Confirm maadla?"
                else:
                    msg = f"{cname} ke naam ₹{amount:,.0f}{mode_str} {tx_label} draft ban gaya hai ({proj_bal_str_hi}). Confirm karein?"

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
