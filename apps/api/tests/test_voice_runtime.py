from app.voice_runtime import VoiceTurn, VoiceTurnController

def test_barge_in_is_debounced():
    c=VoiceTurnController(); c.begin(1.0); c.output(2.0)
    assert c.state is VoiceTurn.SPEAKING
    assert c.interrupt(3.0) is True
    assert c.interrupt(3.1) is False
    assert c.interruption_count==1

def test_voice_to_first_audio_latency():
    c=VoiceTurnController(); c.begin(1.0); c.input_final(1.5); c.output(1.9)
    trace=c.complete(2.0)
    assert trace is not None
    assert trace.voice_to_first_audio_ms==400


def test_voice_latency_rounds_to_nearest_millisecond():
    c=VoiceTurnController(); c.begin(1.0); c.input_final(1.5); c.output(1.9006)
    trace=c.complete(2.0)
    assert trace is not None
    assert trace.voice_to_first_audio_ms==401
