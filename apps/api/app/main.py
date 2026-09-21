from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI(title="AI Growth OS API", version="0.1.0")

class Health(BaseModel):
    status: str
    service: str

@app.get("/health", response_model=Health)
def health():
    return {"status": "ok", "service": "ai-growth-os-api"}

@app.get("/api/v1/tenants")
def list_tenants():
    return {"items": [], "phase": 1}

@app.post("/api/v1/ai/chat")
def chat(payload: dict):
    message = str(payload.get("message", "")).strip()
    return {"reply": "AI provider adapter is not configured yet. Message received safely.", "message": message, "intent": "unknown", "lead": False}
