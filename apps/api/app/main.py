import logging
from fastapi import FastAPI,Depends,HTTPException,Query,Request,WebSocket
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPAuthorizationCredentials,HTTPBearer
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.orm import Session
from pydantic import BaseModel,Field
from .db import SessionLocal
from .models import Tenant,User,Customer,Lead,Service,Product,TenantWhatsAppConnection
from .models_growth import KnowledgeItem,KnowledgeCandidate,Appointment,LoyaltyTransaction,QrEntry,CallRecord,Campaign,BusinessHour,QueueEntry,ServiceRequest,TenantSetting,PlatformSetting,MenuCategory,MenuItem,Order,OrderItem,Bill,Feedback,LoyaltyRule,LoyaltyReward,GameScore,PasswordResetToken,AIProviderUsage
from .models_ai import GlobalFaq,Conversation,ConversationMessage,Department,StaffMember,RoleDefinition
from .schemas import *
from .services import *
from .brain import generate_reply,knowledge_context
from .config import settings
from .signaling import signal
from .events import publish_event_sync, subscribe_events
from .integrations import WhatsAppAdapter,PaymentAdapter,encrypt_channel_config,tenant_whatsapp_adapter,tenant_payment_adapter,decrypt_channel_config

app = FastAPI(
    title="AI Growth OS API",
    version="1.0.0",
)

from .models_integrations import TenantIntegration,PlatformAIProvider
from .models_email import TenantEmailAccount, EmailLog
from .models_monitoring import HealthSnapshot, SelfHealAction, MonitoringAlert, BackupRecord
from .notifications import send_owner_credentials,send_password_reset
from .migrations import ensure_schema
from .faq_seed import FAQS
from .ai_router import detect_language
from .tenant_policy import tenant_policy, capability_enabled, policy_context
from .website_templates import get_template as _get_site_template
from .website_templates import merge_with_tenant as _merge_site_content
from .routes_offline import router as offline_router
from .routes_calls import router as calls_router
from .config_validator import validate_environment
from .logging_config import configure_logging
from .middleware import RequestContextMiddleware
from .error_handler import install_error_handlers
from .health import router as health_router
from .hardening import (
    SecurityHeadersMiddleware, RequestSizeLimitMiddleware,
    auth_rate_limit, enrich_health, install_signal_handlers,
)
from .security import check_secret, cleanup_expired_idempotency, decode_token_strict, verify_hmac_sha256, audit

class RoutingRulePayload(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    intent: str | None = None
    trigger_keywords: str = ""
    department_id: str | None = None
    staff_id: str | None = None
    priority: int = Field(default=100, ge=1, le=10000)
    urgency: str = Field(default="normal", pattern="^(low|normal|high|urgent|emergency)$")
    action: str = Field(default="route", pattern="^(route|alert|route_and_alert)$")
    is_active: bool = True

class ReceptionAlertPayload(BaseModel):
    category: str = Field(default="general", max_length=50)
    priority: str = Field(default="normal", pattern="^(low|normal|high|urgent|emergency)$")
    title: str = Field(min_length=1, max_length=200)
    message: str = Field(min_length=1, max_length=5000)
    department_id: str | None = None
    staff_id: str | None = None
    customer_id: str | None = None
    call_id: str | None = None


from .voice_gateway import VoiceGateway, VoiceProvider, VoiceSessionState, OpenAIRealtimeAdapter, GeminiLiveAdapter
from .voice_escalate import router as voice_escalate_router
from .voice_runtime import VoiceTurnController
from .agent_training import AGENT_TRAINING_CONTEXT

voice_gateway = VoiceGateway({"gemini": GeminiLiveAdapter(), "openai": OpenAIRealtimeAdapter()})

from .routing import route_call, available_staff
from .booking import ensure_default_hours, available_slots, create_appointment, queue_snapshot
from .integration_routes import router as integration_router
from .social_routes import router as social_router
import asyncio,json,base64,uuid
from datetime import datetime,date,time,timedelta
from zoneinfo import ZoneInfo
import time
import websockets
import jwt,secrets,hashlib,hmac

import asyncio
configure_logging()
validate_environment(exit_on_failure=False)
app=FastAPI(title="AI Growth OS API",version="1.0.0")
app.add_middleware(RequestContextMiddleware)
install_error_handlers(app)
app.include_router(health_router)
app.include_router(offline_router)
app.include_router(calls_router)
app.include_router(integration_router)
app.include_router(social_router)
app.include_router(voice_escalate_router)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[x.strip() for x in settings.allowed_origins.split(",") if x.strip()],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)
# ── Timestamp UTC middleware ──
# The backend stores naive UTC (datetime.utcnow()). When serialized to ISO,
# the string has no trailing "Z", so browsers parse it as LOCAL time and shift
# it. This middleware adds "Z" to any ISO-8601 timestamp at the tail of a JSON
# string field ending in :SS or :SS.ffffff, so the browser converts correctly.
import re as _re_ts
_ISO_UTC_RE = _re_ts.compile(r'"(20\d\d-\d\d-\d\dT\d\d:\d\d:\d\d(?:\.\d+)?)"')

@app.middleware("http")
async def _utc_marker_middleware(request: Request, call_next):
    response = await call_next(request)
    ctype = response.headers.get("content-type", "")
    if "application/json" not in ctype:
        return response
    # Stream the body through a small transform. Read fully then rewrite.
    body_chunks = []
    async for chunk in response.body_iterator:
        body_chunks.append(chunk)
    try:
        body = b"".join(body_chunks).decode("utf-8")
        body = _ISO_UTC_RE.sub(r'"\1Z"', body)
        new_body = body.encode("utf-8")
    except Exception:
        new_body = b"".join(body_chunks)
    from starlette.responses import Response as _Resp
    headers = dict(response.headers)
    headers.pop("content-length", None)
    return _Resp(content=new_body, status_code=response.status_code,
                 headers=headers, media_type=response.media_type)
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(RequestSizeLimitMiddleware, max_bytes=2 * 1024 * 1024)


# Lightweight per-process abuse protection. Production multi-instance deployments should
# place the same limits at the edge/API gateway as well.
_rate_buckets={}
_rate_lock=asyncio.Lock()

@app.middleware("http")
async def rate_limit(request:Request, call_next):
    if request.url.path in {"/health","/docs","/openapi.json"}:
        return await call_next(request)
    now=asyncio.get_running_loop().time()
    client=request.client.host if request.client else "unknown"
    # Isolate abuse budgets by tenant/business where the route identifies one.
    # A shared client IP (for example a QA runner or NAT) must not let one tenant
    # exhaust the rate-limit bucket for every other tenant.
    tenant_scope=""
    if "/public/business/" in request.url.path:
        parts=request.url.path.split("/public/business/",1)[1].split("/",1)
        tenant_scope=parts[0] if parts and parts[0] else ""
    elif "/tenants/" in request.url.path:
        parts=request.url.path.split("/tenants/",1)[1].split("/",1)
        tenant_scope=parts[0] if parts and parts[0] else ""

    key=(client,tenant_scope,request.url.path)
    async with _rate_lock:
        bucket=_rate_buckets.get(key)
        if not bucket or now-bucket[0]>=settings.rate_limit_window_seconds:
            _rate_buckets[key]=[now,1]
        else:
            bucket[1]+=1
            if bucket[1]>settings.rate_limit_requests:
                return JSONResponse(status_code=429,content={"detail":"Too many requests"})
    return await call_next(request)

@app.websocket("/ws/tenants/{tenant_id}/events")
async def tenant_events(websocket:WebSocket,tenant_id:str,access_token:str|None=Query(default=None)):
    origin=websocket.headers.get("origin")
    allowed={x.strip().rstrip("/") for x in settings.allowed_origins.split(",") if x.strip()}
    if origin and origin.rstrip("/") not in allowed:
        await websocket.close(code=4403); return
    if not access_token:
        await websocket.close(code=4401); return
    db=SessionLocal()
    try:
        p=jwt.decode(access_token,settings.jwt_secret,algorithms=[settings.jwt_algorithm])
        user=db.get(User,p.get("sub"))
        if not user or not user.is_active or user.tenant_id!=tenant_id:
            await websocket.close(code=4403); return
    except jwt.InvalidTokenError:
        await websocket.close(code=4401); return
    finally:
        db.close()
    await websocket.accept()
    try:
        async for event in subscribe_events(tenant_id):
            await websocket.send_json(event)
    except Exception:
        try: await websocket.close()
        except Exception: pass

@app.websocket("/ws/public/business/{slug}/events")
async def public_business_events(websocket:WebSocket,slug:str,context_token:str|None=Query(default=None)):
    origin=websocket.headers.get("origin")
    allowed={x.strip().rstrip("/") for x in settings.allowed_origins.split(",") if x.strip()}
    if origin and origin.rstrip("/") not in allowed:
        await websocket.close(code=4403); return
    db=SessionLocal()
    try:
        tenant=db.scalar(select(Tenant).where(Tenant.slug==slug.lower()))
        if not tenant:
            await websocket.close(code=4404); return
    finally:
        db.close()
    if not context_token:
        await websocket.close(code=4400); return
    await websocket.accept()
    try:
        async for event in subscribe_events(tenant.id):
            if event.get("context_token") == context_token:
                await websocket.send_json(event)
    except Exception:
        try: await websocket.close()
        except Exception: pass

def issue_call_room_token(call_id:str,audience:str):
    # Browser WebSocket query strings are not a reliable place for a JWT audience
    # exchange across proxies. Use a compact, URL-safe, HMAC-signed room token
    # dedicated to this short-lived public call session.
    exp=int(datetime.utcnow().timestamp())+600
    body=f"v2.{call_id}.{audience}.{exp}"
    signature=hmac.new(settings.jwt_secret.encode("utf-8"),body.encode("utf-8"),hashlib.sha256).hexdigest()
    return f"{body}.{signature}"

def verify_call_room_token(token:str,call_id:str,audience:str):
    try:
        parts=token.split(".")
        if len(parts)!=5 or parts[0]!="v2":
            return False
        _,token_call_id,token_audience,exp_text,signature=parts
        if token_call_id!=call_id or token_audience!=audience:
            return False
        exp=int(exp_text)
        if exp < int(datetime.utcnow().timestamp()):
            return False
        body=".".join(parts[:4])
        expected=hmac.new(settings.jwt_secret.encode("utf-8"),body.encode("utf-8"),hashlib.sha256).hexdigest()
        return hmac.compare_digest(signature,expected)
    except (ValueError,TypeError):
        return False

@app.websocket("/ws/calls/{call_id}")
async def call_signal(websocket:WebSocket,call_id:str,access_token:str|None=Query(default=None),room_token:str|None=Query(default=None)):
    db=SessionLocal()
    call=db.get(CallRecord,call_id)
    if not call:
        await websocket.close(code=4404); db.close(); return
    allow_staff=False
    allow_customer=bool(room_token and verify_call_room_token(room_token,call_id,"call-customer"))
    if access_token:
        try:
            p=jwt.decode(access_token,settings.jwt_secret,algorithms=[settings.jwt_algorithm])
            uid=p.get("sub")
            user=db.get(User,uid)
            staff=db.scalar(select(StaffMember).where(StaffMember.user_id==uid,StaffMember.tenant_id==call.tenant_id))
            allow_staff=bool(
                user and user.is_active and user.tenant_id==call.tenant_id and
                (user.role in ("owner","admin","super_admin","platform_admin") or (staff and staff.id==call.staff_id))
            )
        except jwt.InvalidTokenError:
            allow_staff=False
    db.close()
    if not allow_staff and not allow_customer:
        await websocket.close(code=4403); return
    await signal(websocket,call_id,allow_staff=allow_staff,allow_customer=allow_customer)

security=HTTPBearer(auto_error=False)

@app.on_event("startup")
async def startup():
    install_signal_handlers(app)
    ensure_schema()
    try:
        from .migrations import ensure_email_schema
        ensure_email_schema()
    except Exception:
        import logging; logging.getLogger("api.email").exception("email schema init failed")
    try:
        from .migrations import ensure_monitoring_schema
        ensure_monitoring_schema()
    except Exception:
        import logging; logging.getLogger("api.monitoring").exception("monitoring schema init failed")
    try:
        from .monitoring import start_monitoring
        start_monitoring()
    except Exception:
        import logging; logging.getLogger("api.monitoring").exception("monitoring failed to start")
    try:
        from .email_poller import start_email_poller
        start_email_poller()
    except Exception:
        import logging; logging.getLogger("api.email").exception("email poller failed to start")
    try:
        from .qr import ensure_qr_schema
        from .db import engine as _engine
        ensure_qr_schema(_engine)
    except Exception:
        pass
    try:
        from .whatsapp_migration import ensure_two_channel_whatsapp
        from .db import engine
        ensure_two_channel_whatsapp(engine)
    except Exception:
        pass
    if settings.environment == "production":
        warnings = []
        warnings.extend(check_secret("JWT_SECRET", settings.jwt_secret, 32))
        if settings.whatsapp_credential_encryption_key:
            warnings.extend(check_secret("WHATSAPP_CREDENTIAL_ENCRYPTION_KEY",
                                         settings.whatsapp_credential_encryption_key, 40))
        if settings.integration_credential_encryption_key:
            warnings.extend(check_secret("INTEGRATION_CREDENTIAL_ENCRYPTION_KEY",
                                         settings.integration_credential_encryption_key, 40))
        if warnings:
            import logging as _lg
            _lg.getLogger("api.security").error(
                "SECURITY CONFIG ERRORS IN PRODUCTION: %s", "; ".join(warnings))
            raise RuntimeError("refusing to start: " + "; ".join(warnings))
    db=SessionLocal()
    try:
        if db.scalar(select(GlobalFaq.id).limit(1)) is None:
            for industry,language,intent,question,answer,keywords in FAQS:
                db.add(GlobalFaq(industry=industry,language=language,intent=intent,question=question,answer=answer,keywords=keywords))
            db.commit()
        if settings.platform_admin_email and settings.platform_admin_password:
            existing=db.scalar(select(User).where(User.email==settings.platform_admin_email.lower()))
            platform_tenant=db.scalar(select(Tenant).where(Tenant.slug=="__platform__"))
            if not platform_tenant:
                platform_tenant=Tenant(id=str(uuid.uuid4()),name="AI Growth OS Platform",slug="__platform__",industry="platform",status="active")
                db.add(platform_tenant); db.commit(); db.refresh(platform_tenant)
            if not existing:
                existing=User(id=str(uuid.uuid4()),name=settings.platform_admin_name,email=settings.platform_admin_email.lower(),password_hash=hash_password(settings.platform_admin_password),tenant_id=platform_tenant.id,role="platform_admin")
                db.add(existing); db.commit()
            elif existing.role!="platform_admin":
                existing.role="platform_admin"; existing.tenant_id=platform_tenant.id; db.commit()
    finally:
        db.close()
def get_db():
    db=SessionLocal()
    try: yield db
    finally: db.close()
class Health(BaseModel): status:str; service:str; commit:str="unknown"
@app.get("/health")
def health():
    out = enrich_health()
    out["commit"] = __import__("os").environ.get("RENDER_GIT_COMMIT", "unknown")
    return out
def get_current_user(credentials:HTTPAuthorizationCredentials=Depends(security),db:Session=Depends(get_db))->User:
    if not credentials: raise HTTPException(401,"Authentication required")
    try:
        p=decode_token_strict(credentials.credentials,settings.jwt_secret,settings.jwt_algorithm); uid=p.get("sub")
    except ValueError as exc: raise HTTPException(401,str(exc))
    u=db.get(User,uid)
    if not u or not u.is_active or p.get("tenant_id")!=u.tenant_id: raise HTTPException(401,"Invalid tenant context")
    tenant=db.get(Tenant,u.tenant_id)
    if not tenant or tenant.status!="active": raise HTTPException(403,"Tenant is not active")
    return u
FEATURE_DEFAULTS={"digital_menu":True,"online_ordering":True,"order_tracking":True,"call_waiter":True,"service_requests":True,"games":True,"auto_bill":True,"online_payment":True,"ai_chat":True,"ai_voice":True,"loyalty":False,"referrals":False,"feedback":True,"google_review":True,"bookings":True,"queue":True}
INDUSTRY_FEATURES={
    "restaurant":{"digital_menu":True,"online_ordering":True,"order_tracking":True,"call_waiter":True,"service_requests":True,"games":True,"auto_bill":True,"online_payment":True,"ai_chat":True,"ai_voice":True,"loyalty":False,"referrals":False,"feedback":True,"google_review":True,"bookings":True,"queue":True},
    "cafe":{"digital_menu":True,"online_ordering":True,"order_tracking":True,"call_waiter":True,"service_requests":True,"games":True,"auto_bill":True,"online_payment":True,"ai_chat":True,"ai_voice":True,"loyalty":False,"referrals":False,"feedback":True,"google_review":True,"bookings":True,"queue":True},
    "hotel":{"digital_menu":True,"online_ordering":True,"order_tracking":True,"call_waiter":True,"service_requests":True,"games":False,"auto_bill":True,"online_payment":True,"ai_chat":True,"ai_voice":True,"loyalty":False,"referrals":False,"feedback":True,"google_review":True,"bookings":True,"queue":True},
    "salon":{"digital_menu":False,"online_ordering":False,"order_tracking":False,"call_waiter":False,"service_requests":True,"games":False,"auto_bill":False,"online_payment":True,"ai_chat":True,"ai_voice":True,"loyalty":False,"referrals":False,"feedback":True,"google_review":True,"bookings":True,"queue":True},
    "dental":{"digital_menu":False,"online_ordering":False,"order_tracking":False,"call_waiter":False,"service_requests":True,"games":False,"auto_bill":False,"online_payment":True,"ai_chat":True,"ai_voice":True,"loyalty":False,"referrals":False,"feedback":True,"google_review":True,"bookings":True,"queue":True},
    "gym":{"digital_menu":False,"online_ordering":False,"order_tracking":False,"call_waiter":False,"service_requests":True,"games":True,"auto_bill":False,"online_payment":True,"ai_chat":True,"ai_voice":True,"loyalty":False,"referrals":False,"feedback":True,"google_review":True,"bookings":True,"queue":True},
    "health":{"digital_menu":False,"online_ordering":False,"order_tracking":False,"call_waiter":False,"service_requests":True,"games":False,"auto_bill":False,"online_payment":True,"ai_chat":True,"ai_voice":True,"loyalty":False,"referrals":False,"feedback":True,"google_review":True,"bookings":True,"queue":True},
    "wellness":{"digital_menu":False,"online_ordering":False,"order_tracking":False,"call_waiter":False,"service_requests":True,"games":False,"auto_bill":False,"online_payment":True,"ai_chat":True,"ai_voice":True,"loyalty":False,"referrals":False,"feedback":True,"google_review":True,"bookings":True,"queue":True},
    "real-estate":{"digital_menu":False,"online_ordering":False,"order_tracking":False,"call_waiter":False,"service_requests":True,"games":False,"auto_bill":False,"online_payment":False,"ai_chat":True,"ai_voice":True,"loyalty":False,"referrals":False,"feedback":True,"google_review":True,"bookings":True,"queue":False}
}
GAME_CATALOG=[{"id":"dino","name":"Dino Run"},{"id":"snake","name":"Snake"},{"id":"brick","name":"Brick Breaker"},{"id":"flappy","name":"Flappy"},{"id":"tap","name":"Tap Target"},{"id":"2048","name":"2048"}]
def _feature_config(db,tenant_id):
    row=db.scalar(select(TenantSetting).where(TenantSetting.tenant_id==tenant_id,TenantSetting.key=="features"))
    tenant=db.get(Tenant,tenant_id)
    cfg=dict(FEATURE_DEFAULTS)
    if tenant: cfg.update(INDUSTRY_FEATURES.get((tenant.industry or "").lower(),{}))
    platform=db.scalar(select(PlatformSetting).where(PlatformSetting.key=="feature_defaults"))
    if platform:
        try: cfg.update(json.loads(platform.value_json))
        except Exception: pass
    if row:
        try: cfg.update(json.loads(row.value_json))
        except Exception: pass
    return cfg
def _set_setting(db,tenant_id,key,value):
    row=db.scalar(select(TenantSetting).where(TenantSetting.tenant_id==tenant_id,TenantSetting.key==key))
    if not row:
        row=TenantSetting(tenant_id=tenant_id,key=key,value_json=json.dumps(value)); db.add(row)
    else: row.value_json=json.dumps(value)
    db.commit()
    return value

def require_tenant(user:User,tenant_id:str):
    if user.tenant_id!=tenant_id: raise HTTPException(403,"Tenant access denied")
def user_out(u): return UserOut(id=u.id,email=u.email,name=u.name,tenant_id=u.tenant_id,role=u.role)

class PlatformAIProviderRequest(BaseModel):
    provider:str=Field(min_length=2,max_length=60)
    model:str=Field(min_length=2,max_length=120)
    api_key:str=Field(min_length=8,max_length=500)
    priority:int=Field(default=100,ge=1,le=10000)
    enabled:bool=True

@app.post("/api/v1/platform/ai/providers")
def platform_ai_provider_add(payload:PlatformAIProviderRequest,user:User=Depends(get_current_user),db:Session=Depends(get_db)):
    if user.role not in ("platform_admin","super_admin"):
        raise HTTPException(403,"Platform admin access required")
    key=(settings.integration_credential_encryption_key or settings.whatsapp_credential_encryption_key)
    if not key:
        raise HTTPException(500,"Credential encryption is not configured")
    existing=db.scalar(select(PlatformAIProvider).where(
        PlatformAIProvider.provider==payload.provider.lower(),
        PlatformAIProvider.model==payload.model,
        PlatformAIProvider.config_encrypted==encrypt_channel_config({"api_key":payload.api_key},key)
    ))
    if existing:
        existing.priority=payload.priority; existing.enabled=payload.enabled; existing.status="healthy"
    else:
        db.add(PlatformAIProvider(provider=payload.provider.lower(),model=payload.model,priority=payload.priority,enabled=payload.enabled,status="healthy",config_encrypted=encrypt_channel_config({"api_key":payload.api_key},key)))
    db.commit()
    return {"ok":True,"provider":payload.provider.lower(),"model":payload.model,"priority":payload.priority,"enabled":payload.enabled}

@app.get("/api/v1/platform/ai/providers")
def platform_ai_provider_status(user:User=Depends(get_current_user),db:Session=Depends(get_db)):
    if user.role not in ("platform_admin","super_admin"):
        raise HTTPException(403,"Platform admin access required")
    rows=db.scalars(select(AIProviderUsage).order_by(AIProviderUsage.provider,AIProviderUsage.last_used_at.desc())).all()
    return {"providers":[{"tenant_id":x.tenant_id,"provider":x.provider,"model":x.model,"requests":x.request_count,"successes":x.success_count,"failures":x.failure_count,"rate_limits":x.rate_limit_count,"estimated_input_tokens":x.estimated_input_tokens,"estimated_output_tokens":x.estimated_output_tokens,"last_error":x.last_error,"last_used_at":x.last_used_at,"cooldown_until":x.cooldown_until} for x in rows]}

@app.post("/api/v1/platform/ai/providers/{provider}/recover")
def platform_ai_provider_recover(provider:str,model:str,user:User=Depends(get_current_user),db:Session=Depends(get_db)):
    if user.role not in ("platform_admin","super_admin"):
        raise HTTPException(403,"Platform admin access required")
    rows=db.scalars(select(AIProviderUsage).where(AIProviderUsage.provider==provider,AIProviderUsage.model==model)).all()
    for x in rows:
        x.cooldown_until=None; x.last_error=None
    db.commit()
    return {"ok":True,"provider":provider,"model":model,"recovered_records":len(rows)}

@app.post("/api/v1/auth/register",response_model=AuthResponse,status_code=201)
async def register(request:Request,payload:RegisterRequest,db:Session=Depends(get_db)):
    await auth_rate_limit(request, payload.email)
    if db.scalar(select(User).where(User.email==payload.email.lower())): raise HTTPException(409,"Email already registered")
    if db.scalar(select(Tenant).where(Tenant.slug==payload.slug.lower())): raise HTTPException(409,"Business slug already exists")
    t=create_tenant(db,payload.business_name,payload.slug,payload.industry); u=create_owner(db,payload.name,payload.email,payload.password,t)
    provision_defaults(db,t,payload.industry)
    _set_setting(db,t.id,"features",{**FEATURE_DEFAULTS,**INDUSTRY_FEATURES.get(payload.industry.lower(),{})})
    return {"access_token":create_access_token(u),"token_type":"bearer","user":user_out(u),"tenant":t}
@app.post("/api/v1/auth/login",response_model=AuthResponse)
async def login(request:Request,payload:LoginRequest,db:Session=Depends(get_db)):
    await auth_rate_limit(request, payload.email)
    u=db.scalar(select(User).where(User.email==payload.email.lower()))
    if not u or not u.is_active or not verify_password(payload.password,u.password_hash): raise HTTPException(401,"Invalid email or password")
    t=db.get(Tenant,u.tenant_id)
    try:
        from .platform_tools import mark_tenant_seen
        mark_tenant_seen(db, u.tenant_id)
    except Exception:
        pass
    return {"access_token":create_access_token(u),"token_type":"bearer","user":user_out(u),"tenant":t}
@app.get("/api/v1/auth/me",response_model=AuthResponse)
def me(user:User=Depends(get_current_user),db:Session=Depends(get_db)):
    return {"access_token":"","token_type":"bearer","user":user_out(user),"tenant":db.get(Tenant,user.tenant_id)}

# ============ SESSION10B_MULTI_CHANNEL_WHATSAPP ============

class WhatsAppChannelConfig(BaseModel):
    base_url: str | None = None
    api_key: str | None = None
    session_id: str | None = None
    access_token: str | None = None
    phone_number_id: str | None = None
    whatsapp_business_account_id: str | None = None


class WhatsAppPriorityUpdate(BaseModel):
    priority: str = Field(pattern="^(openwa|meta)$")


@app.get("/api/v1/tenants/{tenant_id}/integrations/whatsapp")
def whatsapp_channels(tenant_id, user=Depends(get_current_user), db: Session = Depends(get_db)):
    require_tenant(user, tenant_id)
    from .whatsapp_channels import all_channels
    return all_channels(db, tenant_id)


