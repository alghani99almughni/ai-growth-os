"""Gender-aware message templates.

Every handler that speaks in first person singular ("I'll...", "I've...",
"Let me...") routes through AgentVoice so that grammar matches the tenant's
configured receptionist gender.

Design:
- Load once per turn from the tenant.
- Render with a language + gender; fall back to the female variant if the
  requested gender is missing.
- Fall back to the language's non-gendered template if no gendered variant
  exists for that language.
- Fall back to English if the language itself is unsupported.

Only 6 of the 11 languages have strongly gendered first-person verbs:
    Hindi, Marathi, Punjabi, Urdu  (always)
    Gujarati, Bengali              (sometimes)
The remaining 5 (Telugu, Tamil, Kannada, Malayalam) use neutral first-person
forms and share a single template across genders.
"""
from __future__ import annotations

from typing import Optional


VALID_GENDERS = ("male", "female")
VALID_LANGUAGES = ("en", "hi", "te", "ta", "kn", "ml", "mr", "bn", "gu", "pa", "ur")
DEFAULT_GENDER = "female"
DEFAULT_LANGUAGE = "en"


# ---------------------------------------------------------------------------
# Gendered templates. Only languages with gendered first-person verbs here.
# Structure: _GENDERED[language][key][gender] = template
# ---------------------------------------------------------------------------

