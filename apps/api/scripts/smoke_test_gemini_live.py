"""Safe smoke test for the configured Gemini Live API key/model.

Run from apps/api with the same environment as the API:
    python scripts/smoke_test_gemini_live.py

The script never prints the API key. It checks setup acknowledgement and whether
Gemini returns at least one audio chunk after a short text prompt.
"""
from __future__ import annotations

import asyncio
import json
import sys

import websockets

from app.config import settings
from app.voice_gateway import normalize_gemini_model


async def main() -> int:
    api_key = settings.gemini_api_key.strip()
    if not api_key:
        print("FAIL: GEMINI_API_KEY is not loaded. Check apps/api/.env (do not paste the key).")
        return 2

    model = normalize_gemini_model(settings.gemini_live_model)
    url = (
        "wss://generativelanguage.googleapis.com/ws/"
        "google.ai.generativelanguage.v1alpha.GenerativeService.BidiGenerateContent"
        f"?key={api_key}"
    )
    setup = {
        "setup": {
            "model": "models/" + model,
            "generationConfig": {
                "responseModalities": ["AUDIO"],
                "speechConfig": {
                    "voiceConfig": {
                        "prebuiltVoiceConfig": {"voiceName": "Puck"}
                    }
                },
            },
            "systemInstruction": {
                "parts": [{"text": "You are a concise voice assistant. Reply in one short sentence."}]
            },
            "inputAudioTranscription": {},
            "outputAudioTranscription": {},
        }
    }

    try:
        async with websockets.connect(
            url, max_size=8 * 1024 * 1024, open_timeout=10, close_timeout=3
        ) as ws:
            await ws.send(json.dumps(setup))
            raw = await asyncio.wait_for(ws.recv(), timeout=15)
            if isinstance(raw, bytes):
                raw = raw.decode()
            message = json.loads(raw)
            if "setupComplete" not in message:
                detail = message.get("error") or message
                print(f"FAIL: Gemini did not acknowledge setup for {model}: {str(detail)[:400]}")
                return 3

            print(f"PASS: Gemini Live setup acknowledged (model={model}).")
            await ws.send(json.dumps({
                "clientContent": {
                    "turns": [{"role": "user", "parts": [{"text": "Say: Gemini voice test successful."}]}],
                    "turnComplete": True,
                }
            }))
            deadline = asyncio.get_running_loop().time() + 25
            while asyncio.get_running_loop().time() < deadline:
                raw = await asyncio.wait_for(ws.recv(), timeout=max(
                    0.1, deadline - asyncio.get_running_loop().time()
                ))
                if isinstance(raw, bytes):
                    raw = raw.decode()
                event = json.loads(raw)
                if "error" in event:
                    print(f"FAIL: Gemini returned an error: {str(event['error'])[:400]}")
                    return 4
                server = event.get("serverContent") or {}
                transcript = (server.get("outputTranscription") or {}).get("text")
                if transcript:
                    print("Gemini transcript:", str(transcript)[:240])
                parts = ((server.get("modelTurn") or {}).get("parts") or [])
                if any((part.get("inlineData") or {}).get("data") for part in parts):
                    print("PASS: Gemini returned audio. API key, model, Live API setup, and audio generation are responding.")
                    return 0

            print("FAIL: Setup worked, but no audio chunk arrived within 25 seconds.")
            return 5
    except asyncio.TimeoutError:
        print("FAIL: Gemini Live timed out during setup or audio generation.")
        return 6
    except Exception as exc:
        # Do not print the URL or the API key if a library exception includes them.
        message = str(exc).replace(api_key, "[REDACTED]")
        print(f"FAIL: Gemini Live connection: {message[:500]}")
        return 7


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
