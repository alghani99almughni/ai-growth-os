from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session
import json, asyncio
from datetime import datetime

from .db import SessionLocal
from .models import Tenant
from .models_integrations import TenantIntegration, PlatformAIProvider
from .integrations import encrypt_channel_config, decrypt_channel_config
from .config import settings

router = APIRouter(prefix="/api/v1", tags=["integrations"])

CATALOG = [
    {"key":"whatsapp","name":"WhatsApp","category":"Communication","mode":"provider","providers":[{"id":"openwa","name":"Built-in WhatsApp","type":"built_in"},{"id":"meta","name":"Meta WhatsApp Cloud API","type":"credentials"}]},
    {"key":"razorpay","name":"Razorpay","category":"Payments","mode":"provider","providers":[{"id":"platform","name":"Platform Razorpay","type":"platform"},{"id":"razorpay","name":"My Razorpay Account","type":"credentials"}]},
    {"key":"gemini","name":"Gemini","category":"AI","mode":"provider","providers":[{"id":"platform","name":"Platform Gemini","type":"platform"},{"id":"gemini","name":"My Gemini API Key","type":"credentials"}]},
    {"key":"openai","name":"OpenAI / ChatGPT","category":"AI","mode":"provider","providers":[{"id":"platform","name":"Platform OpenAI","type":"platform"},{"id":"openai","name":"My OpenAI API Key","type":"credentials"}]},
    {"key":"openrouter","name":"OpenRouter","category":"AI","mode":"provider","providers":[{"id":"platform","name":"Platform OpenRouter","type":"platform"},{"id":"openrouter","name":"My OpenRouter API Key","type":"credentials"}]},
    {"key":"anthropic","name":"Claude","category":"AI","mode":"provider","providers":[{"id":"platform","name":"Platform Claude","type":"platform"},{"id":"anthropic","name":"My Anthropic API Key","type":"credentials"}]},
    {"key":"meta_business","name":"Meta Business","category":"Social & Marketing","mode":"oauth","providers":[{"id":"meta","name":"Connect Meta Business","type":"oauth"}]},
    {"key":"facebook","name":"Facebook","category":"Social & Marketing","mode":"oauth","providers":[{"id":"meta","name":"Connect Facebook","type":"oauth"}]},
    {"key":"instagram","name":"Instagram","category":"Social & Marketing","mode":"oauth","providers":[{"id":"meta","name":"Connect Instagram","type":"oauth"}]},
    {"key":"meta_ads","name":"Meta Ads","category":"Social & Marketing","mode":"oauth","providers":[{"id":"meta","name":"Connect Meta Ads","type":"oauth"}]},
    {"key":"youtube","name":"YouTube","category":"Social & Marketing","mode":"oauth","providers":[{"id":"google","name":"Connect YouTube","type":"oauth"}]},
    {"key":"google_business","name":"Google Business Profile","category":"Social & Marketing","mode":"oauth","providers":[{"id":"google","name":"Connect Google Business","type":"oauth"}]},
    {"key":"email","name":"Email / SMTP","category":"Communication","mode":"provider","providers":[{"id":"platform","name":"Platform Email","type":"platform"},{"id":"smtp","name":"My SMTP","type":"credentials"}]},
    {"key":"voice","name":"Voice & Calling","category":"Voice","mode":"provider","providers":[{"id":"platform","name":"Platform Voice","type":"platform"},{"id":"custom","name":"My Telephony Provider","type":"credentials"}]},
]

SECRET_FIELDS={
 "razorpay":["key_id","key_secret","webhook_secret"],
 "gemini":["api_key"],
 "openai":["api_key"],
 "openrouter":["api_key"],
 "anthropic":["api_key"],
 "meta_business":["access_token"],
 "facebook":["access_token"],
 "instagram":["access_token"],
 "meta_ads":["access_token"],
 "youtube":["client_secret","refresh_token"],
 "google_business":["access_token"],
 "email":["password"],
 "voice":["api_key","auth_token","webhook_secret"],
}