@app.put("/api/v1/tenants/{tenant_id}/integrations/whatsapp/openwa")
async def configure_openwa(tenant_id, payload: WhatsAppChannelConfig, user=Depends(get_current_user), db: Session = Depends(get_db)):
    require_tenant(user, tenant_id)
    data = payload.model_dump(exclude_none=True)
    if not all(data.get(k) for k in ("base_url", "api_key", "session_id")):
        raise HTTPException(400, "OpenWA requires base_url, api_key and session_id")
    try:
        async with __import__("httpx").AsyncClient(timeout=15) as client:
            rr = await client.get(
                data["base_url"].rstrip("/") + "/api/sessions/" + data["session_id"],
                headers={"X-API-Key": data["api_key"]},
            )
            rr.raise_for_status()
            session = rr.json()
            connected_phone = session.get("phoneNumber") or session.get("phone")
    except Exception as exc:
        raise HTTPException(400, "OpenWA credentials could not be validated: " + str(exc))

    from .whatsapp_channels import configure_channel
    return configure_channel(
        db, tenant_id, "openwa",
        {"base_url": data["base_url"], "api_key": data["api_key"], "session_id": data["session_id"]},
        connected_phone, None,
    )


@app.put("/api/v1/tenants/{tenant_id}/integrations/whatsapp/meta")
async def configure_meta(tenant_id, payload: WhatsAppChannelConfig, user=Depends(get_current_user), db: Session = Depends(get_db)):
    require_tenant(user, tenant_id)
    data = payload.model_dump(exclude_none=True)
    if not all(data.get(k) for k in ("access_token", "phone_number_id")):
        raise HTTPException(400, "Meta requires access_token and phone_number_id")
    try:
        async with __import__("httpx").AsyncClient(timeout=15) as client:
            rr = await client.get(
                "https://graph.facebook.com/v23.0/" + data["phone_number_id"],
                headers={"Authorization": "Bearer " + data["access_token"]},
            )
            rr.raise_for_status()
            info = rr.json()
            connected_phone = info.get("display_phone_number")
            display_name = info.get("verified_name")
    except Exception as exc:
        raise HTTPException(400, "Meta credentials could not be validated: " + str(exc))

    from .whatsapp_channels import configure_channel
    return configure_channel(
        db, tenant_id, "meta",
        {"access_token": data["access_token"], "phone_number_id": data["phone_number_id"]},
        connected_phone, display_name,
    )


@app.delete("/api/v1/tenants/{tenant_id}/integrations/whatsapp/{provider}")
def disconnect_channel_endpoint(tenant_id, provider, user=Depends(get_current_user), db: Session = Depends(get_db)):
    require_tenant(user, tenant_id)
    if provider not in ("openwa", "meta"):
        raise HTTPException(400, "provider must be openwa or meta")
    from .whatsapp_channels import disconnect_channel
    return disconnect_channel(db, tenant_id, provider)


@app.put("/api/v1/tenants/{tenant_id}/integrations/whatsapp/priority")
def set_whatsapp_priority(tenant_id, payload: WhatsAppPriorityUpdate, user=Depends(get_current_user), db: Session = Depends(get_db)):
    require_tenant(user, tenant_id)
    from .whatsapp_channels import set_priority, all_channels
    set_priority(db, tenant_id, payload.priority)
    return all_channels(db, tenant_id)


# ==== Meta Cloud API inbound webhook ====

@app.get("/api/v1/webhooks/meta/{tenant_id}")
def meta_webhook_verify(tenant_id: str, hub_mode: str = Query(default="", alias="hub.mode"), hub_challenge: str = Query(default="", alias="hub.challenge"), hub_verify_token: str = Query(default="", alias="hub.verify_token"), db: Session = Depends(get_db)):
    tenant = db.get(Tenant, tenant_id)
    if not tenant:
        raise HTTPException(404, "Tenant not found")
    expected = (settings.openwa_webhook_secret or "")  # reuse for Meta verify token
    if hub_mode == "subscribe" and hub_verify_token and hub_verify_token == expected:
        from fastapi.responses import PlainTextResponse
        return PlainTextResponse(hub_challenge)
    raise HTTPException(403, "Verification failed")


@app.post("/api/v1/webhooks/meta/{tenant_id}")
async def meta_webhook(tenant_id: str, request: Request, db: Session = Depends(get_db)):
    from .security import verify_hmac_sha256
    raw = await request.body()
    sig = request.headers.get("X-Hub-Signature-256", "")
    app_secret = settings.openwa_webhook_secret or ""
    if app_secret and sig and not verify_hmac_sha256(raw, sig, app_secret):
        raise HTTPException(401, "Invalid Meta webhook signature")
    try:
        payload = json.loads(raw.decode("utf-8"))
    except Exception:
        raise HTTPException(400, "Invalid webhook JSON")

    tenant = db.get(Tenant, tenant_id)
    if not tenant:
        raise HTTPException(404, "Tenant not found")

    entry = (payload.get("entry") or [{}])[0]
    changes = (entry.get("changes") or [{}])[0]
    value = changes.get("value") or {}
    messages = value.get("messages") or []
    if not messages:
        return {"ok": True, "ignored": True}

    m = messages[0]
    phone = (m.get("from") or "").strip()
    body = ""
    if m.get("type") == "text":
        body = ((m.get("text") or {}).get("body") or "").strip()
    if not phone or not body:
        return {"ok": True, "ignored": True}

    existing = db.scalar(select(Customer).where(
        Customer.tenant_id == tenant_id,
        Customer.phone == normalize_phone(phone),
    ))
    if not existing:
        try:
            existing = upsert_customer(db, tenant_id, phone, "WhatsApp User", True, source="whatsapp_meta")
        except ValueError:
            raise HTTPException(400, "Invalid phone")

    result = await generate_reply(db, tenant_id, body, None, "whatsapp")
    reply = result.get("reply") or "Thanks. How can I help you today?"

    from .whatsapp_channels import send_text_with_failover
    await send_text_with_failover(db, tenant_id, settings, existing.phone, reply)

    return {"ok": True, "customer_id": existing.id, "reply": reply}

# ============ END SESSION10B ============

class ReferralSettingsUpdate(BaseModel):
    enabled: bool = False
    referrer_points: int = Field(default=50, ge=0, le=100000)
    referee_points: int = Field(default=25, ge=0, le=100000)
    minimum_purchase: float = Field(default=0, ge=0)
    message: str = Field(default="Invite a friend and earn wellness rewards.", max_length=500)

@app.get("/api/v1/tenants/{tenant_id}/referral-settings")
def get_referral_settings(tenant_id,user=Depends(get_current_user),db:Session=Depends(get_db)):
    require_tenant(user,tenant_id)
    row=db.scalar(select(TenantSetting).where(TenantSetting.tenant_id==tenant_id,TenantSetting.key=="referral_settings"))
    try: return {"enabled":_feature_config(db,tenant_id).get("referrals",False),**(json.loads(row.value_json) if row else {"referrer_points":50,"referee_points":25,"minimum_purchase":0,"message":"Invite a friend and earn wellness rewards."})}
    except Exception: return {"enabled":False,"referrer_points":50,"referee_points":25,"minimum_purchase":0,"message":"Invite a friend and earn wellness rewards."}

@app.put("/api/v1/tenants/{tenant_id}/referral-settings")
def update_referral_settings(tenant_id,payload:ReferralSettingsUpdate,user=Depends(get_current_user),db:Session=Depends(get_db)):
    require_tenant(user,tenant_id)
    cfg=payload.model_dump(); enabled=cfg.pop("enabled")
    features=_feature_config(db,tenant_id); features["referrals"]=bool(enabled); _set_setting(db,tenant_id,"features",features)
    return {"enabled":enabled,**_set_setting(db,tenant_id,"referral_settings",cfg)}

class WebsiteContentUpdate(BaseModel):
    eyebrow: str = Field(default="MOINABAD · RANGAREDDY · TELANGANA", max_length=160)
    hero_title: str = Field(default="Feel better.", max_length=160)
    hero_emphasis: str = Field(default="Live consciously.", max_length=160)
    hero_description: str = Field(default="Practical wellness for modern life, with an organic-focused approach to healthier everyday choices.", max_length=1000)
    about_title: str = Field(default="Health consciousness starts with what you do every day.", max_length=300)
    about_text: str = Field(default="SS Nutritions is a local wellness brand based in Moinabad, focused on helping people make informed, sustainable lifestyle choices.", max_length=3000)
    whatsapp_number: str = Field(default="", max_length=32)
    contact_heading: str = Field(default="Your wellness journey can start with one conversation.", max_length=300)
    contact_text: str = Field(default="Tell us what you are looking for and our team can guide you on the next step.", max_length=1000)
    quote: str = Field(default="Wellness is not about changing everything overnight. It is about making better choices, consistently.", max_length=500)
    published: bool = True

DEFAULT_WEBSITE_CONTENT={"eyebrow":"MOINABAD · RANGAREDDY · TELANGANA","hero_title":"Feel better.","hero_emphasis":"Live consciously.","hero_description":"Practical wellness for modern life, with an organic-focused approach to healthier everyday choices.","about_title":"Health consciousness starts with what you do every day.","about_text":"SS Nutritions is a local wellness brand based in Moinabad, focused on helping people make informed, sustainable lifestyle choices.","whatsapp_number":"","contact_heading":"Your wellness journey can start with one conversation.","contact_text":"Tell us what you are looking for and our team can guide you on the next step.","quote":"Wellness is not about changing everything overnight. It is about making better choices, consistently.","published":True}

@app.get("/api/v1/public/business/{slug}/website")
def public_website(slug:str,db:Session=Depends(get_db)):
    t=db.scalar(select(Tenant).where(Tenant.slug==slug.lower(),Tenant.status=="active"))
    if not t: raise HTTPException(404,"Business not found")
    row=db.scalar(select(TenantSetting).where(TenantSetting.tenant_id==t.id,TenantSetting.key=="website_content"))
    tenant_overrides={}
    if row:
        try: tenant_overrides=json.loads(row.value_json) or {}
        except Exception: tenant_overrides={}
    template=_get_site_template(t.industry or "")
    content=_merge_site_content(template, tenant_overrides)
    # tenant name substitution for {name} placeholders
    for k,v in list(content.items()):
        if isinstance(v,str):
            content[k]=v.replace("{name}", t.name or "")
    voice_row=db.scalar(select(TenantSetting).where(TenantSetting.tenant_id==t.id,TenantSetting.key=="agent_voice"))
    agent_voice={"gender":"female"}
    if voice_row:
        try:
            parsed=json.loads(voice_row.value_json)
            agent_voice=parsed if isinstance(parsed,dict) else {"gender":str(parsed).lower()}
        except Exception: pass
    if agent_voice.get("gender") not in ("female","male"): agent_voice["gender"]="female"
    return {
        "business":{
            "id":t.id,"name":t.name,"slug":t.slug,"phone":t.phone,
            "whatsapp_number":t.whatsapp_number,"address":t.address,
            "description":t.description,"industry":t.industry,
            "agent_gender":agent_voice["gender"],
            "features":_feature_config(db, t.id),
        },
        "content":content,
    }

@app.get("/api/v1/tenants/{tenant_id}/website")
def tenant_website(tenant_id,user=Depends(get_current_user),db:Session=Depends(get_db)):
    require_tenant(user,tenant_id)
    row=db.scalar(select(TenantSetting).where(TenantSetting.tenant_id==tenant_id,TenantSetting.key=="website_content"))
    tenant_overrides={}
    if row:
        try: tenant_overrides=json.loads(row.value_json) or {}
        except Exception: tenant_overrides={}
    tenant=db.get(Tenant, tenant_id)
    template=_get_site_template((tenant.industry if tenant else "") or "")
    content=_merge_site_content(template, tenant_overrides)
    # Include tenant name substitution
    for k,v in list(content.items()):
        if isinstance(v,str):
            content[k]=v.replace("{name}", (tenant.name if tenant else "") or "")
    return content

@app.put("/api/v1/tenants/{tenant_id}/website")
def update_website(tenant_id,payload:WebsiteContentUpdate,user=Depends(get_current_user),db:Session=Depends(get_db)):
    require_tenant(user,tenant_id)
    return _set_setting(db,tenant_id,"website_content",payload.model_dump())

@app.get("/api/v1/tenants/{tenant_id}",response_model=TenantOut)
def get_tenant(tenant_id,user=Depends(get_current_user),db:Session=Depends(get_db)):
    require_tenant(user,tenant_id); t=db.get(Tenant,tenant_id)
    if not t: raise HTTPException(404,"Tenant not found")
    return t
@app.put("/api/v1/tenants/{tenant_id}/profile",response_model=TenantOut)
def profile(tenant_id,payload:TenantProfileUpdate,user=Depends(get_current_user),db:Session=Depends(get_db)):
    require_tenant(user,tenant_id); return update_tenant_profile(db,db.get(Tenant,tenant_id),payload.model_dump())
@app.post("/api/v1/tenants/{tenant_id}/services",status_code=201)
def add_service(tenant_id,payload:ServiceCreate,user=Depends(get_current_user),db:Session=Depends(get_db)):
    require_tenant(user,tenant_id); return create_service(db,tenant_id,payload.model_dump())
@app.get("/api/v1/tenants/{tenant_id}/services")
def services(tenant_id,user=Depends(get_current_user),db:Session=Depends(get_db)):
    require_tenant(user,tenant_id); rows=db.scalars(select(Service).where(Service.tenant_id==tenant_id)).all()
    return {"items":[{"id":x.id,"name":x.name,"description":x.description,"price":float(x.price) if x.price is not None else None,"currency":x.currency,"duration_minutes":x.duration_minutes,"is_active":x.is_active} for x in rows]}
@app.post("/api/v1/tenants/{tenant_id}/products",status_code=201)
def add_product(tenant_id,payload:ProductCreate,user=Depends(get_current_user),db:Session=Depends(get_db)):
    require_tenant(user,tenant_id); return create_product(db,tenant_id,payload.model_dump())
@app.get("/api/v1/tenants/{tenant_id}/products")
def products(tenant_id,user=Depends(get_current_user),db:Session=Depends(get_db)):
    require_tenant(user,tenant_id); rows=db.scalars(select(Product).where(Product.tenant_id==tenant_id)).all()
    return {"items":[{"id":x.id,"name":x.name,"description":x.description,"price":float(x.price) if x.price is not None else None,"currency":x.currency,"sku":x.sku,"stock_quantity":x.stock_quantity,"is_active":x.is_active} for x in rows]}

@app.post("/api/v1/customers",status_code=201)
async def customer(payload:CustomerCreate,user=Depends(get_current_user),db:Session=Depends(get_db)):
    require_tenant(user,payload.tenant_id)
    existing=db.scalar(select(Customer).where(Customer.tenant_id==payload.tenant_id,Customer.phone==normalize_phone(payload.phone)))
    try:
        c=upsert_customer(db,payload.tenant_id,payload.phone,payload.name,payload.whatsapp_opt_in,email=payload.email,address=payload.address,notes=payload.notes,tags=payload.tags,source=payload.source)
    except ValueError as exc:
        raise HTTPException(400,str(exc))
    return {"id":c.id,"tenant_id":c.tenant_id,"name":c.name,"phone":c.phone,"email":c.email,"address":c.address,"notes":c.notes,"tags":c.tags,"source":c.source,"portal_token":c.portal_token}
@app.get("/api/v1/tenants/{tenant_id}/customers")
def customers(tenant_id,user=Depends(get_current_user),db:Session=Depends(get_db)):
    require_tenant(user,tenant_id); rows=db.scalars(select(Customer).where(Customer.tenant_id==tenant_id)).all(); return {"items":[{"id":x.id,"name":x.name,"phone":x.phone,"email":x.email,"address":x.address,"notes":x.notes,"tags":x.tags,"source":x.source,"whatsapp_opt_in":x.whatsapp_opt_in,"portal_token":x.portal_token} for x in rows]}

class CustomerUpdate(BaseModel):
    name: str
    email: Optional[str] = None
    address: Optional[str] = None
    notes: Optional[str] = None
    tags: str = ""
    whatsapp_opt_in: Optional[bool] = None

@app.patch("/api/v1/tenants/{tenant_id}/customers/{customer_id}")
def update_customer(tenant_id, customer_id, payload: CustomerUpdate, user=Depends(get_current_user), db:Session=Depends(get_db)):
    require_tenant(user,tenant_id)
    c=db.scalar(select(Customer).where(Customer.id==customer_id,Customer.tenant_id==tenant_id))
    if not c: raise HTTPException(404,"Customer not found")
    for key,value in payload.model_dump(exclude_unset=True).items():
        if value is not None: setattr(c,key,value.strip() if isinstance(value,str) else value)
    db.commit(); db.refresh(c)
    return {"id":c.id,"name":c.name,"phone":c.phone,"email":c.email,"address":c.address,"notes":c.notes,"tags":c.tags,"source":c.source,"whatsapp_opt_in":c.whatsapp_opt_in,"portal_token":c.portal_token}

@app.get("/api/v1/public/customer/{portal_token}")
def public_customer_portal(portal_token, db:Session=Depends(get_db)):
    c=db.scalar(select(Customer).where(Customer.portal_token==portal_token))
    if not c: raise HTTPException(404,"Customer portal not found")
    t=db.get(Tenant,c.tenant_id)
    return {"business":{"name":t.name,"slug":t.slug},"customer":{"name":c.name,"phone":c.phone},"pwa_url":settings.public_app_url+"/customer?business="+t.slug+"&customer="+portal_token}

class LandlineCallRequest(BaseModel):
    caller_phone: str | None = Field(default=None,max_length=32)
    mobile_number: str = Field(min_length=5,max_length=32)
    name: str = Field(min_length=1,max_length=160)
    department: str = "Reception"
    staff_id: str | None = None
    notes: str | None = None

@app.post("/api/v1/tenants/{tenant_id}/telephony/inbound-call",status_code=201)
def inbound_landline_call(tenant_id,payload:LandlineCallRequest,user=Depends(get_current_user),db:Session=Depends(get_db)):
    require_tenant(user,tenant_id)
    try:
        c=upsert_customer(db,tenant_id,payload.mobile_number,payload.name,False,source="landline")
    except ValueError as exc:
        raise HTTPException(400,str(exc))
    call=CallRecord(tenant_id=tenant_id,customer_id=c.id,source="landline",status="connected",department=payload.department,staff_id=payload.staff_id)
    db.add(call); db.commit(); db.refresh(call)
    if payload.notes: call.summary=payload.notes; db.commit()
    t=db.get(Tenant,tenant_id)
    return {"call_id":call.id,"customer_id":c.id,"status":call.status,"department":call.department,"pwa_url":settings.public_app_url+"/customer?business="+t.slug+"&customer="+c.portal_token}

@app.post("/api/v1/tenants/{tenant_id}/customers/{customer_id}/share-pwa")
async def share_customer_pwa(tenant_id,customer_id,user=Depends(get_current_user),db:Session=Depends(get_db)):
    require_tenant(user,tenant_id)
    c=db.scalar(select(Customer).where(Customer.id==customer_id,Customer.tenant_id==tenant_id))
    t=db.get(Tenant,tenant_id)
    if not c or not t: raise HTTPException(404,"Customer not found")
    url=settings.public_app_url+"/customer?business="+t.slug+"&customer="+c.portal_token
    message="Hello "+(c.name or "there")+", thank you for contacting "+t.name+". Continue with your customer portal here: "+url
    if not c.phone: raise HTTPException(409,"Customer phone is required")
    try:
        result=await tenant_whatsapp_adapter(db,tenant_id,settings).send_text(c.phone,message)
    except RuntimeError as exc:
        raise HTTPException(503,str(exc))
    return {"sent":True,"pwa_url":url,"whatsapp":result}
@app.post("/api/v1/webhooks/openwa/{tenant_id}")
async def openwa_webhook(tenant_id:str,request:Request,db:Session=Depends(get_db)):
    raw=await request.body()
    signature=request.headers.get("X-OpenWA-Signature") or request.headers.get("X-Webhook-Signature")
    if not WhatsAppAdapter.verify_webhook(raw,signature,settings.openwa_webhook_secret):
        raise HTTPException(401,"Invalid OpenWA webhook signature")
    try: payload=json.loads(raw.decode("utf-8"))
    except Exception: raise HTTPException(400,"Invalid webhook JSON")
    if payload.get("event")!="message.received": return {"ok":True,"ignored":True}
    data=payload.get("data") or {}
    if data.get("isGroup"): return {"ok":True,"ignored":True}
    phone=str(data.get("senderPhone") or data.get("from") or data.get("chatId") or "").split("@")[0]
    body=str(data.get("body") or "").strip()
    if not phone or not body: return {"ok":True,"ignored":True}
    tenant=db.get(Tenant,tenant_id)
    if not tenant: raise HTTPException(404,"Tenant not found")
    # The first WhatsApp interaction is an identity gate: number is captured from WhatsApp, name must be supplied by the customer.
    existing=db.scalar(select(Customer).where(Customer.tenant_id==tenant_id,Customer.phone==normalize_phone(phone)))
    push_name=((data.get("contact") or {}).get("pushName") or (data.get("contact") or {}).get("name") or "").strip()
    if not existing and not push_name:
        await tenant_whatsapp_adapter(db,tenant_id,settings).send_text(phone,"Welcome to "+tenant.name+"! Before I can assist you, please reply with your name.")
        return {"ok":True,"identity_required":True}
    if not existing:
        try: existing=upsert_customer(db,tenant_id,phone,push_name,True,source="whatsapp")
        except ValueError as exc: raise HTTPException(400,str(exc))
    elif not existing.name and push_name:
        existing.name=push_name; existing.whatsapp_opt_in=True; db.commit()
    # Existing customers may interact freely; new customers must have both mobile + name before AI/business actions.
    result=await generate_reply(db,tenant_id,body,None,"whatsapp")
    reply=result.get("reply") or "Thanks. How can I help you today?"
    await tenant_whatsapp_adapter(db,tenant_id,settings).send_text(existing.phone,reply)
    return {"ok":True,"customer_id":existing.id,"reply":reply}

@app.post("/api/v1/leads",status_code=201)
def lead(payload:LeadCreate,user=Depends(get_current_user),db:Session=Depends(get_db)):
    require_tenant(user,payload.tenant_id); l=create_lead(db,payload.tenant_id,payload.source,payload.customer_id,payload.intent,payload.notes); return {"id":l.id,"status":l.status}
@app.get("/api/v1/tenants/{tenant_id}/leads")
def leads(tenant_id,user=Depends(get_current_user),db:Session=Depends(get_db)):
    require_tenant(user,tenant_id); rows=db.scalars(select(Lead).where(Lead.tenant_id==tenant_id)).all(); return {"items":[{"id":x.id,"customer_id":x.customer_id,"source":x.source,"intent":x.intent,"notes":x.notes,"status":x.status} for x in rows]}

class ChatRequest(BaseModel): tenant_id:str; message:str=Field(min_length=1,max_length=4000); name:str|None=None; phone:str|None=None; conversation_id:str|None=None; channel:str="pwa"

class HoursUpdate(BaseModel):
    items: list[BusinessHourInput]

def require_platform_admin(user:User):
    if user.role not in ("super_admin","platform_admin"): raise HTTPException(403,"Platform admin access required")

@app.post("/api/v1/auth/password-reset/request")
async def password_reset_request(request:Request,payload:PasswordResetRequest,db:Session=Depends(get_db)):
    await auth_rate_limit(request, payload.email)
    user=db.scalar(select(User).where(User.email==payload.email.lower(),User.is_active==True))
    if not user:
        return {"accepted":True}
    tenant=db.get(Tenant,user.tenant_id)
    if not tenant:
        return {"accepted":True}
    now=datetime.utcnow()
    old=db.scalars(select(PasswordResetToken).where(PasswordResetToken.user_id==user.id,PasswordResetToken.used_at.is_(None))).all()
    for row in old:
        row.used_at=now
    raw=secrets.token_urlsafe(32)
    row=PasswordResetToken(
        id=str(uuid.uuid4()),
        user_id=user.id,
        token_hash=hashlib.sha256(raw.encode()).hexdigest(),
        expires_at=now+timedelta(minutes=settings.password_reset_ttl_minutes),
    )
    db.add(row); db.commit()
    await send_password_reset(user,tenant,raw)
    return {"accepted":True}

@app.post("/api/v1/auth/password-reset/confirm")
def password_reset_confirm(payload:PasswordResetConfirm,db:Session=Depends(get_db)):
    digest=hashlib.sha256(payload.token.encode()).hexdigest()
    row=db.scalar(select(PasswordResetToken).where(PasswordResetToken.token_hash==digest))
    now=datetime.utcnow()
    if not row or row.used_at is not None or row.expires_at<=now:
        raise HTTPException(400,"Reset link is invalid or expired")
    user=db.get(User,row.user_id)
    if not user or not user.is_active:
        raise HTTPException(400,"Reset link is invalid")
    user.password_hash=hash_password(payload.password)
    row.used_at=now
    db.commit()
    return {"reset":True}

class TenantStatusUpdate(BaseModel):
    status: str = Field(pattern="^(active|suspended|pending|closed)$")

class PlatformTenantProvisionOut(BaseModel):
    tenant_id: str
    tenant: dict
    owner: dict
    status: str
    notifications: dict = {}

DEFAULT_DEPARTMENTS = {
    "health": ["Administration","Consultation","Customer Support","Sales"],
    "wellness": ["Administration","Consultation","Customer Support","Sales"],
    "dental": ["Reception","Consultation","Treatment","Billing"],
    "restaurant": ["Management","Kitchen","Service","Billing"],
    "hotel": ["Management","Front Office","Housekeeping","Food & Beverage"],
    "salon": ["Management","Reception","Stylist","Billing"],
    "gym": ["Management","Trainers","Membership","Front Desk"],
    "real-estate": ["Management","Sales","Site Visits","Support"],
    "education": ["Administration","Admissions","Teaching","Support"],
}
DEFAULT_PERMISSIONS = ["dashboard.view","customers.view","leads.view","bookings.view","tasks.view"]
ROLE_PRESETS = {
    "owner": ["*"], "admin": ["*"],
    "manager": DEFAULT_PERMISSIONS + ["customers.manage","leads.manage","bookings.manage","staff.view","reports.view"],
    "staff": DEFAULT_PERMISSIONS, "reception": ["dashboard.view","customers.view","leads.view","bookings.view"],
    "sales": ["dashboard.view","customers.view","leads.view","leads.manage","bookings.view"],
    "support": ["dashboard.view","customers.view","leads.view","bookings.view","tasks.view"],
    "billing": ["dashboard.view","customers.view","payments.view","payments.manage"],
}

