import httpx, json
from sqlalchemy import select
from sqlalchemy.orm import Session
from .config import settings
from .models_integrations import TenantIntegration
from .integrations import decrypt_channel_config

# This module is deliberately NOT imported by ai_router. The router is tokenless.
# It is invoked only after deterministic/library/FAQ resolution fails.

async def _call(provider: str, api_key: str, model: str, prompt: str) -> str:
    provider=provider.lower()
    async with httpx.AsyncClient(timeout=30) as client:
        if provider=="gemini":
            url="https://generativelanguage.googleapis.com/v1beta/models/"+model+":generateContent?key="+api_key
            r=await client.post(url,json={"contents":[{"parts":[{"text":prompt}]}]})
            r.raise_for_status()
            return r.json().get("candidates",[{}])[0].get("content",{}).get("parts",[{}])[0].get("text") or ""
        if provider in ("openai","openrouter"):
            base="https://api.openai.com/v1/chat/completions" if provider=="openai" else "https://openrouter.ai/api/v1/chat/completions"
            r=await client.post(base,headers={"Authorization":"Bearer "+api_key,"Content-Type":"application/json"},json={"model":model,"messages":[{"role":"user","content":prompt}],"temperature":0.2})
            r.raise_for_status()
            return r.json().get("choices",[{}])[0].get("message",{}).get("content") or ""
        if provider=="anthropic":
            r=await client.post("https://api.anthropic.com/v1/messages",headers={"x-api-key":api_key,"anthropic-version":"2023-06-01","content-type":"application/json"},json={"model":model,"max_tokens":700,"messages":[{"role":"user","content":prompt}]})
            r.raise_for_status()
            return r.json().get("content",[{}])[0].get("text") or ""
    raise RuntimeError("Unsupported AI provider")

def _tenant_provider(db: Session, tenant_id: str):
    rows=db.scalars(select(TenantIntegration).where(TenantIntegration.tenant_id==tenant_id,TenantIntegration.integration_key.in_(["gemini","openai","openrouter","anthropic"]),TenantIntegration.status=="connected")).all()
    by={r.integration_key:r for r in rows}
    order=["gemini","openai","openrouter","anthropic"]
    for key in order:
        row=by.get(key)
        if not row or not row.config_encrypted: continue
        try:
            cfg=decrypt_channel_config(row.config_encrypted,settings.whatsapp_credential_encryption_key)
            if cfg.get("api_key"):
                return key,cfg.get("api_key"),cfg.get("model") or getattr(settings,key+"_model", "")
        except Exception:
            continue
    return None

def _platform_providers():
    return [
      ("gemini",settings.gemini_api_key,settings.gemini_model),
      ("openrouter",settings.openrouter_api_key,settings.openrouter_model),
      ("openai",settings.openai_api_key,settings.openai_model),
      ("anthropic",settings.anthropic_api_key,settings.anthropic_model),
    ]

async def last_resort_reply(db: Session, tenant_id: str, prompt: str) -> tuple[str,str]:
    # Tenant-owned provider first; platform pool is only the final fallback.
    tenant=_tenant_provider(db,tenant_id)
    candidates=[tenant] if tenant else []
    candidates += [(p,k,m) for p,k,m in _platform_providers() if k]
    for provider,key,model in candidates:
        try:
            reply=await _call(provider,key,model,prompt)
            if reply.strip():
                return reply.strip(),provider
        except Exception:
            continue
    return "", "none"
