import re

"""Deterministic multilingual voice patterns extracted/adapted from Aura Reception AI.

These are language and speech-recognition patterns, not tenant facts. They make the
existing conversation brain more tolerant of natural Indian-language speech and
browser STT variants without replacing the tenant knowledge/calendar layer.
"""


# Indian language names used by the semantic language-switch detector. This is intentionally
# separate from response templates: adding a language must not require adding dozens of phrases.
INDIAN_LANGUAGE_ALIASES = {
    "english":"en","hindi":"hi","telugu":"te","tamil":"ta","kannada":"kn","malayalam":"ml",
    "marathi":"mr","bengali":"bn","bangla":"bn","gujarati":"gu","punjabi":"pa","urdu":"ur",
    "odia":"or","oriya":"or","assamese":"as","konkani":"kok","sanskrit":"sa","sindhi":"sd",
    "kashmiri":"ks","manipuri":"mni","meitei":"mni","nepali":"ne","dogri":"doi","maithili":"mai","santali":"sat",
    "हिंदी":"hi","తెలుగు":"te","தமிழ்":"ta","ಕನ್ನಡ":"kn","മലയാളം":"ml","मराठी":"mr","বাংলা":"bn",
    "ગુજરાતી":"gu","ਪੰਜਾਬੀ":"pa","اردو":"ur","ଓଡ଼ିଆ":"or","অসমীয়া":"as","संस्कृत":"sa","सिन्धी":"sd",
    "कश्मीरी":"ks","नेपाली":"ne","डोगरी":"doi","मैथिली":"mai","ᱥᱟᱱᱛᱟᱲᱤ":"sat","ꯃꯤꯇꯩ":"mni",
}