_GENDERED: dict = {

    # ============================================================
    # HINDI
    # ============================================================
    "hi": {
        "not_configured": {
            "female": "मैं टीम से पुष्टि करके आपको बताऊंगी।",
            "male":   "मैं टीम से पुष्टि करके आपको बताऊंगा।",
        },
        "checking_with_team": {
            "female": "मैं टीम से जाँच करके बताऊंगी।",
            "male":   "मैं टीम से जाँच करके बताऊंगा।",
        },
        "callback_logged": {
            "female": "मैंने आपका कॉलबैक दर्ज कर दिया है। टीम जल्दी कॉल करेगी।",
            "male":   "मैंने आपका कॉलबैक दर्ज कर दिया है। टीम जल्दी कॉल करेगी।",
        },
        "booking_confirmed": {
            "female": "मैंने आपकी अपॉइंटमेंट {time} पर कन्फर्म कर दी है।",
            "male":   "मैंने आपकी अपॉइंटमेंट {time} पर कन्फर्म कर दिया है।",
        },
        "booking_cancelled": {
            "female": "मैंने आपकी अपॉइंटमेंट रद्द कर दी है।",
            "male":   "मैंने आपकी अपॉइंटमेंट रद्द कर दिया है।",
        },
        "order_received": {
            "female": "मैंने आपकी ऑर्डर ले ली है। तैयारी शुरू हो गई है।",
            "male":   "मैंने आपकी ऑर्डर ले लिया है। तैयारी शुरू हो गई है।",
        },
        "handoff_requested": {
            "female": "मैंने आपकी बात टीम तक पहुँचा दी है। कोई सदस्य जल्द ही जुड़ेगा।",
            "male":   "मैंने आपकी बात टीम तक पहुँचा दी है। कोई सदस्य जल्द ही जुड़ेगा।",
        },
        "complaint_received": {
            "female": "मुझे खेद है कि आपको यह अनुभव हुआ। मैंने इसे टीम को भेज दिया है।",
            "male":   "मुझे खेद है कि आपको यह अनुभव हुआ। मैंने इसे टीम को भेज दिया है।",
        },
        "emergency_flagged": {
            "female": "मैंने इसे तत्काल चिह्नित किया है। टीम तुरंत संपर्क करेगी।",
            "male":   "मैंने इसे तत्काल चिह्नित किया है। टीम तुरंत संपर्क करेगी।",
        },
        "refund_forwarded": {
            "female": "मैंने आपका रिफंड अनुरोध टीम को भेज दिया है। वे जल्द ही संपर्क करेंगे।",
            "male":   "मैंने आपका रिफंड अनुरोध टीम को भेज दिया है। वे जल्द ही संपर्क करेंगे।",
        },
        "ownership_claimed": {
            "female": "मैं इसे संभाल लूंगी।",
            "male":   "मैं इसे संभाल लूंगा।",
        },
        "cannot_help": {
            "female": "मैं इस समय इसमें मदद नहीं कर सकती।",
            "male":   "मैं इस समय इसमें मदद नहीं कर सकता।",
        },
        "will_arrange": {
            "female": "मैं इसे व्यवस्थित कर दूंगी।",
            "male":   "मैं इसे व्यवस्थित कर दूंगा।",
        },
        "will_check": {
            "female": "मैं जाँच कर लूंगी।",
            "male":   "मैं जाँच कर लूंगा।",
        },
        "will_call_back": {
            "female": "मैं आपको वापस कॉल करूंगी।",
            "male":   "मैं आपको वापस कॉल करूंगा।",
        },
        "will_inform": {
            "female": "मैं आपको सूचित कर दूंगी।",
            "male":   "मैं आपको सूचित कर दूंगा।",
        },
    },

    # ============================================================
    # MARATHI
    # ============================================================
    "mr": {
        "not_configured": {
            "female": "मी टीमशी पुष्टी करून तुम्हाला सांगेन.",
            "male":   "मी टीमशी पुष्टी करून तुम्हाला सांगण.",
        },
        "checking_with_team": {
            "female": "मी टीमशी तपासून सांगेन.",
            "male":   "मी टीमशी तपासून सांगण.",
        },
        "callback_logged": {
            "female": "मी तुमचा कॉलबॅक नोंदवला आहे. टीम लवकर कॉल करेल.",
            "male":   "मी तुमचा कॉलबॅक नोंदवला आहे. टीम लवकर कॉल करेल.",
        },
        "booking_confirmed": {
            "female": "मी तुमची अपॉइंटमेंट {time} ला कन्फर्म केली आहे.",
            "male":   "मी तुमची अपॉइंटमेंट {time} ला कन्फर्म केला आहे.",
        },
        "booking_cancelled": {
            "female": "मी तुमची अपॉइंटमेंट रद्द केली आहे.",
            "male":   "मी तुमची अपॉइंटमेंट रद्द केला आहे.",
        },
        "order_received": {
            "female": "मी तुमची ऑर्डर घेतली आहे.",
            "male":   "मी तुमची ऑर्डर घेतला आहे.",
        },
        "handoff_requested": {
            "female": "मी हे टीमला कळवले आहे. सदस्य लवकर जोडेल.",
            "male":   "मी हे टीमला कळवले आहे. सदस्य लवकर जोडेल.",
        },
        "complaint_received": {
            "female": "तुम्हाला हा अनुभव आला याबद्दल मला वाईट वाटते. मी हे टीमला पाठवले आहे.",
            "male":   "तुम्हाला हा अनुभव आला याबद्दल मला वाईट वाटते. मी हे टीमला पाठवले आहे.",
        },
        "emergency_flagged": {
            "female": "मी हे तातडीचे म्हणून चिन्हांकित केले आहे. टीम लगेच संपर्क करेल.",
            "male":   "मी हे तातडीचे म्हणून चिन्हांकित केले आहे. टीम लगेच संपर्क करेल.",
        },
        "refund_forwarded": {
            "female": "मी तुमची रिफंड विनंती टीमला पाठवली आहे.",
            "male":   "मी तुमची रिफंड विनंती टीमला पाठवली आहे.",
        },
        "ownership_claimed": {
            "female": "मी हे सांभाळते.",
            "male":   "मी हे सांभाळतो.",
        },
        "cannot_help": {
            "female": "मी यावेळी मदत करू शकत नाही.",
            "male":   "मी यावेळी मदत करू शकत नाही.",
        },
        "will_arrange": {
            "female": "मी हे व्यवस्थित करते.",
            "male":   "मी हे व्यवस्थित करतो.",
        },
        "will_check": {
            "female": "मी तपासते.",
            "male":   "मी तपासतो.",
        },
        "will_call_back": {
            "female": "मी तुम्हाला परत कॉल करते.",
            "male":   "मी तुम्हाला परत कॉल करतो.",
        },
        "will_inform": {
            "female": "मी तुम्हाला कळवते.",
            "male":   "मी तुम्हाला कळवतो.",
        },
    },

    # ============================================================
    # PUNJABI
    # ============================================================
    "pa": {
        "not_configured": {
            "female": "ਮੈਂ ਟੀਮ ਤੋਂ ਪੁਸ਼ਟੀ ਕਰਕੇ ਤੁਹਾਨੂੰ ਦੱਸ ਸਕਦੀ ਹਾਂ।",
            "male":   "ਮੈਂ ਟੀਮ ਤੋਂ ਪੁਸ਼ਟੀ ਕਰਕੇ ਤੁਹਾਨੂੰ ਦੱਸ ਸਕਦਾ ਹਾਂ।",
        },
        "checking_with_team": {
            "female": "ਮੈਂ ਟੀਮ ਤੋਂ ਪੁੱਛ ਕੇ ਦੱਸ ਸਕਦੀ ਹਾਂ।",
            "male":   "ਮੈਂ ਟੀਮ ਤੋਂ ਪੁੱਛ ਕੇ ਦੱਸ ਸਕਦਾ ਹਾਂ।",
        },
        "callback_logged": {
            "female": "ਮੈਂ ਤੁਹਾਡਾ ਕਾਲਬੈਕ ਦਰਜ ਕਰ ਦਿੱਤੀ ਹੈ। ਟੀਮ ਜਲਦੀ ਕਾਲ ਕਰੇਗੀ।",
            "male":   "ਮੈਂ ਤੁਹਾਡਾ ਕਾਲਬੈਕ ਦਰਜ ਕਰ ਦਿੱਤਾ ਹੈ। ਟੀਮ ਜਲਦੀ ਕਾਲ ਕਰੇਗੀ।",
        },
        "booking_confirmed": {
            "female": "ਮੈਂ ਤੁਹਾਡੀ ਅਪਾਇੰਟਮੈਂਟ {time} ਲਈ ਕਨਫਰਮ ਕਰ ਦਿੱਤੀ ਹੈ।",
            "male":   "ਮੈਂ ਤੁਹਾਡੀ ਅਪਾਇੰਟਮੈਂਟ {time} ਲਈ ਕਨਫਰਮ ਕਰ ਦਿੱਤਾ ਹੈ।",
        },
        "booking_cancelled": {
            "female": "ਮੈਂ ਤੁਹਾਡੀ ਅਪਾਇੰਟਮੈਂਟ ਰੱਦ ਕਰ ਦਿੱਤੀ ਹੈ।",
            "male":   "ਮੈਂ ਤੁਹਾਡੀ ਅਪਾਇੰਟਮੈਂਟ ਰੱਦ ਕਰ ਦਿੱਤਾ ਹੈ।",
        },
        "order_received": {
            "female": "ਮੈਂ ਤੁਹਾਡਾ ਆਰਡਰ ਲੈ ਲਿਆ ਹੈ।",
            "male":   "ਮੈਂ ਤੁਹਾਡਾ ਆਰਡਰ ਲੈ ਲਿਆ ਹੈ।",
        },
        "handoff_requested": {
            "female": "ਮੈਂ ਤੁਹਾਡੀ ਗੱਲ ਟੀਮ ਤੱਕ ਪਹੁੰਚਾ ਦਿੱਤੀ ਹੈ।",
            "male":   "ਮੈਂ ਤੁਹਾਡੀ ਗੱਲ ਟੀਮ ਤੱਕ ਪਹੁੰਚਾ ਦਿੱਤੀ ਹੈ।",
        },
        "complaint_received": {
            "female": "ਮਾਫ ਕਰਨਾ ਤੁਹਾਨੂੰ ਇਹ ਅਨੁਭਵ ਹੋਇਆ। ਮੈਂ ਇਹ ਟੀਮ ਨੂੰ ਭੇਜ ਦਿੱਤੀ ਹੈ।",
            "male":   "ਮਾਫ ਕਰਨਾ ਤੁਹਾਨੂੰ ਇਹ ਅਨੁਭਵ ਹੋਇਆ। ਮੈਂ ਇਹ ਟੀਮ ਨੂੰ ਭੇਜ ਦਿੱਤੀ ਹੈ।",
        },
        "emergency_flagged": {
            "female": "ਮੈਂ ਇਸਨੂੰ ਜ਼ਰੂਰੀ ਵਜੋਂ ਨਿਸ਼ਾਨ ਲਗਾਇਆ ਹੈ। ਟੀਮ ਤੁਰੰਤ ਸੰਪਰਕ ਕਰੇਗੀ।",
            "male":   "ਮੈਂ ਇਸਨੂੰ ਜ਼ਰੂਰੀ ਵਜੋਂ ਨਿਸ਼ਾਨ ਲਗਾਇਆ ਹੈ। ਟੀਮ ਤੁਰੰਤ ਸੰਪਰਕ ਕਰੇਗੀ।",
        },
        "refund_forwarded": {
            "female": "ਮੈਂ ਤੁਹਾਡੀ ਰਿਫੰਡ ਬੇਨਤੀ ਟੀਮ ਨੂੰ ਭੇਜ ਦਿੱਤੀ ਹੈ।",
            "male":   "ਮੈਂ ਤੁਹਾਡੀ ਰਿਫੰਡ ਬੇਨਤੀ ਟੀਮ ਨੂੰ ਭੇਜ ਦਿੱਤੀ ਹੈ।",
        },
        "ownership_claimed": {
            "female": "ਮੈਂ ਇਸਨੂੰ ਸੰਭਾਲ ਲਵਾਂਗੀ।",
            "male":   "ਮੈਂ ਇਸਨੂੰ ਸੰਭਾਲ ਲਵਾਂਗਾ।",
        },
        "cannot_help": {
            "female": "ਮੈਂ ਇਸ ਸਮੇਂ ਮਦਦ ਨਹੀਂ ਕਰ ਸਕਦੀ।",
            "male":   "ਮੈਂ ਇਸ ਸਮੇਂ ਮਦਦ ਨਹੀਂ ਕਰ ਸਕਦਾ।",
        },
        "will_arrange": {
            "female": "ਮੈਂ ਇਸਦਾ ਪ੍ਰਬੰਧ ਕਰ ਦੇਵਾਂਗੀ।",
            "male":   "ਮੈਂ ਇਸਦਾ ਪ੍ਰਬੰਧ ਕਰ ਦੇਵਾਂਗਾ।",
        },
        "will_check": {
            "female": "ਮੈਂ ਜਾਂਚ ਕਰ ਲਵਾਂਗੀ।",
            "male":   "ਮੈਂ ਜਾਂਚ ਕਰ ਲਵਾਂਗਾ।",
        },
        "will_call_back": {
            "female": "ਮੈਂ ਤੁਹਾਨੂੰ ਵਾਪਸ ਕਾਲ ਕਰਾਂਗੀ।",
            "male":   "ਮੈਂ ਤੁਹਾਨੂੰ ਵਾਪਸ ਕਾਲ ਕਰਾਂਗਾ।",
        },
        "will_inform": {
            "female": "ਮੈਂ ਤੁਹਾਨੂੰ ਦੱਸ ਦੇਵਾਂਗੀ।",
            "male":   "ਮੈਂ ਤੁਹਾਨੂੰ ਦੱਸ ਦੇਵਾਂਗਾ।",
        },
    },

    # ============================================================
    # URDU
    # ============================================================
    "ur": {
        "not_configured": {
            "female": "میں ٹیم سے تصدیق کر کے آپ کو بتاؤں گی۔",
            "male":   "میں ٹیم سے تصدیق کر کے آپ کو بتاؤں گا۔",
        },
        "checking_with_team": {
            "female": "میں ٹیم سے چیک کر کے بتاؤں گی۔",
            "male":   "میں ٹیم سے چیک کر کے بتاؤں گا۔",
        },
        "callback_logged": {
            "female": "میں نے آپ کا کال بیک درج کر دیا ہے۔ ٹیم جلد کال کرے گی۔",
            "male":   "میں نے آپ کا کال بیک درج کر دیا ہے۔ ٹیم جلد کال کرے گی۔",
        },
        "booking_confirmed": {
            "female": "میں نے آپ کی اپائنٹمنٹ {time} پر کنفرم کر دی ہے۔",
            "male":   "میں نے آپ کی اپائنٹمنٹ {time} پر کنفرم کر دیا ہے۔",
        },
        "booking_cancelled": {
            "female": "میں نے آپ کی اپائنٹمنٹ منسوخ کر دی ہے۔",
            "male":   "میں نے آپ کی اپائنٹمنٹ منسوخ کر دیا ہے۔",
        },
        "order_received": {
            "female": "میں نے آپ کا آرڈر لے لیا ہے۔",
            "male":   "میں نے آپ کا آرڈر لے لیا ہے۔",
        },
        "handoff_requested": {
            "female": "میں نے آپ کی بات ٹیم تک پہنچا دی ہے۔",
            "male":   "میں نے آپ کی بات ٹیم تک پہنچا دی ہے۔",
        },
        "complaint_received": {
            "female": "افسوس کہ آپ کو یہ تجربہ ہوا۔ میں نے یہ ٹیم کو بھیج دی ہے۔",
            "male":   "افسوس کہ آپ کو یہ تجربہ ہوا۔ میں نے یہ ٹیم کو بھیج دیا ہے۔",
        },
        "emergency_flagged": {
            "female": "میں نے اسے فوری نشان زد کیا ہے۔ ٹیم فوراً رابطہ کرے گی۔",
            "male":   "میں نے اسے فوری نشان زد کیا ہے۔ ٹیم فوراً رابطہ کرے گی۔",
        },
        "refund_forwarded": {
            "female": "میں نے آپ کی رقم واپسی کی درخواست ٹیم کو بھیج دی ہے۔",
            "male":   "میں نے آپ کی رقم واپسی کی درخواست ٹیم کو بھیج دی ہے۔",
        },
        "ownership_claimed": {
            "female": "میں اسے سنبھال لوں گی۔",
            "male":   "میں اسے سنبھال لوں گا۔",
        },
        "cannot_help": {
            "female": "میں اس وقت مدد نہیں کر سکتی۔",
            "male":   "میں اس وقت مدد نہیں کر سکتا۔",
        },
        "will_arrange": {
            "female": "میں اس کا انتظام کر دوں گی۔",
            "male":   "میں اس کا انتظام کر دوں گا۔",
        },
        "will_check": {
            "female": "میں چیک کر لوں گی۔",
            "male":   "میں چیک کر لوں گا۔",
        },
        "will_call_back": {
            "female": "میں آپ کو واپس کال کروں گی۔",
            "male":   "میں آپ کو واپس کال کروں گا۔",
        },
        "will_inform": {
            "female": "میں آپ کو مطلع کر دوں گی۔",
            "male":   "میں آپ کو مطلع کر دوں گا۔",
        },
    },

    # ============================================================
    # GUJARATI
    # ============================================================
    "gu": {
        "not_configured": {
            "female": "હું ટીમ સાથે ખાતરી કરીને જણાવીશ.",
            "male":   "હું ટીમ સાથે ખાતરી કરીને જણાવીશ.",
        },
        "callback_logged": {
            "female": "મેં તમારો કૉલબેક નોંધી લીધો છે. ટીમ જલદી કૉલ કરશે.",
            "male":   "મેં તમારો કૉલબેક નોંધી લીધો છે. ટીમ જલદી કૉલ કરશે.",
        },
        "booking_confirmed": {
            "female": "મેં તમારી એપોઇન્ટમેન્ટ {time} પર કન્ફર્મ કરી દીધી છે.",
            "male":   "મેં તમારી એપોઇન્ટમેન્ટ {time} પર કન્ફર્મ કરી દીધી છે.",
        },
        "handoff_requested": {
            "female": "મેં આ ટીમને જણાવી દીધું છે.",
            "male":   "મેં આ ટીમને જણાવી દીધું છે.",
        },
        "ownership_claimed": {
            "female": "હું આ સંભાળી લઈશ.",
            "male":   "હું આ સંભાળી લઈશ.",
        },
    },

    # ============================================================
    # BENGALI
    # ============================================================
    "bn": {
        "not_configured": {
            "female": "আমি টিমের সাথে নিশ্চিত করে জানাব।",
            "male":   "আমি টিমের সাথে নিশ্চিত করে জানাব।",
        },
        "callback_logged": {
            "female": "আমি আপনার কলব্যাক নথিভুক্ত করেছি। টিম শীঘ্রই কল করবে।",
            "male":   "আমি আপনার কলব্যাক নথিভুক্ত করেছি। টিম শীঘ্রই কল করবে।",
        },
        "booking_confirmed": {
            "female": "আমি আপনার অ্যাপয়েন্টমেন্ট {time} এ নিশ্চিত করেছি।",
            "male":   "আমি আপনার অ্যাপয়েন্টমেন্ট {time} এ নিশ্চিত করেছি।",
        },
        "ownership_claimed": {
            "female": "আমি এটি সামলাব।",
            "male":   "আমি এটি সামলাব।",
        },
    },
}


