from app.ai_router import detect_language, normalize

def test_language_detection():
    assert detect_language("Hello, how are you?") == "en"
    assert detect_language("నమస్కారం ఎలా ఉన్నారు") == "te"
    assert detect_language("नमस्ते कैसे हैं") == "hi"

def test_unicode_knowledge_tokenization():
    assert "నమస్కారం" in normalize("నమస్కారం ఎలా ఉన్నారు")
    assert "स्वास्थ्य" in normalize("स्वास्थ्य के बारे में बताएं")