def provision_defaults(db, tenant, industry):
    key=industry.lower().replace("_","-")
    for name in DEFAULT_DEPARTMENTS.get(key, ["Administration","Sales","Customer Support"]):
        if not db.scalar(select(Department).where(Department.tenant_id==tenant.id,Department.name==name)):
            db.add(Department(tenant_id=tenant.id,name=name))
    for name,permissions in ROLE_PRESETS.items():
        if not db.scalar(select(RoleDefinition).where(RoleDefinition.tenant_id==tenant.id,RoleDefinition.name==name)):
            db.add(RoleDefinition(tenant_id=tenant.id,name=name,permissions_json=json.dumps(permissions),is_system=True))
    db.commit()

@app.post("/api/v1/platform/tenants/provision",response_model=PlatformTenantProvisionOut,status_code=201)
async def platform_provision_tenant(payload:TenantProvisionRequest,user=Depends(get_current_user),db:Session=Depends(get_db)):
    require_platform_admin(user)
    if db.scalar(select(Tenant).where(Tenant.slug==payload.slug.lower())): raise HTTPException(409,"Business slug already exists")
    if db.scalar(select(User).where(User.email==payload.owner_email.lower())): raise HTTPException(409,"Owner email already registered")
    t=create_tenant(db,payload.business_name,payload.slug,payload.industry)
    t.phone=payload.phone; t.whatsapp_number=payload.whatsapp_number; t.address=payload.address
    db.commit(); db.refresh(t)
    owner=create_owner(db,payload.owner_name,payload.owner_email,payload.owner_password,t)
    provision_defaults(db,t,payload.template or payload.industry)
    notification_status=await send_owner_credentials(t,owner,payload.owner_password)
    return {"tenant_id":t.id,"tenant":{"id":t.id,"name":t.name,"slug":t.slug,"industry":t.industry,"status":t.status},"owner":{"id":owner.id,"name":owner.name,"email":owner.email,"role":owner.role},"status":"active","notifications":notification_status}

@app.get("/api/v1/platform/tenants/{tenant_id}")
def platform_tenant_detail(tenant_id,user=Depends(get_current_user),db:Session=Depends(get_db)):
    require_platform_admin(user)
    t=db.get(Tenant,tenant_id)
    if not t: raise HTTPException(404,"Tenant not found")
    return {"id":t.id,"name":t.name,"slug":t.slug,"industry":t.industry,"status":t.status,"phone":t.phone,"whatsapp_number":t.whatsapp_number,"email":t.email,"address":t.address}

@app.get("/api/v1/platform/tenants")
def platform_tenants(user=Depends(get_current_user),db:Session=Depends(get_db)):
    require_platform_admin(user)
    tenants=db.scalars(select(Tenant).order_by(Tenant.created_at.desc())).all()
    return {"items":[
        {"id":t.id,"name":t.name,"slug":t.slug,"industry":t.industry,"status":t.status,"created_at":t.created_at.isoformat()}
        for t in tenants
    ]}

@app.patch("/api/v1/platform/tenants/{tenant_id}/status")
def platform_tenant_status(tenant_id,payload:TenantStatusUpdate,user=Depends(get_current_user),db:Session=Depends(get_db)):
    require_platform_admin(user)
    tenant=db.get(Tenant,tenant_id)
    if not tenant: raise HTTPException(404,"Tenant not found")
    tenant.status=payload.status
    db.commit()
    return {"id":tenant.id,"status":tenant.status}

@app.get("/api/v1/platform/feature-defaults")
def platform_feature_defaults(user=Depends(get_current_user),db:Session=Depends(get_db)):
    require_platform_admin(user)
    row=db.scalar(select(PlatformSetting).where(PlatformSetting.key=="feature_defaults"))
    try: return {"features":{**FEATURE_DEFAULTS,**(json.loads(row.value_json) if row else {})}}
    except Exception: return {"features":FEATURE_DEFAULTS}

@app.put("/api/v1/platform/feature-defaults")
def update_platform_feature_defaults(payload:FeatureUpdate,user=Depends(get_current_user),db:Session=Depends(get_db)):
    require_platform_admin(user)
    cfg=dict(FEATURE_DEFAULTS)
    for key,value in payload.features.items():
        if key in FEATURE_DEFAULTS: cfg[key]=bool(value)
    row=db.scalar(select(PlatformSetting).where(PlatformSetting.key=="feature_defaults"))
    if not row: row=PlatformSetting(key="feature_defaults",value_json=json.dumps(cfg)); db.add(row)
    else: row.value_json=json.dumps(cfg)
    db.commit()
    return {"features":cfg}


@app.get("/api/v1/tenants/{tenant_id}/routing-rules")
def list_routing_rules(tenant_id,user=Depends(get_current_user),db:Session=Depends(get_db)):
    require_tenant(user,tenant_id)
    rows=db.scalars(select(RoutingRule).where(RoutingRule.tenant_id==tenant_id).order_by(RoutingRule.priority,RoutingRule.name)).all()
    return {"items":[{"id":x.id,"name":x.name,"intent":x.intent,"trigger_keywords":x.trigger_keywords,"department_id":x.department_id,"staff_id":x.staff_id,"priority":x.priority,"urgency":x.urgency,"action":x.action,"is_active":x.is_active} for x in rows]}

@app.post("/api/v1/tenants/{tenant_id}/routing-rules",status_code=201)
def create_routing_rule(tenant_id,payload:RoutingRulePayload,user=Depends(get_current_user),db:Session=Depends(get_db)):
    require_tenant(user,tenant_id)
    if payload.department_id and not db.scalar(select(Department).where(Department.id==payload.department_id,Department.tenant_id==tenant_id)): raise HTTPException(400,"Invalid department")
    if payload.staff_id and not db.scalar(select(StaffMember).where(StaffMember.id==payload.staff_id,StaffMember.tenant_id==tenant_id)): raise HTTPException(400,"Invalid staff member")
    x=RoutingRule(tenant_id=tenant_id,**payload.model_dump()); db.add(x); db.commit(); db.refresh(x)
    return {"id":x.id,"name":x.name,"intent":x.intent,"trigger_keywords":x.trigger_keywords,"department_id":x.department_id,"staff_id":x.staff_id,"priority":x.priority,"urgency":x.urgency,"action":x.action,"is_active":x.is_active}

@app.put("/api/v1/tenants/{tenant_id}/routing-rules/{rule_id}")
def update_routing_rule(tenant_id,rule_id,payload:RoutingRulePayload,user=Depends(get_current_user),db:Session=Depends(get_db)):
    require_tenant(user,tenant_id)
    x=db.scalar(select(RoutingRule).where(RoutingRule.id==rule_id,RoutingRule.tenant_id==tenant_id))
    if not x: raise HTTPException(404,"Routing rule not found")
    for key,value in payload.model_dump().items(): setattr(x,key,value)
    db.commit()
    return {"id":x.id,"name":x.name,"intent":x.intent,"trigger_keywords":x.trigger_keywords,"department_id":x.department_id,"staff_id":x.staff_id,"priority":x.priority,"urgency":x.urgency,"action":x.action,"is_active":x.is_active}

@app.delete("/api/v1/tenants/{tenant_id}/routing-rules/{rule_id}")
def delete_routing_rule(tenant_id,rule_id,user=Depends(get_current_user),db:Session=Depends(get_db)):
    require_tenant(user,tenant_id)
    x=db.scalar(select(RoutingRule).where(RoutingRule.id==rule_id,RoutingRule.tenant_id==tenant_id))
    if not x: raise HTTPException(404,"Routing rule not found")
    db.delete(x); db.commit()
    return {"deleted":True}

@app.get("/api/v1/tenants/{tenant_id}/reception/alerts")
def list_reception_alerts(tenant_id,status:str|None=None,limit:int=50,user=Depends(get_current_user),db:Session=Depends(get_db)):
    require_tenant(user,tenant_id)
    q=select(ReceptionAlert).where(ReceptionAlert.tenant_id==tenant_id).order_by(ReceptionAlert.created_at.desc()).limit(min(max(limit,1),200))
    if status: q=q.where(ReceptionAlert.status==status)
    rows=db.scalars(q).all()
    return {"items":[{"id":x.id,"customer_id":x.customer_id,"call_id":x.call_id,"department_id":x.department_id,"staff_id":x.staff_id,"category":x.category,"priority":x.priority,"title":x.title,"message":x.message,"status":x.status,"acknowledged_at":x.acknowledged_at,"created_at":x.created_at} for x in rows]}

@app.post("/api/v1/tenants/{tenant_id}/reception/alerts",status_code=201)
def create_reception_alert(tenant_id,payload:ReceptionAlertPayload,user=Depends(get_current_user),db:Session=Depends(get_db)):
    require_tenant(user,tenant_id)
    x=ReceptionAlert(tenant_id=tenant_id,**payload.model_dump()); db.add(x); db.flush()
    db.add(InteractionEvent(tenant_id=tenant_id,customer_id=x.customer_id,call_id=x.call_id,channel="reception",event_type="reception_alert_created",payload_json=json.dumps({"alert_id":x.id,"priority":x.priority,"category":x.category},ensure_ascii=False)))
    db.commit(); db.refresh(x)
    return {"id":x.id,"status":x.status,"priority":x.priority}

@app.post("/api/v1/tenants/{tenant_id}/reception/alerts/{alert_id}/ack")
def acknowledge_reception_alert(tenant_id,alert_id,user=Depends(get_current_user),db:Session=Depends(get_db)):
    require_tenant(user,tenant_id)
    x=db.scalar(select(ReceptionAlert).where(ReceptionAlert.id==alert_id,ReceptionAlert.tenant_id==tenant_id))
    if not x: raise HTTPException(404,"Alert not found")
    x.status="acknowledged"; x.acknowledged_at=datetime.utcnow()
    db.add(InteractionEvent(tenant_id=tenant_id,customer_id=x.customer_id,call_id=x.call_id,channel="reception",event_type="reception_alert_acknowledged",payload_json=json.dumps({"alert_id":x.id},ensure_ascii=False)))
    db.commit()
    return {"id":x.id,"status":x.status,"acknowledged_at":x.acknowledged_at}

@app.get("/api/v1/tenants/{tenant_id}/customers/{customer_id}/interaction-timeline")
def interaction_timeline(tenant_id,customer_id,user=Depends(get_current_user),db:Session=Depends(get_db)):
    require_tenant(user,tenant_id)
    if not db.scalar(select(Customer.id).where(Customer.id==customer_id,Customer.tenant_id==tenant_id)): raise HTTPException(404,"Customer not found")
    rows=db.scalars(select(InteractionEvent).where(InteractionEvent.tenant_id==tenant_id,InteractionEvent.customer_id==customer_id).order_by(InteractionEvent.created_at.desc()).limit(200)).all()
    return {"items":[{"id":x.id,"call_id":x.call_id,"channel":x.channel,"event_type":x.event_type,"payload":json.loads(x.payload_json or "{}"),"created_at":x.created_at} for x in rows]}

@app.get("/api/v1/tenants/{tenant_id}/departments")
def list_departments(tenant_id,user=Depends(get_current_user),db:Session=Depends(get_db)):
    require_tenant(user,tenant_id)
    rows=db.scalars(select(Department).where(Department.tenant_id==tenant_id).order_by(Department.name)).all()
    return {"items":[{"id":x.id,"name":x.name,"description":x.description,"skills":x.skills,"is_active":x.is_active} for x in rows]}

@app.post("/api/v1/tenants/{tenant_id}/departments",status_code=201)
def create_department(tenant_id,payload:DepartmentCreate,user=Depends(get_current_user),db:Session=Depends(get_db)):
    require_tenant(user,tenant_id)
    x=Department(tenant_id=tenant_id,**payload.model_dump()); db.add(x); db.commit(); db.refresh(x)
    return {"id":x.id,"name":x.name,"description":x.description,"skills":x.skills,"is_active":x.is_active}

@app.get("/api/v1/tenants/{tenant_id}/roles")
def list_roles(tenant_id,user=Depends(get_current_user),db:Session=Depends(get_db)):
    require_tenant(user,tenant_id)
    rows=db.scalars(select(RoleDefinition).where(RoleDefinition.tenant_id==tenant_id).order_by(RoleDefinition.name)).all()
    return {"items":[{"id":x.id,"name":x.name,"permissions":json.loads(x.permissions_json or "[]"),"is_system":x.is_system} for x in rows]}

@app.post("/api/v1/tenants/{tenant_id}/roles",status_code=201)
def create_role(tenant_id,payload:RoleDefinitionCreate,user=Depends(get_current_user),db:Session=Depends(get_db)):
    require_tenant(user,tenant_id)
    if db.scalar(select(RoleDefinition).where(RoleDefinition.tenant_id==tenant_id,RoleDefinition.name==payload.name)): raise HTTPException(409,"Role already exists")
    x=RoleDefinition(tenant_id=tenant_id,name=payload.name,permissions_json=json.dumps(payload.permissions),is_system=False)
    db.add(x); db.commit(); db.refresh(x)
    return {"id":x.id,"name":x.name,"permissions":payload.permissions,"is_system":False}

@app.get("/api/v1/tenants/{tenant_id}/staff")
def list_staff(tenant_id,user=Depends(get_current_user),db:Session=Depends(get_db)):
    require_tenant(user,tenant_id)
    rows=db.scalars(select(StaffMember).where(StaffMember.tenant_id==tenant_id).order_by(StaffMember.name)).all()
    result=[]
    for x in rows:
        u=db.get(User,x.user_id) if x.user_id else None
        d=db.get(Department,x.department_id) if x.department_id else None
        result.append({"id":x.id,"name":x.name,"email":u.email if u else None,"role":u.role if u else "staff","department_id":x.department_id,"department_name":d.name if d else None,"skills":x.skills,"is_active":x.is_active,"is_available":x.is_available})
    return {"items":result}

@app.post("/api/v1/tenants/{tenant_id}/staff",status_code=201)
def create_staff(tenant_id,payload:StaffCreate,user=Depends(get_current_user),db:Session=Depends(get_db)):
    require_tenant(user,tenant_id)
    if db.scalar(select(User).where(User.email==payload.email.lower())): raise HTTPException(409,"Email already registered")
    if payload.department_id and not db.scalar(select(Department).where(Department.id==payload.department_id,Department.tenant_id==tenant_id)): raise HTTPException(400,"Invalid department")
    if not db.scalar(select(RoleDefinition).where(RoleDefinition.tenant_id==tenant_id,RoleDefinition.name==payload.role)): raise HTTPException(400,"Invalid role")
    u=User(id=str(uuid.uuid4()),name=payload.name,email=payload.email.lower(),password_hash=hash_password(payload.password),tenant_id=tenant_id,role=payload.role)
    db.add(u); db.flush()
    s=StaffMember(tenant_id=tenant_id,user_id=u.id,name=payload.name,department_id=payload.department_id,skills=payload.skills)
    db.add(s); db.commit(); db.refresh(s)
    return {"id":s.id,"name":s.name,"email":u.email,"role":u.role,"department_id":s.department_id}

@app.patch("/api/v1/tenants/{tenant_id}/staff/{staff_id}")
def update_staff(tenant_id,staff_id,payload:StaffUpdate,user=Depends(get_current_user),db:Session=Depends(get_db)):
    require_tenant(user,tenant_id)
    s=db.scalar(select(StaffMember).where(StaffMember.id==staff_id,StaffMember.tenant_id==tenant_id))
    if not s: raise HTTPException(404,"Staff member not found")
    u=db.get(User,s.user_id) if s.user_id else None
    if payload.department_id is not None and not db.scalar(select(Department).where(Department.id==payload.department_id,Department.tenant_id==tenant_id)): raise HTTPException(400,"Invalid department")
    if payload.role is not None and not db.scalar(select(RoleDefinition).where(RoleDefinition.tenant_id==tenant_id,RoleDefinition.name==payload.role)): raise HTTPException(400,"Invalid role")
    if payload.role is not None and u: u.role=payload.role
    for key in ("department_id","skills","is_active","is_available"):
        value=getattr(payload,key)
        if value is not None: setattr(s,key,value)
    db.commit()
    return {"id":s.id,"role":u.role if u else None,"department_id":s.department_id,"is_active":s.is_active,"is_available":s.is_available}

class BusinessBrainUpdate(BaseModel):
    instructions: str = Field(default="", max_length=20000)
    publish_website_to_agent: bool = True

@app.get("/api/v1/tenants/{tenant_id}/business-brain")
def get_business_brain(tenant_id,user=Depends(get_current_user),db:Session=Depends(get_db)):
    require_tenant(user,tenant_id)
    policy=tenant_policy(db,tenant_id)
    brain=policy.get("business_brain") or {}
    return {
        "instructions": brain.get("instructions",""),
        "publish_website_to_agent": brain.get("publish_website_to_agent",True),
        "features": policy.get("features",{}),
        "website": policy.get("website",{}),
        "services": [{"id":x.id,"name":x.name,"price":float(x.price) if x.price is not None else None,"currency":x.currency,"active":x.is_active} for x in policy.get("services",[])],
        "products": [{"id":x.id,"name":x.name,"price":float(x.price) if x.price is not None else None,"currency":x.currency,"active":x.is_active} for x in policy.get("products",[])],
    }

@app.put("/api/v1/tenants/{tenant_id}/business-brain")
def update_business_brain(tenant_id,payload:BusinessBrainUpdate,user=Depends(get_current_user),db:Session=Depends(get_db)):
    require_tenant(user,tenant_id)
    value={"instructions":payload.instructions.strip(),"publish_website_to_agent":payload.publish_website_to_agent}
    _set_setting(db,tenant_id,"business_brain",value)
    return {"saved":True,**value}

@app.get("/api/v1/tenants/{tenant_id}/features")
def tenant_features(tenant_id,user=Depends(get_current_user),db:Session=Depends(get_db)):
    require_tenant(user,tenant_id); return {"features":_feature_config(db,tenant_id),"games":GAME_CATALOG}

@app.put("/api/v1/tenants/{tenant_id}/features")
def update_features(tenant_id,payload:FeatureUpdate,user=Depends(get_current_user),db:Session=Depends(get_db)):
    require_tenant(user,tenant_id)
    cfg=_feature_config(db,tenant_id)
    for key,value in payload.features.items():
        if key in FEATURE_DEFAULTS: cfg[key]=bool(value)
    _set_setting(db,tenant_id,"features",cfg)
    return {"features":cfg,"games":GAME_CATALOG}

@app.get("/api/v1/tenants/{tenant_id}/review-settings")
def get_review_settings(tenant_id,user=Depends(get_current_user),db:Session=Depends(get_db)):
    require_tenant(user,tenant_id)
    row=db.scalar(select(TenantSetting).where(TenantSetting.tenant_id==tenant_id,TenantSetting.key=="google_review"))
    try: return json.loads(row.value_json) if row else {"review_url":""}
    except Exception: return {"review_url":""}

@app.put("/api/v1/tenants/{tenant_id}/review-settings")
def set_review_settings(tenant_id,payload:GoogleReviewUpdate,user=Depends(get_current_user),db:Session=Depends(get_db)):
    require_tenant(user,tenant_id); return _set_setting(db,tenant_id,"google_review",{"review_url":payload.review_url or ""})

@app.get("/api/v1/tenants/{tenant_id}/menu")
def tenant_menu(tenant_id,user=Depends(get_current_user),db:Session=Depends(get_db)):
    require_tenant(user,tenant_id)
    cats=db.scalars(select(MenuCategory).where(MenuCategory.tenant_id==tenant_id,MenuCategory.is_active==True).order_by(MenuCategory.sort_order)).all()
    items=db.scalars(select(MenuItem).where(MenuItem.tenant_id==tenant_id,MenuItem.is_active==True).order_by(MenuItem.sort_order)).all()
    return {"categories":[{"id":x.id,"name":x.name,"sort_order":x.sort_order} for x in cats],"items":[{"id":x.id,"category_id":x.category_id,"name":x.name,"description":x.description,"price":x.price,"currency":x.currency,"image_url":x.image_url,"is_available":x.is_available} for x in items]}

@app.post("/api/v1/tenants/{tenant_id}/menu/categories",status_code=201)
def add_menu_category(tenant_id,payload:MenuCategoryCreate,user=Depends(get_current_user),db:Session=Depends(get_db)):
    require_tenant(user,tenant_id); x=MenuCategory(tenant_id=tenant_id,**payload.model_dump()); db.add(x); db.commit(); db.refresh(x); return {"id":x.id,"name":x.name}

@app.post("/api/v1/tenants/{tenant_id}/menu/items",status_code=201)
def add_menu_item(tenant_id,payload:MenuItemCreate,user=Depends(get_current_user),db:Session=Depends(get_db)):
    require_tenant(user,tenant_id)
    if payload.category_id and not db.scalar(select(MenuCategory).where(MenuCategory.id==payload.category_id,MenuCategory.tenant_id==tenant_id)): raise HTTPException(400,"Invalid category")
    x=MenuItem(tenant_id=tenant_id,**payload.model_dump()); db.add(x); db.commit(); db.refresh(x); return {"id":x.id,"name":x.name,"price":x.price}

@app.patch("/api/v1/tenants/{tenant_id}/menu/items/{item_id}")
def update_menu_item(tenant_id,item_id,payload:dict,user=Depends(get_current_user),db:Session=Depends(get_db)):
    require_tenant(user,tenant_id)
    x=db.scalar(select(MenuItem).where(MenuItem.id==item_id,MenuItem.tenant_id==tenant_id))
    if not x: raise HTTPException(404,"Menu item not found")
    for key in ["name","description","price","category_id","image_url","is_active","is_available"]:
        if key in payload: setattr(x,key,payload[key])
    db.commit(); return {"id":x.id,"updated":True}

@app.get("/api/v1/tenants/{tenant_id}/loyalty-rules")
def get_loyalty_rules(tenant_id,user=Depends(get_current_user),db:Session=Depends(get_db)):
    require_tenant(user,tenant_id)
    rows=db.scalars(select(LoyaltyRule).where(LoyaltyRule.tenant_id==tenant_id)).all()
    return {"items":[{"id":x.id,"event_type":x.event_type,"name":x.name,"points":x.points,"is_active":x.is_active,"config":json.loads(x.config_json or "{}")} for x in rows]}

@app.post("/api/v1/tenants/{tenant_id}/loyalty-rules",status_code=201)
def create_loyalty_rule(tenant_id,payload:LoyaltyRuleCreate,user=Depends(get_current_user),db:Session=Depends(get_db)):
    require_tenant(user,tenant_id)
    if not _feature_config(db, tenant_id).get("loyalty", True): raise HTTPException(403, "Loyalty program is disabled for this business")
    x=LoyaltyRule(tenant_id=tenant_id,event_type=payload.event_type,name=payload.name,points=payload.points,is_active=payload.is_active,config_json=json.dumps(payload.config))
    db.add(x); db.commit(); db.refresh(x); return {"id":x.id}

@app.get("/api/v1/tenants/{tenant_id}/loyalty")
def tenant_loyalty_summary(tenant_id, customer_id: str | None = Query(default=None), user=Depends(get_current_user), db: Session=Depends(get_db)):
    require_tenant(user, tenant_id)
    enabled = _feature_config(db, tenant_id).get("loyalty", True)
    if customer_id:
        customer = db.scalar(select(Customer).where(Customer.id == customer_id, Customer.tenant_id == tenant_id))
        if not customer: raise HTTPException(404, "Customer not found")
        transactions = db.scalars(select(LoyaltyTransaction).where(LoyaltyTransaction.tenant_id == tenant_id, LoyaltyTransaction.customer_id == customer_id).order_by(LoyaltyTransaction.created_at.desc())).all()
        balance = sum(x.points for x in transactions)
        return {"enabled": enabled, "customer_id": customer_id, "balance": balance, "transactions": [{"id": x.id, "points": x.points, "reason": x.reason, "reference_id": x.reference_id, "created_at": x.created_at.isoformat()} for x in transactions[:100]]}
    return {"enabled": enabled}

@app.patch("/api/v1/tenants/{tenant_id}/loyalty-rules/{rule_id}")
def update_loyalty_rule(tenant_id, rule_id, payload: LoyaltyRuleUpdate, user=Depends(get_current_user), db: Session=Depends(get_db)):
    require_tenant(user, tenant_id)
    if not _feature_config(db, tenant_id).get("loyalty", True): raise HTTPException(403, "Loyalty program is disabled for this business")
    row = db.scalar(select(LoyaltyRule).where(LoyaltyRule.id == rule_id, LoyaltyRule.tenant_id == tenant_id))
    if not row: raise HTTPException(404, "Loyalty rule not found")
    for key in ("name", "points", "is_active"):
        value = getattr(payload, key)
        if value is not None: setattr(row, key, value)
    if payload.config is not None: row.config_json = json.dumps(payload.config)
    db.commit(); db.refresh(row)
    return {"id": row.id, "event_type": row.event_type, "name": row.name, "points": row.points, "is_active": row.is_active, "config": json.loads(row.config_json or "{}")}

@app.get("/api/v1/tenants/{tenant_id}/loyalty-rewards")
def list_loyalty_rewards(tenant_id, user=Depends(get_current_user), db: Session=Depends(get_db)):
    require_tenant(user, tenant_id)
    rows = db.scalars(select(LoyaltyReward).where(LoyaltyReward.tenant_id == tenant_id).order_by(LoyaltyReward.points_cost)).all()
    return {"enabled": _feature_config(db, tenant_id).get("loyalty", True), "items": [{"id": x.id, "name": x.name, "points_cost": x.points_cost, "description": x.description, "is_active": x.is_active} for x in rows]}

@app.post("/api/v1/tenants/{tenant_id}/loyalty-rewards", status_code=201)
def create_loyalty_reward(tenant_id, payload: LoyaltyRewardCreate, user=Depends(get_current_user), db: Session=Depends(get_db)):
    require_tenant(user, tenant_id)
    if not _feature_config(db, tenant_id).get("loyalty", True): raise HTTPException(403, "Loyalty program is disabled for this business")
    x = LoyaltyReward(tenant_id=tenant_id, **payload.model_dump()); db.add(x); db.commit(); db.refresh(x)
    return {"id": x.id, "name": x.name, "points_cost": x.points_cost, "description": x.description, "is_active": x.is_active}

