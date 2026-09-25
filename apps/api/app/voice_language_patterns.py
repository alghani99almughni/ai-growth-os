"""Deterministic multilingual voice patterns extracted/adapted from Aura Reception AI.

These are language and speech-recognition patterns, not tenant facts. They make the
existing conversation brain more tolerant of natural Indian-language speech and
browser STT variants without replacing the tenant knowledge/calendar layer.
"""

LANGUAGE_REQUEST_PHRASES = {
    "en": ("speak english", "in english", "english please"),
    "hi": ("speak hindi", "speak in hindi", "hindi mein", "hindi me", "हिंदी", "हिन्दी"),
    "te": ("speak telugu", "in telugu", "telugulo", "తెలుగు"),
    "ta": ("speak tamil", "in tamil", "tamil la", "தமிழ்"),
    "kn": ("speak kannada", "in kannada", "kannadadalli", "ಕನ್ನಡ"),
    "ml": ("speak malayalam", "in malayalam", "malayalathil", "മലയാളം"),
    "mr": ("speak marathi", "in marathi", "marathit", "मराठी"),
    "bn": ("speak bengali", "in bengali", "banglay", "বাংলা"),
    "gu": ("speak gujarati", "in gujarati", "gujarati ma", "ગુજરાતી"),
    "pa": ("speak punjabi", "in punjabi", "punjabi vich", "ਪੰਜਾਬੀ"),
    "ur": ("speak urdu", "in urdu", "urdu mein", "اردو"),
}

ROMANIZED_LANGUAGE_HINTS = {
    "hi": ("mujhe", "aap", "aapke", "kal", "kya", "hai", "hain", "chahiye", "karna", "karni", "bataiye", "batao"),
    "te": ("naaku", "meeru", "repu", "enti", "kavali", "cheyyali", "matladagalara", "unnara", "gantlaki"),
    "ta": ("enakku", "ungal", "naalai", "venum", "pannanum", "enna", "eppo", "pesanum"),
    "kn": ("nanage", "nimma", "naale", "beku", "enu", "madbeku", "maatadbeku", "yavaga"),
    "ml": ("enikku", "ningalude", "naale", "venam", "enthaa", "eppozha", "parayamo"),
    "mr": ("mala", "tumche", "udya", "aahe", "kay", "havi", "sanga", "karaychi"),
    "bn": ("amar", "apnader", "korte", "chai", "koto", "kokhon", "bolben"),
    "gu": ("mane", "tamara", "kaale", "joiye", "shu", "chhe", "kyare", "kahi"),
    "pa": ("mainu", "tuhade", "chahidi", "kadon", "kinna", "gal", "karni", "ne"),
    "ur": ("aap", "aapke", "mujhe", "kaun", "hai", "hain", "bataiye", "karna"),
}

RELATIVE_DAY_PHRASES = {
    "today": (
        "today", "aaj", "आज", "ee roju", "ivala", "ఈ రోజు",
        "indru", "இன்று", "ivattu", "ಇಂದು", "innu", "ഇന്ന്",
        "aaj", "आज", "aajke", "আজ", "aaje", "આજે",
        "aj", "ਅੱਜ", "aaj", "آج",
    ),
    "tomorrow": (
        "tomorrow", "kal", "kaal", "cal", "कल",
        "repu", "repu", "రేపు", "naalai", "நாளை", "naale", "ನಾಳೆ",
        "naale", "നാളെ", "udya", "उद्या", "kal", "কাল",
        "kaale", "કાલે", "kal", "ਕੱਲ", "kal", "کل",
    ),
    "day_after_tomorrow": (
        "day after tomorrow", "parson", "parso", "परसों",
        "repu taruvatha", "ఎల్లుండి", "naalai marunaal", "நாளை மறுநாள்",
        "naale marudina", "ಮರುದಿನ", "mattannal", "മറ്റന്നാൾ",
        "parva", "परवा", "poroshur", "পরশু", "parso", "પરમદિવસ",
        "parso", "ਪਰਸੋਂ",
    ),
}

CLARIFICATION_PHRASES = {
    "vpm", "vp m", "vpm", "han", "hmm", "hm", "uh", "um", "umm",
    "uhh", "mmm", "manoj", "man of", "man off", "cal", "kaal",
}

def language_from_romanized(text: str) -> str | None:
    value = text.casefold()
    words = set(value.replace("-", " ").split())
    best = None
    best_score = 0
    for language, hints in ROMANIZED_LANGUAGE_HINTS.items():
        score = sum(1 for hint in hints if hint in words or hint in value)
        if score > best_score:
            best = language
            best_score = score
    return best if best_score >= 2 else None

def language_request(text: str) -> str | None:
    value = text.casefold()
    for language, phrases in LANGUAGE_REQUEST_PHRASES.items():
        if any(phrase.casefold() in value for phrase in phrases):
            return language
    return None

def relative_day_from_text(text: str) -> str | None:
    value = text.casefold().strip()
    if any(phrase.casefold() in value for phrase in RELATIVE_DAY_PHRASES["day_after_tomorrow"]):
        return "day_after_tomorrow"
    if any(phrase.casefold() in value for phrase in RELATIVE_DAY_PHRASES["tomorrow"]):
        return "tomorrow"
    if any(phrase.casefold() in value for phrase in RELATIVE_DAY_PHRASES["today"]):
        return "today"
    return None

def needs_voice_clarification(text: str) -> bool:
    value = " ".join(text.casefold().split())
    return value in CLARIFICATION_PHRASES

SPOKEN_CLARIFICATION = {
    "en": "Sorry, I didn't catch that. Could you please repeat it?",
    "hi": "Maaf kijiye, ek baar phir se bataiye.",
    "te": "Kshaminchandi, malli cheppagalara?",
    "ta": "Mannikkavum, marubadi sollunga.",
    "kn": "Kshamisi, matte heli.",
    "ml": "Kshamikkanam, onnu koodi parayamo?",
    "mr": "Maaf kara, punha sangal ka?",
    "bn": "Dukkhito, abar bolben?",
    "gu": "Maaf karjo, fari kahi shako?",
    "pa": "Maaf karna, dubara dasso.",
    "ur": "Maaf kijiye, dobara batayenge?",
}
