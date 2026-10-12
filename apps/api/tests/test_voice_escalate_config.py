"""Specialist (Gemini Live) bridge: tuned turn-taking/transcript hints with a safe fallback."""
import asyncio

import pytest
from google.genai import types

from app import voice_escalate as ve


def test_tuned_config_has_fast_turn_detection_and_language_hints():
    cfg, ok = ve._live_config(types, "prompt", tuned=True,
                              language_codes=["en-IN"], vocabulary=["QA real-estate", "Monday"])
    assert ok is True
    vad = cfg.realtime_input_config.automatic_activity_detection
    assert vad.silence_duration_ms == 400 and vad.prefix_padding_ms == 100
    assert vad.end_of_speech_sensitivity == types.EndSensitivity.END_SENSITIVITY_HIGH
    assert cfg.input_audio_transcription.language_codes == ["en-IN"]
    assert "Monday" in cfg.input_audio_transcription.custom_vocabulary
    assert cfg.tools  # the human-handoff tool is still there


def test_baseline_config_is_unchanged_behaviour():
    cfg, ok = ve._live_config(types, "prompt", tuned=False)
    assert ok is True
    assert cfg.realtime_input_config is None
    assert not cfg.input_audio_transcription.language_codes
    assert cfg.tools


def test_vad_is_tunable_from_the_environment(monkeypatch):
    monkeypatch.setenv("SPECIALIST_VAD_SILENCE_MS", "650")
    monkeypatch.setenv("SPECIALIST_VAD_PREFIX_MS", "not-a-number")
    assert ve._vad_settings() == {"silence_duration_ms": 650, "prefix_padding_ms": 100}


def test_transcription_language_hints(monkeypatch):
    monkeypatch.delenv("SPECIALIST_TRANSCRIPTION_LANGUAGES", raising=False)
    assert ve._transcription_language_codes({}) == ["en-IN"]
    assert ve._transcription_language_codes({"voice": {"locale": "te"}}) == ["te-IN", "en-IN"]
    assert ve._transcription_language_codes({"language": {"locale": "hi-IN"}}) == ["hi-IN", "en-IN"]
    assert ve._transcription_language_codes({"voice": {"locale": "en_IN"}}) == ["en-IN"]
    monkeypatch.setenv("SPECIALIST_TRANSCRIPTION_LANGUAGES", "auto")
    assert ve._transcription_language_codes({"voice": {"locale": "te"}}) == []
    monkeypatch.setenv("SPECIALIST_TRANSCRIPTION_LANGUAGES", "en-IN, hi-IN")
    assert ve._transcription_language_codes({}) == ["en-IN", "hi-IN"]


class _FakeLive:
    def __init__(self, refuse_configs):
        self.refuse_configs = refuse_configs
        self.attempts = []
        self.closed = []

    def connect(self, model, config):
        outer = self

        class _Ctx:
            async def __aenter__(self_inner):
                outer.attempts.append(config)
                if config in outer.refuse_configs:
                    raise RuntimeError("1007 invalid argument")
                return f"session-with-{config}"

            async def __aexit__(self_inner, *exc):
                outer.closed.append(config)

        return _Ctx()


class _FakeClient:
    def __init__(self, live):
        self.aio = type("Aio", (), {"live": live})()


def _run(live, tuned, baseline):
    async def go():
        async with ve._connect_live(_FakeClient(live), "m", tuned, baseline) as session:
            return session

    return asyncio.run(go())


def test_tuned_session_is_used_when_the_server_accepts_it():
    live = _FakeLive(refuse_configs=set())
    assert _run(live, "tuned", "baseline") == "session-with-tuned"
    assert live.attempts == ["tuned"] and live.closed == ["tuned"]


def test_server_refusing_tuned_options_falls_back_to_baseline():
    live = _FakeLive(refuse_configs={"tuned"})
    assert _run(live, "tuned", "baseline") == "session-with-baseline"
    assert live.attempts == ["tuned", "baseline"]
    assert live.closed == ["baseline"]


def test_baseline_failure_still_raises_so_the_call_can_escalate_to_a_human():
    live = _FakeLive(refuse_configs={"tuned", "baseline"})
    with pytest.raises(RuntimeError):
        _run(live, "tuned", "baseline")
    assert live.attempts == ["tuned", "baseline"]