@app.patch("/api/v1/tenants/{tenant_id}/loyalty-rewards/{reward_id}")
def update_loyalty_reward(tenant_id, reward_id, payload: LoyaltyRewardUpdate, user=Depends(get_current_user), db: Session=Depends(get_db)):
    require_tenant(user, tenant_id)
    if not _feature_config(db, tenant_id).get("loyalty", True): raise HTTPException(403, "Loyalty program is disabled for this business")
    row = db.scalar(select(LoyaltyReward).where(LoyaltyReward.id == reward_id, LoyaltyReward.tenant_id == tenant_id))
    if not row: raise HTTPException(404, "Loyalty reward not found")
    for key in ("name", "points_cost", "description", "is_active"):
        value = getattr(payload, key)
        if value is not None: setattr(row, key, value)
    db.commit(); db.refresh(row)
    return {"id": row.id, "name": row.name, "points_cost": row.points_cost, "description": row.description, "is_active": row.is_active}

@app.post("/api/v1/tenants/{tenant_id}/loyalty-redeem")
def redeem_loyalty_reward(tenant_id, payload: LoyaltyRedeemRequest, user=Depends(get_current_user), db: Session=Depends(get_db)):
    require_tenant(user, tenant_id)
    if not _feature_config(db, tenant_id).get("loyalty", True): raise HTTPException(403, "Loyalty program is disabled for this business")
    customer = db.scalar(select(Customer).where(Customer.id == payload.customer_id, Customer.tenant_id == tenant_id))
    reward = db.scalar(select(LoyaltyReward).where(LoyaltyReward.id == payload.reward_id, LoyaltyReward.tenant_id == tenant_id, LoyaltyReward.is_active == True))
    if not customer: raise HTTPException(404, "Customer not found")
    if not reward: raise HTTPException(404, "Reward not found")
    balance = db.scalar(select(__import__("sqlalchemy").func.coalesce(__import__("sqlalchemy").func.sum(LoyaltyTransaction.points), 0)).where(LoyaltyTransaction.tenant_id == tenant_id, LoyaltyTransaction.customer_id == customer.id)) or 0
    if balance < reward.points_cost: raise HTTPException(409, "Insufficient loyalty points")
    tx = LoyaltyTransaction(tenant_id=tenant_id, customer_id=customer.id, points=-reward.points_cost, reason="redeem:" + reward.id, reference_id=reward.id)
    db.add(tx); db.commit(); db.refresh(tx)
    return {"redeemed": True, "reward_id": reward.id, "points_spent": reward.points_cost, "balance": balance - reward.points_cost, "transaction_id": tx.id}

@app.get("/api/v1/tenants/{tenant_id}/business-hours")
def get_business_hours(tenant_id,user=Depends(get_current_user),db:Session=Depends(get_db)):
    require_tenant(user,tenant_id)
    rows=ensure_default_hours(db,tenant_id)
    t=db.get(Tenant,tenant_id)
    return {"items":[{"weekday":x.weekday,"open_time":x.open_time.strftime("%H:%M"),"close_time":x.close_time.strftime("%H:%M"),"is_closed":x.is_closed,"slot_interval_minutes":x.slot_interval_minutes} for x in rows],
            "queue":{"enabled":t.queue_enabled,"threshold":t.queue_threshold,"avg_service_minutes":t.queue_avg_service_minutes}}

@app.put("/api/v1/tenants/{tenant_id}/business-hours")
def set_business_hours(tenant_id,payload:HoursUpdate,user=Depends(get_current_user),db:Session=Depends(get_db)):
    require_tenant(user,tenant_id)
    if len(payload.items)!=7: raise HTTPException(400,"Provide all 7 weekdays")
    existing={x.weekday:x for x in db.scalars(select(BusinessHour).where(BusinessHour.tenant_id==tenant_id)).all()}
    for item in payload.items:
        try: op=time.fromisoformat(item.open_time); cl=time.fromisoformat(item.close_time)
        except ValueError: raise HTTPException(400,"Time must use HH:MM")
        if not item.is_closed and cl<=op: raise HTTPException(400,"Closing time must be after opening time")
        row=existing.get(item.weekday)
        if not row: row=BusinessHour(tenant_id=tenant_id,weekday=item.weekday); db.add(row)
        row.open_time=op; row.close_time=cl; row.is_closed=item.is_closed; row.slot_interval_minutes=item.slot_interval_minutes
    db.commit()
    return get_business_hours(tenant_id,user,db)

@app.put("/api/v1/tenants/{tenant_id}/queue-settings")
def set_queue_settings(tenant_id,payload:QueueSettingsInput,user=Depends(get_current_user),db:Session=Depends(get_db)):
    require_tenant(user,tenant_id)
    t=db.get(Tenant,tenant_id)
    t.queue_enabled=payload.queue_enabled; t.queue_threshold=payload.queue_threshold; t.queue_avg_service_minutes=payload.queue_avg_service_minutes
    db.commit()
    return {"enabled":t.queue_enabled,"threshold":t.queue_threshold,"avg_service_minutes":t.queue_avg_service_minutes}

def _appointment_out(a,tenant,db,queue=None):
    service=db.get(Service,a.service_id) if a.service_id else None
    staff=db.get(StaffMember,a.staff_id) if a.staff_id else None
    return {"id":a.id,"customer_id":a.customer_id,"service_id":a.service_id,"service_name":service.name if service else None,
            "staff_id":a.staff_id,"staff_name":staff.name if staff else None,
            "starts_at":a.starts_at.isoformat(),"ends_at":a.ends_at.isoformat(),"timezone":tenant.timezone,
            "status":a.status,"source":a.source,"notes":a.notes,"queue_token":a.queue_token,"queue_status":a.queue_status,
            "queue":({"token":queue.token,"status":queue.status,"people_ahead":queue.people_ahead,"estimated_wait_minutes":queue.estimated_wait_minutes} if queue else None)}

@app.get("/api/v1/tenants/{tenant_id}/availability")
def availability(tenant_id,service_id:str,date_value:str=Query(alias="date"),staff_id:str|None=None,user=Depends(get_current_user),db:Session=Depends(get_db)):
    require_tenant(user,tenant_id)
    try: day=date.fromisoformat(date_value)
    except ValueError: raise HTTPException(400,"date must be YYYY-MM-DD")
    t=db.get(Tenant,tenant_id)
    try: slots=available_slots(db,t,service_id,day,staff_id)
    except ValueError as e: raise HTTPException(400,str(e))
    return {"date":date_value,"timezone":t.timezone,"service_id":service_id,"slots":slots}

@app.post("/api/v1/tenants/{tenant_id}/appointments",status_code=201)
def create_manual_appointment(tenant_id,payload:AppointmentCreate,user=Depends(get_current_user),db:Session=Depends(get_db)):
    require_tenant(user,tenant_id)
    t=db.get(Tenant,tenant_id)
    customer=db.get(Customer,payload.customer_id) if payload.customer_id else None
    if customer and customer.tenant_id!=tenant_id: raise HTTPException(403,"Customer access denied")
    if not customer:
        if not payload.phone: raise HTTPException(400,"customer_id or phone is required")
        customer=upsert_customer(db,tenant_id,payload.phone,payload.name,False,source=payload.source)
    service=db.scalar(select(Service).where(Service.id==payload.service_id,Service.tenant_id==tenant_id,Service.is_active==True))
    if not service: raise HTTPException(404,"Service not found")
    try: a,q=create_appointment(db,t,customer,service,payload.starts_at,payload.source,payload.staff_id,payload.notes,payload.queue_if_busy,payload.force_queue)
    except ValueError as e: raise HTTPException(409,str(e))
    return _appointment_out(a,t,db,q)

@app.get("/api/v1/tenants/{tenant_id}/appointments")
def appointments(tenant_id,date_value:str|None=Query(default=None,alias="date"),user=Depends(get_current_user),db:Session=Depends(get_db)):
    require_tenant(user,tenant_id); t=db.get(Tenant,tenant_id)
    q=select(Appointment).where(Appointment.tenant_id==tenant_id)
    if date_value:
        try: day=date.fromisoformat(date_value)
        except ValueError: raise HTTPException(400,"date must be YYYY-MM-DD")
        from datetime import time as _time; start=datetime.combine(day,_time.min); end=start+timedelta(days=1)
        from .booking import local_to_utc_naive
        q=q.where(Appointment.starts_at>=local_to_utc_naive(start,t.timezone),Appointment.starts_at<local_to_utc_naive(end,t.timezone))
    rows=db.scalars(q.order_by(Appointment.starts_at)).all()
    return {"items":[_appointment_out(a,t,db,db.scalar(select(QueueEntry).where(QueueEntry.appointment_id==a.id))) for a in rows]}

@app.patch("/api/v1/tenants/{tenant_id}/appointments/{appointment_id}")
def update_appointment_status(tenant_id,appointment_id,payload:AppointmentStatusUpdate,user=Depends(get_current_user),db:Session=Depends(get_db)):
    require_tenant(user,tenant_id); a=db.scalar(select(Appointment).where(Appointment.id==appointment_id,Appointment.tenant_id==tenant_id))
    if not a: raise HTTPException(404,"Appointment not found")
    a.status=payload.status
    q=db.scalar(select(QueueEntry).where(QueueEntry.appointment_id==a.id))
    if q:
        if payload.status=="checked_in": q.status="waiting"; a.queue_status="waiting"
        elif payload.status=="serving": q.status="serving"; q.called_at=datetime.utcnow(); a.queue_status="serving"
        elif payload.status in ("completed","cancelled","no_show"): q.status=payload.status; q.completed_at=datetime.utcnow(); a.queue_status=payload.status
    db.commit()
    if q: queue_snapshot(db,db.get(Tenant,tenant_id),q.queue_date)
    return _appointment_out(a,db.get(Tenant,tenant_id),db,q)

@app.post("/api/v1/tenants/{tenant_id}/appointments/{appointment_id}/queue")
def appointment_queue_checkin(tenant_id,appointment_id,payload:QueueCheckIn,user=Depends(get_current_user),db:Session=Depends(get_db)):
    require_tenant(user,tenant_id); a=db.scalar(select(Appointment).where(Appointment.id==appointment_id,Appointment.tenant_id==tenant_id))
    if not a: raise HTTPException(404,"Appointment not found")
    t=db.get(Tenant,tenant_id)
    q=db.scalar(select(QueueEntry).where(QueueEntry.appointment_id==a.id))
    if not q:
        from .booking import utc_naive_to_local,next_queue_token
        day=utc_naive_to_local(a.starts_at,t.timezone).date()
        seq,token=next_queue_token(db,tenant_id,day)
        q=QueueEntry(tenant_id=tenant_id,appointment_id=a.id,customer_id=a.customer_id,queue_date=day,sequence=seq,token=token,status="waiting")
        db.add(q); a.queue_token=token; a.queue_status="waiting"
    a.status="checked_in"; q.status="waiting"; db.commit(); queue_snapshot(db,t,q.queue_date); db.refresh(q)
    return _appointment_out(a,t,db,q)

@app.get("/api/v1/tenants/{tenant_id}/queue")
def tenant_queue(tenant_id,date_value:str|None=Query(default=None,alias="date"),user=Depends(get_current_user),db:Session=Depends(get_db)):
    require_tenant(user,tenant_id); t=db.get(Tenant,tenant_id)
    day=date.fromisoformat(date_value) if date_value else datetime.utcnow().date()
    rows=queue_snapshot(db,t,day)
    return {"date":day.isoformat(),"items":[{"id":q.id,"appointment_id":q.appointment_id,"token":q.token,"status":q.status,"people_ahead":q.people_ahead,"estimated_wait_minutes":q.estimated_wait_minutes,"customer_id":q.customer_id} for q in rows]}

@app.get("/api/v1/public/business/{slug}/availability")
def public_availability(slug,service_id:str,date_value:str=Query(alias="date"),db:Session=Depends(get_db)):
    t=db.scalar(select(Tenant).where(Tenant.slug==slug.lower()))
    if not t: raise HTTPException(404,"Business not found")
    try: day=date.fromisoformat(date_value)
    except ValueError: raise HTTPException(400,"date must be YYYY-MM-DD")
    try: slots=available_slots(db,t,service_id,day)
    except ValueError as e: raise HTTPException(400,str(e))
    return {"business":t.name,"timezone":t.timezone,"date":date_value,"slots":slots}

@app.post("/api/v1/public/business/{slug}/appointments",status_code=201)
def public_appointment(slug,payload:AppointmentCreate,db:Session=Depends(get_db)):
    t=db.scalar(select(Tenant).where(Tenant.slug==slug.lower()))
    if not t: raise HTTPException(404,"Business not found")
    if not _feature_config(db,t.id).get("bookings",True): raise HTTPException(403,"Bookings are not available for this business")
    if not payload.phone and not payload.customer_id: raise HTTPException(400,"Phone is required for a public booking")
    customer=db.get(Customer,payload.customer_id) if payload.customer_id else None
    if customer and customer.tenant_id!=t.id: raise HTTPException(403,"Customer access denied")
    if not customer: customer=upsert_customer(db,t.id,payload.phone,payload.name,False,source=payload.source or "pwa")
    service=db.scalar(select(Service).where(Service.id==payload.service_id,Service.tenant_id==t.id,Service.is_active==True))
    if not service: raise HTTPException(404,"Service not found")
    try: a,q=create_appointment(db,t,customer,service,payload.starts_at,payload.source or "pwa",payload.staff_id,payload.notes,payload.queue_if_busy,payload.force_queue)
    except ValueError as e: raise HTTPException(409,str(e))
    return _appointment_out(a,t,db,q)

@app.get("/api/v1/public/business/{slug}/queue/{appointment_id}")
def public_queue(slug,appointment_id,db:Session=Depends(get_db)):
    t=db.scalar(select(Tenant).where(Tenant.slug==slug.lower()))
    if not t: raise HTTPException(404,"Business not found")
    q=db.scalar(select(QueueEntry).join(Appointment,QueueEntry.appointment_id==Appointment.id).where(QueueEntry.appointment_id==appointment_id,Appointment.tenant_id==t.id))
    if not q: raise HTTPException(404,"Queue token not found")
    queue_snapshot(db,t,q.queue_date); db.refresh(q)
    return {"business":t.name,"token":q.token,"status":q.status,"people_ahead":q.people_ahead,"estimated_wait_minutes":q.estimated_wait_minutes,"queue_date":q.queue_date.isoformat()}


def _request_out(r,db):
    staff=db.get(StaffMember,r.assigned_staff_id) if r.assigned_staff_id else None
    return {"id":r.id,"request_type":r.request_type,"message":r.message,"status":r.status,"context_token":r.context_token,"customer_id":r.customer_id,"assigned_staff_id":r.assigned_staff_id,"assigned_staff_name":staff.name if staff else None,"created_at":r.created_at.isoformat()}

@app.post("/api/v1/public/business/{slug}/service-requests",status_code=201)
def create_service_request(slug,payload:ServiceRequestCreate,db:Session=Depends(get_db)):
    t=db.scalar(select(Tenant).where(Tenant.slug==slug.lower()))
    if not t: raise HTTPException(404,"Business not found")
    if not _feature_config(db,t.id).get("service_requests",True):
        raise HTTPException(403,"Service requests are disabled")
    if payload.request_type=="waiter" and not _feature_config(db,t.id).get("call_waiter",True):
        raise HTTPException(403,"Call waiter is disabled")
    if payload.request_type=="waiter" and t.industry.lower() not in ("restaurant","cafe","hotel","hospitality","food"):
        raise HTTPException(400,"Waiter calling is not enabled for this business type")
    if payload.customer_id and not db.scalar(select(Customer.id).where(Customer.id==payload.customer_id,Customer.tenant_id==t.id)):
        raise HTTPException(400,"Invalid customer")
    staff=None
    dept=db.scalar(select(Department).where(Department.tenant_id==t.id,Department.name.ilike("%service%"),Department.is_active==True))
    if not dept: dept=db.scalar(select(Department).where(Department.tenant_id==t.id,Department.name.ilike("%reception%"),Department.is_active==True))
    if dept: staff=db.scalar(select(StaffMember).where(StaffMember.tenant_id==t.id,StaffMember.department_id==dept.id,StaffMember.is_active==True,StaffMember.is_available==True))
    r=ServiceRequest(tenant_id=t.id,customer_id=payload.customer_id,context_token=payload.context_token,request_type=payload.request_type,message=payload.message,status="requested",assigned_staff_id=staff.id if staff else None)
    db.add(r); db.commit(); db.refresh(r)
    publish_event_sync(t.id,"service_request.created",{
        "request_id":r.id,"request_type":r.request_type,"message":r.message,
        "status":r.status,"assigned_staff_id":r.assigned_staff_id
    },context_token=r.context_token)
    return _request_out(r,db)

@app.get("/api/v1/tenants/{tenant_id}/service-requests")
def list_service_requests(tenant_id,status_value:str|None=Query(default=None,alias="status"),user=Depends(get_current_user),db:Session=Depends(get_db)):
    require_tenant(user,tenant_id)
    q=select(ServiceRequest).where(ServiceRequest.tenant_id==tenant_id)
    if status_value: q=q.where(ServiceRequest.status==status_value)
    rows=db.scalars(q.order_by(ServiceRequest.created_at.desc())).all()
    return {"items":[_request_out(r,db) for r in rows]}

@app.patch("/api/v1/tenants/{tenant_id}/service-requests/{request_id}")
def update_service_request(tenant_id,request_id,payload:ServiceRequestStatusUpdate,user=Depends(get_current_user),db:Session=Depends(get_db)):
    require_tenant(user,tenant_id)
    r=db.scalar(select(ServiceRequest).where(ServiceRequest.id==request_id,ServiceRequest.tenant_id==tenant_id))
    if not r: raise HTTPException(404,"Service request not found")
    transitions={"requested":{"acknowledged","cancelled"},"acknowledged":{"in_progress","completed","cancelled"},"in_progress":{"completed","cancelled"},"completed":set(),"cancelled":set()}
    if payload.status not in transitions.get(r.status,set()):
        raise HTTPException(409,f"Invalid service request transition: {r.status} -> {payload.status}")
    r.status=payload.status
    if payload.status=="acknowledged": r.acknowledged_at=datetime.utcnow()
    if payload.status in ("completed","cancelled"): r.completed_at=datetime.utcnow()
    db.commit(); db.refresh(r)
    publish_event_sync(tenant_id,"service_request.updated",{
        "request_id":r.id,"request_type":r.request_type,"status":r.status,
        "assigned_staff_id":r.assigned_staff_id
    },context_token=r.context_token)
    return _request_out(r,db)

@app.post("/api/v1/public/business/{slug}/games/{game}/score")
def save_game_score(slug,game:str,score:int=Query(ge=0,le=1000000),customer_id:str|None=None,db:Session=Depends(get_db)):
    t=db.scalar(select(Tenant).where(Tenant.slug==slug.lower()))
    if not t: raise HTTPException(404,"Business not found")
    from .games import submit_score
    result=submit_score(db,t.id,game,score,customer_id)
    if not result.ok:
        code={"games_disabled":403,"unknown_game":400,"invalid_score":400}.get(result.reason,400)
        raise HTTPException(code,result.reason.replace("_"," "))
    return {"id":result.score_id,"game":game,"score":result.score,
            "reward_points":result.reward_points,"reward_reason":result.reward_reason}

@app.post("/api/v1/public/business/{slug}/bills/{bill_id}/payment-order")
def create_bill_payment(slug,bill_id,db:Session=Depends(get_db)):
    t=db.scalar(select(Tenant).where(Tenant.slug==slug.lower()))
    if not t: raise HTTPException(404,"Business not found")
    if not _feature_config(db,t.id).get("online_payment",True): raise HTTPException(403,"Online payment is disabled")
    bill=db.scalar(select(Bill).where(Bill.id==bill_id,Bill.tenant_id==t.id))
    if not bill: raise HTTPException(404,"Bill not found")
    if bill.status=="paid": return {"paid":True,"bill_id":bill.id}
    try:
        adapter=tenant_payment_adapter(db,t.id,settings)
        result=asyncio.run(adapter.create_order(int(bill.total)*100,"INR","bill-"+bill.id[:24]))
    except RuntimeError as exc: raise HTTPException(503,str(exc))
    except Exception as exc: raise HTTPException(502,"Unable to create payment order")
    return {"bill_id":bill.id,"key_id":adapter.key_id,"amount":result.get("amount"),"currency":result.get("currency"),"razorpay_order_id":result.get("id")}

@app.post("/api/v1/public/business/{slug}/bills/{bill_id}/verify-payment")
def verify_bill_payment(slug,bill_id,payload:PaymentVerify,db:Session=Depends(get_db)):
    from .security import check_idempotency, store_idempotent_response, audit, verify_razorpay_signature
    t=db.scalar(select(Tenant).where(Tenant.slug==slug.lower()))
    if not t: raise HTTPException(404,"Bill not found")
    idem_key=f"{bill_id}:{payload.razorpay_order_id}:{payload.razorpay_payment_id}"
    idem_payload={"bill_id":bill_id,"order_id":payload.razorpay_order_id,"payment_id":payload.razorpay_payment_id}
    idem=check_idempotency(db,t.id,"payment.verify",idem_key,idem_payload)
    if idem.conflict:
        raise HTTPException(409,"Payment does not match a previous attempt for the same bill")
    if not idem.first_seen:
        return idem.cached_response or {"paid":True,"bill_id":bill_id,"payment_id":payload.razorpay_payment_id}
    bill=db.scalar(select(Bill).where(Bill.id==bill_id,Bill.tenant_id==t.id))
    if not bill:
        store_idempotent_response(db,t.id,"payment.verify",idem_key,{"error":"bill_not_found"})
        raise HTTPException(404,"Bill not found")
    if bill.status=="paid":
        if bill.payment_id and bill.payment_id!=payload.razorpay_payment_id:
            raise HTTPException(409,"Bill is already paid with another payment")
        response={"paid":True,"bill_id":bill.id,"payment_id":bill.payment_id}
        store_idempotent_response(db,t.id,"payment.verify",idem_key,response)
        return response
    adapter=tenant_payment_adapter(db,t.id,settings)
    if not adapter.key_secret:
        raise HTTPException(503,"Razorpay is not configured")
    if not verify_razorpay_signature(payload.razorpay_order_id,payload.razorpay_payment_id,payload.razorpay_signature,adapter.key_secret):
        raise HTTPException(400,"Invalid payment signature")
    bill.payment_id=payload.razorpay_payment_id
    bill.status="paid"
    bill.paid_at=datetime.utcnow()
    o=db.get(Order,bill.order_id)
    if o:
        o.payment_status="paid"
        o.updated_at=datetime.utcnow()
    db.commit()
    audit(db,tenant_id=t.id,actor_id=None,action="payment.captured",target_type="bill",target_id=bill.id,detail={"order_id":bill.order_id,"payment_id":bill.payment_id,"amount":bill.total})
    response={"paid":True,"bill_id":bill.id,"payment_id":bill.payment_id}
    store_idempotent_response(db,t.id,"payment.verify",idem_key,response)
    return response

@app.post("/api/v1/webhooks/razorpay")
async def razorpay_webhook(request:Request,db:Session=Depends(get_db)):
    from .security import check_idempotency, store_idempotent_response, audit
    raw=await request.body()
    signature=request.headers.get("X-Razorpay-Signature","")
    if not settings.razorpay_key_secret or not signature:
        raise HTTPException(401,"Webhook signature required")
    if not verify_hmac_sha256(raw,signature,settings.razorpay_key_secret):
        raise HTTPException(400,"Invalid webhook signature")
    try:
        payload=json.loads(raw.decode("utf-8"))
    except Exception:
        raise HTTPException(400,"Invalid webhook JSON")
    entity=payload.get("payload",{}).get("payment",{}).get("entity",{}) or {}
    event_id=payload.get("event_id") or payload.get("id") or ""
    payment_id=entity.get("id") or ""
    receipt=(entity.get("notes") or {}).get("receipt") or ""
    if not (event_id or payment_id):
        return {"received":True,"ignored":True}
    idem_key=event_id or f"payment:{payment_id}"
    idem_payload={"event_id":event_id,"payment_id":payment_id,"receipt":receipt,"status":entity.get("status")}
    idem=check_idempotency(db,"__platform__","payment.webhook",idem_key,idem_payload)
    if idem.conflict:
        raise HTTPException(409,"Idempotency conflict for webhook event")
    if not idem.first_seen:
        return idem.cached_response or {"received":True,"replayed":True}
    if receipt.startswith("bill-") and entity.get("status") in ("captured","authorized"):
        bill=db.scalar(select(Bill).where(Bill.id==receipt[5:]))
        if bill and bill.status!="paid":
            bill.status="paid"
            bill.payment_id=entity.get("id")
            bill.paid_at=datetime.utcnow()
            o=db.get(Order,bill.order_id)
            if o:
                o.payment_status="paid"
            db.commit()
            audit(db,tenant_id=bill.tenant_id,actor_id=None,action="payment.webhook_captured",target_type="bill",target_id=bill.id,detail={"payment_id":entity.get("id"),"event_id":event_id,"amount":entity.get("amount")})
    response={"received":True}
    store_idempotent_response(db,"__platform__","payment.webhook",idem_key,response)
    return response

@app.get("/api/v1/public/business/{slug}/service-requests/{request_id}")
def public_service_request(slug,request_id,context_token:str|None=Query(default=None),db:Session=Depends(get_db)):
    t=db.scalar(select(Tenant).where(Tenant.slug==slug.lower()))
    if not t: raise HTTPException(404,"Business not found")
    r=db.scalar(select(ServiceRequest).where(ServiceRequest.id==request_id,ServiceRequest.tenant_id==t.id))
    if not r: raise HTTPException(404,"Service request not found")
    if not context_token or r.context_token != context_token:
        raise HTTPException(403,"Service request context token required")
    return _request_out(r,db)

@app.post("/api/v1/ai/chat")
async def ai_chat(payload:ChatRequest,user=Depends(get_current_user),db:Session=Depends(get_db)):
    require_tenant(user,payload.tenant_id); result=await generate_reply(db,payload.tenant_id,payload.message,payload.conversation_id,payload.channel)
    return {**result,"tenant_id":payload.tenant_id}