class IntegrationPayload(BaseModel):
    provider: str
    mode: str = "tenant"
    config: dict = Field(default_factory=dict)
    account_name: str | None = None
    account_id: str | None = None
    metadata: dict = Field(default_factory=dict)

def get_db():
    db=SessionLocal()
    try: yield db
    finally: db.close()

def _user(credentials, db):
    from .main import get_current_user
    return get_current_user(credentials=credentials, db=db)

def _require(user, tenant_id):
    if user.tenant_id != tenant_id:
        raise HTTPException(403,"Tenant access denied")

def _catalog_item(key):
    return next((x for x in CATALOG if x["key"]==key),None)

def _safe_config(key, config):
    return {k: ("configured" if k in SECRET_FIELDS.get(key,[]) and v else v) for k,v in config.items()}

def _out(row):
    cfg={}
    if row.config_encrypted:
        try: cfg=decrypt_channel_config(row.config_encrypted, settings.whatsapp_credential_encryption_key)
        except Exception: pass
    return {
      "key":row.integration_key,"provider":row.provider,"mode":row.mode,"status":row.status,
      "account_name":row.account_name,"account_id":row.account_id,
      "config":_safe_config(row.integration_key,cfg),
      "metadata":json.loads(row.metadata_json or "{}"),
    }

@router.get("/tenants/{tenant_id}/integrations/catalog")
def integration_catalog(tenant_id: str, credentials=Depends(__import__("fastapi").security.HTTPBearer(auto_error=False)), db: Session=Depends(get_db)):
    user=_user(credentials,db); _require(user,tenant_id)
    return {"items":CATALOG}

@router.get("/tenants/{tenant_id}/integrations")
def integrations(tenant_id: str, credentials=Depends(__import__("fastapi").security.HTTPBearer(auto_error=False)), db: Session=Depends(get_db)):
    user=_user(credentials,db); _require(user,tenant_id)
    rows=db.scalars(select(TenantIntegration).where(TenantIntegration.tenant_id==tenant_id)).all()
    return {"items":[_out(x) for x in rows]}

@router.get("/tenants/{tenant_id}/integrations/{key}")
def integration_status(tenant_id: str, key: str, credentials=Depends(__import__("fastapi").security.HTTPBearer(auto_error=False)), db: Session=Depends(get_db)):
    user=_user(credentials,db); _require(user,tenant_id)
    row=db.scalar(select(TenantIntegration).where(TenantIntegration.tenant_id==tenant_id,TenantIntegration.integration_key==key))
    if not row: return {"key":key,"status":"disconnected","provider":"platform","mode":"platform","configured":False,"config":{}}
    out=_out(row); out["configured"]=bool(row.config_encrypted) or row.mode in ("platform","oauth"); return out

@router.put("/tenants/{tenant_id}/integrations/{key}")
def save_integration(tenant_id: str, key: str, payload: IntegrationPayload, credentials=Depends(__import__("fastapi").security.HTTPBearer(auto_error=False)), db: Session=Depends(get_db)):
    user=_user(credentials,db); _require(user,tenant_id)
    item=_catalog_item(key)
    if not item: raise HTTPException(404,"Integration not found")
    if payload.provider not in {p["id"] for p in item["providers"]}: raise HTTPException(400,"Unsupported provider")
    config=dict(payload.config)
    for field in SECRET_FIELDS.get(key,[]):
        if field in config and not config[field]:
            config.pop(field,None)
    existing=db.scalar(select(TenantIntegration).where(TenantIntegration.tenant_id==tenant_id,TenantIntegration.integration_key==key))
    if existing and any(k in SECRET_FIELDS.get(key,[]) and v for k,v in config.items()):
        try:
            old=decrypt_channel_config(existing.config_encrypted,settings.whatsapp_credential_encryption_key) if existing.config_encrypted else {}
            for k in SECRET_FIELDS.get(key,[]):
                if k not in config and old.get(k): config[k]=old[k]
        except Exception: pass
    encrypted=encrypt_channel_config(config,settings.whatsapp_credential_encryption_key) if config else ""
    if not existing:
        existing=TenantIntegration(tenant_id=tenant_id,integration_key=key,provider=payload.provider,mode=payload.mode)
        db.add(existing)
    existing.provider=payload.provider; existing.mode=payload.mode; existing.status="connected" if (config or payload.mode in ("platform","oauth")) else "disconnected"
    existing.config_encrypted=encrypted
    existing.account_name=payload.account_name; existing.account_id=payload.account_id
    existing.metadata_json=json.dumps(payload.metadata or {})
    existing.updated_at=datetime.utcnow()
    db.commit(); db.refresh(existing)
    return _out(existing)

