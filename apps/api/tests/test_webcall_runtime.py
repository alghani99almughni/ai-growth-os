from app.webcall_runtime import PcmAudioTrack


def test_pcm_framer_preserves_partial_chunks():
    framer = PcmAudioTrack(sample_rate=24000, frame_ms=20)
    frame_bytes = 24000 // 50 * 2
    assert framer.feed(b"a" * (frame_bytes - 10)) == []
    out = framer.feed(b"b" * 20)
    assert len(out) == 1
    assert len(out[0]) == frame_bytes
    assert out[0][-10:] == b"b" * 10


def test_pcm_framer_emits_multiple_frames():
    framer = PcmAudioTrack(sample_rate=24000, frame_ms=20)
    frame_bytes = 24000 // 50 * 2
    out = framer.feed(b"x" * (frame_bytes * 2 + 7))
    assert len(out) == 2
    assert all(len(x) == frame_bytes for x in out)
    assert len(framer.buffer) == 7


from app.language_policy import language_persona_policy, language_policy_prompt


def test_hindi_female_persona_is_explicit_and_customer_gender_can_be_unknown():
    policy = language_persona_policy(language="hi-IN", agent_gender="female")
    prompt = language_policy_prompt(policy)
    assert policy["locale"] == "hi-IN"
    assert policy["agent_gender"] == "female"
    assert policy["customer_gender"] == "unknown"
    assert "feminine first-person forms" in prompt
    assert "Do not infer customer gender from a name" in prompt


def test_unknown_language_falls_back_to_indian_english():
    policy = language_persona_policy(language="xx-XX", agent_gender="bad-value")
    assert policy["locale"] == "en-IN"
    assert policy["agent_gender"] == "neutral"
