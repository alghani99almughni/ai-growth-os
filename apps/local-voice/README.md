# AI Growth OS — Local Voice Engine (isolated sidecar)

This package is an additive, self-hosted inference sidecar. It does not replace the AI Growth OS API, CRM, Knowledge Brain, tenant data, booking actions, call recorder or existing WebRTC/PSTN runtimes.

## Included

- Ollama + Qwen 2.5 for local text generation
- Faster-Whisper for local speech recognition
- Kokoro ONNX for local speech synthesis
- Local sentence-transformers retrieval over the supplied industry FAQ JSON
- Separate HTTP endpoints for chat turns, transcription and synthesis

No external inference API credentials are used by this sidecar. Initial image/model/weight downloads still require network access unless you preload and mirror all model artifacts. After provisioning, the inference path can run offline.

## Important integration boundary

The service is not yet wired into production WebRTC or the Twilio Media Streams route. The core API must supply tenant identity and approved tenant context; it remains authoritative for CRM, booking, pricing, availability, payments, permissions, notifications and recording. Do not expose this sidecar directly to the public internet. Put it on a private network and authenticate core-API requests before production integration.

The pasted Pipecat sample is not copied verbatim: it constructs SmallWebRTCTransport without a SmallWebRTCConnection, calls handle_offer on that transport, and passes generic TextFrame/AudioRawFrame objects through a pipeline that does not correctly implement Pipecat's current STT/LLM/TTS context contracts. Current Pipecat examples create a SmallWebRTCConnection, construct SmallWebRTCTransport(webrtc_connection=..., params=...), use context aggregators, and run a worker. See the official Small WebRTC example:
https://github.com/pipecat-ai/pipecat/blob/main/examples/transports/transports-small-webrtc.py

## Provision models

1. Copy .env.example to .env and replace the placeholder with a long random LOCAL_VOICE_API_KEY value. The inference routes require this key in the X-Local-Voice-Key header. Keep .env private and never commit it.
2. Download the Kokoro ONNX model and voice file into apps/local-voice/models/.
3. Start the stack from this directory with docker compose up -d --build.
4. Pull Qwen once: docker exec -it ai_voice_ollama ollama pull qwen2.5:7b-instruct-q4_K_M.
5. The first startup downloads the Faster-Whisper and sentence-transformers model weights if they are not already cached. For a fully offline deployment, prepopulate model caches and mount them read-only.
6. Check http://localhost:7860/health.

The compose default runs Faster-Whisper on CPU (int8) because the Python image does not bundle the CUDA/cuDNN runtime required by CTranslate2. Ollama is configured for NVIDIA GPU acceleration. Enable Whisper GPU only after building an image with the matching CUDA 12 and cuDNN 9 runtime libraries and validating it on the target host.

## HTTP API

- GET /health
- POST /v1/turn — JSON with text, optional history, company_name, industry_name, and approved_context; requires X-Local-Voice-Key
- POST /v1/transcribe — multipart upload containing a WAV audio file; requires X-Local-Voice-Key
- POST /v1/synthesize — JSON with text, optional voice and Kokoro language code; returns WAV; requires X-Local-Voice-Key

Example chat request:

    {
      "text": "Ghar se sample collection hota hai kya?",
      "company_name": "Example Diagnostics",
      "industry_name": "Diagnostic Center & Pathology Lab",
      "approved_context": "Home collection is available only in approved service areas."
    }

## Safety and accuracy notes

- Generic industry FAQs are prompts/retrieval hints, never evidence of the tenant's real hours, prices, slots, medical advice or policies.
- The diagnostic FAQ starter deliberately avoids the unverified fasting and report-turnaround claims in the sample transcript.
- Dubai property claims such as rental yield, appreciation, financing, Golden Visa eligibility, taxes and project amenities must be confirmed against current approved tenant documents. They must not be repeated as universal facts.
- The local model can still hallucinate. It must not be allowed to execute CRM or booking actions directly. Actions remain behind authenticated core-API tools and explicit confirmation.
- The supplied all-MiniLM-L6-v2 embedding model is primarily English-oriented; Hinglish and Indian-language recall must be measured before launch. Add multilingual embeddings or translated query expansion only after benchmark tests.
- A rolling 12-message window controls prompt growth; it does not prove constant latency. Latency depends on model, GPU, context size, concurrent calls and audio chunking.

## Current status

Prototype sidecar only. No production call routing, SIP integration, tenant authentication, audio recording, notification delivery or real-time Pipecat transport is included yet. The sidecar must pass language, retrieval, latency, concurrency and audio-quality benchmarks before it is enabled for live customers.
