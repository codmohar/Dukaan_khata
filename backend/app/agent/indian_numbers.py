"""Deterministic parser for Indian spoken numbers (Hindi, Hinglish, Kannada, English)
and Kirana shop-floor vs. ledger talk classifier helpers.
"""
import re

# Direct colloquial Indian phrases -> numeric rupee values
PHRASE_VALUES: list[tuple[re.Pattern, float]] = [
    # Hindi / Hinglish fractional hundreds & thousands
    (re.compile(r"\bsaade\s+(?:ek|1)\s*(?:hazaar|hazar|thousand)\b", re.I), 1500.0),
    (re.compile(r"\bdedh\s*(?:hazaar|hazar|thousand)\b", re.I), 1500.0),
    (re.compile(r"\bdhai\s*(?:hazaar|hazar|thousand)\b", re.I), 2500.0),
    (re.compile(r"\bsaade\s+(?:do|2)\s*(?:hazaar|hazar|thousand)\b", re.I), 2500.0),
    (re.compile(r"\bsaade\s+(?:teen|3)\s*(?:hazaar|hazar|thousand)\b", re.I), 3500.0),
    (re.compile(r"\bsawa\s*(?:hazaar|hazar|thousand)\b", re.I), 1250.0),
    (re.compile(r"\bpaune\s+(?:do|2)\s*(?:hazaar|hazar|thousand)\b", re.I), 1750.0),
    (re.compile(r"\bpaune\s*(?:hazaar|hazar|thousand)\b", re.I), 750.0),
    (re.compile(r"\bsaade\s+(?:ek|1)\s*sau\b", re.I), 150.0),
    (re.compile(r"\bdedh\s*sau\b", re.I), 150.0),
    (re.compile(r"\bdhai\s*sau\b", re.I), 250.0),
    (re.compile(r"\bsawa\s*sau\b", re.I), 125.0),
    (re.compile(r"\bsawa\s+(?:do|2)\s*sau\b", re.I), 225.0),
    (re.compile(r"\bsaade\s+(?:do|2)\s*sau\b", re.I), 250.0),
    (re.compile(r"\bsaade\s+(?:teen|3)\s*sau\b", re.I), 350.0),
    (re.compile(r"\bsaade\s+(?:chaar|char|4)\s*sau\b", re.I), 450.0),
    (re.compile(r"\bsaade\s+(?:paanch|panch|5)\s*sau\b", re.I), 550.0),
    (re.compile(r"\bsaade\s+(?:chhe|che|6)\s*sau\b", re.I), 650.0),
    (re.compile(r"\bsaade\s+(?:saat|7)\s*sau\b", re.I), 750.0),
    (re.compile(r"\bsaade\s+(?:aath|8)\s*sau\b", re.I), 850.0),
    (re.compile(r"\bpaune\s+(?:do|2)\s*sau\b", re.I), 175.0),
    (re.compile(r"\bpaune\s+(?:teen|3)\s*sau\b", re.I), 275.0),
    (re.compile(r"\bpaune\s+(?:chaar|char|4)\s*sau\b", re.I), 375.0),
    (re.compile(r"\bpaune\s+(?:paanch|panch|5)\s*sau\b", re.I), 475.0),

    # Compound Hindi thousands + hundreds
    (re.compile(r"\bdo\s*(?:hazaar|hazar)\s*paanch\s*sau\b", re.I), 2500.0),
    (re.compile(r"\bek\s*(?:hazaar|hazar)\s*paanch\s*sau\b", re.I), 1500.0),
    (re.compile(r"\bteen\s*(?:hazaar|hazar)\s*paanch\s*sau\b", re.I), 3500.0),
    (re.compile(r"\bek\s*lakh\b", re.I), 100000.0),
    (re.compile(r"\b(?:ek\s*)?(?:hazaar|hazar)\b", re.I), 1000.0),
    (re.compile(r"\bdo\s*(?:hazaar|hazar)\b", re.I), 2000.0),
    (re.compile(r"\bteen\s*(?:hazaar|hazar)\b", re.I), 3000.0),
    (re.compile(r"\bchaar\s*(?:hazaar|hazar)\b", re.I), 4000.0),
    (re.compile(r"\bpaanch\s*(?:hazaar|hazar)\b", re.I), 5000.0),
    (re.compile(r"\bdas\s*(?:hazaar|hazar)\b", re.I), 10000.0),
    (re.compile(r"\bpaanch\s*sau\b", re.I), 500.0),
    (re.compile(r"\bchaar\s*sau\b", re.I), 400.0),
    (re.compile(r"\bteen\s*sau\b", re.I), 300.0),
    (re.compile(r"\bdo\s*sau\b", re.I), 200.0),
    (re.compile(r"\bek\s*sau\b", re.I), 100.0),

    # Kannada spoken hundreds & thousands
    (re.compile(r"\beradu\s*savira\s*aidu\s*nooru\b", re.I), 2500.0),
    (re.compile(r"\bondu\s*savira\s*aidu\s*nooru\b", re.I), 1500.0),
    (re.compile(r"\beradu\s*savira\b", re.I), 2000.0),
    (re.compile(r"\bmooru\s*savira\b", re.I), 3000.0),
    (re.compile(r"\bnaalku\s*savira\b", re.I), 4000.0),
    (re.compile(r"\baidu\s*savira\b", re.I), 5000.0),
    (re.compile(r"\bhattu\s*savira\b", re.I), 10000.0),
    (re.compile(r"\b(?:ondu\s*)?savira\b", re.I), 1000.0),
    (re.compile(r"\bombattu\s*nooru\b", re.I), 900.0),
    (re.compile(r"\bentu\s*nooru\b", re.I), 800.0),
    (re.compile(r"\b(?:yelu|elu)\s*nooru\b", re.I), 700.0),
    (re.compile(r"\baaru\s*nooru\b", re.I), 600.0),
    (re.compile(r"\baidu\s*nooru\b", re.I), 500.0),
    (re.compile(r"\bnaalku\s*nooru\b", re.I), 400.0),
    (re.compile(r"\bmooru\s*nooru\b", re.I), 300.0),
    (re.compile(r"\binnooru\b", re.I), 200.0),
    (re.compile(r"\bnooru\b", re.I), 100.0),

    # Kannada spoken tens
    (re.compile(r"\btombattu\b", re.I), 90.0),
    (re.compile(r"\bembattu\b", re.I), 80.0),
    (re.compile(r"\beppattu\b", re.I), 70.0),
    (re.compile(r"\baravattu\b", re.I), 60.0),
    (re.compile(r"\baivattu\b", re.I), 50.0),
    (re.compile(r"\bnalvattu\b", re.I), 40.0),
    (re.compile(r"\bmoovattu\b", re.I), 30.0),
    (re.compile(r"\bippattu\b", re.I), 20.0),
    (re.compile(r"\bhattu\b", re.I), 10.0),

    # Hindi spoken tens (sound-alike awareness)
    (re.compile(r"\bnabbe\b", re.I), 90.0),
    (re.compile(r"\bassi\b", re.I), 80.0),
    (re.compile(r"\bsattar\b", re.I), 70.0),
    (re.compile(r"\bsaath\b|\bsath\b", re.I), 60.0),
    (re.compile(r"\bpachas\b|\bpachaas\b", re.I), 50.0),
    (re.compile(r"\bchaalis\b|\bchalis\b", re.I), 40.0),
    (re.compile(r"\btees\b", re.I), 30.0),
    (re.compile(r"\bbees\b", re.I), 20.0),
    (re.compile(r"\bdas\b", re.I), 10.0),

    # Devanagari spoken numbers
    (re.compile(r"डेढ़\s*(?:हज़ार|हजार)", re.I), 1500.0),
    (re.compile(r"ढाई\s*(?:हज़ार|हजार)", re.I), 2500.0),
    (re.compile(r"साढ़े\s*तीन\s*(?:हज़ार|हजार)", re.I), 3500.0),
    (re.compile(r"डेढ़\s*सौ", re.I), 150.0),
    (re.compile(r"ढाई\s*सौ", re.I), 250.0),
    (re.compile(r"साढ़े\s*तीन\s*सौ", re.I), 350.0),
    (re.compile(r"साढ़े\s*चार\s*सौ", re.I), 450.0),
    (re.compile(r"साढ़े\s*(?:पांच|पाँच)\s*सौ", re.I), 550.0),
    (re.compile(r"दो\s*(?:हज़ार|हजार)\s*(?:पांच|पाँच)\s*सौ", re.I), 2500.0),
    (re.compile(r"एक\s*(?:हज़ार|हजार)\s*(?:पांच|पाँच)\s*सौ", re.I), 1500.0),
    (re.compile(r"(?:एक\s*)?लाख", re.I), 100000.0),
    (re.compile(r"दस\s*(?:हज़ार|हजार)", re.I), 10000.0),
    (re.compile(r"(?:पांच|पाँच)\s*(?:हज़ार|हजार)", re.I), 5000.0),
    (re.compile(r"चार\s*(?:हज़ार|हजार)", re.I), 4000.0),
    (re.compile(r"तीन\s*(?:हज़ार|हजार)", re.I), 3000.0),
    (re.compile(r"दो\s*(?:हज़ार|हजार)", re.I), 2000.0),
    (re.compile(r"(?:एक\s*)?(?:हज़ार|हजार)", re.I), 1000.0),
    (re.compile(r"(?:पांच|पाँच)\s*सौ", re.I), 500.0),
    (re.compile(r"चार\s*सौ", re.I), 400.0),
    (re.compile(r"तीन\s*सौ", re.I), 300.0),
    (re.compile(r"दो\s*सौ", re.I), 200.0),
    (re.compile(r"(?:एक\s*)?सौ", re.I), 100.0),
    (re.compile(r"नब्बे", re.I), 90.0),
    (re.compile(r"अस्सी", re.I), 80.0),
    (re.compile(r"सत्तर", re.I), 70.0),
    (re.compile(r"साठ", re.I), 60.0),
    (re.compile(r"पचास", re.I), 50.0),
    (re.compile(r"चालीस", re.I), 40.0),
    (re.compile(r"तीस", re.I), 30.0),
    (re.compile(r"बीस", re.I), 20.0),
    (re.compile(r"दस", re.I), 10.0),
]

