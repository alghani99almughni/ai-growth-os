from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session
import json, asyncio
from datetime import datetime, timezone

from .db import SessionLocal
from .models import Tenant
from .models_integrations import TenantIntegration, PlatformAIProvider
from .integrations import encrypt_channel_config, decrypt_channel_config
from .config import settings

router = APIRouter(prefix="/api/v1", tags=["integrations"])

CATALOG = [
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

def _platform_available(key):
    if key=="razorpay": return bool(settings.razorpay_key_id and settings.razorpay_key_secret)
    if key=="gemini": return bool(settings.gemini_api_key)
    if key=="openai": return bool(settings.openai_api_key)
    if key=="openrouter": return bool(settings.openrouter_api_key)
    if key=="anthropic": return bool(settings.anthropic_api_key)
    if key=="email": return True
    if key=="voice": return bool(settings.telephony_provider and settings.telephony_api_key)
    return False

def _out(row):
    cfg={}
    if row.config_encrypted:
        try: cfg=decrypt_channel_config(row.config_encrypted, (settings.integration_credential_encryption_key or settings.whatsapp_credential_encryption_key))
        except Exception: pass
    return {
      "key":row.integration_key,"provider":row.provider,"mode":row.mode,"status":row.status,
      "account_name":row.account_name,"account_id":row.account_id,
      "config":_safe_config(row.integration_key,cfg),
      "metadata":json.loads(row.metadata_json or "{}"),
    }

@router.get("/tenants/{tenant_id}/integrations/catalog")
def integration_catalog(tenant_id: str, credentials: HTTPAuthorizationCredentials=Depends(HTTPBearer(auto_error=False)), db: Session=Depends(get_db)):
    user=_user(credentials,db); _require(user,tenant_id)
    return {"items":CATALOG}

@router.get("/tenants/{tenant_id}/integrations")
def integrations(tenant_id: str, credentials: HTTPAuthorizationCredentials=Depends(HTTPBearer(auto_error=False)), db: Session=Depends(get_db)):
    user=_user(credentials,db); _require(user,tenant_id)
    rows=db.scalars(select(TenantIntegration).where(TenantIntegration.tenant_id==tenant_id)).all()
    items=[_out(x) for x in rows]
    existing={x["key"] for x in items}
    for item in CATALOG:
        platform=next((p for p in item["providers"] if p["type"]=="platform"),None)
        if platform and item["key"] not in existing:
            items.append({"key":item["key"],"provider":"platform","mode":"platform","status":"connected" if _platform_available(item["key"]) else "available","account_name":"Platform service","account_id":None,"config":{},"metadata":{}})
    return {"items":items}

@router.get("/tenants/{tenant_id}/integrations/{key}")
def integration_status(tenant_id: str, key: str, credentials: HTTPAuthorizationCredentials=Depends(HTTPBearer(auto_error=False)), db: Session=Depends(get_db)):
    user=_user(credentials,db); _require(user,tenant_id)
    row=db.scalar(select(TenantIntegration).where(TenantIntegration.tenant_id==tenant_id,TenantIntegration.integration_key==key))
    if not row:
        item=_catalog_item(key)
        platform=next((p for p in item["providers"] if p["type"]=="platform"),None) if item else None
        if platform: return {"key":key,"status":"connected" if _platform_available(key) else "available","provider":"platform","mode":"platform","configured":_platform_available(key),"config":{}}
        return {"key":key,"status":"disconnected","provider":item["providers"][0]["id"] if item else "platform","mode":item["mode"] if item else "platform","configured":False,"config":{}}
    out=_out(row); out["configured"]=bool(row.config_encrypted) or row.mode in ("platform","oauth"); return out

@router.put("/tenants/{tenant_id}/integrations/{key}")
def save_integration(tenant_id: str, key: str, payload: IntegrationPayload, credentials: HTTPAuthorizationCredentials=Depends(HTTPBearer(auto_error=False)), db: Session=Depends(get_db)):
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
            old=decrypt_channel_config(existing.config_encrypted,(settings.integration_credential_encryption_key or settings.whatsapp_credential_encryption_key)) if existing.config_encrypted else {}
            for k in SECRET_FIELDS.get(key,[]):
                if k not in config and old.get(k): config[k]=old[k]
        except Exception: pass
    encrypted=encrypt_channel_config(config,(settings.integration_credential_encryption_key or settings.whatsapp_credential_encryption_key)) if config else ""
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
def disconnect_integration(tenant_id: str, key: str, credentials: HTTPAuthorizationCredentials=Depends(HTTPBearer(auto_error=False)), db: Session=Depends(get_db)):
    user=_user(credentials,db); _require(user,tenant_id)
    row=db.scalar(select(TenantIntegration).where(TenantIntegration.tenant_id==tenant_id,TenantIntegration.integration_key==key))
    if row:
        row.status="disconnected"; row.config_encrypted=""; row.account_name=None; row.account_id=None; db.commit()
    return {"key":key,"status":"disconnected"}

@router.get("/platform/ai/providers")
def platform_ai_providers(credentials: HTTPAuthorizationCredentials=Depends(HTTPBearer(auto_error=False)), db: Session=Depends(get_db)):
    user=_user(credentials,db)
    if user.role not in ("super_admin","platform_admin"): raise HTTPException(403,"Platform admin required")
    rows=db.scalars(select(PlatformAIProvider).order_by(PlatformAIProvider.priority)).all()
    return {"items":[{"id":x.id,"provider":x.provider,"model":x.model,"priority":x.priority,"enabled":x.enabled,"status":x.status,"last_error":x.last_error,"last_used_at":x.last_used_at.isoformat() if x.last_used_at else None} for x in rows]}

@router.put("/platform/ai/providers/{provider_id}")
def update_platform_ai_provider(provider_id: str, payload: dict, credentials: HTTPAuthorizationCredentials=Depends(HTTPBearer(auto_error=False)), db: Session=Depends(get_db)):
    user=_user(credentials,db)
    if user.role not in ("super_admin","platform_admin"): raise HTTPException(403,"Platform admin required")
    row=db.get(PlatformAIProvider,provider_id)
    if not row: raise HTTPException(404,"AI provider not found")
    if "api_key" in payload and payload["api_key"]:
        row.config_encrypted=encrypt_channel_config({"api_key":payload["api_key"]},(settings.integration_credential_encryption_key or settings.whatsapp_credential_encryption_key))
    for k in ("model","priority","enabled"):
        if k in payload: setattr(row,k,payload[k])
    db.commit(); return {"id":row.id,"provider":row.provider,"model":row.model,"priority":row.priority,"enabled":row.enabled}

@router.post("/platform/ai/providers")
def create_platform_ai_provider(payload: dict, credentials: HTTPAuthorizationCredentials=Depends(HTTPBearer(auto_error=False)), db: Session=Depends(get_db)):
    user=_user(credentials,db)
    if user.role not in ("super_admin","platform_admin"): raise HTTPException(403,"Platform admin required")
    row=PlatformAIProvider(provider=payload.get("provider","gemini"),model=payload.get("model",""),priority=int(payload.get("priority",100)),enabled=bool(payload.get("enabled",True)))
    if payload.get("api_key"): row.config_encrypted=encrypt_channel_config({"api_key":payload["api_key"]},(settings.integration_credential_encryption_key or settings.whatsapp_credential_encryption_key))
    db.add(row); db.commit(); db.refresh(row); return {"id":row.id,"provider":row.provider,"model":row.model,"priority":row.priority,"enabled":row.enabled}


class BuiltinWhatsAppConnect(BaseModel):
    phone: str = Field(min_length=8,max_length=32)
    method: str = Field(default="pairing", pattern=r"^(pairing|qr)$")

async def _openwa_request(method, url, api_key, **kwargs):
    import httpx
    headers=kwargs.pop("headers",{})
    headers["X-API-Key"]=api_key
    async with httpx.AsyncClient(timeout=20) as client:
        r=await client.request(method,url,headers=headers,**kwargs)
        r.raise_for_status()
        return r.json() if r.content else {}

@router.post("/tenants/{tenant_id}/integrations/whatsapp/builtin/connect")
async def builtin_whatsapp_connect(tenant_id: str, payload: BuiltinWhatsAppConnect, credentials: HTTPAuthorizationCredentials=Depends(HTTPBearer(auto_error=False)), db: Session=Depends(get_db)):
    user=_user(credentials,db); _require(user,tenant_id)
    if not settings.openwa_base_url or not settings.openwa_api_key:
        raise HTTPException(503,"Built-in WhatsApp service is not configured on the platform")
    tenant=db.get(Tenant,tenant_id)
    if not tenant: raise HTTPException(404,"Tenant not found")
    created=await _openwa_request("POST",settings.openwa_base_url.rstrip("/")+"/api/sessions",settings.openwa_api_key,json={"name":"tenant-"+tenant.slug})
    sid=created.get("id")
    if not sid: raise HTTPException(502,"OpenWA did not return a session ID")
    await _openwa_request("POST",settings.openwa_base_url.rstrip("/")+"/api/sessions/"+sid+"/start",settings.openwa_api_key,json={})
    from .models import TenantWhatsAppConnection
    row=db.scalar(select(TenantWhatsAppConnection).where(TenantWhatsAppConnection.tenant_id==tenant_id))
    if not row:
        row=TenantWhatsAppConnection(id=__import__("secrets").token_hex(18),tenant_id=tenant_id)
        db.add(row)
    row.provider="openwa"; row.status="connecting"; row.config_encrypted=encrypt_channel_config({"provider":"openwa","base_url":settings.openwa_base_url,"api_key":settings.openwa_api_key,"session_id":sid,"connected_phone":payload.phone},(settings.integration_credential_encryption_key or settings.whatsapp_credential_encryption_key)); row.connected_phone=payload.phone; row.display_name=tenant.name; row.updated_at=datetime.utcnow(); db.commit()
    if payload.method=="pairing":
        result=await _openwa_request("POST",settings.openwa_base_url.rstrip("/")+"/api/sessions/"+sid+"/pairing-code",settings.openwa_api_key,json={"phoneNumber":payload.phone})
        return {"session_id":sid,"method":"pairing","status":"connecting","pairing_code":result.get("code") or result.get("pairingCode")}
    return {"session_id":sid,"method":"qr","status":"connecting","qr_url":"/api/v1/tenants/"+tenant_id+"/integrations/whatsapp/builtin/qr"}

@router.get("/tenants/{tenant_id}/integrations/whatsapp/builtin/status")
async def builtin_whatsapp_status(tenant_id: str, credentials: HTTPAuthorizationCredentials=Depends(HTTPBearer(auto_error=False)), db: Session=Depends(get_db)):
    user=_user(credentials,db); _require(user,tenant_id)
    from .models import TenantWhatsAppConnection
    row=db.scalar(select(TenantWhatsAppConnection).where(TenantWhatsAppConnection.tenant_id==tenant_id))
    if not row or not row.config_encrypted: return {"status":"disconnected","connected_phone":None,"display_name":None}
    cfg=decrypt_channel_config(row.config_encrypted,(settings.integration_credential_encryption_key or settings.whatsapp_credential_encryption_key))
    try:
        info=await _openwa_request("GET",cfg["base_url"].rstrip("/")+"/api/sessions/"+cfg["session_id"],cfg["api_key"])
        state=info.get("status") or info.get("state") or row.status
        row.status="connected" if state in ("ready","connected") else ("connecting" if state in ("connecting","qr") else state)
        row.connected_phone=info.get("phone") or info.get("phoneNumber") or row.connected_phone
        db.commit()
    except Exception:
        state=row.status
    return {"session_id":cfg.get("session_id"),"status":row.status,"connected_phone":row.connected_phone,"display_name":row.display_name}

@router.get("/tenants/{tenant_id}/integrations/whatsapp/builtin/qr")
async def builtin_whatsapp_qr(tenant_id: str, credentials: HTTPAuthorizationCredentials=Depends(HTTPBearer(auto_error=False)), db: Session=Depends(get_db)):
    user=_user(credentials,db); _require(user,tenant_id)
    from .models import TenantWhatsAppConnection
    row=db.scalar(select(TenantWhatsAppConnection).where(TenantWhatsAppConnection.tenant_id==tenant_id))
    if not row or not row.config_encrypted: raise HTTPException(404,"Built-in WhatsApp session not found")
    cfg=decrypt_channel_config(row.config_encrypted,(settings.integration_credential_encryption_key or settings.whatsapp_credential_encryption_key))
    return await _openwa_request("GET",cfg["base_url"].rstrip("/")+"/api/sessions/"+cfg["session_id"]+"/qr",cfg["api_key"])


# OAuth connections for tenant-owned social accounts.
import base64, hashlib, hmac, secrets as _secrets
from urllib.parse import urlencode

def _oauth_state(tenant_id: str, key: str):
    issued_at = str(int(datetime.now(timezone.utc).timestamp()))
    nonce = _secrets.token_urlsafe(18)
    raw=f"{tenant_id}:{key}:{issued_at}:{nonce}"
    sig=hmac.new(settings.jwt_secret.encode(),raw.encode(),hashlib.sha256).hexdigest()
    return base64.urlsafe_b64encode((raw+"."+sig).encode()).decode()

def _verify_oauth_state(state: str):
    try:
        raw=base64.urlsafe_b64decode(state.encode()).decode()
        value,sig=raw.rsplit(".",1)
        expected=hmac.new(settings.jwt_secret.encode(),value.encode(),hashlib.sha256).hexdigest()
        if not hmac.compare_digest(sig,expected): raise ValueError("bad signature")
        tenant_id,key,issued_at,nonce=value.split(":",3)
        age=int(datetime.now(timezone.utc).timestamp())-int(issued_at)
        if age < 0 or age > settings.oauth_state_ttl_seconds: raise ValueError("expired state")
        return tenant_id,key
    except Exception:
        raise HTTPException(400,"Invalid or expired OAuth state")

def _oauth_row(db, tenant_id, key):
    return db.scalar(select(TenantIntegration).where(TenantIntegration.tenant_id==tenant_id,TenantIntegration.integration_key==key))

async def _http_json(method,url,**kwargs):
    import httpx
    async with httpx.AsyncClient(timeout=30) as client:
        r=await client.request(method,url,**kwargs)
        r.raise_for_status()
        return r.json()

@router.get("/oauth/{provider}/start")
def oauth_start(provider: str, tenant_id: str, integration_key: str, credentials: HTTPAuthorizationCredentials=Depends(HTTPBearer(auto_error=False)), db: Session=Depends(get_db)):
    user=_user(credentials,db); _require(user,tenant_id)
    if integration_key not in {"meta_business","facebook","instagram","meta_ads","youtube","google_business"}: raise HTTPException(400,"Unsupported OAuth integration")
    state=_oauth_state(tenant_id,integration_key)
    if provider=="meta":
        if not settings.meta_client_id or not settings.meta_redirect_uri: raise HTTPException(503,"Meta OAuth is not configured")
        scopes="pages_show_list,pages_read_engagement,pages_manage_metadata,business_management,instagram_basic,instagram_content_publish,ads_read,ads_management"
        url=f"https://www.facebook.com/{settings.meta_graph_api_version}/dialog/oauth?"+urlencode({"client_id":settings.meta_client_id,"redirect_uri":settings.meta_redirect_uri,"state":state,"scope":scopes})
    elif provider=="google":
        if not settings.google_client_id or not settings.google_redirect_uri: raise HTTPException(503,"Google OAuth is not configured")
        scopes={
          "youtube":"https://www.googleapis.com/auth/youtube https://www.googleapis.com/auth/youtube.readonly",
          "google_business":"https://www.googleapis.com/auth/business.manage"
        }.get(integration_key)
        if not scopes: raise HTTPException(400,"Unsupported Google integration")
        url="https://accounts.google.com/o/oauth2/v2/auth?"+urlencode({"client_id":settings.google_client_id,"redirect_uri":settings.google_redirect_uri,"response_type":"code","access_type":"offline","prompt":"consent","include_granted_scopes":"true","scope":scopes,"state":state})
    else: raise HTTPException(400,"Unsupported OAuth provider")
    return {"authorization_url":url}

@router.post("/oauth/{provider}/start")
async def oauth_start_post(provider: str, payload: dict, credentials: HTTPAuthorizationCredentials=Depends(HTTPBearer(auto_error=False)), db: Session=Depends(get_db)):
    return oauth_start(provider, str(payload.get("tenant_id")), str(payload.get("integration_key")), credentials, db)

@router.get("/oauth/meta/callback")
async def oauth_meta_callback(code: str, state: str, db: Session=Depends(get_db)):
    tenant_id,key=_verify_oauth_state(state)
    if not settings.meta_client_id or not settings.meta_client_secret: raise HTTPException(503,"Meta OAuth is not configured")
    token=await _http_json("GET",f"https://graph.facebook.com/{settings.meta_graph_api_version}/oauth/access_token",params={"client_id":settings.meta_client_id,"client_secret":settings.meta_client_secret,"redirect_uri":settings.meta_redirect_uri,"code":code})
    access_token=token["access_token"]
    me=await _http_json("GET",f"https://graph.facebook.com/{settings.meta_graph_api_version}/me",params={"fields":"id,name","access_token":access_token})
    account_id=me.get("id"); account_name=me.get("name")
    if key in ("facebook","meta_business","instagram","meta_ads"):
        if key in ("facebook","meta_business"):
            pages=await _http_json("GET",f"https://graph.facebook.com/{settings.meta_graph_api_version}/me/accounts",params={"fields":"id,name,access_token,instagram_business_account","access_token":access_token})
            page=(pages.get("data") or [{}])[0]
            account_id=page.get("id") or account_id; account_name=page.get("name") or account_name
            if page.get("access_token"): access_token=page["access_token"]
        elif key=="instagram":
            pages=await _http_json("GET","https://graph.facebook.com/{settings.meta_graph_api_version}/me/accounts",params={"fields":"id,name,instagram_business_account","access_token":access_token})
            page=next((p for p in pages.get("data",[]) if p.get("instagram_business_account")),None)
            if page:
                ig=await _http_json("GET",f"https://graph.facebook.com/{settings.meta_graph_api_version}/{page['instagram_business_account']['id']}",params={"fields":"id,username,name","access_token":access_token})
                account_id=ig.get("id") or account_id; account_name=ig.get("username") or ig.get("name") or account_name
        elif key=="meta_ads":
            ads=await _http_json("GET",f"https://graph.facebook.com/{settings.meta_graph_api_version}/me/adaccounts",params={"fields":"id,name,account_id","access_token":access_token})
            ad=(ads.get("data") or [{}])[0]
            account_id=ad.get("id") or ad.get("account_id") or account_id; account_name=ad.get("name") or account_name
    row=_oauth_row(db,tenant_id,key)
    if not row: row=TenantIntegration(tenant_id=tenant_id,integration_key=key,provider="meta",mode="oauth"); db.add(row)
    row.status="connected"; row.config_encrypted=encrypt_channel_config({"access_token":access_token},(settings.integration_credential_encryption_key or settings.whatsapp_credential_encryption_key)); row.account_id=account_id; row.account_name=account_name; row.metadata_json=json.dumps({"oauth":"meta","connected_at":datetime.utcnow().isoformat()}); db.commit()
    from fastapi.responses import RedirectResponse
    return RedirectResponse(settings.public_app_url+"/dashboard?integration="+key+"&connected=1")

@router.get("/oauth/google/callback")
async def oauth_google_callback(code: str, state: str, db: Session=Depends(get_db)):
    tenant_id,key=_verify_oauth_state(state)
    if not settings.google_client_id or not settings.google_client_secret: raise HTTPException(503,"Google OAuth is not configured")
    token=await _http_json("POST","https://oauth2.googleapis.com/token",data={"code":code,"client_id":settings.google_client_id,"client_secret":settings.google_client_secret,"redirect_uri":settings.google_redirect_uri,"grant_type":"authorization_code"})
    existing=_oauth_row(db,tenant_id,key)
    previous={}
    if existing and existing.config_encrypted:
        try:
            previous=decrypt_channel_config(existing.config_encrypted,(settings.integration_credential_encryption_key or settings.whatsapp_credential_encryption_key))
        except Exception:
            previous={}
    cfg={"access_token":token.get("access_token"),"refresh_token":token.get("refresh_token") or previous.get("refresh_token"),"token_type":token.get("token_type"),"scope":token.get("scope")}
    account_id=None; account_name=None
    if key=="youtube":
        info=await _http_json("GET","https://www.googleapis.com/youtube/v3/channels",params={"part":"snippet,contentDetails","mine":"true"},headers={"Authorization":"Bearer "+cfg["access_token"]})
        item=(info.get("items") or [{}])[0]; account_id=item.get("id"); account_name=(item.get("snippet") or {}).get("title")
    elif key=="google_business":
        accounts=await _http_json("GET","https://mybusinessaccountmanagement.googleapis.com/v1/accounts",headers={"Authorization":"Bearer "+cfg["access_token"]})
        item=(accounts.get("accounts") or [{}])[0]; account_id=item.get("name"); account_name=item.get("accountName")
    row=_oauth_row(db,tenant_id,key)
    if not row: row=TenantIntegration(tenant_id=tenant_id,integration_key=key,provider="google",mode="oauth"); db.add(row)
    row.status="connected"; row.config_encrypted=encrypt_channel_config(cfg,(settings.integration_credential_encryption_key or settings.whatsapp_credential_encryption_key)); row.account_id=account_id; row.account_name=account_name; row.metadata_json=json.dumps({"oauth":"google","connected_at":datetime.utcnow().isoformat()}); db.commit()
    from fastapi.responses import RedirectResponse
    return RedirectResponse(settings.public_app_url+"/dashboard?integration="+key+"&connected=1")