@router.delete("/tenants/{tenant_id}/integrations/{key}")
def disconnect_integration(tenant_id: str, key: str, credentials=Depends(__import__("fastapi").security.HTTPBearer(auto_error=False)), db: Session=Depends(get_db)):
    user=_user(credentials,db); _require(user,tenant_id)
    row=db.scalar(select(TenantIntegration).where(TenantIntegration.tenant_id==tenant_id,TenantIntegration.integration_key==key))
    if row:
        row.status="disconnected"; row.config_encrypted=""; row.account_name=None; row.account_id=None; db.commit()
    return {"key":key,"status":"disconnected"}

@router.get("/platform/ai/providers")
def platform_ai_providers(credentials=Depends(__import__("fastapi").security.HTTPBearer(auto_error=False)), db: Session=Depends(get_db)):
    user=_user(credentials,db)
    if user.role not in ("super_admin","platform_admin"): raise HTTPException(403,"Platform admin required")
    rows=db.scalars(select(PlatformAIProvider).order_by(PlatformAIProvider.priority)).all()
    return {"items":[{"id":x.id,"provider":x.provider,"model":x.model,"priority":x.priority,"enabled":x.enabled,"status":x.status,"last_error":x.last_error,"last_used_at":x.last_used_at.isoformat() if x.last_used_at else None} for x in rows]}

@router.put("/platform/ai/providers/{provider_id}")
def update_platform_ai_provider(provider_id: str, payload: dict, credentials=Depends(__import__("fastapi").security.HTTPBearer(auto_error=False)), db: Session=Depends(get_db)):
    user=_user(credentials,db)
    if user.role not in ("super_admin","platform_admin"): raise HTTPException(403,"Platform admin required")
    row=db.get(PlatformAIProvider,provider_id)
    if not row: raise HTTPException(404,"AI provider not found")
    if "api_key" in payload and payload["api_key"]:
        row.config_encrypted=encrypt_channel_config({"api_key":payload["api_key"]},settings.whatsapp_credential_encryption_key)
    for k in ("model","priority","enabled"):
        if k in payload: setattr(row,k,payload[k])
    db.commit(); return {"id":row.id,"provider":row.provider,"model":row.model,"priority":row.priority,"enabled":row.enabled}

@router.post("/platform/ai/providers")
def create_platform_ai_provider(payload: dict, credentials=Depends(__import__("fastapi").security.HTTPBearer(auto_error=False)), db: Session=Depends(get_db)):
    user=_user(credentials,db)
    if user.role not in ("super_admin","platform_admin"): raise HTTPException(403,"Platform admin required")
    row=PlatformAIProvider(provider=payload.get("provider","gemini"),model=payload.get("model",""),priority=int(payload.get("priority",100)),enabled=bool(payload.get("enabled",True)))
    if payload.get("api_key"): row.config_encrypted=encrypt_channel_config({"api_key":payload["api_key"]},settings.whatsapp_credential_encryption_key)
    db.add(row); db.commit(); db.refresh(row); return {"id":row.id,"provider":row.provider,"model":row.model,"priority":row.priority,"enabled":row.enabled}