INDIC_DIGITS_MAP = str.maketrans("०१२३४५६७८९೦೧೨೩೪೫೬೭೮೯", "01234567890123456789")


def extract_indian_amount(text: str) -> float | None:
    """Extract numeric rupee amount from digits or spoken Hindi/Kannada/English number phrases."""
    if not text:
        return None
    for pat, val in PHRASE_VALUES:
        if pat.search(text):
            return val

    # Normalize Indic digits and remove inner grouping commas like 1,500 -> 1500
    norm_text = text.translate(INDIC_DIGITS_MAP)
    norm_text = re.sub(r"(?<=\d),(?=\d)", "", norm_text)

    # 0. Partial payment extraction: "500 mein se 300 diya", "600 alli 250 kottru", "400 out of 1000"
    partial_match = re.search(r"\b\d+\s*(?:mein\s*se|alli)\s*(\d{1,7}(?:\.\d{1,2})?)\b", norm_text, re.I)
    if partial_match:
        return float(partial_match.group(1))
    out_of_match = re.search(r"\b(\d{1,7}(?:\.\d{1,2})?)\s*out\s*of\s*\d+\b", norm_text, re.I)
    if out_of_match:
        return float(out_of_match.group(1))

    # 1. Prefer explicit currency marker association (e.g. "20 rupayi", "₹50", "Rs 100", "50 rupaye")
    cur_match = re.search(
        r"(?:rs\.?|inr|₹)\s*(\d{1,7}(?:\.\d{1,2})?)|"
        r"(\d{1,7}(?:\.\d{1,2})?)\s*(?:rupayi|rupaye|rupae|rupai|rupiya|rupya|rupay|rupayya|roopayi|roopaye|rupee|rupees|rs|inr|₹|taka|tanka|rooba|roobai)",
        norm_text,
        re.I,
    )
    if cur_match:
        val_str = cur_match.group(1) or cur_match.group(2)
        if val_str:
            return float(val_str)

    # 2. Extract digits, filtering out product quantity prefixes (e.g. "1 packet biscuit 20" -> 20)
    all_digit_matches = list(re.finditer(r"(?<!\d)(\d{1,7}(?:\.\d{1,2})?)(?!\d)", norm_text))
    valid_numbers: list[tuple[float, bool]] = []
    for m in all_digit_matches:
        token = m.group(1)
        if len(token.split(".")[0]) >= 9:
            continue
        val = float(token)
        # Check if immediately followed by quantity words
        after_text = norm_text[m.end():m.end() + 15].strip().lower()
        is_qty = bool(re.match(r"^(?:l\b|ltr|liter|litre|packet|pkt|kilo|kg|gm|piece|pc|pcs|dabba|pouch|glass|cup)\b", after_text))
        valid_numbers.append((val, is_qty))

    if valid_numbers:
        # If there's a non-quantity number, prefer it (e.g. in "1 packet biscuit 20", pick 20)
        non_qty = [v for v, is_q in valid_numbers if not is_q]
        if non_qty:
            return non_qty[0]
        return None

    return None