# ---------------------------------------------------------------------------
# Non-gendered fallbacks (used when no gendered variant exists)
# ---------------------------------------------------------------------------

_FALLBACK: dict = {
    "en": {
        "not_configured": "I'll have the team confirm and get back to you.",
        "checking_with_team": "Let me check with the team.",
        "callback_logged": "I've logged your callback request. The team will call you back shortly.",
        "booking_confirmed": "I've confirmed your appointment for {time}.",
        "booking_cancelled": "I've cancelled your appointment.",
        "order_received": "I've received your order.",
        "handoff_requested": "I've passed this to the team. A member will join shortly.",
        "complaint_received": "I'm sorry you had that experience. I've shared this with the team.",
        "emergency_flagged": "I've flagged this as urgent. The team will reach out immediately.",
        "refund_forwarded": "I've passed your refund request to the team.",
        "ownership_claimed": "I'll take care of this.",
        "cannot_help": "I'm unable to help with this at the moment.",
        "will_arrange": "I'll arrange it.",
        "will_check": "I'll check.",
        "will_call_back": "I'll call you back.",
        "will_inform": "I'll let you know.",
    },
    "hi": {
        "not_configured": "मैं टीम से पुष्टि करके बताऊंगी।",
        "checking_with_team": "मैं टीम से जाँच करूंगी।",
        "callback_logged": "मैंने आपका कॉलबैक दर्ज किया है। टीम जल्दी कॉल करेगी।",
        "booking_confirmed": "मैंने आपकी अपॉइंटमेंट {time} पर कन्फर्म की है।",
        "booking_cancelled": "मैंने आपकी अपॉइंटमेंट रद्द की है।",
        "order_received": "मैंने आपकी ऑर्डर ली है।",
        "handoff_requested": "मैंने आपकी बात टीम तक पहुँचाई है।",
        "complaint_received": "मुझे खेद है। मैंने इसे टीम को भेजा है।",
        "emergency_flagged": "मैंने इसे तत्काल चिह्नित किया है।",
        "refund_forwarded": "मैंने आपका रिफंड अनुरोध टीम को भेजा है।",
        "ownership_claimed": "मैं इसे संभाल लूंगी।",
        "cannot_help": "मैं इस समय इसमें मदद नहीं कर सकती।",
        "will_arrange": "मैं इसे व्यवस्थित कर दूंगी।",
        "will_check": "मैं जाँच कर लूंगी।",
        "will_call_back": "मैं आपको वापस कॉल करूंगी।",
        "will_inform": "मैं आपको सूचित कर दूंगी।",
    },
    "te": {
        "not_configured": "నేను బృందంతో నిర్ధారించి మీకు తెలియజేస్తాను.",
        "checking_with_team": "నేను బృందంతో తనిఖీ చేస్తాను.",
        "callback_logged": "మీ కాల్‌బ్యాక్ నమోదు చేయబడింది. బృందం త్వరలో కాల్ చేస్తుంది.",
        "booking_confirmed": "{time}కి మీ అపాయింట్‌మెంట్ నిర్ధారించబడింది.",
        "booking_cancelled": "మీ అపాయింట్‌మెంట్ రద్దు చేయబడింది.",
        "order_received": "మీ ఆర్డర్ స్వీకరించబడింది.",
        "handoff_requested": "మీ అభ్యర్థన బృందానికి పంపబడింది.",
        "complaint_received": "క్షమించండి. దీన్ని బృందానికి పంపాను.",
        "emergency_flagged": "ఇది అత్యవసరంగా గుర్తించబడింది.",
        "refund_forwarded": "మీ రీఫండ్ అభ్యర్థన బృందానికి పంపబడింది.",
        "ownership_claimed": "నేను దీన్ని చూసుకుంటాను.",
        "cannot_help": "ఈ సమయంలో నేను సహాయం చేయలేను.",
        "will_arrange": "నేను ఏర్పాటు చేస్తాను.",
        "will_check": "నేను తనిఖీ చేస్తాను.",
        "will_call_back": "నేను మీకు తిరిగి కాల్ చేస్తాను.",
        "will_inform": "నేను మీకు తెలియజేస్తాను.",
    },
    "ta": {
        "not_configured": "குழுவுடன் உறுதிசெய்து தெரிவிக்கிறேன்.",
        "checking_with_team": "குழுவுடன் சரிபார்க்கிறேன்.",
        "callback_logged": "உங்கள் கால்-பேக் பதிவு செய்யப்பட்டது. குழு விரைவில் அழைக்கும்.",
        "booking_confirmed": "{time} அன்று உங்கள் அப்பாயிண்ட்மென்ட் உறுதிசெய்யப்பட்டது.",
        "booking_cancelled": "உங்கள் அப்பாயிண்ட்மென்ட் ரத்து செய்யப்பட்டது.",
        "order_received": "உங்கள் ஆர்டர் பெறப்பட்டது.",
        "handoff_requested": "உங்கள் கோரிக்கை குழுவுக்கு அனுப்பப்பட்டது.",
        "complaint_received": "வருந்துகிறேன். இதை குழுவுக்கு அனுப்பியுள்ளேன்.",
        "emergency_flagged": "இது அவசரமாகக் குறிக்கப்பட்டது.",
        "refund_forwarded": "உங்கள் பணத் திரும்பக் கோரிக்கை அனுப்பப்பட்டது.",
        "ownership_claimed": "நான் இதை கவனித்துக்கொள்கிறேன்.",
        "cannot_help": "இந்த நேரத்தில் என்னால் உதவ முடியாது.",
        "will_arrange": "நான் ஏற்பாடு செய்கிறேன்.",
        "will_check": "நான் சரிபார்க்கிறேன்.",
        "will_call_back": "நான் உங்களை மீண்டும் அழைக்கிறேன்.",
        "will_inform": "நான் உங்களுக்கு தெரிவிக்கிறேன்.",
    },
    "kn": {
        "not_configured": "ನಾನು ತಂಡದೊಂದಿಗೆ ಖಚಿತಪಡಿಸಿ ತಿಳಿಸುತ್ತೇನೆ.",
        "checking_with_team": "ನಾನು ತಂಡದೊಂದಿಗೆ ಪರಿಶೀಲಿಸುತ್ತೇನೆ.",
        "callback_logged": "ನಿಮ್ಮ ಕಾಲ್‌ಬ್ಯಾಕ್ ದಾಖಲಾಗಿದೆ. ತಂಡ ಶೀಘ್ರವಾಗಿ ಕರೆ ಮಾಡುತ್ತದೆ.",
        "booking_confirmed": "{time} ಗೆ ನಿಮ್ಮ ಅಪಾಯಿಂಟ್‌ಮೆಂಟ್ ದೃಢೀಕರಿಸಲಾಗಿದೆ.",
        "booking_cancelled": "ನಿಮ್ಮ ಅಪಾಯಿಂಟ್‌ಮೆಂಟ್ ರದ್ದುಗೊಳಿಸಲಾಗಿದೆ.",
        "order_received": "ನಿಮ್ಮ ಆರ್ಡರ್ ಸ್ವೀಕರಿಸಲಾಗಿದೆ.",
        "handoff_requested": "ನಿಮ್ಮ ವಿನಂತಿ ತಂಡಕ್ಕೆ ಕಳುಹಿಸಲಾಗಿದೆ.",
        "complaint_received": "ಕ್ಷಮಿಸಿ. ಇದನ್ನು ತಂಡಕ್ಕೆ ಕಳುಹಿಸಿದ್ದೇನೆ.",
        "emergency_flagged": "ಇದನ್ನು ತುರ್ತು ಎಂದು ಗುರುತಿಸಲಾಗಿದೆ.",
        "refund_forwarded": "ನಿಮ್ಮ ಮರುಪಾವತಿ ವಿನಂತಿ ಕಳುಹಿಸಲಾಗಿದೆ.",
        "ownership_claimed": "ನಾನು ಇದನ್ನು ನೋಡಿಕೊಳ್ಳುತ್ತೇನೆ.",
        "cannot_help": "ಈ ಸಮಯದಲ್ಲಿ ನಾನು ಸಹಾಯ ಮಾಡಲು ಸಾಧ್ಯವಿಲ್ಲ.",
        "will_arrange": "ನಾನು ವ್ಯವಸ್ಥೆ ಮಾಡುತ್ತೇನೆ.",
        "will_check": "ನಾನು ಪರಿಶೀಲಿಸುತ್ತೇನೆ.",
        "will_call_back": "ನಾನು ನಿಮಗೆ ಮತ್ತೆ ಕರೆ ಮಾಡುತ್ತೇನೆ.",
        "will_inform": "ನಾನು ನಿಮಗೆ ತಿಳಿಸುತ್ತೇನೆ.",
    },
    "ml": {
        "not_configured": "ടീമുമായി സ്ഥിരീകരിച്ച് അറിയിക്കാം.",
        "checking_with_team": "ടീമുമായി പരിശോധിക്കാം.",
        "callback_logged": "നിങ്ങളുടെ കോൾബാക്ക് രേഖപ്പെടുത്തി. ടീം ഉടൻ വിളിക്കും.",
        "booking_confirmed": "{time}-ന് നിങ്ങളുടെ അപ്പോയിന്റ്മെന്റ് സ്ഥിരീകരിച്ചു.",
        "booking_cancelled": "നിങ്ങളുടെ അപ്പോയിന്റ്മെന്റ് റദ്ദാക്കി.",
        "order_received": "നിങ്ങളുടെ ഓർഡർ ലഭിച്ചു.",
        "handoff_requested": "നിങ്ങളുടെ അഭ്യർത്ഥന ടീമിന് അയച്ചു.",
        "complaint_received": "ക്ഷമിക്കണം. ഇത് ടീമിന് അയച്ചു.",
        "emergency_flagged": "ഇത് അടിയന്തിരമായി അടയാളപ്പെടുത്തി.",
        "refund_forwarded": "നിങ്ങളുടെ റീഫണ്ട് അഭ്യർത്ഥന അയച്ചു.",
        "ownership_claimed": "ഞാൻ ഇത് ശ്രദ്ധിക്കാം.",
        "cannot_help": "ഈ സമയത്ത് എനിക്ക് സഹായിക്കാൻ കഴിയില്ല.",
        "will_arrange": "ഞാൻ ക്രമീകരിക്കാം.",
        "will_check": "ഞാൻ പരിശോധിക്കാം.",
        "will_call_back": "ഞാൻ നിങ്ങളെ തിരികെ വിളിക്കാം.",
        "will_inform": "ഞാൻ നിങ്ങളെ അറിയിക്കാം.",
    },
    "mr": {
        "not_configured": "मी टीमशी पुष्टी करून सांगेन.",
        "checking_with_team": "मी टीमशी तपासते.",
        "callback_logged": "मी तुमचा कॉलबॅक नोंदवला आहे.",
        "booking_confirmed": "{time} ला तुमची अपॉइंटमेंट कन्फर्म केली आहे.",
        "booking_cancelled": "तुमची अपॉइंटमेंट रद्द केली आहे.",
        "order_received": "तुमची ऑर्डर मिळाली.",
        "handoff_requested": "हे टीमला कळवले आहे.",
        "complaint_received": "माफ करा. हे टीमला पाठवले आहे.",
        "emergency_flagged": "हे तातडीचे म्हणून चिन्हांकित केले आहे.",
        "refund_forwarded": "तुमची रिफंड विनंती पाठवली आहे.",
        "ownership_claimed": "मी हे सांभाळते.",
        "cannot_help": "यावेळी मी मदत करू शकत नाही.",
        "will_arrange": "मी व्यवस्थित करते.",
        "will_check": "मी तपासते.",
        "will_call_back": "मी तुम्हाला परत कॉल करते.",
        "will_inform": "मी तुम्हाला कळवते.",
    },
    "bn": {
        "not_configured": "টিমের সাথে নিশ্চিত করে জানাব।",
        "checking_with_team": "টিমের সাথে যাচাই করছি।",
        "callback_logged": "আপনার কলব্যাক নথিভুক্ত করেছি। টিম শীঘ্রই কল করবে।",
        "booking_confirmed": "{time} এ আপনার অ্যাপয়েন্টমেন্ট নিশ্চিত করা হয়েছে।",
        "booking_cancelled": "আপনার অ্যাপয়েন্টমেন্ট বাতিল করা হয়েছে।",
        "order_received": "আপনার অর্ডার পেয়েছি।",
        "handoff_requested": "আপনার অনুরোধ টিমে পাঠিয়েছি।",
        "complaint_received": "দুঃখিত। এটি টিমে পাঠিয়েছি।",
        "emergency_flagged": "এটি জরুরি হিসেবে চিহ্নিত করেছি।",
        "refund_forwarded": "আপনার রিফান্ড অনুরোধ পাঠিয়েছি।",
        "ownership_claimed": "আমি এটি সামলাব।",
        "cannot_help": "এই সময়ে সাহায্য করতে পারছি না।",
        "will_arrange": "আমি ব্যবস্থা করব।",
        "will_check": "আমি যাচাই করব।",
        "will_call_back": "আমি আপনাকে আবার কল করব।",
        "will_inform": "আমি আপনাকে জানাব।",
    },
    "gu": {
        "not_configured": "હું ટીમ સાથે ખાતરી કરીને જણાવીશ.",
        "checking_with_team": "હું ટીમ સાથે તપાસ કરું છું.",
        "callback_logged": "તમારો કૉલબેક નોંધ્યો છે. ટીમ જલદી કૉલ કરશે.",
        "booking_confirmed": "{time} પર તમારી એપોઇન્ટમેન્ટ કન્ફર્મ કરી છે.",
        "booking_cancelled": "તમારી એપોઇન્ટમેન્ટ રદ કરી છે.",
        "order_received": "તમારો ઓર્ડર મળ્યો.",
        "handoff_requested": "આ ટીમને જણાવ્યું છે.",
        "complaint_received": "માફ કરશો. આ ટીમને મોકલ્યું છે.",
        "emergency_flagged": "આને ઈમરજન્સી તરીકે ચિહ્નિત કર્યું છે.",
        "refund_forwarded": "તમારી રિફંડ વિનંતી મોકલી છે.",
        "ownership_claimed": "હું આ સંભાળી લઈશ.",
        "cannot_help": "આ સમયે હું મદદ કરી શકતો નથી.",
        "will_arrange": "હું ગોઠવી દઈશ.",
        "will_check": "હું તપાસ કરું છું.",
        "will_call_back": "હું તમને પાછો કૉલ કરીશ.",
        "will_inform": "હું તમને જણાવીશ.",
    },
    "pa": {
        "not_configured": "ਮੈਂ ਟੀਮ ਤੋਂ ਪੁਸ਼ਟੀ ਕਰਕੇ ਦੱਸਾਂਗੀ।",
        "checking_with_team": "ਮੈਂ ਟੀਮ ਤੋਂ ਪੁੱਛਦੀ ਹਾਂ।",
        "callback_logged": "ਮੈਂ ਤੁਹਾਡਾ ਕਾਲਬੈਕ ਦਰਜ ਕੀਤਾ ਹੈ।",
        "booking_confirmed": "{time} ਲਈ ਤੁਹਾਡੀ ਅਪਾਇੰਟਮੈਂਟ ਕਨਫਰਮ ਕੀਤੀ ਹੈ।",
        "booking_cancelled": "ਤੁਹਾਡੀ ਅਪਾਇੰਟਮੈਂਟ ਰੱਦ ਕੀਤੀ ਹੈ।",
        "order_received": "ਤੁਹਾਡਾ ਆਰਡਰ ਮਿਲਿਆ।",
        "handoff_requested": "ਇਹ ਟੀਮ ਨੂੰ ਦੱਸਿਆ ਹੈ।",
        "complaint_received": "ਮਾਫ ਕਰਨਾ। ਇਹ ਟੀਮ ਨੂੰ ਭੇਜਿਆ ਹੈ।",
        "emergency_flagged": "ਇਸਨੂੰ ਜ਼ਰੂਰੀ ਨਿਸ਼ਾਨ ਲਗਾਇਆ ਹੈ।",
        "refund_forwarded": "ਤੁਹਾਡੀ ਰਿਫੰਡ ਬੇਨਤੀ ਭੇਜੀ ਹੈ।",
        "ownership_claimed": "ਮੈਂ ਇਸਨੂੰ ਸੰਭਾਲਦੀ ਹਾਂ।",
        "cannot_help": "ਇਸ ਸਮੇਂ ਮੈਂ ਮਦਦ ਨਹੀਂ ਕਰ ਸਕਦੀ।",
        "will_arrange": "ਮੈਂ ਪ੍ਰਬੰਧ ਕਰਦੀ ਹਾਂ।",
        "will_check": "ਮੈਂ ਜਾਂਚ ਕਰਦੀ ਹਾਂ।",
        "will_call_back": "ਮੈਂ ਵਾਪਸ ਕਾਲ ਕਰਦੀ ਹਾਂ।",
        "will_inform": "ਮੈਂ ਦੱਸਦੀ ਹਾਂ।",
    },
    "ur": {
        "not_configured": "میں ٹیم سے تصدیق کر کے بتاؤں گی۔",
        "checking_with_team": "میں ٹیم سے چیک کرتی ہوں۔",
        "callback_logged": "میں نے کال بیک درج کیا ہے۔",
        "booking_confirmed": "{time} پر آپ کی اپائنٹمنٹ کنفرم کی ہے۔",
        "booking_cancelled": "آپ کی اپائنٹمنٹ منسوخ کی ہے۔",
        "order_received": "آپ کا آرڈر موصول ہوا۔",
        "handoff_requested": "یہ ٹیم کو بتا دیا ہے۔",
        "complaint_received": "معذرت۔ یہ ٹیم کو بھیج دیا ہے۔",
        "emergency_flagged": "اسے فوری نشان زد کیا ہے۔",
        "refund_forwarded": "آپ کی رقم واپسی کی درخواست بھیجی ہے۔",
        "ownership_claimed": "میں اسے سنبھال لیتی ہوں۔",
        "cannot_help": "اس وقت میں مدد نہیں کر سکتی۔",
        "will_arrange": "میں انتظام کرتی ہوں۔",
        "will_check": "میں چیک کرتی ہوں۔",
        "will_call_back": "میں واپس کال کرتی ہوں۔",
        "will_inform": "میں بتا دیتی ہوں۔",
    },
}