LANGUAGE_REQUEST_PHRASES = {
    "en": ("speak english", "in english", "english please", "talk in english"),
    "hi": ("speak hindi", "speak in hindi", "hindi mein", "hindi me", "i want hindi", "talk to me in hindi", "can we talk in hindi", "can you reply in hindi", "hindi please", "हिंदी", "हिन्दी"),
    "te": ("speak telugu", "in telugu", "telugulo", "telugu cheppandi", "telugu lo cheppandi", "telugulo cheppandi", "telugu matladandi", "telugu lo maatladandi", "తెలుగు"),
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
    """Semantically detect a request to switch/continue in a named language.

    Supports the full Indian-language name catalog without requiring a separate
    hard-coded sentence for every language. It accepts natural forms such as
    "speak Telugu", "Telugu lo cheppandi", "can you talk in Marathi", and
    native-script language names.
    """
    value = text.casefold().strip()
    for language, phrases in LANGUAGE_REQUEST_PHRASES.items():
        if any(phrase.casefold() in value for phrase in phrases):
            return language
    for name, language in INDIAN_LANGUAGE_ALIASES.items():
        if name.casefold() not in value:
            continue
        if language == "en" and value.strip() == name.casefold():
            return language
        # A bare language name in a voice turn is a valid switch signal.
        if re.search(rf"(^|\s|[,:;.!?]){re.escape(name.casefold())}($|\s|[,:;.!?])", value):
            return language
        if any(token in value for token in ("speak","talk","language","in ","mein","lo ","dalli","la ","ma ","vich","mein ","cheppandi","matlad","bol","bata","habla","paray","sang")):
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

CONFIRMATION_PHRASES = {
    "yes", "yeah", "yep", "yes please", "sure", "confirm", "confirmed", "please confirm",
    "go ahead", "do it", "okay confirm", "ok confirm", "okay", "ok",
    "haan", "han", "ji haan", "haan confirm", "confirm kijiye",
    "avunu", "sare", "sari", "confirm cheyyandi",
    "aamaam", "seri", "confirm pannunga",
    "howdu", "sari", "confirm madi",
    "athe", "shari", "confirm cheyyu",
    "ho", "barobar", "confirm kara",
    "hyan", "thik ache", "confirm korun",
    "haan", "theek", "confirm karo",
    "ಹೌದು", "సరే", "हो", "হ্যাঁ", "હા", "ਹਾਂ", "آں", "نعم",
}

def is_explicit_confirmation(text: str) -> bool:
    """Recognize a short affirmative confirmation without tying it to English only."""
    value = " ".join(text.casefold().split()).strip(" .,!?:;")
    if not value or len(value) > 80:
        return False
    if value in CONFIRMATION_PHRASES:
        return True
    # Natural confirmation with a small polite suffix.
    return bool(re.search(
        r"^(yes|yeah|yep|sure|confirm|confirmed|okay|ok|haan|han|avunu|sare|sari|howdu|athe|ho|hyan)"
        r"(\s+(please|sir|maam|ma'am|ji|kijiye|cheyyandi|pannunga|madi|kara|karo))?$",
        value,
    ))

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

LANGUAGE_SWITCH_CONFIRMATIONS = {
    "en": "Yes. I can continue in English.",
    "hi": "Haan, main Hindi mein baat kar sakti hoon.",
    "te": "Avunu, nenu Telugu lo maatladagalanu.",
    "ta": "Aamaam, naan Tamil-la pesalaam.",
    "kn": "Howdu, naanu Kannada dalli maatadabahudu.",
    "ml": "Athe, enikku Malayalam samsarikkaam.",
    "mr": "Ho, mi Marathi madhye bolu shakte.",
    "bn": "Hyan, ami Banglay kotha bolte pari.",
    "gu": "Haan, hu Gujarati ma vaat kari shaku chhu.",
    "pa": "Haan, main Punjabi vich gal kar sakdi haan.",
    "ur": "Ji haan, main Urdu mein baat kar sakti hoon.",
}

BUSINESS_HOURS_SIMPLE = {
    "en": "We're open Monday to Saturday, {opening} to {closing}. Sunday we're closed.",
    "hi": "Hum Monday se Saturday, {opening} se {closing} tak open hain. Sunday ko band rehte hain.",
    "te": "Memu Monday nundi Saturday varaku {opening} nundi {closing} varaku open untamu. Sunday closed.",
    "ta": "Naanga Monday mudhal Saturday varai {opening} mudhal {closing} varai open-a iruppom. Sunday closed.",
    "kn": "Naavu Monday inda Saturday varege {opening} inda {closing} varege open irutteve. Sunday closed.",
    "ml": "Njangal Monday muthal Saturday vare {opening} muthal {closing} vare open aanu. Sunday closed aanu.",
    "mr": "Amhi Monday te Saturday, {opening} te {closing} paryant open aahot. Sunday la band aste.",
    "bn": "Amra Monday theke Saturday {opening} theke {closing} porjonto open thaki. Sunday bondho.",
    "gu": "Ame Monday thi Saturday {opening} thi {closing} sudhi open chhiye. Sunday bandh hoy chhe.",
    "pa": "Asi Monday ton Saturday {opening} ton {closing} tak open haan. Sunday nu band hunde haan.",
    "ur": "Hum Monday se Saturday {opening} se {closing} tak open hain. Sunday ko band rehte hain.",
}

AVAILABILITY_PROMPTS = {
    "en": "I can help check availability. What day and time are you looking for?",
    "hi": "Main availability check kar sakti hoon. Aap kis din aur kis time ke liye dekh rahe hain?",
    "te": "Nenu availability check cheyyagalanu. Meeku ye roju, ye time kavali?",
    "ta": "Availability check pannalaam. Endha naal, endha time venum?",
    "kn": "Availability check madabahudu. Yava dina, yava samaya beku?",
    "ml": "Availability check cheyyam. Ethu divasam, ethu samayam venam?",
    "mr": "Mi availability check karu shakte. Kontya divshi ani kiti vajta pahije?",
    "bn": "Ami availability check korte pari. Kon din ebong koto tay chan?",
    "gu": "Hu availability check kari shaku chhu. Kaya divase ane ketla vagye joiye?",
    "pa": "Main availability check kar sakdi haan. Kehre din te kinne vajje chahide ne?",
    "ur": "Main availability check kar sakti hoon. Kis din aur kis waqt chahiye?",
}

DOCTOR_DETAILS_MISSING = {
    "en": "I don't have verified doctor details configured yet. I can arrange for the team to share the doctor's name and details with you.",
    "hi": "Doctor ki verified details abhi configured nahi hain. Main team se doctor ka naam aur details share karne ke liye keh sakti hoon.",
    "te": "Doctor verified details ippudu configure cheyyaledu. Team tho doctor peru mariyu details share cheyinchagalanu.",
    "ta": "Doctor-oda verified details innum configure pannala. Team kitta doctor peru matrum details share panna sollalaam.",
    "kn": "Doctor avara verified details innu configure aagilla. Team inda doctor hesaru mattu details share madisabahudu.",
    "ml": "Doctorinte verified details ippol configure cheythittilla. Teamine kondu doctorinte perum detailsum share cheyyikkaam.",
    "mr": "Doctoranchi verified mahiti ajun configure keleli nahi. Mi team kadun doctoranche naav ani details share karu shakte.",
    "bn": "Doctor-er verified details ekhono configure kora nei. Ami team-ke doctor-er naam ebong details share korte bolte pari.",
    "gu": "Doctor ni verified details haju configure nathi. Hu team pase doctor nu naam ane details share karavi shaku chhu.",
    "pa": "Doctor di verified details hun tak configure nahi han. Main team ton doctor da naam te details share karva sakdi haan.",
    "ur": "Doctor ki verified details abhi configured nahi hain. Main team se doctor ka naam aur details share karwa sakti hoon.",
}
