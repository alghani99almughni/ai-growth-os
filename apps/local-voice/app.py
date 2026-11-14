"""Local inference sidecar. No external inference API is called.

The core AI Growth OS API remains the source of truth for tenant data, booking,
CRM and permissions. This service only performs local STT, retrieval, LLM and TTS.
"""
from __future__ import annotations

import asyncio
import io
import json
import os
import hmac
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import httpx
import numpy as np
import soundfile as sf
from fastapi import Depends, FastAPI, File, Header, HTTPException, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, Field
from scipy.signal import resample_poly

KB_PATH = Path(os.getenv("KNOWLEDGE_BASE_PATH", "/app/knowledge_base.json"))
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/")
LLM_MODEL = os.getenv("LLM_MODEL", "qwen2.5:7b-instruct-q4_K_M")
ACTIVE_VERTICAL = os.getenv("ACTIVE_VERTICAL", "general")
COMPANY_NAME = os.getenv("COMPANY_NAME", "Local Business")
WHISPER_MODEL = os.getenv("WHISPER_MODEL", "small")
WHISPER_DEVICE = os.getenv("WHISPER_DEVICE", "cuda")
WHISPER_COMPUTE_TYPE = os.getenv("WHISPER_COMPUTE_TYPE", "float16")
KOKORO_MODEL_PATH = os.getenv("KOKORO_MODEL_PATH", "/models/kokoro-v1.0.onnx")
KOKORO_VOICES_PATH = os.getenv("KOKORO_VOICES_PATH", "/models/voices-v1.0.bin")
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2")
LOCAL_VOICE_API_KEY = os.getenv("LOCAL_VOICE_API_KEY", "")

runtime: dict[str, Any] = {"kb": {}, "faqs": [], "embedder": None, "embeddings": None,
                           "whisper": None, "kokoro": None}


def _load_knowledge() -> None:
    if not KB_PATH.is_file():
        raise RuntimeError(f"Knowledge base file not found: {KB_PATH}")
    kb = json.loads(KB_PATH.read_text(encoding="utf-8"))
    vertical = kb.get("industries", {}).get(ACTIVE_VERTICAL, {})
    faqs = list(kb.get("global_reception_faqs", [])) + list(vertical.get("faqs", []))
    runtime["kb"] = kb
    runtime["faqs"] = faqs


def _retrieve(query: str, top_k: int = 3) -> list[dict[str, Any]]:
    faqs = runtime["faqs"]
    embedder = runtime["embedder"]
    embeddings = runtime["embeddings"]
    if not faqs or embedder is None or embeddings is None:
        return []
    query_vector = embedder.encode([query], normalize_embeddings=True)
    scores = np.asarray(query_vector) @ np.asarray(embeddings).T
    indexes = np.argsort(scores[0])[::-1][:top_k]
    return [faqs[int(i)] for i in indexes if float(scores[0][i]) >= 0.28]


@asynccontextmanager
async def lifespan(_: FastAPI):
    _load_knowledge()
    from sentence_transformers import SentenceTransformer
    from faster_whisper import WhisperModel
    from kokoro_onnx import Kokoro

    embedder = SentenceTransformer(EMBEDDING_MODEL)
    texts = [" ".join(item.get("questions", [])) + " " + item.get("answer", "")
             for item in runtime["faqs"]]
    runtime["embedder"] = embedder
    runtime["embeddings"] = embedder.encode(texts, normalize_embeddings=True) if texts else np.empty((0, 0))
    runtime["whisper"] = WhisperModel(WHISPER_MODEL, device=WHISPER_DEVICE,
                                      compute_type=WHISPER_COMPUTE_TYPE)
    runtime["kokoro"] = Kokoro(KOKORO_MODEL_PATH, KOKORO_VOICES_PATH)
    yield
    runtime.clear()


app = FastAPI(title="AI Growth OS Local Voice Engine", version="0.1.0", lifespan=lifespan)


def _authorize(x_local_voice_key: str | None = Header(default=None)) -> None:
    if not LOCAL_VOICE_API_KEY or not x_local_voice_key or not hmac.compare_digest(
        LOCAL_VOICE_API_KEY, x_local_voice_key
    ):
        raise HTTPException(401, "Invalid local voice service credential")


def _run_transcription(samples: np.ndarray):
    segments, info = runtime["whisper"].transcribe(
        samples, language=None, vad_filter=True, beam_size=3,
        condition_on_previous_text=False,
    )
    return (" ".join(segment.text.strip() for segment in segments).strip(),
            info.language, info.language_probability)


class TurnRequest(BaseModel):
    text: str = Field(min_length=1, max_length=8000)
    history: list[dict[str, str]] = Field(default_factory=list, max_length=24)
    company_name: str | None = Field(default=None, max_length=160)
    industry_name: str | None = Field(default=None, max_length=160)
    approved_context: str = Field(default="", max_length=30000)