# ---------------------------------------------------------------------------
# AgentVoice
# ---------------------------------------------------------------------------

class AgentVoice:
    """Resolves a message key to a language- and gender-correct string."""

    def __init__(self, language: Optional[str] = None, gender: Optional[str] = None):
        self.language = language if language in VALID_LANGUAGES else DEFAULT_LANGUAGE
        self.gender = gender if gender in VALID_GENDERS else DEFAULT_GENDER

    def render(self, key: str, **kwargs) -> str:
        """Render a message with the current language and gender.

        Fallback chain:
          1. _GENDERED[language][key][gender]
          2. _GENDERED[language][key]["female"]
          3. _FALLBACK[language][key]
          4. _FALLBACK["en"][key]
          5. key itself (last resort — better than crashing)
        """
        template = None

        # 1 & 2: gendered variant for this language
        lang_bucket = _GENDERED.get(self.language)
        if lang_bucket:
            entry = lang_bucket.get(key)
            if entry:
                template = entry.get(self.gender) or entry.get(DEFAULT_GENDER)

        # 3 & 4: non-gendered fallback
        if template is None:
            lang_fallback = _FALLBACK.get(self.language) or {}
            template = lang_fallback.get(key)

        if template is None:
            template = _FALLBACK["en"].get(key)

        if template is None:
            return key

        try:
            return template.format(**kwargs) if kwargs else template
        except (KeyError, IndexError):
            return template

    # Convenience accessors
    def gender_female(self) -> bool:
        return self.gender == "female"

    def gender_male(self) -> bool:
        return self.gender == "male"