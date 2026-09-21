from app.ai_router import detect_language

def test_language_detection():
    assert detect_language("Hello, how are you?") == "en"
    assert detect_language("నమస్కారం ఎలా ఉన్నారు") == "te"
    assert detect_language("नमस्ते कैसे हैं") == "hi"

def test_supported_faq_seed():
    from app.faq_seed import FAQS
    assert len(FAQS) >= 20
    assert any(row[0] == "dental" for row in FAQS)
    assert any(row[0] == "hotel" for row in FAQS)