@app.get("/health")
async def health():
    return {"status": "ok", "engine": "local", "llm_model": LLM_MODEL,
            "stt_loaded": runtime.get("whisper") is not None,
            "tts_loaded": runtime.get("kokoro") is not None}


@app.post("/v1/turn")
async def turn(payload: TurnRequest, _: None = Depends(_authorize)):
    if runtime.get("embedder") is None:
        raise HTTPException(503, "Local models are still loading")
    matches = _retrieve(payload.text)
    facts = "\n".join(
        f"- {item.get('questions', [''])[0]}: {item.get('answer', '')}" for item in matches
    )
    vertical = payload.industry_name or runtime["kb"].get("industries", {}).get(
        ACTIVE_VERTICAL, {}).get("industry_name", "General")
    company = payload.company_name or COMPANY_NAME
    system = (
        f"You are the phone receptionist for {company} ({vertical}). "
        "Reply in concise, natural spoken language. Match the caller's language, including "
        "Romanized Hindi/Hinglish where appropriate. Ask one question at a time. "
        "Never invent tenant-specific prices, hours, addresses, staff, availability, medical "
        "advice, bookings, payment status, project returns or visa eligibility. "
        "Use the approved tenant context and relevant knowledge below. If a fact is missing, "
        "say you cannot verify it and offer a callback or human assistance. "
        "Generic industry FAQs are guidance, not proof of this tenant's actual policies.\n\n"
        f"APPROVED TENANT CONTEXT:\n{payload.approved_context or '(none supplied)'}\n\n"
        f"RETRIEVED INDUSTRY KNOWLEDGE:\n{facts or '(no matching approved FAQ)'}"
    )
    messages = [{"role": "system", "content": system}]
    for item in payload.history[-12:]:
        if item.get("role") in {"user", "assistant"} and item.get("content"):
            messages.append({"role": item["role"], "content": item["content"][:4000]})
    messages.append({"role": "user", "content": payload.text})
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(45.0, connect=3.0)) as client:
            response = await client.post(
                f"{OLLAMA_BASE_URL}/api/chat",
                json={"model": LLM_MODEL, "messages": messages, "stream": False,
                      "options": {"temperature": 0.2, "num_ctx": 8192}},
            )
            response.raise_for_status()
            answer = response.json().get("message", {}).get("content", "").strip()
    except (httpx.HTTPError, ValueError) as exc:
        raise HTTPException(503, f"Local LLM unavailable: {type(exc).__name__}") from exc
    if not answer:
        raise HTTPException(502, "Local LLM returned an empty response")
    return {"text": answer, "knowledge_ids": [item.get("id") for item in matches],
            "model": LLM_MODEL, "provider": "local"}


@app.post("/v1/transcribe")
async def transcribe(audio: UploadFile = File(...), _: None = Depends(_authorize)):
    if runtime.get("whisper") is None:
        raise HTTPException(503, "Local speech model is still loading")
    raw = await audio.read()
    if not raw or len(raw) > 25 * 1024 * 1024:
        raise HTTPException(400, "Audio is empty or exceeds 25 MB")
    try:
        samples, sample_rate = sf.read(io.BytesIO(raw), dtype="float32", always_2d=False)
        if samples.ndim == 2:
            samples = samples.mean(axis=1)
        if sample_rate != 16000:
            from math import gcd
            factor = gcd(int(sample_rate), 16000)
            samples = resample_poly(samples, 16000 // factor, int(sample_rate) // factor)
        text, language, language_probability = await asyncio.to_thread(_run_transcription, samples)
        return {"text": text, "language": language,
                "language_probability": language_probability, "provider": "local"}
    except Exception as exc:
        raise HTTPException(422, f"Audio transcription failed: {type(exc).__name__}") from exc


@app.post("/v1/synthesize")
async def synthesize(payload: dict[str, Any], _: None = Depends(_authorize)):
    if runtime.get("kokoro") is None:
        raise HTTPException(503, "Local speech synthesis model is still loading")
    text = str(payload.get("text") or "").strip()
    if not text or len(text) > 4000:
        raise HTTPException(400, "Text must contain 1–4000 characters")
    voice = str(payload.get("voice") or "af_bella")
    language = str(payload.get("language") or "en-us")
    try:
        samples, sample_rate = await asyncio.to_thread(
            runtime["kokoro"].create, text, voice=voice, speed=1.0, lang=language
        )
        output = io.BytesIO()
        sf.write(output, np.asarray(samples, dtype=np.float32), sample_rate, format="WAV")
        return Response(output.getvalue(), media_type="audio/wav")
    except Exception as exc:
        raise HTTPException(422, f"Speech synthesis failed: {type(exc).__name__}") from exc
