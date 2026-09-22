import httpx, json, math
from datetime import datetime, timedelta
from sqlalchemy import select
from sqlalchemy.orm import Session
from .models_integrations import TenantIntegration, PlatformAIProvider
from .models_growth import AIProviderUsage
from .integrations import decrypt_channel_config
from .config import settings

# Provider failover is deliberately centralized. Business logic never depends on a
# specific AI vendor. Provider health, rate limits and usage are recorded here.
COOLDOWN_MINUTES = 2

def _estimate_tokens(text: str) -> int:
    return max(1, math.ceil(len(text or "") / 4))

def _usage_row(db: Session, tenant_id: str|None, provider: str, model: str) -> AIProviderUsage:
    row=db.scalar(select(AIProviderUsage).where(
        AIProviderUsage.tenant_id==tenant_id,
        AIProviderUsage.provider==provider,
        AIProviderUsage.model==model
    ))
    if not row:
        row=AIProviderUsage(tenant_id=tenant_id,provider=provider,model=model)
        db.add(row); db.flush()
    return row

def _available(row: AIProviderUsage|None) -> bool:
    return not row or not row.cooldown_until or row.cooldown_until <= datetime.utcnow()

def _record(db, tenant_id, provider, model, *, success=False, error="", rate_limited=False, input_tokens=0, output_tokens=0):
    row=_usage_row(db,tenant_id,provider,model)
    row.request_count=(row.request_count or 0)+1
    row.success_count=(row.success_count or 0)+(1 if success else 0)
    row.failure_count=(row.failure_count or 0)+(0 if success else 1)
    row.rate_limit_count=(row.rate_limit_count or 0)+(1 if rate_limited else 0)
    row.estimated_input_tokens=(row.estimated_input_tokens or 0)+input_tokens
    row.estimated_output_tokens=(row.estimated_output_tokens or 0)+output_tokens
    row.last_error=(error or "")[-2000:] or None
    row.last_used_at=datetime.utcnow()
    if rate_limited:
        row.cooldown_until=datetime.utcnow()+timedelta(minutes=COOLDOWN_MINUTES)
    elif success:
        row.cooldown_until=None
    db.commit()

def _tenant_providers(db: Session, tenant_id: str):
    rows=db.scalars(select(TenantIntegration).where(
        TenantIntegration.tenant_id==tenant_id,
        TenantIntegration.integration_key.in_(["gemini","openai","openrouter","anthropic"]),
        TenantIntegration.status=="connected"
    )).all()
    by={r.integration_key:r for r in rows}
    result=[]
    # Tenant ordering can later be made configurable; these are safe defaults.
    for key in ["gemini","openai","openrouter","anthropic"]:
        row=by.get(key)
        if not row or not row.config_encrypted: continue
        try:
            cfg=decrypt_channel_config(row.config_encrypted,(settings.integration_credential_encryption_key or settings.whatsapp_credential_encryption_key))
            if cfg.get("api_key"):
                result.append((key,cfg.get("api_key"),cfg.get("model") or getattr(settings,key+"_model", ""),"tenant"))
        except Exception:
            continue
    return result

def _platform_providers(db: Session):
    rows=db.scalars(select(PlatformAIProvider).where(
        PlatformAIProvider.enabled==True,
        PlatformAIProvider.status.in_(["healthy","cooldown"])
    ).order_by(PlatformAIProvider.priority, PlatformAIProvider.created_at)).all()
    result=[]
    for row in rows:
        try:
            cfg=decrypt_channel_config(row.config_encrypted,(settings.integration_credential_encryption_key or settings.whatsapp_credential_encryption_key))
            if cfg.get("api_key"):
                result.append((row.provider,cfg["api_key"],row.model,"platform"))
        except Exception:
            continue
    # Environment keys remain a break-glass fallback and are never exposed to clients.
    result += [
        ("gemini",settings.gemini_api_key,settings.gemini_model,"env"),
        ("openrouter",settings.openrouter_api_key,settings.openrouter_model,"env"),
        ("openai",settings.openai_api_key,settings.openai_model,"env"),
        ("anthropic",settings.anthropic_api_key,settings.anthropic_model,"env"),
    ]
    return [x for x in result if x[1] and x[2]]

async def _call(provider: str, api_key: str, model: str, prompt: str) -> str:
    provider=provider.lower()
    async with httpx.AsyncClient(timeout=30) as client:
        if provider=="gemini":
            url="https://generativelanguage.googleapis.com/v1beta/models/"+model+":generateContent?key="+api_key
            r=await client.post(url,json={"contents":[{"parts":[{"text":prompt}]}]})
        elif provider=="openai":
            r=await client.post("https://api.openai.com/v1/responses",headers={"Authorization":"Bearer "+api_key,"Content-Type":"application/json"},json={"model":model,"input":prompt})
        elif provider=="openrouter":
            r=await client.post("https://openrouter.ai/api/v1/chat/completions",headers={"Authorization":"Bearer "+api_key,"Content-Type":"application/json"},json={"model":model,"messages":[{"role":"user","content":prompt}],"temperature":0.2})
        elif provider=="anthropic":
            r=await client.post("https://api.anthropic.com/v1/messages",headers={"x-api-key":api_key,"anthropic-version":"2023-06-01","content-type":"application/json"},json={"model":model,"max_tokens":700,"messages":[{"role":"user","content":prompt}]})
        else:
            raise RuntimeError("Unsupported AI provider")
        if r.status_code >= 400:
            body=r.text[:1000]
            err=RuntimeError(f"{provider} HTTP {r.status_code}: {body}")
            setattr(err,"status_code",r.status_code)
            raise err
        data=r.json()
        if provider=="openai": return data.get("output_text") or ""
        if provider=="openrouter": return data.get("choices",[{}])[0].get("message",{}).get("content") or ""
        if provider=="anthropic": return data.get("content",[{}])[0].get("text") or ""
        return data.get("candidates",[{}])[0].get("content",{}).get("parts",[{}])[0].get("text") or ""

async def last_resort_reply(db: Session, tenant_id: str, prompt: str) -> tuple[str,str]:
    # Build a fresh provider pool on every miss so an exhausted provider is skipped
    # immediately. A rate-limit/quota failure is cooled down automatically.
    candidates=_tenant_providers(db,tenant_id)+_platform_providers(db)
    seen=set()
    input_tokens=_estimate_tokens(prompt)
    for provider,key,model,owner in candidates:
        identity=(provider,model,key[-12:])
        if identity in seen: continue
        seen.add(identity)
        usage=db.scalar(select(AIProviderUsage).where(
            AIProviderUsage.tenant_id==tenant_id,
            AIProviderUsage.provider==provider,
            AIProviderUsage.model==model
        ))
        if not _available(usage):
            continue
        try:
            reply=await _call(provider,key,model,prompt)
            if not reply.strip():
                raise RuntimeError("Provider returned an empty response")
            _record(db,tenant_id,provider,model,success=True,input_tokens=input_tokens,output_tokens=_estimate_tokens(reply))
            return reply.strip(),provider
        except Exception as exc:
            code=getattr(exc,"status_code",0)
            rate_limited=code in (402,403,408,409,425,429,500,502,503,504)
            _record(db,tenant_id,provider,model,error=str(exc),rate_limited=rate_limited,input_tokens=input_tokens)
            continue
    return "", "none"
