from app.voice_gateway import GEMINI_DEFAULT_MODEL, normalize_gemini_model


def test_gemini_live_default_is_current_native_audio_live_model():
    assert GEMINI_DEFAULT_MODEL == "gemini-3.8-live"
    assert normalize_gemini_model(None) == "gemini-3.8-live"
    assert normalize_gemini_model("  ") == "gemini-3.8-live"


def test_gemini_live_normalizes_legacy_environment_and_tenant_model_ids():
    legacy_ids = [
        "gemini-live-2.5-flash-native-audio",
        "gemini-2.5-flash-native-audio-latest",
        "gemini-2.5-flash-native-audio-preview-12-2025",
        "gemini-2.0-flash-live-001",
    ]
    for model in legacy_ids:
        assert normalize_gemini_model(model) == "gemini-3.8-live"


def test_gemini_live_strips_resource_prefix_but_preserves_current_model():
    assert normalize_gemini_model("models/gemini-3.8-live") == "gemini-3.8-live"
    assert normalize_gemini_model("gemini-3.8-live") == "gemini-3.8-live"