@app.get("/api/v1/tenants/{tenant_id}/knowledge")
def knowledge(tenant_id,user=Depends(get_current_user),db:Session=Depends(get_db)):
    require_tenant(user,tenant_id); rows=db.scalars(select(KnowledgeItem).where(KnowledgeItem.tenant_id==tenant_id)).all(); return {"items":[{"id":x.id,"title":x.title,"content":x.content,"kind":x.kind,"is_active":x.is_active} for x in rows]}
class KnowledgeCreate(BaseModel): title:str; content:str; kind:str="faq"
@app.post("/api/v1/tenants/{tenant_id}/knowledge",status_code=201)
def add_knowledge(tenant_id,payload:KnowledgeCreate,user=Depends(get_current_user),db:Session=Depends(get_db)):
    require_tenant(user,tenant_id); x=KnowledgeItem(tenant_id=tenant_id,**payload.model_dump()); db.add(x); db.commit(); db.refresh(x); return x

class DepartmentCreate(BaseModel):
    name: str = Field(min_length=2, max_length=100)
    description: str | None = None
    skills: str = ""

class StaffCreate(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    user_id: str | None = None
    department_id: str | None = None
    skills: str = ""
    is_available: bool = True
    max_concurrent_calls: int = Field(default=1, ge=1, le=20)

@app.get("/api/v1/tenants/{tenant_id}/departments")
def departments(tenant_id, user=Depends(get_current_user), db: Session=Depends(get_db)):
    require_tenant(user, tenant_id)
    rows=db.scalars(select(Department).where(Department.tenant_id==tenant_id)).all()
    return {"items":[{"id":x.id,"name":x.name,"description":x.description,"skills":x.skills,"is_active":x.is_active} for x in rows]}

@app.post("/api/v1/tenants/{tenant_id}/departments", status_code=201)
def add_department(tenant_id, payload: DepartmentCreate, user=Depends(get_current_user), db: Session=Depends(get_db)):
    require_tenant(user, tenant_id)
    x=Department(tenant_id=tenant_id, **payload.model_dump())
    db.add(x); db.commit(); db.refresh(x)
    return {"id":x.id,"name":x.name,"description":x.description,"skills":x.skills,"is_active":x.is_active}

@app.get("/api/v1/tenants/{tenant_id}/staff")
def staff(tenant_id, user=Depends(get_current_user), db: Session=Depends(get_db)):
    require_tenant(user, tenant_id)
    from .models_ai import StaffMember
    rows=db.scalars(select(StaffMember).where(StaffMember.tenant_id==tenant_id)).all()
    return {"items":[{"id":x.id,"name":x.name,"user_id":x.user_id,"department_id":x.department_id,"skills":x.skills,"is_active":x.is_active,"is_available":x.is_available} for x in rows]}

@app.post("/api/v1/tenants/{tenant_id}/staff", status_code=201)
def add_staff(tenant_id, payload: StaffCreate, user=Depends(get_current_user), db: Session=Depends(get_db)):
    require_tenant(user, tenant_id)
    from .models_ai import StaffMember
    if payload.user_id:
        linked=db.scalar(select(User).where(User.id==payload.user_id,User.tenant_id==tenant_id,User.is_active==True))
        if not linked: raise HTTPException(400,"Invalid staff user for this tenant")
        existing=db.scalar(select(StaffMember).where(StaffMember.user_id==payload.user_id))
        if existing: raise HTTPException(409,"User is already linked to a staff member")
    x=StaffMember(tenant_id=tenant_id, **payload.model_dump())
    db.add(x); db.commit(); db.refresh(x)
    return {"id":x.id,"name":x.name,"department_id":x.department_id,"skills":x.skills,"is_available":x.is_available}

@app.post("/api/v1/tenants/{tenant_id}/calls/{call_id}/route")
def route_existing_call(tenant_id, call_id, intent: str | None = None, user=Depends(get_current_user), db: Session=Depends(get_db)):
    require_tenant(user, tenant_id)
    call=db.scalar(select(CallRecord).where(CallRecord.id==call_id, CallRecord.tenant_id==tenant_id))
    if not call: raise HTTPException(404, "Call not found")
    routed=route_call(db, tenant_id, call, intent)
    db.add(InteractionEvent(tenant_id=tenant_id,customer_id=call.customer_id,call_id=call.id,channel=call.source or "pwa",event_type="call_routed",payload_json=json.dumps(routed,ensure_ascii=False)))
    if routed.get("urgency") in ("high","urgent","emergency"):
        db.add(ReceptionAlert(tenant_id=tenant_id,customer_id=call.customer_id,call_id=call.id,department_id=routed.get("department_id"),staff_id=(routed.get("staff") or {}).get("id"),category=intent or "general",priority=routed.get("urgency","normal"),title="Customer call requires attention",message=(call.summary or call.intent or "Customer requested assistance")))
    db.commit()
    return routed

@app.get("/api/v1/tenants/{tenant_id}/calls/{call_id}/context")
def call_context(tenant_id, call_id, user=Depends(get_current_user), db: Session=Depends(get_db)):
    require_tenant(user, tenant_id)
    call=db.scalar(select(CallRecord).where(CallRecord.id==call_id,CallRecord.tenant_id==tenant_id))
    if not call: raise HTTPException(404, "Call not found")
    customer=db.get(Customer,call.customer_id) if call.customer_id else None
    conversations=db.scalars(select(Conversation).where(Conversation.tenant_id==tenant_id,Conversation.customer_id==call.customer_id).order_by(Conversation.updated_at.desc())).all() if call.customer_id else []
    staff_member=db.get(StaffMember,call.staff_id) if call.staff_id else None
    return {
        "call":{"id":call.id,"status":call.status,"department":call.department,"staff_id":call.staff_id,"staff_name":staff_member.name if staff_member else None,"room_id":call.room_id,"intent":call.intent,"summary":call.summary,"transcript":call.transcript,"created_at":call.created_at},
        "customer": {"id":customer.id,"name":customer.name,"phone":customer.phone,"whatsapp_opt_in":customer.whatsapp_opt_in} if customer else None,
        "conversation_ids":[c.id for c in conversations[:10]],
    }

@app.post("/api/v1/tenants/{tenant_id}/calls/{call_id}/handoff")
def handoff_call(tenant_id, call_id, user=Depends(get_current_user), db: Session=Depends(get_db)):
    require_tenant(user, tenant_id)
    call=db.scalar(select(CallRecord).where(CallRecord.id==call_id,CallRecord.tenant_id==tenant_id))
    if not call: raise HTTPException(404, "Call not found")
    routed=route_call(db,tenant_id,call,call.intent or "human_handoff")
    if not routed.get("staff"):
        call.status="handoff_unavailable"
        db.commit()
        return {**routed,"call_id":call.id,"status":call.status,"room_id":None}
    call.room_id="call-"+call.id
    call.status="handoff_requested"
    db.commit()
    return {**routed,"call_id":call.id,"status":call.status,"room_id":call.room_id,"room_token":issue_call_room_token(call.id,"call-customer")}

class HandoffDecision(BaseModel):
    decision: str = Field(pattern="^(accept|decline)$")

@app.post("/api/v1/tenants/{tenant_id}/calls/{call_id}/handoff/decision")
def handoff_decision(tenant_id, call_id, payload: HandoffDecision, user=Depends(get_current_user), db: Session=Depends(get_db)):
    require_tenant(user, tenant_id)
    call=db.scalar(select(CallRecord).where(CallRecord.id==call_id, CallRecord.tenant_id==tenant_id))
    if not call: raise HTTPException(404, "Call not found")
    if not call.staff_id: raise HTTPException(409, "No staff assigned")
    staff=db.get(StaffMember, call.staff_id)
    if not (user.role in ("owner","admin","super_admin","platform_admin") or (staff and staff.user_id==user.id)):
        raise HTTPException(403, "Only the assigned staff member or a tenant administrator can accept this call")
    if not staff or not staff.is_active: raise HTTPException(409, "Assigned staff is unavailable")
    if payload.decision=="accept":
        call.status="handoff_accepted"
        staff.is_available=False
    else:
        call.status="handoff_declined"
    db.commit()
    return {"call_id":call.id,"status":call.status,"room_id":call.room_id,"staff":{"id":staff.id,"name":staff.name}}

@app.post("/api/v1/tenants/{tenant_id}/calls/{call_id}/staff-release")
def staff_release(tenant_id, call_id, user=Depends(get_current_user), db: Session=Depends(get_db)):
    require_tenant(user, tenant_id)
    call=db.scalar(select(CallRecord).where(CallRecord.id==call_id, CallRecord.tenant_id==tenant_id))
    if not call: raise HTTPException(404, "Call not found")
    if call.staff_id:
        staff=db.get(StaffMember,call.staff_id)
        if staff: staff.is_available=True
    call.status="ended"
    db.commit()
    return {"call_id":call.id,"status":call.status}

@app.get("/api/v1/tenants/{tenant_id}/calls")
def calls(tenant_id, user=Depends(get_current_user), db: Session=Depends(get_db)):
    require_tenant(user, tenant_id)
    rows=db.scalars(select(CallRecord).where(CallRecord.tenant_id==tenant_id).order_by(CallRecord.created_at.desc())).all()
    return {"items":[{"id":x.id,"customer_id":x.customer_id,"customer_name":(db.get(Customer,x.customer_id).name if x.customer_id and db.get(Customer,x.customer_id) else "Customer"),"source":x.source,"status":x.status,"department":x.department,"staff_id":x.staff_id,"room_id":x.room_id,"intent":x.intent,"summary":x.summary,"transcript":x.transcript,"created_at":x.created_at} for x in rows]}

class VoiceTurnRequest(BaseModel):
    transcript:str=Field(min_length=1,max_length=4000)
    conversation_id:str|None=None
    channel:str="voice"


@app.get("/api/v1/tenants/{tenant_id}/voice/ice")
async def voice_ice_config(tenant_id, user=Depends(get_current_user), db: Session = Depends(get_db)):
    require_tenant(user, tenant_id)
    from .turn import generate_ice_config
    result = await generate_ice_config(tenant_id=tenant_id, user_id=user.id)
    return {
        "ice_servers": result.ice_servers,
        "provider": result.provider,
        "ttl_seconds": result.ttl_seconds,
    }

@app.post("/api/v1/tenants/{tenant_id}/voice/turn")
async def voice_turn(tenant_id,payload:VoiceTurnRequest,user=Depends(get_current_user),db:Session=Depends(get_db)):
    require_tenant(user,tenant_id)
    result=await generate_reply(db,tenant_id,payload.transcript,payload.conversation_id,payload.channel)
    return {**result,"audio_generation":"provider_adapter_pending"}

@app.get("/api/v1/public/languages")
def supported_languages():
    return {"languages":[{"code":"en","name":"English"},{"code":"hi","name":"Hindi"},{"code":"te","name":"Telugu"},{"code":"ta","name":"Tamil"},{"code":"kn","name":"Kannada"},{"code":"ml","name":"Malayalam"},{"code":"mr","name":"Marathi"},{"code":"bn","name":"Bengali"},{"code":"gu","name":"Gujarati"},{"code":"pa","name":"Punjabi"},{"code":"ur","name":"Urdu"},{"code":"or","name":"Odia"},{"code":"as","name":"Assamese"},{"code":"kok","name":"Konkani"},{"code":"sa","name":"Sanskrit"},{"code":"sd","name":"Sindhi"},{"code":"ks","name":"Kashmiri"},{"code":"mni","name":"Manipuri"},{"code":"ne","name":"Nepali"},{"code":"doi","name":"Dogri"},{"code":"mai","name":"Maithili"},{"code":"sat","name":"Santali"}]}

@app.get("/api/v1/tenants/{tenant_id}/conversations/{conversation_id}")
def conversation_history(tenant_id,conversation_id,user=Depends(get_current_user),db:Session=Depends(get_db)):
    require_tenant(user,tenant_id)
    c=db.scalar(select(Conversation).where(Conversation.id==conversation_id,Conversation.tenant_id==tenant_id))
    if not c: raise HTTPException(404,"Conversation not found")
    rows=db.scalars(select(ConversationMessage).where(ConversationMessage.conversation_id==c.id).order_by(ConversationMessage.created_at)).all()
    return {"id":c.id,"language":c.language,"state":c.state,"intent":c.intent,"turns":c.turns,"messages":[{"role":x.role,"content":x.content,"language":x.language,"intent":x.intent,"created_at":x.created_at} for x in rows]}

@app.get("/api/v1/global/faqs")
def global_faqs(industry:str|None=None,language:str="en",db:Session=Depends(get_db)):
    q=select(GlobalFaq).where(GlobalFaq.is_active==True,GlobalFaq.language==language)
    if industry: q=q.where(GlobalFaq.industry.in_([industry,"general"]))
    rows=db.scalars(q).all()
    return {"items":[{"id":x.id,"industry":x.industry,"language":x.language,"intent":x.intent,"question":x.question,"answer":x.answer,"keywords":x.keywords} for x in rows]}

@app.get("/api/v1/public/business/resolve")
def public_business_resolve(name: str = Query(min_length=2, max_length=160), db: Session = Depends(get_db)):
    normalized = " ".join(name.strip().lower().split())
    tenants = db.scalars(select(Tenant)).all()
    matches = [t for t in tenants if " ".join((t.name or "").strip().lower().split()) == normalized and t.status == "active"]
    if not matches:
        raise HTTPException(404, "Business not found")
    t = sorted(matches, key=lambda x: x.created_at or datetime.min, reverse=True)[0]
    return {"id": t.id, "name": t.name, "slug": t.slug, "industry": t.industry}

@app.get("/api/v1/public/business/{slug}")
def public_business(slug:str,db:Session=Depends(get_db)):
    t=db.scalar(select(Tenant).where(Tenant.slug==slug.lower(),)); 
    if not t: raise HTTPException(404,"Business not found")
    services=db.scalars(select(Service).where(Service.tenant_id==t.id,Service.is_active==True)).all()
    return {"id":t.id,"name":t.name,"slug":t.slug,"industry":t.industry,"description":t.description,"phone":t.phone,"whatsapp_number":t.whatsapp_number,"address":t.address,"timezone":t.timezone,"features":_feature_config(db,t.id),"games":GAME_CATALOG,"menu":_public_menu(db,t),"services":[{"id":x.id,"name":x.name,"description":x.description,"price":float(x.price) if x.price is not None else None,"currency":x.currency,"duration_minutes":x.duration_minutes} for x in services]}
def _public_menu(db,t):
    if not _feature_config(db,t.id).get("digital_menu",True): return {"enabled":False,"categories":[],"items":[]}
    cats=db.scalars(select(MenuCategory).where(MenuCategory.tenant_id==t.id,MenuCategory.is_active==True).order_by(MenuCategory.sort_order)).all()
    items=db.scalars(select(MenuItem).where(MenuItem.tenant_id==t.id,MenuItem.is_active==True,MenuItem.is_available==True).order_by(MenuItem.sort_order)).all()
    return {"enabled":True,"categories":[{"id":x.id,"name":x.name} for x in cats],"items":[{"id":x.id,"category_id":x.category_id,"name":x.name,"description":x.description,"price":x.price,"currency":x.currency} for x in items]}

@app.get("/api/v1/public/business/{slug}/menu")
def public_menu(slug,db:Session=Depends(get_db)):
    t=db.scalar(select(Tenant).where(Tenant.slug==slug.lower()))
    if not t: raise HTTPException(404,"Business not found")
    if not _feature_config(db,t.id).get("digital_menu",True): raise HTTPException(403,"Menu is not available for this business")
    return _public_menu(db,t)

class PublicOrderItem(BaseModel):
    menu_item_id:str
    quantity:int=Field(ge=1,le=50)
    notes:str|None=None
class PublicOrderCreate(BaseModel):
    items:list[PublicOrderItem]=Field(min_length=1,max_length=50)
    context_token:str|None=None
    customer_id:str|None=None

def _order_out(o,db):
    rows=db.scalars(select(OrderItem).where(OrderItem.order_id==o.id)).all()
    bill=db.scalar(select(Bill).where(Bill.order_id==o.id))
    return {"id":o.id,"status":o.status,"context_token":o.context_token,"subtotal":o.subtotal,"tax":o.tax,"discount":o.discount,"total":o.total,"payment_status":o.payment_status,
            "items":[{"name":x.name,"price":x.price,"quantity":x.quantity,"notes":x.notes} for x in rows],
            "bill":({"id":bill.id,"status":bill.status,"total":bill.total} if bill else None)}

@app.post("/api/v1/public/business/{slug}/orders",status_code=201)
def create_public_order(slug,payload:PublicOrderCreate,db:Session=Depends(get_db)):
    t=db.scalar(select(Tenant).where(Tenant.slug==slug.lower()))
    if not t: raise HTTPException(404,"Business not found")
    if not _feature_config(db,t.id).get("online_ordering",True): raise HTTPException(403,"Online ordering is disabled")
    customer=None
    if payload.customer_id:
        customer=db.scalar(select(Customer).where(Customer.id==payload.customer_id,Customer.tenant_id==t.id))
    o=Order(tenant_id=t.id,customer_id=customer.id if customer else None,context_token=payload.context_token,status="pending")
    db.add(o); db.flush(); subtotal=0
    for req in payload.items:
        item=db.scalar(select(MenuItem).where(MenuItem.id==req.menu_item_id,MenuItem.tenant_id==t.id,MenuItem.is_active==True,MenuItem.is_available==True))
        if not item: db.rollback(); raise HTTPException(400,"One or more items are unavailable")
        subtotal += item.price*req.quantity
        db.add(OrderItem(order_id=o.id,menu_item_id=item.id,name=item.name,price=item.price,quantity=req.quantity,notes=req.notes))
    o.subtotal=subtotal; o.total=subtotal; o.updated_at=datetime.utcnow()
    db.commit(); db.refresh(o)
    publish_event_sync(t.id,"order.created",{
        "order_id":o.id,"status":o.status,"total":o.total,
        "customer_id":o.customer_id,"items":[
            {"name":x.name,"price":x.price,"quantity":x.quantity}
            for x in db.scalars(select(OrderItem).where(OrderItem.order_id==o.id)).all()
        ]
    },context_token=o.context_token)
    return _order_out(o,db)

@app.get("/api/v1/public/business/{slug}/orders/{order_id}")
def public_order_status(slug,order_id,context_token:str|None=Query(default=None),db:Session=Depends(get_db)):
    t=db.scalar(select(Tenant).where(Tenant.slug==slug.lower()))
    o=db.scalar(select(Order).where(Order.id==order_id,Order.tenant_id==t.id)) if t else None
    if not o: raise HTTPException(404,"Order not found")
    if not context_token or o.context_token != context_token:
        raise HTTPException(403,"Order context token required")
    return _order_out(o,db)

@app.get("/api/v1/tenants/{tenant_id}/orders")
def tenant_orders(tenant_id,status:str|None=None,user=Depends(get_current_user),db:Session=Depends(get_db)):
    require_tenant(user,tenant_id)
    q=select(Order).where(Order.tenant_id==tenant_id)
    if status: q=q.where(Order.status==status)
    return {"items":[_order_out(x,db) for x in db.scalars(q.order_by(Order.created_at.desc())).all()]}

@app.patch("/api/v1/tenants/{tenant_id}/orders/{order_id}")
def update_order(tenant_id,order_id,payload:OrderStatusUpdate,user=Depends(get_current_user),db:Session=Depends(get_db)):
    require_tenant(user,tenant_id)
    o=db.scalar(select(Order).where(Order.id==order_id,Order.tenant_id==tenant_id))
    if not o: raise HTTPException(404,"Order not found")
    prev=o.status
    o.status=payload.status; o.updated_at=datetime.utcnow()
    if payload.status=="completed" and prev!="completed":
        b=db.scalar(select(Bill).where(Bill.order_id==o.id))
        if not b:
            db.add(Bill(tenant_id=tenant_id,order_id=o.id,subtotal=o.subtotal,tax=o.tax,discount=o.discount,total=o.total))
        db.commit()
        # SESSION9_LOYALTY_WALLET: route awards through the ledger
        try:
            from .loyalty import award_for_order
            awarded = award_for_order(db, tenant_id, o)
            if awarded:
                import logging as _lg
                _lg.getLogger("api.loyalty").info("order=%s awarded=%s", o.id, awarded)
        except Exception:
            pass
    else:
        db.commit()
    db.refresh(o)
    bill=db.scalar(select(Bill).where(Bill.order_id==o.id))
    publish_event_sync(tenant_id,"order.updated",{
        "order_id":o.id,"status":o.status,"total":o.total,
        "payment_status":o.payment_status,
        "bill":{"id":bill.id,"status":bill.status,"total":bill.total} if bill else None
    },context_token=o.context_token)
    return _order_out(o,db)

@app.get("/api/v1/tenants/{tenant_id}/bills")
def tenant_bills(tenant_id,user=Depends(get_current_user),db:Session=Depends(get_db)):
    require_tenant(user,tenant_id)
    rows=db.scalars(select(Bill).where(Bill.tenant_id==tenant_id).order_by(Bill.issued_at.desc())).all()
    return {"items":[{"id":x.id,"order_id":x.order_id,"subtotal":x.subtotal,"tax":x.tax,"discount":x.discount,"total":x.total,"status":x.status,"issued_at":x.issued_at.isoformat()} for x in rows]}

@app.post("/api/v1/public/business/{slug}/feedback",status_code=201)
def create_feedback(slug,payload:FeedbackCreate,db:Session=Depends(get_db)):
    t=db.scalar(select(Tenant).where(Tenant.slug==slug.lower()))
    if not t: raise HTTPException(404,"Business not found")
    if not _feature_config(db,t.id).get("feedback",True): raise HTTPException(403,"Feedback is not available for this business")
    f=Feedback(tenant_id=t.id,**payload.model_dump()); db.add(f); db.commit()
    row=db.scalar(select(TenantSetting).where(TenantSetting.tenant_id==t.id,TenantSetting.key=="google_review"))
    review_url=""
    if row:
        try: review_url=json.loads(row.value_json).get("review_url","")
        except Exception: pass
    return {"id":f.id,"saved":True,"google_review_url":review_url}

@app.post("/api/v1/public/chat")
async def public_chat(payload:ChatRequest,db:Session=Depends(get_db)):
    t=db.get(Tenant,payload.tenant_id)
    if not t: raise HTTPException(404,"Business not found")
    if not _feature_config(db,t.id).get("ai_chat",True): raise HTTPException(403,"AI chat is not available for this business")
    if not payload.phone or not payload.name:
        return {"identity_required":True,"required":["phone","name"],"tenant_id":t.id,"message":"Please provide your mobile number and name before we continue."}
    try:
        upsert_customer(db,t.id,payload.phone,payload.name,False,source=payload.channel)
    except ValueError as exc:
        raise HTTPException(400,str(exc))
    result=await generate_reply(db,t.id,payload.message,payload.conversation_id,payload.channel)
    if payload.phone:
        c=upsert_customer(db,t.id,payload.phone,payload.name,False)
        if result["intent"] in ("booking","human_handoff","pricing"): create_lead(db,t.id,"customer_pwa",c.id,result["intent"],payload.message)
    return {**result,"tenant_id":t.id}

@app.post("/api/v1/tenants/{tenant_id}/qr",status_code=201)
def create_qr(tenant_id,kind:str="business",label:str="Business QR",user=Depends(get_current_user),db:Session=Depends(get_db)):
    require_tenant(user,tenant_id); t=db.get(Tenant,tenant_id)
    if not t: raise HTTPException(404,"Tenant not found")
    q=QrEntry(tenant_id=tenant_id,token=secrets.token_urlsafe(18),kind=kind,label=label); db.add(q); db.commit(); db.refresh(q)
    return {"id":q.id,"token":q.token,"url":settings.public_app_url+"/pwa/"+t.slug+"?qr="+q.token,"kind":q.kind,"label":q.label}
@app.get("/api/v1/public/qr/{token}")
def scan_qr(token,db:Session=Depends(get_db)):
    q=db.scalar(select(QrEntry).where(QrEntry.token==token))
    if not q: raise HTTPException(404,"QR not found")
    q.scans+=1; db.commit(); t=db.get(Tenant,q.tenant_id); return {"tenant_id":t.id,"slug":t.slug,"url":settings.public_app_url.rstrip("/")+"/pwa/"+t.slug+"?qr="+q.token,"kind":q.kind}

class PublicCallStartRequest(BaseModel):
    name:str=Field(min_length=1,max_length=160)
    phone:str=Field(min_length=5,max_length=32)

@app.post("/api/v1/public/business/{slug}/call",status_code=201)
def start_public_call(slug:str,payload:PublicCallStartRequest,db:Session=Depends(get_db)):
    t=db.scalar(select(Tenant).where(Tenant.slug==slug.lower()))
    if not t: raise HTTPException(404,"Business not found")
    if not _feature_config(db,t.id).get("ai_voice",True): raise HTTPException(403,"Voice calling is not available for this business")
    customer=None
    try:
        customer=upsert_customer(db,t.id,payload.phone.strip(),payload.name.strip(),False,source="pwa_voice")
    except ValueError as exc:
        raise HTTPException(400,str(exc))
    previous_calls=db.scalar(select(__import__("sqlalchemy").func.count(CallRecord.id)).where(CallRecord.tenant_id==t.id,CallRecord.customer_id==customer.id)) or 0
    now=datetime.utcnow()
    call=CallRecord(tenant_id=t.id,customer_id=customer.id if customer else None,source="pwa_voice",status="ringing",started_at=now,call_number=previous_calls+1)
    db.add(call); db.commit(); db.refresh(call)
    return {"call_id":call.id,"customer_id":customer.id if customer else None,"status":"ringing","business_name":t.name,"room_token":issue_call_room_token(call.id,"call-customer")}

@app.websocket("/ws/public/voice/{call_id}")
async def public_voice(websocket:WebSocket,call_id:str):
    import logging
    logging.getLogger("uvicorn.error").info("PUBLIC_VOICE_WS_HANDSHAKE call_id=%s origin=%s", call_id, websocket.headers.get("origin"))
    # The call id is a cryptographically random UUID created server-side.
    # For the public AI leg, bind the WebSocket directly to the short-lived
    # call record instead of relying on query-string JWT/HMAC exchange.
    # This avoids proxy/browser token issues while still requiring:
    #   - a real PWA voice call record
    #   - an active/ringing call
    #   - a call created within the last 10 minutes
    # Accept the WebSocket handshake first. Rejecting before accept is surfaced by
    # Uvicorn/Render as HTTP 403, which hides the real application reason from the
    # browser and makes production debugging difficult.
    await websocket.accept()
    logging.getLogger("uvicorn.error").info("PUBLIC_VOICE_WS_ACCEPTED call_id=%s", call_id)
    db=SessionLocal()
    call=db.get(CallRecord,call_id)
    if not call:
        await websocket.send_json({"type":"error","code":"call_not_found","message":"Call session not found."})
        await websocket.close(code=4404); db.close(); return
    now=datetime.utcnow()
    age=(now-call.started_at).total_seconds() if call.started_at else None
    if call.source!="pwa_voice" or call.status not in ("ringing","connected") or age is None or age>600:
        await websocket.send_json({"type":"error","code":"call_not_active","message":"Call session is no longer active."})
        await websocket.close(code=4403); db.close(); return
    tenant=db.get(Tenant,call.tenant_id)
    if not tenant:
        await websocket.send_json({"type":"error","message":"AI voice is not configured for this business."}); await websocket.close(); db.close(); return
    customer=db.get(Customer,call.customer_id) if call.customer_id else None
    context=knowledge_context(db,tenant.id)
    policy=tenant_policy(db,tenant.id)
    system = f"""You are the AI customer engagement voice agent for {tenant.name}.

UNIVERSAL AGENT TRAINING:
{AGENT_TRAINING_CONTEXT}

TENANT POLICY:
{policy_context(policy)}

APPROVED BUSINESS CONTEXT:
{context}

BUSINESS PROFILE:
Address: {tenant.address or "not configured"}
Phone: {tenant.phone or "not configured"}
Website: {tenant.website or "not configured"}
Only state a location, address, phone number, or website when it is present in the business profile or approved business context. Never invent a location.

CUSTOMER ALREADY VERIFIED:
Name: {customer.name if customer else "Customer"}
Mobile: {customer.phone if customer else "not provided"}

This call has already collected and verified the customer's name and mobile number before the AI connection started.
Do NOT ask the customer for their name or mobile number again.
Start the call immediately with a warm spoken greeting such as:
"Hello {customer.name if customer and customer.name else "there"}, welcome to {tenant.name}. How can I help you today?"
Then listen for the customer's request.
Do not invent business facts, prices, availability, policies, bookings or payment success.
Today in the business timezone is {datetime.now(ZoneInfo(tenant.timezone)).date().isoformat()}. Resolve phrases such as "coming Tuesday", "next Tuesday", "this Friday", "tomorrow", and "the 29th" to an actual calendar date before discussing an appointment. Never ask the customer which date a weekday means when the calendar can resolve it.
For business-hours questions, answer briefly in natural speech (for example, "Monday to Saturday, 9 AM to 6 PM. Sunday we're closed").
For appointment requests, never hand off merely because the customer has not supplied every booking detail. Guide them one step at a time: identify the requested day/date, then preferred time, then service if needed. If the caller has already supplied one booking detail and then supplies another (for example, "5:30" followed by "today"), preserve the earlier detail and combine them. A phrase such as "is it possible today" is a day/date update, not a new time; do not invent or change the time. If a caller gives a bare numeric time such as "5:30" and the business is open during the PM hour but closed at that AM time, treat it as the business-hour PM time unless the caller explicitly says AM. Never turn "today" into "today at 5:30 AM" merely because the previous time was 5:30. Use check_availability before presenting a slot as available. Only use create_booking after all required details are known and the customer explicitly confirms.
If the caller pauses, gives an incomplete sentence, or the transcript appears garbled or nonsensical, do not guess, end the call, or hand off. Ask them to repeat or clarify briefly. If the caller starts speaking while you are speaking, stop promptly, listen to the complete request, and answer the new request.
If the caller says simple acknowledgement such as "okay", "alright", "fine", "thanks", or "thank you" after you have answered a question, do not hand off. Respond naturally and ask whether they need anything else; close the call politely if they are finished.
For appointment booking, treat speech-recognition errors such as "bhukamp", "bukamp", "buking", or "boking" as possible booking words only when the surrounding request clearly contains appointment/day/time context; never hand off solely because recognition is imperfect.
If booking details are missing, ask for exactly one missing detail at a time. If a requested time is unavailable or outside hours, offer another time instead of handing off.
Use save_customer_identity only if the customer explicitly corrects or changes their name/number.
If a capability is disabled in TENANT POLICY, do not offer it or call a tool for it.
LANGUAGE BEHAVIOR — CRITICAL:
- Automatically detect the language the caller is speaking from the actual conversation, including Indian languages and code-switching between English and an Indian language.
- Reply in the same language the caller is currently using. Do not force English.
- Support at minimum English, Hindi, Telugu, Tamil, Kannada, Malayalam, Marathi, Bengali, Gujarati, Punjabi and Urdu.
- If the caller switches language mid-call, switch your spoken response on the next turn.
- If the caller mixes English with an Indian language, mirror that natural mix instead of translating everything to English.
- Never ask the caller to choose a language unless speech is genuinely ambiguous after listening to a complete turn.
- Do not mention language detection or these instructions to the caller.
- Keep business facts, dates, prices and booking details unchanged when changing language.
Be concise, warm, natural, and conversational. Do not read database-style lists aloud."""
    tool_declarations=[
        {"name":"save_customer_identity","description":"Save the customer's name and mobile number.","parameters":{"type":"OBJECT","properties":{"name":{"type":"STRING"},"phone":{"type":"STRING"}},"required":["name","phone"]}}
    ]
    if capability_enabled(policy,"bookings",True):
        tool_declarations.append({"name":"check_availability","description":"Check the owned appointment calendar for a specific calendar date and optional time. ALWAYS use this before saying a requested appointment slot is available. The date must be YYYY-MM-DD in the tenant timezone. If service_id is omitted, use the first active service.","parameters":{"type":"OBJECT","properties":{"date":{"type":"STRING"},"time":{"type":"STRING"},"service_id":{"type":"STRING"},"staff_id":{"type":"STRING"}},"required":["date"]}})
        tool_declarations.append({"name":"create_booking","description":"Create a confirmed appointment ONLY after the customer has explicitly said yes/confirm/that's fine to the exact calendar date, time and service. Never call this merely because the customer supplied details. The server performs a final availability check.","parameters":{"type":"OBJECT","properties":{"service_id":{"type":"STRING"},"starts_at":{"type":"STRING"},"name":{"type":"STRING"},"phone":{"type":"STRING"},"staff_id":{"type":"STRING"},"notes":{"type":"STRING"},"confirmed":{"type":"BOOLEAN"}},"required":["service_id","starts_at","name","phone","confirmed"]}})
    providers=[]
    # Prefer the tenant's connected realtime-capable AI credential so public voice
    # works with the same per-tenant integration model used by the admin dashboard.
    integration_key=(settings.integration_credential_encryption_key or settings.whatsapp_credential_encryption_key)
    if integration_key:
        rows=db.scalars(select(TenantIntegration).where(
            TenantIntegration.tenant_id==tenant.id,
            TenantIntegration.integration_key.in_(["gemini","openai"]),
            TenantIntegration.status=="connected"
        )).all()
        for row in rows:
            try:
                cfg=decrypt_channel_config(row.config_encrypted,integration_key)
                api_key=cfg.get("api_key") or cfg.get("access_token") or ""
                if not api_key: continue
                if row.integration_key=="gemini":
                    model=cfg.get("realtime_model") or cfg.get("live_model") or settings.gemini_live_model
                    providers.append(VoiceProvider("gemini",model,api_key,priority=10))
                elif row.integration_key=="openai":
                    model=cfg.get("realtime_model") or settings.openai_realtime_model
                    providers.append(VoiceProvider("openai",model,api_key,priority=20))
            except Exception:
                logging.getLogger("uvicorn.error").exception(
                    "PUBLIC_VOICE_WS_TENANT_PROVIDER_CONFIG_FAILED call_id=%s provider=%s",
                    call.id,row.integration_key
                )
    # Platform/environment credentials remain fallback providers.
    if settings.gemini_api_key:
        providers.append(VoiceProvider("gemini",settings.gemini_live_model,settings.gemini_api_key,priority=100))
    if settings.openai_api_key:
        providers.append(VoiceProvider("openai",getattr(settings,"openai_realtime_model","gpt-realtime-2.1"),settings.openai_api_key,priority=200))
    providers.sort(key=lambda p:p.priority)
    state=VoiceSessionState(call_id=call.id,provider_name="")
    turn_controller=VoiceTurnController()
    gateway=VoiceGateway({"gemini":GeminiLiveAdapter(),"openai":OpenAIRealtimeAdapter()})
    provider=None
    session=None
    try:
        provider,session=await gateway.connect_with_failover(providers,system_instruction=system,tools=tool_declarations,state=state)
    except Exception:
        logging.getLogger("uvicorn.error").exception(
            "PUBLIC_VOICE_WS_PROVIDER_CONNECT_FAILED call_id=%s providers=%s",
            call.id, [p.name for p in providers],
        )
        call.status="failed"
        call.resolution="ai_provider_unavailable"
        db.commit()
        try:
            await websocket.send_json({
                "type":"error",
                "code":"ai_provider_unavailable",
                "message":"The AI voice service is temporarily unavailable.",
                "recoverable":True,
            })
            await websocket.close(code=1011)
        except Exception:
            pass
        db.close()
        return
    try:
        await websocket.send_json({"type":"status","status":"ai_connected","provider":provider.name})
        await gateway.adapter_for(provider).send_text(session,"Begin the call now.")
        while True:
            recv_task=asyncio.create_task(websocket.receive_text())
            provider_task=asyncio.create_task(gateway.adapter_for(provider).recv(session))
            done,_=await asyncio.wait([recv_task,provider_task],return_when=asyncio.FIRST_COMPLETED)
            if recv_task in done:
                msg=json.loads(recv_task.result()); typ=msg.get("type"); state.last_activity=time.time()
                if typ=="audio":
                    await gateway.adapter_for(provider).send_audio(session,msg["data"])
                elif typ=="interrupt":
                    state.interrupted=True
                    await gateway.adapter_for(provider).interrupt(session)
                elif typ=="text":
                    await gateway.adapter_for(provider).send_text(session,msg.get("text",""))
                elif typ=="stop":
                    break
                if not provider_task.done(): provider_task.cancel()
            else:
                if not recv_task.done(): recv_task.cancel()
                try:
                    event=provider_task.result()
                except Exception:
                    old_provider=provider
                    try: await gateway.adapter_for(old_provider).close(session)
                    except Exception: pass
                    try:
                        provider,session=await gateway.reconnect(providers,old_provider,system_instruction=system,tools=tool_declarations,state=state)
                    except Exception:
                        logging.getLogger("uvicorn.error").exception(
                            "PUBLIC_VOICE_WS_RECONNECT_FAILED call_id=%s provider=%s",
                            call.id, old_provider.name if old_provider else None,
                        )
                        try:
                            await websocket.send_json({
                                "type":"error",
                                "code":"ai_provider_reconnect_failed",
                                "message":"The AI voice connection was interrupted and could not be recovered.",
                                "recoverable":True,
                            })
                            await websocket.close(code=1011)
                        except Exception:
                            pass
                        break
                    await websocket.send_json({"type":"status","status":"ai_reconnected","provider":provider.name,"reconnects":state.reconnects,"failovers":state.failovers})
                    await gateway.adapter_for(provider).send_text(session,"Continue the call naturally from the preserved context.")
                    continue
                gw=event.get("_gateway") or {}
                if gw.get("event")=="interruption":
                    state.interrupted=True
                    if turn_controller.interrupt():
                        await websocket.send_json({"type":"interruption"})
                    continue
                if gw.get("event")=="response_done":
                    trace=turn_controller.complete()
                    if trace:
                        await websocket.send_json({"type":"turn_metrics","voice_to_first_audio_ms":trace.voice_to_first_audio_ms,"interrupted":trace.interrupted_at is not None})
                    continue
                sc=event.get("serverContent") or {}
                inp=(sc.get("inputTranscription") or {}).get("text")
                out=(sc.get("outputTranscription") or {}).get("text")
                if inp:
                    turn_controller.input_final()
                    state.customer_transcript.append(inp); state.turn_index+=1
                    call.transcript=((call.transcript+"\\n") if call.transcript else "")+"CUSTOMER: "+inp
                    call.language=detect_language(inp); call.ai_turns=(call.ai_turns or 0)+1
                    db.commit(); await websocket.send_json({"type":"transcript","role":"customer","text":inp})
                if out:
                    turn_controller.output(chars=len(out))
                    state.assistant_transcript.append(out)
                    call.transcript=((call.transcript+"\\n") if call.transcript else "")+"AI: "+out
                    db.commit(); await websocket.send_json({"type":"transcript","role":"ai","text":out})
                if event.get("toolCall"):
                    responses=[]
                    for fc in event["toolCall"].get("functionCalls",[]):
                        args=fc.get("args",{}); name=fc.get("name")
                        if name=="check_availability":
                            try:
                                if not capability_enabled(tenant_policy(db,tenant.id),"bookings",True):
                                    raise ValueError("Appointments are disabled for this business.")
                                requested_date=date.fromisoformat(str(args.get("date","")))
                                service_id=str(args.get("service_id","")).strip()
                                service=db.scalar(select(Service).where(Service.id==service_id,Service.tenant_id==tenant.id,Service.is_active==True)) if service_id else db.scalar(select(Service).where(Service.tenant_id==tenant.id,Service.is_active==True).order_by(Service.name).limit(1))
                                if not service:
                                    raise ValueError("No active appointment service is configured.")
                                slots=available_slots(db,tenant,service.id,requested_date,str(args.get("staff_id")) if args.get("staff_id") else None)
                                weekday_rule=db.scalar(select(BusinessHour).where(
                                    BusinessHour.tenant_id==tenant.id,BusinessHour.weekday==requested_date.weekday()
                                ))
                                requested_time=str(args.get("time","")).strip().upper().replace(".","")
                                if requested_time:
                                    import re as _re
                                    # Voice models occasionally attach AM to a bare time such as
                                    # "5:30" after the caller never said AM. If that AM time is
                                    # outside the tenant's business hours, prefer the corresponding
                                    # PM time when the tenant is open then.
                                    bare_time=None
                                    tm_bare=_re.match(r"^(\d{1,2})(?::(\d{2}))?$",requested_time)
                                    if tm_bare:
                                        bare_time=True
                                        hh=int(tm_bare.group(1)); mm=int(tm_bare.group(2) or 0)
                                        if 1 <= hh <= 11:
                                            requested_time=f"{hh}:{mm:02d} PM"
                                    tm=_re.match(r"^(\d{1,2})(?::(\d{2}))?\s*(AM|PM)$",requested_time)
                                    if tm:
                                        hh=int(tm.group(1)); mm=int(tm.group(2) or 0); mer=tm.group(3)
                                        if mer=="AM" and hh < 12:
                                            # Only reinterpret an AM value when the same PM value
                                            # is within business hours AND the recent customer
                                            # transcript did not explicitly say AM.
                                            explicit_am=bool(_re.search(r"\b"+str(hh)+r"(?::"+f"{mm:02d}"+r")?\s*a\.?m\.?\b", (call.transcript or "").lower()))
                                            if not explicit_am and hh < 12:
                                                pm_hour=hh+12
                                                rule=weekday_rule
                                                if rule and rule.open_time <= time(pm_hour,mm) < rule.close_time:
                                                    mer="PM"
                                        if mer=="PM" and hh!=12: hh+=12
                                        if mer=="AM" and hh==12: hh=0
                                        wanted=f"{hh:02d}:{mm:02d}"
                                        slots=[s for s in slots if s["start"][11:16]==wanted]
                                responses.append({"id":fc.get("id"),"name":name,"response":{"result":{"date":requested_date.isoformat(),"timezone":tenant.timezone,"service_id":service.id,"service_name":service.name,"requested_time":requested_time or None,"available":bool(slots),"slots":slots[:20]}}})
                            except Exception as exc:
                                responses.append({"id":fc.get("id"),"name":name,"response":{"result":{"available":False,"error":str(exc)}}})
                        elif name=="save_customer_identity":
                            try:
                                c=upsert_customer(db,tenant.id,str(args.get("phone","")).strip(),str(args.get("name","")).strip(),False,source="ai_voice")
                                call.customer_id=c.id; call.status="connected"; call.answered_at=call.answered_at or datetime.utcnow(); db.commit()
                                responses.append({"id":fc.get("id"),"name":name,"response":{"result":{"customer_id":c.id,"verified":True}}})
                            except Exception as exc:
                                db.rollback(); responses.append({"id":fc.get("id"),"name":name,"response":{"result":{"verified":False,"error":str(exc)}}})
                        elif name=="create_booking":
                            try:
                                import logging as _logging
                                _log=_logging.getLogger("uvicorn.error")
                                if not capability_enabled(tenant_policy(db,tenant.id),"bookings",True):
                                    raise ValueError("Appointments are disabled for this business.")
                                # Realtime providers can serialize booleans as true/false strings.
                                confirmed=args.get("confirmed")
                                if isinstance(confirmed,str):
                                    confirmed=confirmed.strip().lower() in ("true","1","yes","confirm","confirmed")
                                if confirmed is not True:
                                    raise ValueError("Customer confirmation is required before booking.")
                                if not call.customer_id:
                                    raise ValueError("Verified customer is unavailable")
                                c=db.get(Customer,call.customer_id)
                                if not c:
                                    raise ValueError("Verified customer is unavailable")
                                # The model may omit service_id when there is only one active
                                # appointment service. Resolve it server-side instead of failing
                                # a valid customer confirmation.
                                service_id=str(args.get("service_id","")).strip()
                                service=(db.scalar(select(Service).where(
                                    Service.id==service_id,Service.tenant_id==tenant.id,Service.is_active==True
                                )) if service_id else db.scalar(select(Service).where(
                                    Service.tenant_id==tenant.id,Service.is_active==True
                                ).order_by(Service.name).limit(1)))
                                if not service:
                                    raise ValueError("No active appointment service is configured.")
                                raw_starts=str(args.get("starts_at","")).strip()
                                if not raw_starts:
                                    raise ValueError("Appointment date and time are required.")
                                starts_at=datetime.fromisoformat(raw_starts.replace("Z","+00:00"))
                                # Appointment times from the voice model are business-local.
                                # Normalize aware values into the tenant-local wall clock before
                                # create_appointment converts them to UTC.
                                if starts_at.tzinfo is not None:
                                    starts_at=starts_at.astimezone(ZoneInfo(tenant.timezone)).replace(tzinfo=None)
                                # If the model turned a bare business-hour time such as 5:30
                                # into 05:30 AM, correct it to 17:30 only when the caller did
                                # not explicitly say AM and the PM time is within hours.
                                weekday_rule=db.scalar(select(BusinessHour).where(
                                    BusinessHour.tenant_id==tenant.id,BusinessHour.weekday==starts_at.weekday()
                                ))
                                if weekday_rule and starts_at.hour < 12:
                                    import re as _re
                                    explicit_am=bool(_re.search(
                                        r"\b"+str(starts_at.hour)+r"(?::"+f"{starts_at.minute:02d}"+r")?\s*a\.?m\.?\b",
                                        (call.transcript or "").lower()
                                    ))
                                    pm_time=time(starts_at.hour+12,starts_at.minute)
                                    if not explicit_am and weekday_rule.open_time <= pm_time < weekday_rule.close_time:
                                        starts_at=starts_at.replace(hour=starts_at.hour+12)
                                # Booking is an owned core workflow: validate the tenant's
                                # hours and live availability before committing anything.
                                if weekday_rule and weekday_rule.is_closed:
                                    raise ValueError("The business is closed at that time.")
                                if weekday_rule and (starts_at.time()<weekday_rule.open_time or starts_at.time()>=weekday_rule.close_time):
                                    raise ValueError("That time is outside business hours.")
                                staff_id=str(args.get("staff_id")).strip() if args.get("staff_id") else None
                                a,q=create_appointment(
                                    db,tenant,c,service,starts_at,"ai_voice",staff_id,
                                    str(args.get("notes")) if args.get("notes") else None,True,False
                                )
                                db.commit()
                                _log.info("VOICE_BOOKING_CONFIRMED call_id=%s booking_id=%s service_id=%s starts_at=%s",
                                          call.id,a.id,service.id,a.starts_at.isoformat())
                                responses.append({"id":fc.get("id"),"name":name,"response":{"result":{
                                    "booking_id":a.id,"confirmed":True,"starts_at":a.starts_at.isoformat(),
                                    "queue_token":q.token if q else None,"service_id":service.id,"service_name":service.name
                                }}})
                            except Exception as exc:
                                db.rollback()
                                import logging as _logging
                                _logging.getLogger("uvicorn.error").exception("VOICE_BOOKING_FAILED call_id=%s args=%s",call.id,args)
                                responses.append({"id":fc.get("id"),"name":name,"response":{"result":{
                                    "confirmed":False,"error":str(exc),"retryable":False
                                }}})
                    if responses: await gateway.adapter_for(provider).send_tool_response(session,responses)
    except Exception as exc:
        # Preserve transcript/session state and transparently attempt provider/session recovery.
        try:
            old_provider=provider
            old_session=session
            await gateway.adapter_for(old_provider).close(old_session)
            provider,session=await gateway.reconnect(providers,old_provider,system_instruction=system,tools=tool_declarations,state=state)
            await websocket.send_json({"type":"status","status":"ai_reconnected","provider":provider.name,"reconnects":state.reconnects,"failovers":state.failovers})
            await gateway.adapter_for(provider).send_text(session,"Continue the call naturally from the preserved context.")
            while True:
                raw=await websocket.receive_text(); msg=json.loads(raw)
                if msg.get("type")=="stop": break
                if msg.get("type")=="interrupt": await gateway.adapter_for(provider).interrupt(session)
                elif msg.get("type")=="audio": await gateway.adapter_for(provider).send_audio(session,msg["data"])
                elif msg.get("type")=="text": await gateway.adapter_for(provider).send_text(session,msg.get("text",""))
                else:
                    continue
        except Exception as recovery_exc:
            try: await websocket.send_json({"type":"error","message":"Voice session could not be recovered.","recovered":False})
            except Exception: pass
    finally:
        try:
            if 'session' in locals(): await gateway.adapter_for(provider).close(session)
        except Exception: pass
        try:
            db.refresh(call); now=datetime.utcnow(); call.ended_at=now
            if call.started_at: call.duration_seconds=max(0,int((now-call.started_at).total_seconds()))
            if call.status not in {"handoff_requested","handoff_accepted","connected"}: call.status="ended"
            if not call.resolution: call.resolution="completed"
            db.commit()
        finally: db.close()

class PublicVoiceTurnRequest(BaseModel):
    transcript:str=Field(min_length=1,max_length=4000)
    conversation_id:str|None=None
    call_id:str|None=None
    channel:str="voice"

@app.post("/api/v1/public/business/{slug}/call/{call_id}/handoff")
def public_handoff_start(slug:str, call_id:str, db:Session=Depends(get_db)):
    """Promote an AI call to an authenticated staff WebRTC room without exposing tenant auth to the customer."""
    t=db.scalar(select(Tenant).where(Tenant.slug==slug.lower()))
    if not t: raise HTTPException(404,"Business not found")
    if not _feature_config(db,t.id).get("human_handoff",True): raise HTTPException(403,"Human handoff is not available for this business")
    call=db.scalar(select(CallRecord).where(
        CallRecord.id==call_id, CallRecord.tenant_id==t.id, CallRecord.source=="pwa_voice"
    ))
    if not call: raise HTTPException(404,"Call not found")
    age=(datetime.utcnow()-call.started_at).total_seconds() if call.started_at else 999999
    if age>900: raise HTTPException(410,"Call session expired")
    if call.status not in ("handoff_requested","handoff_accepted","connected"):
        raise HTTPException(409,"Call is not ready for human handoff")
    routed=route_call(db,t.id,call,call.intent or "human_handoff")
    if not routed.get("staff"):
        call.status="handoff_unavailable"
        db.commit()
        return {"call_id":call.id,"status":call.status,"room_id":None,"message":"No assigned staff is currently available."}
    call.staff_id=(routed.get("staff") or {}).get("id") or call.staff_id
    call.room_id=call.room_id or "call-"+call.id
    call.status="handoff_requested"
    db.commit()
    return {
        "call_id":call.id,
        "status":call.status,
        "room_id":call.room_id,
        "room_token":issue_call_room_token(call.id,"call-customer"),
        "staff":routed.get("staff")
    }

@app.get("/api/v1/public/business/{slug}/call/{call_id}/handoff")
def public_handoff_status(slug:str, call_id:str, db:Session=Depends(get_db)):
    t=db.scalar(select(Tenant).where(Tenant.slug==slug.lower()))
    if not t: raise HTTPException(404,"Business not found")
    if not _feature_config(db,t.id).get("human_handoff",True): raise HTTPException(403,"Human handoff is not available for this business")
    call=db.scalar(select(CallRecord).where(CallRecord.id==call_id,CallRecord.tenant_id==t.id))
    if not call: raise HTTPException(404,"Call not found")
    staff=db.get(StaffMember,call.staff_id) if call.staff_id else None
    return {"call_id":call.id,"status":call.status,"room_id":call.room_id,"room_token":issue_call_room_token(call.id,"call-customer") if call.room_id and call.status in ("handoff_requested","handoff_accepted","connected") else None,"staff":{"id":staff.id,"name":staff.name} if staff else None}

@app.get("/api/v1/public/business/{slug}/voice/ice")
async def public_voice_ice(slug: str, db: Session = Depends(get_db)):
    t = db.scalar(select(Tenant).where(Tenant.slug == slug.lower()))
    if not t:
        raise HTTPException(404, "Business not found")
    if not _feature_config(db, t.id).get("ai_voice", True):
        raise HTTPException(403, "Voice calling is not available for this business")
    from .turn import generate_ice_config
    result = await generate_ice_config(tenant_id=t.id)
    return {
        "ice_servers": result.ice_servers,
        "provider": result.provider,
        "ttl_seconds": result.ttl_seconds,
    }

@app.post("/api/v1/public/business/{slug}/voice/turn")
async def public_voice_turn(slug:str,payload:PublicVoiceTurnRequest,db:Session=Depends(get_db)):
    t=db.scalar(select(Tenant).where(Tenant.slug==slug.lower()))
    if not t: raise HTTPException(404,"Business not found")
    if not _feature_config(db,t.id).get("ai_voice",True): raise HTTPException(403,"Voice calling is not available for this business")
    result=await generate_reply(db,t.id,payload.transcript,payload.conversation_id,payload.channel)

    # Browser/PWA voice currently uses the deterministic /voice/turn path.
    # Execute confirmed appointments here; the realtime WebSocket has a
    # separate provider-tool path and is not involved in these calls.
    booking=result.get("booking") or {}
    if payload.call_id and booking.get("confirmation_requested"):
        call_for_booking=db.scalar(select(CallRecord).where(
            CallRecord.id==payload.call_id,CallRecord.tenant_id==t.id
        ))
        try:
            if not call_for_booking or not call_for_booking.customer_id:
                raise ValueError("Customer identity is required before booking.")
            customer=db.get(Customer,call_for_booking.customer_id)
            if not customer:
                raise ValueError("Customer record was not found.")
            service_id=booking.get("service_id")
            service=db.get(Service,service_id) if service_id else db.scalar(
                select(Service).where(Service.tenant_id==t.id,Service.is_active==True)
                .order_by(Service.name).limit(1)
            )
            # A tenant can enable bookings before configuring a service. Keep the
            # booking engine usable by creating one explicit generic appointment
            # service instead of failing the confirmed transaction.
            if not service:
                service=Service(
                    id=str(uuid.uuid4()),
                    tenant_id=t.id,
                    name="General Appointment",
                    description="Default appointment service; replace with your configured service.",
                    price=0,
                    currency="INR",
                    duration_minutes=30,
                    is_active=True,
                )
                db.add(service)
                db.flush()
                logging.getLogger("uvicorn.error").info(
                    "VOICE_BOOKING_DEFAULT_SERVICE_CREATED tenant_id=%s service_id=%s",
                    t.id, service.id,
                )
            date_text=str(booking.get("date") or "").strip()
            time_text=str(booking.get("time") or "").strip().upper()
            if not date_text or not time_text:
                raise ValueError("The appointment date or time could not be verified.")
            starts_at=datetime.strptime(
                f"{date_text} {time_text}", "%Y-%m-%d %I:%M %p"
            ) if ":" in time_text else datetime.strptime(
                f"{date_text} {time_text}", "%Y-%m-%d %I %p"
            )
            hours=db.scalar(select(BusinessHour).where(
                BusinessHour.tenant_id==t.id,
                BusinessHour.weekday==starts_at.weekday()
            ))
            if hours and hours.is_closed:
                raise ValueError("The business is closed at that time.")
            if hours and (starts_at.time()<hours.open_time or starts_at.time()>=hours.close_time):
                raise ValueError("That time is outside business hours.")
            # Idempotency guard: a repeated voice confirmation must not create a duplicate.
            from .booking import local_to_utc_naive
            starts_utc=local_to_utc_naive(starts_at,t.timezone)
            existing_appointment=db.scalar(select(Appointment).where(
                Appointment.tenant_id==t.id,
                Appointment.customer_id==customer.id,
                Appointment.service_id==service.id,
                Appointment.starts_at==starts_utc,
                Appointment.status.in_(["requested","confirmed","checked_in","serving"])
            ))
            if existing_appointment:
                appointment,queue=existing_appointment,None
            else:
                appointment,queue=create_appointment(
                    db,t,customer,service,starts_at,"ai_voice",None,None,False,False
                )
            db.commit()
            conversation_row=db.get(Conversation, result.get("conversation_id"))
            if conversation_row:
                conversation_row.state="booking_confirmed"
                conversation_row.last_assistant_message=(
                    f"Perfect. Your appointment is confirmed for "
                    f"{starts_at.strftime('%A, %B %-d')} at {starts_at.strftime('%-I:%M %p')}. "
                    "We look forward to seeing you."
                )
                db.commit()
            result["reply"]=(
                f"Perfect. Your appointment is confirmed for "
                f"{starts_at.strftime('%A, %B %-d')} at {starts_at.strftime('%-I:%M %p')}. "
                "We look forward to seeing you."
            )
            result["booking"]={**booking,"confirmed":True,"booking_id":appointment.id,
                               "queue_token":queue.token if queue else None}
        except ValueError as exc:
            db.rollback()
            logging.getLogger("uvicorn.error").warning(
                "VOICE_PUBLIC_BOOKING_REJECTED call_id=%s booking=%s error=%s",
                payload.call_id, booking, exc,
            )
            conversation_row=db.get(Conversation, result.get("conversation_id")) if result.get("conversation_id") else None
            if conversation_row:
                # Do not leave the conversation in booking_confirmation after a
                # failed transaction; otherwise the next unrelated sentence can
                # resurrect the stale date/time from the previous attempt.
                conversation_row.state="booking_conflict"
                conversation_row.last_assistant_message=(
                    "The selected slot was rechecked and was no longer available. "
                    "Let's choose a fresh slot."
                )
                db.commit()
            result["reply"]="That slot was no longer available when I rechecked it. Let's choose a fresh available time."
            result["booking"]={**booking,"confirmed":False,"error":str(exc),"stale":True}
            result["handoff_required"]=False
        except Exception as exc:
            db.rollback()
            logging.getLogger("uvicorn.error").exception(
                "VOICE_PUBLIC_BOOKING_FAILED call_id=%s booking=%s", payload.call_id, booking
            )
            conversation_row=db.get(Conversation, result.get("conversation_id")) if result.get("conversation_id") else None
            if conversation_row:
                conversation_row.state="booking_conflict"
                conversation_row.last_assistant_message="I couldn't complete that booking. Let's choose a fresh available time."
                db.commit()
            result["reply"]="I couldn't complete that booking. Let's choose a fresh available time."
            result["booking"]={**booking,"confirmed":False,"error":str(exc),"stale":True}
            result["handoff_required"]=False

    if payload.call_id and booking.get("cancel_requested"):
        call_for_cancel=db.scalar(select(CallRecord).where(
            CallRecord.id==payload.call_id,CallRecord.tenant_id==t.id
        ))
        try:
            if not call_for_cancel or not call_for_cancel.customer_id:
                raise ValueError("Customer identity is required before cancelling an appointment.")
            customer=db.get(Customer,call_for_cancel.customer_id)
            if not customer:
                raise ValueError("Customer record was not found.")
            appointment=None
            date_text=str(booking.get("date") or "").strip()
            time_text=str(booking.get("time") or "").strip().upper()
            if date_text and time_text:
                starts_at=datetime.strptime(
                    f"{date_text} {time_text}", "%Y-%m-%d %I:%M %p"
                ) if ":" in time_text else datetime.strptime(
                    f"{date_text} {time_text}", "%Y-%m-%d %I %p"
                )
                from .booking import local_to_utc_naive
                starts_utc=local_to_utc_naive(starts_at,t.timezone)
                appointment=db.scalar(select(Appointment).where(
                    Appointment.tenant_id==t.id,
                    Appointment.customer_id==customer.id,
                    Appointment.starts_at==starts_utc,
                    Appointment.status.in_(["requested","confirmed","checked_in","serving"])
                ).order_by(Appointment.created_at.desc()).limit(1))
            if not appointment:
                appointment=db.scalar(select(Appointment).where(
                    Appointment.tenant_id==t.id,
                    Appointment.customer_id==customer.id,
                    Appointment.starts_at>=datetime.utcnow(),
                    Appointment.status.in_(["requested","confirmed","checked_in","serving"])
                ).order_by(Appointment.starts_at.asc()).limit(1))
            if not appointment:
                raise ValueError("No active upcoming appointment was found.")
            appointment.status="cancelled"
            q=db.scalar(select(QueueEntry).where(QueueEntry.appointment_id==appointment.id))
            if q:
                q.status="cancelled"
                q.completed_at=datetime.utcnow()
                appointment.queue_status="cancelled"
            db.commit()
            result["reply"]={
                "hi":f"ठीक है। आपका {appointment.starts_at.strftime('%-d %B')} का अपॉइंटमेंट रद्द कर दिया गया है।",
                "te":f"సరే. మీ {appointment.starts_at.strftime('%-d %B')} అపాయింట్‌మెంట్ రద్దు చేశాను."
            }.get(
                result.get("language"),
                f"Okay. Your appointment for {appointment.starts_at.strftime('%B %-d at %-I:%M %p')} has been cancelled."
            )
            result["booking"]={**booking,"cancel_requested":False,"cancelled":True,
                               "booking_id":appointment.id,"cancellation_confirmed":True}
        except Exception as exc:
            db.rollback()
            logging.getLogger("uvicorn.error").warning(
                "VOICE_PUBLIC_BOOKING_CANCEL_REJECTED call_id=%s booking=%s error=%s",
                payload.call_id, booking, exc,
            )
            result["reply"]="I could not find an active appointment to cancel."
            result["booking"]={**booking,"cancel_requested":False,"cancelled":False,
                               "cancellation_confirmed":False,"error":str(exc)}

    if payload.call_id:
        call=db.scalar(select(CallRecord).where(CallRecord.id==payload.call_id,CallRecord.tenant_id==t.id))
        if call:
            now=datetime.utcnow()
            call.transcript=((call.transcript+"\\n") if call.transcript else "")+"CUSTOMER: "+payload.transcript+"\\nAI: "+result["reply"]
            call.intent=result.get("intent")
            call.language=result.get("language") or detect_language(payload.transcript)
            call.ai_turns=(call.ai_turns or 0)+1
            if result.get("knowledge_hit"): call.knowledge_hits=(call.knowledge_hits or 0)+1
            if result.get("handoff_required"):
                call.human_callback_requested=True; call.status="handoff_requested"; call.resolution="human_callback"
                route_call(db,t.id,call,result.get("intent"))
            elif result.get("knowledge_hit"):
                call.resolution="knowledge"
            else:
                call.resolution="ai"
            if call.answered_at is None: call.answered_at=now
            db.commit()
    return {**result,"tenant_id":t.id,"call_id":payload.call_id}
@app.post("/api/v1/tenants/{tenant_id}/calls",status_code=201)
def create_call(tenant_id,user=Depends(get_current_user),db:Session=Depends(get_db)):
    require_tenant(user,tenant_id); c=CallRecord(tenant_id=tenant_id,status="created"); db.add(c); db.commit(); db.refresh(c); return {"id":c.id,"status":c.status}
@app.get("/api/v1/tenants/{tenant_id}/loyalty/{customer_id}")
def loyalty_balance(tenant_id,customer_id,user=Depends(get_current_user),db:Session=Depends(get_db)):
    require_tenant(user,tenant_id)
    from .loyalty import balance as _bal, history as _hist
    if not _feature_config(db,tenant_id).get("loyalty",False):
        raise HTTPException(403,"Loyalty is disabled for this business")
    return {"points":_bal(db,tenant_id,customer_id),"history":_hist(db,tenant_id,customer_id,50)}


@app.patch("/api/v1/tenants/{tenant_id}/calls/{call_id}")
def update_call(tenant_id,call_id,payload:dict,user=Depends(get_current_user),db:Session=Depends(get_db)):
    require_tenant(user,tenant_id); c=db.scalar(select(CallRecord).where(CallRecord.id==call_id,CallRecord.tenant_id==tenant_id))
    if not c: raise HTTPException(404,"Call not found")
    for k in ["status","department","transcript","summary","intent"]:
        if k in payload: setattr(c,k,payload[k])
    db.commit(); return {"id":c.id,"status":c.status}


# --- Knowledge learning + CRM call intelligence ---
class KnowledgeCandidateCreate(BaseModel):
    question: str = Field(min_length=2, max_length=4000)
    answer: str = Field(min_length=1, max_length=8000)
    language: str = Field(default="en", max_length=16)
    intent: str | None = Field(default=None, max_length=120)

@app.get("/api/v1/tenants/{tenant_id}/knowledge-candidates")
def list_knowledge_candidates(tenant_id, status: str | None = None, user=Depends(get_current_user), db:Session=Depends(get_db)):
    require_tenant(user,tenant_id)
    q=select(KnowledgeCandidate).where(KnowledgeCandidate.tenant_id==tenant_id)
    if status: q=q.where(KnowledgeCandidate.status==status)
    rows=db.scalars(q.order_by(KnowledgeCandidate.last_asked_at.desc())).all()
    return {"items":[{"id":x.id,"question":x.question,"answer":x.answer,"language":x.language,"intent":x.intent,"status":x.status,"source":x.source,"provider":x.provider,"times_asked":x.times_asked,"first_asked_at":x.first_asked_at.isoformat() if x.first_asked_at else None,"last_asked_at":x.last_asked_at.isoformat() if x.last_asked_at else None} for x in rows]}

@app.post("/api/v1/tenants/{tenant_id}/knowledge-candidates/{candidate_id}/approve")
def approve_knowledge_candidate(tenant_id,candidate_id,user=Depends(get_current_user),db:Session=Depends(get_db)):
    require_tenant(user,tenant_id)
    x=db.scalar(select(KnowledgeCandidate).where(KnowledgeCandidate.id==candidate_id,KnowledgeCandidate.tenant_id==tenant_id))
    if not x: raise HTTPException(404,"Knowledge candidate not found")
    item=KnowledgeItem(tenant_id=tenant_id,title=x.question,content=x.answer,kind="learned_faq",language=x.language,source="conversation_learning",approval_status="approved")
    db.add(item); x.status="approved"; db.commit(); db.refresh(item)
    return {"id":item.id,"candidate_id":x.id,"status":"approved"}

@app.post("/api/v1/tenants/{tenant_id}/knowledge-candidates/{candidate_id}/reject")
def reject_knowledge_candidate(tenant_id,candidate_id,user=Depends(get_current_user),db:Session=Depends(get_db)):
    require_tenant(user,tenant_id)
    x=db.scalar(select(KnowledgeCandidate).where(KnowledgeCandidate.id==candidate_id,KnowledgeCandidate.tenant_id==tenant_id))
    if not x: raise HTTPException(404,"Knowledge candidate not found")
    x.status="rejected"; db.commit(); return {"id":x.id,"status":"rejected"}

class CallResolution(BaseModel):
    status: str = Field(default="resolved", max_length=40)
    summary: str = Field(min_length=1, max_length=8000)
    knowledge_answer: str | None = Field(default=None, max_length=8000)
    language: str | None = Field(default=None, max_length=16)

@app.post("/api/v1/tenants/{tenant_id}/calls/{call_id}/resolve")
def resolve_call(tenant_id,call_id,payload:CallResolution,user=Depends(get_current_user),db:Session=Depends(get_db)):
    require_tenant(user,tenant_id)
    call=db.scalar(select(CallRecord).where(CallRecord.id==call_id,CallRecord.tenant_id==tenant_id))
    if not call: raise HTTPException(404,"Call not found")
    call.status=payload.status
    call.resolution="human_resolved"
    call.summary=payload.summary
    if payload.language: call.language=payload.language
    if call.ended_at is None: call.ended_at=datetime.utcnow()
    if call.started_at: call.duration_seconds=max(0,int((call.ended_at-call.started_at).total_seconds()))
    candidate=None
    if payload.knowledge_answer:
        question=""
        if call.transcript:
            parts=[x.removeprefix("CUSTOMER: ").strip() for x in call.transcript.split("\\n") if x.startswith("CUSTOMER: ")]
            question=parts[-1] if parts else ""
        if question:
            existing=db.scalar(select(KnowledgeCandidate).where(
                KnowledgeCandidate.tenant_id==tenant_id,
                KnowledgeCandidate.question==question,
                KnowledgeCandidate.status.in_(["pending","approved"])
            ))
            if existing:
                existing.answer=payload.knowledge_answer
                existing.times_asked=(existing.times_asked or 0)+1
                existing.last_asked_at=datetime.utcnow()
                candidate=existing
            else:
                candidate=KnowledgeCandidate(
                    tenant_id=tenant_id,question=question,answer=payload.knowledge_answer,
                    language=payload.language or call.language or "en",intent=call.intent,status="pending",
                    source="human_callback",provider="human",times_asked=1
                )
                db.add(candidate)
    db.commit()
    return {"call_id":call.id,"status":call.status,"resolution":call.resolution,
            "knowledge_candidate_id":candidate.id if candidate else None}

@app.get("/api/v1/tenants/{tenant_id}/call-logs")
def list_call_logs(tenant_id,customer_id: str|None=None,limit:int=Query(default=100,ge=1,le=500),user=Depends(get_current_user),db:Session=Depends(get_db)):
    require_tenant(user,tenant_id)
    q=select(CallRecord).where(CallRecord.tenant_id==tenant_id)
    if customer_id:q=q.where(CallRecord.customer_id==customer_id)
    rows=db.scalars(q.order_by(CallRecord.created_at.desc()).limit(limit)).all()
    return {"items":[{"id":x.id,"customer_id":x.customer_id,"source":x.source,"status":x.status,"department":x.department,"staff_id":x.staff_id,"language":x.language,"started_at":x.started_at.isoformat() if x.started_at else None,"answered_at":x.answered_at.isoformat() if x.answered_at else None,"ended_at":x.ended_at.isoformat() if x.ended_at else None,"duration_seconds":x.duration_seconds,"call_number":x.call_number,"resolution":x.resolution,"intent":x.intent,"summary":x.summary,"knowledge_hits":x.knowledge_hits,"ai_turns":x.ai_turns,"human_callback_requested":x.human_callback_requested,"transcript":x.transcript} for x in rows]}

@app.get("/api/v1/tenants/{tenant_id}/customers/{customer_id}/call-summary")
def customer_call_summary(tenant_id,customer_id,user=Depends(get_current_user),db:Session=Depends(get_db)):
    require_tenant(user,tenant_id)
    rows=db.scalars(select(CallRecord).where(CallRecord.tenant_id==tenant_id,CallRecord.customer_id==customer_id).order_by(CallRecord.created_at)).all()
    return {"customer_id":customer_id,"total_calls":len(rows),"total_duration_seconds":sum(x.duration_seconds or 0 for x in rows),"last_call_at":rows[-1].created_at.isoformat() if rows else None,"languages":sorted({x.language for x in rows if x.language}),"calls":[{"id":x.id,"call_number":x.call_number,"created_at":x.created_at.isoformat(),"duration_seconds":x.duration_seconds,"status":x.status,"resolution":x.resolution,"language":x.language,"human_callback_requested":x.human_callback_requested,"intent":x.intent,"summary":x.summary} for x in rows]}

@app.post("/api/v1/auth/password-reset/request")
async def password_reset_request(payload:PasswordResetRequest,db:Session=Depends(get_db)):
    user=db.scalar(select(User).where(User.email==payload.email.lower().strip()))
    if user and user.is_active:
        raw=secrets.token_urlsafe(48); digest=hashlib.sha256(raw.encode()).hexdigest(); expires=datetime.utcnow()+timedelta(minutes=settings.password_reset_ttl_minutes)
        db.add(PasswordResetToken(user_id=user.id,token_hash=digest,expires_at=expires)); db.commit(); tenant=db.get(Tenant,user.tenant_id); await send_password_reset(user,tenant,raw) if tenant else None
    return {"sent":True,"message":"If the account exists, reset instructions have been sent."}

@app.post("/api/v1/auth/password-reset/confirm")
def password_reset_confirm(payload:PasswordResetConfirm,db:Session=Depends(get_db)):
    digest=hashlib.sha256(payload.token.encode()).hexdigest(); token=db.scalar(select(PasswordResetToken).where(PasswordResetToken.token_hash==digest))
    if not token or token.used_at or token.expires_at<datetime.utcnow(): raise HTTPException(400,"Reset link is invalid or expired")
    user=db.get(User,token.user_id)
    if not user or not user.is_active: raise HTTPException(400,"Reset link is invalid or expired")
    user.password_hash=hash_password(payload.password); token.used_at=datetime.utcnow(); db.commit()
    return {"reset":True,"message":"Password updated successfully."}

# ============ SESSION12_FULL_QR ============

class QrCreateRequest(BaseModel):
    kind: str = Field(default="business", pattern="^(business|context|campaign)$")
    label: str = Field(default="Business QR", max_length=160)
    context_type: str | None = Field(default=None, max_length=40)
    context_value: str | None = Field(default=None, max_length=120)
    campaign_id: str | None = Field(default=None, max_length=36)


@app.post("/api/v1/tenants/{tenant_id}/qr", status_code=201)
def create_qr_endpoint(tenant_id, payload: QrCreateRequest, user=Depends(get_current_user), db: Session = Depends(get_db)):
    require_tenant(user, tenant_id)
    from .qr import create_qr
    from .security import audit
    try:
        entry = create_qr(
            db, tenant_id,
            kind=payload.kind, label=payload.label,
            context_type=payload.context_type, context_value=payload.context_value,
            campaign_id=payload.campaign_id, created_by=user.id,
            public_base=settings.public_app_url,
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    audit(db, tenant_id=tenant_id, actor_id=user.id,
          action="qr.created", target_type="qr", target_id=entry["id"],
          detail={"kind": entry["kind"], "label": entry["label"]})
    return entry


@app.get("/api/v1/tenants/{tenant_id}/qr")
def list_qr_endpoint(tenant_id, user=Depends(get_current_user), db: Session = Depends(get_db)):
    require_tenant(user, tenant_id)
    from .qr import list_qrs
    items = list_qrs(db, tenant_id)
    # attach full URL
    base = (settings.public_app_url or "").rstrip("/")
    for it in items:
        it["url"] = f"{base}/c/{it['token']}"
    return {"items": items}


@app.get("/api/v1/tenants/{tenant_id}/qr/{qr_id}")
def get_qr_endpoint(tenant_id, qr_id, user=Depends(get_current_user), db: Session = Depends(get_db)):
    require_tenant(user, tenant_id)
    from .qr import get_qr
    entry = get_qr(db, tenant_id, qr_id)
    if not entry:
        raise HTTPException(404, "QR not found")
    base = (settings.public_app_url or "").rstrip("/")
    entry["url"] = f"{base}/c/{entry['token']}"
    return entry


@app.get("/api/v1/tenants/{tenant_id}/qr/{qr_id}/png")
def get_qr_png_endpoint(tenant_id, qr_id, size: int = 400, user=Depends(get_current_user), db: Session = Depends(get_db)):
    require_tenant(user, tenant_id)
    from .qr import generate_qr_png_for_entry
    from fastapi.responses import Response
    try:
        png, url = generate_qr_png_for_entry(
            db, tenant_id, qr_id,
            size=min(max(int(size), 100), 1000),
            public_base=settings.public_app_url,
        )
    except ValueError as exc:
        raise HTTPException(404, str(exc))
    return Response(content=png, media_type="image/png",
                    headers={"Cache-Control": "no-store"})


@app.delete("/api/v1/tenants/{tenant_id}/qr/{qr_id}")
def delete_qr_endpoint(tenant_id, qr_id, user=Depends(get_current_user), db: Session = Depends(get_db)):
    require_tenant(user, tenant_id)
    from .qr import delete_qr
    from .security import audit
    ok = delete_qr(db, tenant_id, qr_id)
    if not ok:
        raise HTTPException(404, "QR not found")
    audit(db, tenant_id=tenant_id, actor_id=user.id,
          action="qr.deleted", target_type="qr", target_id=qr_id)
    return {"deleted": True}


@app.get("/api/v1/tenants/{tenant_id}/qr-analytics")
def qr_analytics_endpoint(tenant_id, days: int = 30, user=Depends(get_current_user), db: Session = Depends(get_db)):
    require_tenant(user, tenant_id)
    from .qr import qr_analytics
    return qr_analytics(db, tenant_id, days=days)


@app.get("/api/v1/public/qr/{token}/resolve")
def public_qr_resolve(token: str, db: Session = Depends(get_db)):
    from .qr import resolve_token
    info = resolve_token(db, token)
    if not info:
        raise HTTPException(404, "QR not found or tenant inactive")
    return info


class QrScanRequest(BaseModel):
    token: str = Field(min_length=4, max_length=100)
    customer_id: str | None = Field(default=None, max_length=36)


@app.post("/api/v1/public/business/{slug}/qr-scan")
def public_qr_scan(slug: str, payload: QrScanRequest, request: Request, db: Session = Depends(get_db)):
    from .qr import resolve_token, record_scan
    t = db.scalar(select(Tenant).where(Tenant.slug == slug.lower()))
    if not t:
        raise HTTPException(404, "Business not found")
    info = resolve_token(db, payload.token)
    if not info or info["tenant_slug"] != t.slug:
        raise HTTPException(404, "QR not found")
    # capture metadata
    ua = request.headers.get("user-agent")
    ref = request.headers.get("referer") or request.headers.get("referrer")
    ip = request.client.host if request.client else None
    result = record_scan(
        db,
        tenant_id=t.id,
        qr_id=info["qr_id"],
        token=info["token"],
        kind=info["kind"],
        context_type=info["context_type"],
        context_value=info["context_value"],
        campaign_id=info["campaign_id"],
        customer_id=payload.customer_id,
        user_agent=ua, referrer=ref, ip=ip,
    )
    return {**result, "context_type": info["context_type"], "context_value": info["context_value"], "campaign_id": info["campaign_id"], "kind": info["kind"]}

# ============ END SESSION12 ============

# ============ SESSION17A_PLATFORM_TOOLS ============

class FeatureOverrideRequest(BaseModel):
    features: dict


class AdminQrRequest(BaseModel):
    kind: str = Field(default="business", pattern="^(business|context|campaign)$")
    label: str = Field(default="Admin generated QR", max_length=160)
    context_type: str | None = Field(default=None, max_length=40)
    context_value: str | None = Field(default=None, max_length=120)
    campaign_id: str | None = Field(default=None, max_length=36)


class PlatformSettingsUpdate(BaseModel):
    updates: dict


@app.get("/api/v1/platform/overview")
def platform_overview(days: int = 30, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    require_platform_admin(user)
    from .platform_tools import overview
    return overview(db, days=days)


@app.get("/api/v1/platform/tenants")
def platform_tenants_v2(search: str = "", status: str = "", limit: int = 500,
                        user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    require_platform_admin(user)
    from .platform_tools import list_tenants
    return {"items": list_tenants(db, search=search, status=status, limit=limit)}


@app.get("/api/v1/platform/tenants/{tenant_id}/detail")
def platform_tenant_detail(tenant_id: str,
                            user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    require_platform_admin(user)
    t = db.get(Tenant, tenant_id)
    if not t:
        raise HTTPException(404, "Tenant not found")
    from .platform_tools import tenant_health_score, activity_metrics
    from .platform_settings import status as settings_status
    score = tenant_health_score(db, tenant_id)
    return {
        "id": t.id,
        "name": t.name,
        "slug": t.slug,
        "industry": t.industry,
        "status": t.status,
        "plan": getattr(t, "plan", None),
        "city": getattr(t, "city", None),
        "phone": getattr(t, "phone", None),
        "whatsapp_number": getattr(t, "whatsapp_number", None),
        "email": getattr(t, "email", None),
        "address": getattr(t, "address", None),
        "timezone": getattr(t, "timezone", None),
        "created_at": t.created_at.isoformat() if t.created_at else None,
        "last_seen_at": getattr(t, "last_seen_at", None).isoformat() if getattr(t, "last_seen_at", None) else None,
        "health_status": getattr(t, "health_status", "unknown"),
        "region": getattr(t, "region", "GLOBAL"),
        "compliance_flags": getattr(t, "compliance_flags", "{}"),
        "health_score": score,
        "activity": activity_metrics(db, tenant_id, days=30),
    }


@app.get("/api/v1/platform/tenants/{tenant_id}/overrides")
def platform_get_overrides(tenant_id: str,
                            user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    require_platform_admin(user)
    from .platform_tools import get_overrides
    return {"features": get_overrides(db, tenant_id)}


@app.put("/api/v1/platform/tenants/{tenant_id}/overrides")
def platform_set_overrides(tenant_id: str, payload: FeatureOverrideRequest,
                            user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    require_platform_admin(user)
    from .platform_tools import set_overrides
    return {"features": set_overrides(db, tenant_id, payload.features, actor_id=user.id)}


@app.get("/api/v1/platform/tenants/{tenant_id}/whatsapp")
def platform_whatsapp_status(tenant_id: str,
                              user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    require_platform_admin(user)
    from .platform_tools import whatsapp_status
    return whatsapp_status(db, tenant_id)


@app.get("/api/v1/platform/tenants/{tenant_id}/razorpay")
def platform_razorpay_status(tenant_id: str,
                              user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    require_platform_admin(user)
    from .platform_tools import razorpay_status
    return razorpay_status(db, tenant_id)


@app.get("/api/v1/platform/tenants/{tenant_id}/activity")
def platform_activity(tenant_id: str, days: int = 30,
                      user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    require_platform_admin(user)
    from .platform_tools import activity_metrics
    return activity_metrics(db, tenant_id, days=days)


@app.post("/api/v1/platform/tenants/{tenant_id}/qr", status_code=201)
def platform_admin_create_qr(tenant_id: str, payload: AdminQrRequest,
                              user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    require_platform_admin(user)
    from .platform_tools import admin_create_qr
    try:
        return admin_create_qr(
            db, tenant_id,
            kind=payload.kind, label=payload.label,
            context_type=payload.context_type,
            context_value=payload.context_value,
            campaign_id=payload.campaign_id,
            admin_id=user.id,
            public_base=settings.public_app_url,
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc))


@app.get("/api/v1/platform/settings")
def platform_get_settings(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    require_platform_admin(user)
    from .platform_settings import get_all
    return get_all(db)


@app.put("/api/v1/platform/settings")
def platform_update_settings(payload: PlatformSettingsUpdate,
                              user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    require_platform_admin(user)
    from .platform_settings import set_many
    return set_many(db, payload.updates, actor_id=user.id)

# ============ END SESSION17A ============

# ============ SESSION17B_TICKETS ============

class TicketCreateRequest(BaseModel):
    subject: str = Field(min_length=2, max_length=300)
    body: str = Field(default="", max_length=8000)
    category: str = Field(default="support", max_length=40)
    priority: str = Field(default="normal", max_length=20)


class TicketStatusRequest(BaseModel):
    status: str = Field(pattern="^(new|acknowledged|in_progress|waiting_on_tenant|resolved|closed)$")


class TicketReplyRequest(BaseModel):
    message: str = Field(min_length=1, max_length=8000)
    from_tenant: bool = False


class TicketAssignRequest(BaseModel):
    staff_user_id: str | None = None


@app.get("/api/v1/platform/tickets")
def platform_tickets_list(status: str = "", category: str = "", tenant_id: str = "", include_breached_only: bool = False, limit: int = 200, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    require_platform_admin(user)
    from .tickets import list_tickets, sla_summary
    items = list_tickets(db, tenant_id=tenant_id or None, status=status or None, category=category or None, include_breached_only=include_breached_only, limit=limit)
    return {"items": items, "summary": sla_summary(db, tenant_id=tenant_id or None)}


@app.get("/api/v1/platform/tickets/{ticket_id}")
def platform_ticket_get(ticket_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    require_platform_admin(user)
    from .tickets import get_ticket
    t = get_ticket(db, ticket_id)
    if not t:
        raise HTTPException(404, "Ticket not found")
    return t


@app.post("/api/v1/platform/tickets", status_code=201)
def platform_ticket_create(payload: TicketCreateRequest, tenant_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    require_platform_admin(user)
    from .tickets import create_ticket
    try:
        return create_ticket(db, tenant_id=tenant_id, subject=payload.subject, body=payload.body, category=payload.category, priority=payload.priority, created_by=user.id)
    except ValueError as exc:
        raise HTTPException(400, str(exc))


@app.patch("/api/v1/platform/tickets/{ticket_id}/status")
def platform_ticket_set_status(ticket_id: str, payload: TicketStatusRequest, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    require_platform_admin(user)
    from .tickets import set_status
    try:
        return set_status(db, ticket_id, payload.status, actor_id=user.id)
    except ValueError as exc:
        raise HTTPException(400, str(exc))


@app.patch("/api/v1/platform/tickets/{ticket_id}/assign")
def platform_ticket_assign(ticket_id: str, payload: TicketAssignRequest, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    require_platform_admin(user)
    from .tickets import assign
    try:
        return assign(db, ticket_id, payload.staff_user_id, actor_id=user.id)
    except ValueError as exc:
        raise HTTPException(400, str(exc))


@app.post("/api/v1/platform/tickets/{ticket_id}/reply")
def platform_ticket_reply(ticket_id: str, payload: TicketReplyRequest, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    require_platform_admin(user)
    from .tickets import reply
    try:
        return reply(db, ticket_id, payload.message, from_tenant=payload.from_tenant, actor_id=user.id)
    except ValueError as exc:
        raise HTTPException(400, str(exc))

# ============ END SESSION17B_TICKETS ============

# ============ SESSION17B_MESSAGES ============

class PlatformMessageRequest(BaseModel):
    subject: str = Field(min_length=2, max_length=300)
    body: str = Field(default="", max_length=8000)
    send_email: bool = True


@app.get("/api/v1/platform/messages")
def platform_messages_list(tenant_id: str = "", limit: int = 200, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    require_platform_admin(user)
    from .platform_messages import list_messages
    return {"items": list_messages(db, tenant_id=tenant_id or None, limit=limit)}


@app.post("/api/v1/platform/tenants/{tenant_id}/messages", status_code=201)
def platform_message_send(tenant_id: str, payload: PlatformMessageRequest, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    require_platform_admin(user)
    from .platform_messages import send_message
    try:
        return send_message(db, tenant_id=tenant_id, subject=payload.subject, body=payload.body, from_admin_id=user.id, send_email=payload.send_email)
    except ValueError as exc:
        raise HTTPException(400, str(exc))


@app.patch("/api/v1/platform/messages/{message_id}/read")
def platform_message_read(message_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    require_platform_admin(user)
    from .platform_messages import mark_read
    r = mark_read(db, message_id)
    if not r:
        raise HTTPException(404, "Message not found")
    return r

# ============ END SESSION17B_MESSAGES ============

# ============ SESSION17B_CALENDAR ============

@app.get("/api/v1/platform/calendar")
def platform_calendar(year: int = 0, month: int = 0, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    require_platform_admin(user)
    from .calendar import month_view
    now = datetime.utcnow()
    y = year or now.year
    m = month or now.month
    try:
        return month_view(db, y, m)
    except ValueError as exc:
        raise HTTPException(400, str(exc))


@app.get("/api/v1/platform/follow-ups")
def platform_follow_ups(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    require_platform_admin(user)
    from .calendar import follow_ups
    return follow_ups(db)

# ============ END SESSION17B_CALENDAR ============

# ============ SESSION17B_CAL_EVENTS ============

@app.get("/api/v1/platform/calendar/events")
def platform_calendar_events(start: str, end: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    require_platform_admin(user)
    from .calendar import events_between
    try:
        return {"items": events_between(db, start, end)}
    except ValueError as exc:
        raise HTTPException(400, str(exc))

# ============ END SESSION17B_CAL_EVENTS ============

# ============ SESSION17B_TASKS ============

class TaskCreateRequest(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    notes: str = Field(default="", max_length=8000)
    due_at: str = Field(min_length=10, max_length=40)
    tenant_id: str | None = None
    kind: str = Field(default="followup", max_length=40)
    priority: str = Field(default="normal", max_length=20)


class TaskStatusRequest(BaseModel):
    status: str = Field(pattern="^(pending|done|cancelled)$")


@app.get("/api/v1/platform/tasks")
def platform_tasks_list(start: str = "", end: str = "", tenant_id: str = "", status: str = "", limit: int = 300, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    require_platform_admin(user)
    from .tasks import list_tasks, overdue_count
    items = list_tasks(db, start_iso=start or None, end_iso=end or None, tenant_id=tenant_id or None, status=status or None, limit=limit)
    return {"items": items, "overdue": overdue_count(db)}


@app.post("/api/v1/platform/tasks", status_code=201)
def platform_tasks_create(payload: TaskCreateRequest, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    require_platform_admin(user)
    from .tasks import create_task
    try:
        due = datetime.fromisoformat(payload.due_at.replace("Z", "+00:00"))
    except Exception:
        raise HTTPException(400, "due_at must be ISO format")
    try:
        return create_task(db, title=payload.title, due_at=due, notes=payload.notes, tenant_id=payload.tenant_id, kind=payload.kind, priority=payload.priority, created_by=user.id)
    except ValueError as exc:
        raise HTTPException(400, str(exc))


@app.patch("/api/v1/platform/tasks/{task_id}/status")
def platform_tasks_set_status(task_id: str, payload: TaskStatusRequest, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    require_platform_admin(user)
    from .tasks import set_status
    try:
        return set_status(db, task_id, payload.status, actor_id=user.id)
    except ValueError as exc:
        raise HTTPException(400, str(exc))


@app.delete("/api/v1/platform/tasks/{task_id}")
def platform_tasks_delete(task_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    require_platform_admin(user)
    from .tasks import delete_task
    ok = delete_task(db, task_id)
    if not ok:
        raise HTTPException(404, "Task not found")
    return {"deleted": True}

# ============ END SESSION17B_TASKS ============

# ============ SESSION17B_TENANT_CALENDAR ============

class TenantTaskCreate(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    notes: str = Field(default="", max_length=8000)
    due_at: str = Field(min_length=10, max_length=40)
    kind: str = Field(default="followup", max_length=40)
    priority: str = Field(default="normal", max_length=20)
    duration_minutes: int = Field(default=30, ge=5, le=1440)
    all_day: bool = False


def _require_tenant_self(user, tenant_id):
    """A tenant user can only access their own tenant. SuperAdmin can access any."""
    if user.role in ("platform_admin", "super_admin"):
        return
    if user.tenant_id != tenant_id:
        raise HTTPException(403, "Access denied")


@app.get("/api/v1/tenants/{tenant_id}/calendar")
def tenant_calendar_month(tenant_id, year: int = 0, month: int = 0, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    require_tenant(user, tenant_id)
    _require_tenant_self(user, tenant_id)
    from .calendar import month_view
    from datetime import datetime as _dt
    now = _dt.utcnow()
    y = year or now.year
    m = month or now.month
    try:
        data = month_view(db, y, m)
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    # Filter signups to this tenant only
    for day in data["days"]:
        day["signups"] = [s for s in day["signups"] if s["id"] == tenant_id]
    return data


@app.get("/api/v1/tenants/{tenant_id}/calendar/events")
def tenant_calendar_events(tenant_id, start: str, end: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    require_tenant(user, tenant_id)
    _require_tenant_self(user, tenant_id)
    from .calendar import events_between
    from .models_growth import PlatformTask
    from sqlalchemy import select as _select
    try:
        events = events_between(db, start, end)
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    # Only this tenant's events
    events = [e for e in events if e.get("tenant_id") == tenant_id]
    # Add this tenant's tasks
    try:
        from datetime import datetime as _dt
        start_dt = _dt.fromisoformat(start)
        end_dt = _dt.fromisoformat(end)
        task_rows = db.scalars(
            _select(PlatformTask).where(
                PlatformTask.tenant_id == tenant_id,
                PlatformTask.due_at >= start_dt,
                PlatformTask.due_at < end_dt,
            )
        ).all()
        for t in task_rows:
            dur = int(getattr(t, "duration_minutes", 30) or 30)
            at = t.due_at.isoformat()
            ends_at = (t.due_at + __import__("datetime").timedelta(minutes=dur)).isoformat()
            events.append({
                "at": at,
                "ends_at": ends_at,
                "kind": "task",
                "title": ("✓ " if t.status == "done" else "") + t.title,
                "tenant_id": tenant_id,
                "link": "/dashboard/calendar",
                "duration_minutes": dur,
                "all_day": bool(getattr(t, "all_day", False)),
                "meta": {"status": t.status, "priority": t.priority, "task_id": t.id},
            })
    except Exception:
        pass
    events.sort(key=lambda x: x.get("at", ""))
    return {"items": events}


@app.get("/api/v1/tenants/{tenant_id}/calendar/tasks")
def tenant_calendar_tasks(tenant_id, start: str = "", end: str = "", status: str = "", limit: int = 300, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    require_tenant(user, tenant_id)
    _require_tenant_self(user, tenant_id)
    from .tasks import list_tasks
    items = list_tasks(db, start_iso=start or None, end_iso=end or None, tenant_id=tenant_id, status=status or None, limit=limit)
    return {"items": items}


@app.post("/api/v1/tenants/{tenant_id}/calendar/tasks", status_code=201)
def tenant_calendar_create_task(tenant_id, payload: TenantTaskCreate, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    require_tenant(user, tenant_id)
    _require_tenant_self(user, tenant_id)
    from .tasks import create_task
    from datetime import datetime as _dt
    try:
        due = _dt.fromisoformat(payload.due_at.replace("Z", "+00:00"))
    except Exception:
        raise HTTPException(400, "due_at must be ISO format")
    try:
        return create_task(
            db,
            title=payload.title,
            due_at=due,
            notes=payload.notes,
            tenant_id=tenant_id,
            kind=payload.kind,
            priority=payload.priority,
            created_by=user.id,
            duration_minutes=payload.duration_minutes,
            all_day=payload.all_day,
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc))


@app.patch("/api/v1/tenants/{tenant_id}/calendar/tasks/{task_id}/status")
def tenant_calendar_set_task_status(tenant_id, task_id, payload: TaskStatusRequest, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    require_tenant(user, tenant_id)
    _require_tenant_self(user, tenant_id)
    from .tasks import set_status
    from .models_growth import PlatformTask
    t = db.get(PlatformTask, task_id)
    if not t or t.tenant_id != tenant_id:
        raise HTTPException(404, "Task not found")
    try:
        return set_status(db, task_id, payload.status, actor_id=user.id)
    except ValueError as exc:
        raise HTTPException(400, str(exc))


@app.delete("/api/v1/tenants/{tenant_id}/calendar/tasks/{task_id}")
def tenant_calendar_delete_task(tenant_id, task_id, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    require_tenant(user, tenant_id)
    _require_tenant_self(user, tenant_id)
    from .models_growth import PlatformTask
    t = db.get(PlatformTask, task_id)
    if not t or t.tenant_id != tenant_id:
        raise HTTPException(404, "Task not found")
    db.delete(t)
    db.commit()
    return {"deleted": True}

# ============ END SESSION17B_TENANT_CALENDAR ============

# === ENDPOINT FEATURE GATES ===

# SESSION11_PAYMENT_IDEMPOTENCY

# SESSION10B_MULTI_CHANNEL_WHATSAPP

@app.get("/api/v1/health/turn")
def turn_health(user=Depends(get_current_user)):
    from .turn import turn_config_status
    return turn_config_status()

# SESSION14_EPHEMERAL_TURN

# ============ SESSION15_AUDIT_ENDPOINT ============

@app.get("/api/v1/platform/audit-log")
def platform_audit_log(
    limit: int = 100,
    tenant_id: str | None = None,
    action: str | None = None,
    user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    require_platform_admin(user)
    from .models_growth import AuditLog
    q = select(AuditLog).order_by(AuditLog.created_at.desc())
    if tenant_id:
        q = q.where(AuditLog.tenant_id == tenant_id)
    if action:
        q = q.where(AuditLog.action == action)
    rows = db.scalars(q.limit(min(max(limit, 1), 500))).all()
    return {"items": [{
        "id": r.id,
        "tenant_id": r.tenant_id,
        "actor_id": r.actor_id,
        "action": r.action,
        "target_type": r.target_type,
        "target_id": r.target_id,
        "detail": json.loads(r.detail_json or "{}"),
        "request_id": r.request_id,
        "created_at": r.created_at.isoformat() if r.created_at else None,
    } for r in rows]}

# ============ END SESSION15 ============

# SESSION16_HARDENING


# ============ SESSION17B_TENANT_TICKETS ============

@app.get("/api/v1/tenants/{tenant_id}/tickets")
def tenant_tickets_list(tenant_id, status: str = "", category: str = "", limit: int = 200,
                        user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    require_tenant(user, tenant_id)
    from .tickets import list_tickets
    items = list_tickets(db, tenant_id=tenant_id, status=status or None,
                         category=category or None, limit=limit)
    return {"items": items}


@app.post("/api/v1/tenants/{tenant_id}/tickets", status_code=201)
def tenant_ticket_create(tenant_id, payload: TicketCreateRequest,
                         user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    require_tenant(user, tenant_id)
    from .tickets import create_ticket
    try:
        return create_ticket(db, tenant_id=tenant_id, subject=payload.subject,
                             body=payload.body, category=payload.category,
                             priority=payload.priority, created_by=user.id)
    except ValueError as exc:
        raise HTTPException(400, str(exc))


@app.post("/api/v1/tenants/{tenant_id}/tickets/{ticket_id}/reply")
def tenant_ticket_reply(tenant_id, ticket_id, payload: TicketReplyRequest,
                        user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    require_tenant(user, tenant_id)
    from .tickets import reply, get_ticket
    t = get_ticket(db, ticket_id)
    if not t or t.get("tenant_id") != tenant_id:
        raise HTTPException(404, "Ticket not found")
    try:
        return reply(db, ticket_id, payload.message, from_tenant=True, actor_id=user.id)
    except ValueError as exc:
        raise HTTPException(400, str(exc))

# ============ END SESSION17B_TENANT_TICKETS ============

# ============ SESSION18_EMAIL ============

class EmailAccountCreate(BaseModel):
    label: str = Field(default="Primary mailbox", max_length=120)
    provider: str = Field(pattern="^(gmail|outlook|custom)$")
    email_address: str = Field(min_length=3, max_length=200)
    role: str = Field(default="general", pattern="^(contact|support|billing|general)$")
    imap_host: str | None = None
    imap_port: int | None = None
    imap_user: str | None = None
    imap_password: str | None = None
    smtp_host: str | None = None
    smtp_port: int | None = None
    smtp_user: str | None = None
    smtp_password: str | None = None


@app.get("/api/v1/tenants/{tenant_id}/email-accounts")
def tenant_email_accounts_list(tenant_id, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    require_tenant(user, tenant_id)
    from .email_integration import list_accounts
    return {"items": list_accounts(db, tenant_id)}


@app.post("/api/v1/tenants/{tenant_id}/email-accounts", status_code=201)
def tenant_email_accounts_create(tenant_id, payload: EmailAccountCreate,
                                  user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    require_tenant(user, tenant_id)
    from .email_integration import build_config_from_input, create_account, test_connection_sync
    cfg = build_config_from_input(payload.provider, payload.model_dump(exclude_none=True))
    missing = [k for k in ("imap_host", "imap_port", "imap_user", "imap_password", "smtp_host", "smtp_port", "smtp_user", "smtp_password") if not cfg.get(k)]
    if missing:
        raise HTTPException(400, "Missing email config fields: " + ", ".join(missing))
    test = test_connection_sync(cfg)
    if not test.get("ok"):
        raise HTTPException(400, "IMAP connection failed: " + str(test.get("error")))
    return create_account(
        db, tenant_id,
        label=payload.label,
        provider=payload.provider,
        email_address=payload.email_address,
        role=payload.role,
        cfg=cfg,
    )


@app.delete("/api/v1/tenants/{tenant_id}/email-accounts/{account_id}")
def tenant_email_accounts_delete(tenant_id, account_id,
                                  user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    require_tenant(user, tenant_id)
    from .email_integration import delete_account
    ok = delete_account(db, tenant_id, account_id)
    if not ok:
        raise HTTPException(404, "Email account not found")
    return {"deleted": True}


@app.post("/api/v1/tenants/{tenant_id}/email-accounts/{account_id}/test")
def tenant_email_accounts_test(tenant_id, account_id,
                                user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    require_tenant(user, tenant_id)
    from .models_email import TenantEmailAccount
    from .email_integration import decrypt_email_config, test_connection_sync
    row = db.scalar(select(TenantEmailAccount).where(
        TenantEmailAccount.id == account_id,
        TenantEmailAccount.tenant_id == tenant_id,
    ))
    if not row:
        raise HTTPException(404, "Email account not found")
    cfg = decrypt_email_config(row.config_encrypted)
    return test_connection_sync(cfg)


@app.patch("/api/v1/tenants/{tenant_id}/email-accounts/{account_id}")
def tenant_email_accounts_update(tenant_id, account_id, payload: dict,
                                  user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    require_tenant(user, tenant_id)
    from .models_email import TenantEmailAccount
    row = db.scalar(select(TenantEmailAccount).where(
        TenantEmailAccount.id == account_id,
        TenantEmailAccount.tenant_id == tenant_id,
    ))
    if not row:
        raise HTTPException(404, "Email account not found")
    for k in ("label", "is_active", "auto_reply_enabled", "role"):
        if k in payload:
            setattr(row, k, payload[k])
    db.commit()
    db.refresh(row)
    from .email_integration import _account_out
    return _account_out(row)


@app.get("/api/v1/tenants/{tenant_id}/email-log")
def tenant_email_log(tenant_id, limit: int = 100,
                     user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    require_tenant(user, tenant_id)
    from .email_integration import list_log
    return {"items": list_log(db, tenant_id, limit=limit)}

# ============ END SESSION18_EMAIL ============


@app.on_event("shutdown")
async def _shutdown_email_poller():
    try:
        from .email_poller import stop_email_poller
        stop_email_poller()
    except Exception:
        pass


# ============ SESSION20A_MONITORING ============

@app.get("/api/v1/platform/monitoring/snapshots")
def monitoring_snapshots(limit: int = 200, category: str = "",
                         user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    require_platform_admin(user)
    from .models_monitoring import HealthSnapshot
    q = select(HealthSnapshot).order_by(HealthSnapshot.created_at.desc()).limit(min(max(limit, 1), 1000))
    if category:
        q = q.where(HealthSnapshot.category == category)
    rows = db.scalars(q).all()
    return {"items": [{
        "id": r.id,
        "category": r.category,
        "status": r.status,
        "detail": json.loads(r.detail_json or "{}"),
        "latency_ms": r.latency_ms,
        "created_at": r.created_at.isoformat() if r.created_at else None,
    } for r in rows]}


@app.get("/api/v1/platform/monitoring/current")
def monitoring_current(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    require_platform_admin(user)
    from .models_monitoring import HealthSnapshot
    categories = ["backend", "database", "email_poller", "whatsapp", "ai_provider", "disk", "backup"]
    result = {}
    for cat in categories:
        row = db.scalar(
            select(HealthSnapshot).where(HealthSnapshot.category == cat)
            .order_by(HealthSnapshot.created_at.desc())
        )
        result[cat] = {
            "status": row.status if row else "unknown",
            "detail": json.loads(row.detail_json or "{}") if row else {},
            "at": row.created_at.isoformat() if row and row.created_at else None,
            "latency_ms": row.latency_ms if row else None,
        }
    return result


@app.get("/api/v1/platform/monitoring/actions")
def monitoring_actions(limit: int = 100,
                       user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    require_platform_admin(user)
    from .models_monitoring import SelfHealAction
    rows = db.scalars(
        select(SelfHealAction).order_by(SelfHealAction.created_at.desc()).limit(min(max(limit, 1), 500))
    ).all()
    return {"items": [{
        "id": r.id,
        "component": r.component,
        "action": r.action,
        "outcome": r.outcome,
        "detail": r.detail,
        "created_at": r.created_at.isoformat() if r.created_at else None,
    } for r in rows]}


@app.get("/api/v1/platform/monitoring/alerts")
def monitoring_alerts(limit: int = 100,
                      user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    require_platform_admin(user)
    from .models_monitoring import MonitoringAlert
    rows = db.scalars(
        select(MonitoringAlert).order_by(MonitoringAlert.created_at.desc()).limit(min(max(limit, 1), 500))
    ).all()
    return {"items": [{
        "id": r.id,
        "severity": r.severity,
        "component": r.component,
        "title": r.title,
        "body": r.body,
        "email_sent": r.email_sent,
        "whatsapp_sent": r.whatsapp_sent,
        "delivery_error": r.delivery_error,
        "created_at": r.created_at.isoformat() if r.created_at else None,
    } for r in rows]}


@app.get("/api/v1/platform/monitoring/backups")
def monitoring_backups(limit: int = 100,
                       user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    require_platform_admin(user)
    from .models_monitoring import BackupRecord
    rows = db.scalars(
        select(BackupRecord).order_by(BackupRecord.created_at.desc()).limit(min(max(limit, 1), 500))
    ).all()
    return {"items": [{
        "id": r.id,
        "source_path": r.source_path,
        "backup_path": r.backup_path,
        "size_bytes": r.size_bytes,
        "ok": r.ok,
        "error": r.error,
        "created_at": r.created_at.isoformat() if r.created_at else None,
    } for r in rows]}

# ============ END SESSION20A_MONITORING ============