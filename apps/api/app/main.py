from fastapi import FastAPI,Depends,HTTPException,Query,Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPAuthorizationCredentials,HTTPBearer
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.orm import Session
from pydantic import BaseModel,Field
from .db import SessionLocal
from .models import Tenant,User,Customer,Lead,Service,Product,TenantWhatsAppConnection
from .models_growth import KnowledgeItem,Appointment,LoyaltyTransaction,QrEntry,CallRecord,Campaign,BusinessHour,QueueEntry,ServiceRequest,TenantSetting,PlatformSetting,MenuCategory,MenuItem,Order,OrderItem,Bill,Feedback,LoyaltyRule,LoyaltyReward,GameScore
from .models_ai import GlobalFaq,Conversation,ConversationMessage,Department,StaffMember,RoleDefinition
from .schemas import *
from .services import *
from .brain import generate_reply,knowledge_context
from .config import settings
from .signaling import signal
from .events import publish_event_sync, subscribe_events
from .integrations import WhatsAppAdapter,PaymentAdapter,encrypt_channel_config,tenant_whatsapp_adapter,tenant_payment_adapter
from .notifications import send_owner_credentials,send_password_reset
from .migrations import ensure_schema
from .faq_seed import FAQS
from .ai_router import detect_language
from .routing import route_call, available_staff
from .booking import ensure_default_hours, available_slots, create_appointment, queue_snapshot
from .integration_routes import router as integration_router
from .social_routes import router as social_router
import asyncio,json,base64,uuid
from datetime import datetime,date,time,timedelta
import websockets
import jwt,secrets,hashlib

import asyncio
app=FastAPI(title="AI Growth OS API",version="1.0.0")
app.include_router(integration_router)
app.include_router(social_router)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[x.strip() for x in settings.allowed_origins.split(",") if x.strip()],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

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
    key=(client,request.url.path)
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
async def tenant_events(websocket,tenant_id:str,access_token:str|None=Query(default=None)):
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
async def public_business_events(websocket,slug:str,context_token:str|None=Query(default=None)):
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
    return jwt.encode(
        {"sub":call_id,"call_id":call_id,"aud":audience,"exp":datetime.utcnow().timestamp()+600},
        settings.jwt_secret,
        algorithm=settings.jwt_algorithm,
    )

def verify_call_room_token(token:str,call_id:str,audience:str):
    try:
        p=jwt.decode(token,settings.jwt_secret,algorithms=[settings.jwt_algorithm],options={"require":["exp","sub","aud"]},audience=audience)
        return p.get("call_id")==call_id
    except jwt.InvalidTokenError:
        return False

@app.websocket("/ws/calls/{call_id}")
async def call_signal(websocket,call_id:str,access_token:str|None=Query(default=None),room_token:str|None=Query(default=None)):
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
    await signal(websocket,call_id,allow_staff=allow_staff)

security=HTTPBearer(auto_error=False)

@app.on_event("startup")
async def startup():
    ensure_schema()
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
class Health(BaseModel): status:str; service:str
@app.get("/health",response_model=Health)
def health(): return {"status":"ok","service":"ai-growth-os-api"}
def get_current_user(credentials:HTTPAuthorizationCredentials=Depends(security),db:Session=Depends(get_db))->User:
    if not credentials: raise HTTPException(401,"Authentication required")
    try:
        p=jwt.decode(credentials.credentials,settings.jwt_secret,algorithms=[settings.jwt_algorithm]); uid=p.get("sub")
    except jwt.InvalidTokenError: raise HTTPException(401,"Invalid or expired token")
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

@app.post("/api/v1/auth/register",response_model=AuthResponse,status_code=201)
def register(payload:RegisterRequest,db:Session=Depends(get_db)):
    if db.scalar(select(User).where(User.email==payload.email.lower())): raise HTTPException(409,"Email already registered")
    if db.scalar(select(Tenant).where(Tenant.slug==payload.slug.lower())): raise HTTPException(409,"Business slug already exists")
    t=create_tenant(db,payload.business_name,payload.slug,payload.industry); u=create_owner(db,payload.name,payload.email,payload.password,t)
    provision_defaults(db,t,payload.industry)
    _set_setting(db,t.id,"features",{**FEATURE_DEFAULTS,**INDUSTRY_FEATURES.get(payload.industry.lower(),{})})
    return {"access_token":create_access_token(u),"token_type":"bearer","user":user_out(u),"tenant":t}
@app.post("/api/v1/auth/login",response_model=AuthResponse)
def login(payload:LoginRequest,db:Session=Depends(get_db)):
    u=db.scalar(select(User).where(User.email==payload.email.lower()))
    if not u or not u.is_active or not verify_password(payload.password,u.password_hash): raise HTTPException(401,"Invalid email or password")
    t=db.get(Tenant,u.tenant_id)
    return {"access_token":create_access_token(u),"token_type":"bearer","user":user_out(u),"tenant":t}
@app.get("/api/v1/auth/me",response_model=AuthResponse)
def me(user:User=Depends(get_current_user),db:Session=Depends(get_db)):
    return {"access_token":"","token_type":"bearer","user":user_out(user),"tenant":db.get(Tenant,user.tenant_id)}

@app.get("/api/v1/tenants/{tenant_id}/integrations/whatsapp",response_model=WhatsAppConnectionStatus)
def whatsapp_connection(tenant_id,user=Depends(get_current_user),db:Session=Depends(get_db)):
    require_tenant(user,tenant_id)
    row=db.scalar(select(TenantWhatsAppConnection).where(TenantWhatsAppConnection.tenant_id==tenant_id))
    if not row: return {"provider":settings.whatsapp_provider,"status":"disconnected","connected_phone":None,"display_name":None,"configured":False}
    return {"provider":row.provider,"status":row.status,"connected_phone":row.connected_phone,"display_name":row.display_name,"configured":bool(row.config_encrypted)}

@app.put("/api/v1/tenants/{tenant_id}/integrations/whatsapp",response_model=WhatsAppConnectionStatus)
async def configure_whatsapp(tenant_id,payload:WhatsAppConnectionConfig,user=Depends(get_current_user),db:Session=Depends(get_db)):
    require_tenant(user,tenant_id)
    data=payload.model_dump(exclude_none=True)
    provider=data.pop("provider")
    if provider=="openwa" and not all(data.get(k) for k in ("base_url","api_key","session_id")): raise HTTPException(400,"OpenWA requires base URL, API key and session ID")
    if provider=="meta" and not all(data.get(k) for k in ("access_token","phone_number_id")): raise HTTPException(400,"Meta requires access token and phone number ID")
    try:
        adapter=WhatsAppAdapter(provider=provider,openwa_base_url=data.get("base_url",""),openwa_api_key=data.get("api_key",""),openwa_session_id=data.get("session_id",""),access_token=data.get("access_token",""),phone_number_id=data.get("phone_number_id",""))
        if provider=="openwa":
            async with __import__("httpx").AsyncClient(timeout=15) as client:
                rr=await client.get(data["base_url"].rstrip("/")+"/api/sessions/"+data["session_id"],headers={"X-API-Key":data["api_key"]}); rr.raise_for_status()
                session=rr.json(); data["connected_phone"]=data.get("connected_phone") or session.get("phoneNumber") or session.get("phone")
        else:
            async with __import__("httpx").AsyncClient(timeout=15) as client:
                rr=await client.get("https://graph.facebook.com/v23.0/"+data["phone_number_id"],headers={"Authorization":"Bearer "+data["access_token"]}); rr.raise_for_status()
                info=rr.json(); data["connected_phone"]=data.get("connected_phone") or info.get("display_phone_number"); data["display_name"]=data.get("display_name") or info.get("verified_name")
    except Exception as exc:
        raise HTTPException(400,"WhatsApp provider credentials could not be validated: "+str(exc))
    row=db.scalar(select(TenantWhatsAppConnection).where(TenantWhatsAppConnection.tenant_id==tenant_id))
    now=datetime.utcnow()
    encrypted=encrypt_channel_config({"provider":provider,**data},settings.whatsapp_credential_encryption_key)
    if not row: row=TenantWhatsAppConnection(id=secrets.token_hex(18),tenant_id=tenant_id); db.add(row)
    row.provider=provider; row.status="connected"; row.config_encrypted=encrypted; row.connected_phone=data.get("connected_phone"); row.display_name=data.get("display_name"); row.updated_at=now; db.commit(); db.refresh(row)
    return {"provider":row.provider,"status":row.status,"connected_phone":row.connected_phone,"display_name":row.display_name,"configured":True}

@app.delete("/api/v1/tenants/{tenant_id}/integrations/whatsapp",response_model=WhatsAppConnectionStatus)
def disconnect_whatsapp(tenant_id,user=Depends(get_current_user),db:Session=Depends(get_db)):
    require_tenant(user,tenant_id)
    row=db.scalar(select(TenantWhatsAppConnection).where(TenantWhatsAppConnection.tenant_id==tenant_id))
    if row: row.status="disconnected"; row.config_encrypted=""; row.updated_at=datetime.utcnow(); db.commit()
    return {"provider":row.provider if row else settings.whatsapp_provider,"status":"disconnected","connected_phone":None,"display_name":None,"configured":False}

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
    try: content={**DEFAULT_WEBSITE_CONTENT,**(json.loads(row.value_json) if row else {})}
    except Exception: content=dict(DEFAULT_WEBSITE_CONTENT)
    return {"business":{"id":t.id,"name":t.name,"slug":t.slug,"phone":t.phone,"whatsapp_number":t.whatsapp_number,"address":t.address,"description":t.description},"content":content}

@app.get("/api/v1/tenants/{tenant_id}/website")
def tenant_website(tenant_id,user=Depends(get_current_user),db:Session=Depends(get_db)):
    require_tenant(user,tenant_id)
    row=db.scalar(select(TenantSetting).where(TenantSetting.tenant_id==tenant_id,TenantSetting.key=="website_content"))
    try: return {**DEFAULT_WEBSITE_CONTENT,**(json.loads(row.value_json) if row else {})}
    except Exception: return dict(DEFAULT_WEBSITE_CONTENT)

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
async def password_reset_request(payload:PasswordResetRequest,db:Session=Depends(get_db)):
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
        start=datetime.combine(day,time.min); end=start+timedelta(days=1)
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
    if not _feature_config(db,t.id).get("games",True): raise HTTPException(403,"Games are disabled")
    if game not in {x["id"] for x in GAME_CATALOG}: raise HTTPException(400,"Game not available")
    customer=None
    if customer_id:
        customer=db.scalar(select(Customer).where(Customer.id==customer_id,Customer.tenant_id==t.id))
    # Reward is deliberately capped and limited to three rewarded plays per game/day/customer.
    reward=0 if not customer or not _feature_config(db,t.id).get("loyalty",False) else min(25,max(1,score//20))
    if customer and reward:
        day_start=datetime.utcnow().replace(hour=0,minute=0,second=0,microsecond=0)
        rewarded_count=db.scalar(select(__import__("sqlalchemy").func.count(GameScore.id)).where(GameScore.tenant_id==t.id,GameScore.customer_id==customer.id,GameScore.game==game,GameScore.reward_points>0,GameScore.created_at>=day_start)) or 0
        if rewarded_count>=3: reward=0
    row=GameScore(tenant_id=t.id,customer_id=customer.id if customer else None,game=game,score=score,reward_points=reward)
    db.add(row); db.flush()
    if customer and reward and _feature_config(db,t.id).get("loyalty",False):
        existing=db.scalar(select(LoyaltyTransaction).where(LoyaltyTransaction.tenant_id==t.id,LoyaltyTransaction.customer_id==customer.id,LoyaltyTransaction.reason=="game:"+game,LoyaltyTransaction.reference_id==row.id))
        if not existing: db.add(LoyaltyTransaction(tenant_id=t.id,customer_id=customer.id,points=reward,reason="game:"+game,reference_id=row.id))
    db.commit(); db.refresh(row)
    return {"id":row.id,"game":game,"score":score,"reward_points":reward}

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
    import hmac,hashlib
    t=db.scalar(select(Tenant).where(Tenant.slug==slug.lower()))
    bill=db.scalar(select(Bill).where(Bill.id==bill_id,Bill.tenant_id==t.id)) if t else None
    if not bill: raise HTTPException(404,"Bill not found")
    if bill.status=="paid":
        if bill.payment_id and bill.payment_id!=payload.razorpay_payment_id: raise HTTPException(409,"Bill is already paid with another payment")
        return {"paid":True,"bill_id":bill.id,"payment_id":bill.payment_id}
    payment_adapter=tenant_payment_adapter(db,t.id,settings)
    if not payment_adapter.key_secret: raise HTTPException(503,"Razorpay is not configured")
    expected=hmac.new(payment_adapter.key_secret.encode(),(payload.razorpay_order_id+"|"+payload.razorpay_payment_id).encode(),hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected,payload.razorpay_signature): raise HTTPException(400,"Invalid payment signature")
    bill.payment_id=payload.razorpay_payment_id; bill.status="paid"; bill.paid_at=datetime.utcnow()
    order=db.get(Order,bill.order_id)
    if order: order.payment_status="paid"; order.updated_at=datetime.utcnow()
    db.commit()
    return {"paid":True,"bill_id":bill.id,"payment_id":bill.payment_id}

@app.post("/api/v1/webhooks/razorpay")
async def razorpay_webhook(request:Request,db:Session=Depends(get_db)):
    import hmac,hashlib
    raw=await request.body()
    signature=request.headers.get("X-Razorpay-Signature","")
    if not settings.razorpay_key_secret or not signature: raise HTTPException(401,"Webhook signature required")
    expected=hmac.new(settings.razorpay_key_secret.encode(),raw,hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected,signature): raise HTTPException(400,"Invalid webhook signature")
    payload=json.loads(raw.decode("utf-8"))
    entity=payload.get("payload",{}).get("payment",{}).get("entity",{})
    receipt=(entity.get("notes") or {}).get("receipt") or ""
    if receipt.startswith("bill-") and entity.get("status") in ("captured","authorized"):
        bill=db.scalar(select(Bill).where(Bill.id==receipt[5:]))
        if bill and bill.status!="paid":
            bill.status="paid"; bill.payment_id=entity.get("id"); bill.paid_at=datetime.utcnow()
            order=db.get(Order,bill.order_id)
            if order: order.payment_status="paid"
            db.commit()
    return {"received":True}

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
    return route_call(db, tenant_id, call, intent)

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
    return {"items":[{"id":x.id,"customer_id":x.customer_id,"source":x.source,"status":x.status,"department":x.department,"staff_id":x.staff_id,"room_id":x.room_id,"intent":x.intent,"summary":x.summary,"transcript":x.transcript,"created_at":x.created_at} for x in rows]}

@app.get("/api/v1/tenants/{tenant_id}/voice/ice")
def voice_ice_config(tenant_id,user=Depends(get_current_user)):
    require_tenant(user,tenant_id)
    servers=[{"urls":"stun:stun.l.google.com:19302"}]
    if settings.turn_url:
        servers.append({"urls":settings.turn_url,"username":settings.turn_username,"credential":settings.turn_credential})
    return {"ice_servers":servers}

class VoiceTurnRequest(BaseModel):
    transcript:str=Field(min_length=1,max_length=4000)
    conversation_id:str|None=None
    channel:str="voice"

@app.post("/api/v1/tenants/{tenant_id}/voice/turn")
async def voice_turn(tenant_id,payload:VoiceTurnRequest,user=Depends(get_current_user),db:Session=Depends(get_db)):
    require_tenant(user,tenant_id)
    result=await generate_reply(db,tenant_id,payload.transcript,payload.conversation_id,payload.channel)
    return {**result,"audio_generation":"provider_adapter_pending"}

@app.get("/api/v1/public/languages")
def supported_languages():
    return {"languages":[{"code":"en","name":"English"},{"code":"hi","name":"Hindi"},{"code":"te","name":"Telugu"},{"code":"ta","name":"Tamil"},{"code":"kn","name":"Kannada"},{"code":"ml","name":"Malayalam"},{"code":"mr","name":"Marathi"},{"code":"bn","name":"Bengali"},{"code":"gu","name":"Gujarati"},{"code":"pa","name":"Punjabi"},{"code":"ur","name":"Urdu"},{"code":"or","name":"Odia"},{"code":"as","name":"Assamese"}]}

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
    o.status=payload.status; o.updated_at=datetime.utcnow()
    if payload.status=="completed":
        b=db.scalar(select(Bill).where(Bill.order_id==o.id))
        if not b: db.add(Bill(tenant_id=tenant_id,order_id=o.id,subtotal=o.subtotal,tax=o.tax,discount=o.discount,total=o.total))
        if o.customer_id and _feature_config(db,tenant_id).get("loyalty",False):
            rules=db.scalars(select(LoyaltyRule).where(LoyaltyRule.tenant_id==tenant_id,LoyaltyRule.event_type=="purchase",LoyaltyRule.is_active==True)).all()
            for rule in rules:
                cfg=json.loads(rule.config_json or "{}")
                if int(cfg.get("minimum_bill",0))<=o.total:
                    existing=db.scalar(select(LoyaltyTransaction).where(LoyaltyTransaction.tenant_id==tenant_id,LoyaltyTransaction.customer_id==o.customer_id,LoyaltyTransaction.reason==rule.name,LoyaltyTransaction.reference_id==o.id))
                    if not existing:
                        db.add(LoyaltyTransaction(tenant_id=tenant_id,customer_id=o.customer_id,points=rule.points,reason=rule.name,reference_id=o.id))
    db.commit(); db.refresh(o)
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
    q.scans+=1; db.commit(); t=db.get(Tenant,q.tenant_id); return {"tenant_id":t.id,"slug":t.slug,"url":settings.public_app_url+"/customer","kind":q.kind}

class PublicCallStartRequest(BaseModel):
    name:str=Field(min_length=1,max_length=160)
    phone:str=Field(min_length=5,max_length=32)

@app.post("/api/v1/public/business/{slug}/call",status_code=201)
def start_public_call(slug:str,payload:PublicCallStartRequest,db:Session=Depends(get_db)):
    t=db.scalar(select(Tenant).where(Tenant.slug==slug.lower()))
    if not t: raise HTTPException(404,"Business not found")
    customer=None
    try:
        customer=upsert_customer(db,t.id,payload.phone.strip(),payload.name.strip(),False,source="pwa_voice")
    except ValueError as exc:
        raise HTTPException(400,str(exc))
    call=CallRecord(tenant_id=t.id,customer_id=customer.id if customer else None,source="pwa_voice",status="ringing")
    db.add(call); db.commit(); db.refresh(call)
    return {"call_id":call.id,"customer_id":customer.id if customer else None,"status":"ringing","business_name":t.name,"voice_token":issue_call_room_token(call.id,"call-ai")}

@app.websocket("/ws/public/voice/{call_id}")
async def public_voice(websocket,call_id:str,voice_token:str|None=Query(default=None)):
    if not voice_token or not verify_call_room_token(voice_token,call_id,"call-ai"):
        await websocket.close(code=4403); return
    await websocket.accept()
    db=SessionLocal(); call=db.get(CallRecord,call_id)
    if not call:
        await websocket.close(code=4404); db.close(); return
    tenant=db.get(Tenant,call.tenant_id)
    if not tenant or not settings.gemini_api_key:
        await websocket.send_json({"type":"error","message":"AI voice is not configured for this business."}); await websocket.close(); db.close(); return
    context=knowledge_context(db,tenant.id)
    system=(f"You are the AI customer engagement voice agent for {tenant.name}.\
\
APPROVED BUSINESS CONTEXT:\
{context}\
\
"
             "At the beginning of every new call, say exactly: \\\"Hello! Welcome to [Business Name]. Before I can assist you, may I confirm your name and mobile number?\\\" "
             "Replace [Business Name] with the real business name. Ask the customer to state their name and mobile number. "
             "Do not invent business facts, prices, availability, policies, bookings or payment success. "
             "When the customer has provided both their name and mobile number, call save_customer_identity before continuing. "
             "After identity is saved, say a short confirmation and ask how you can help. For booking requests, use the approved service IDs in the business context, ask for an exact date and time, and call create_booking only after the customer explicitly confirms the selected slot. Never claim a booking is confirmed unless the tool returns confirmed=true. If a queue token is returned, tell the customer the token and estimated wait. Be concise, natural and multilingual when appropriate.")
    ws_url="wss://generativelanguage.googleapis.com/ws/google.ai.generativelanguage.v1beta.GenerativeService.BidiGenerateContent?key="+settings.gemini_api_key
    setup={"setup":{"model":"models/"+settings.gemini_live_model,"generationConfig":{"responseModalities":["AUDIO"]},"systemInstruction":{"parts":[{"text":system}]},"inputAudioTranscription":{},"outputAudioTranscription":{},"sessionResumption":{},"tools":[{"functionDeclarations":[{"name":"save_customer_identity","description":"Save and verify the customer's name and mobile number after the customer has stated both during the call.","parameters":{"type":"OBJECT","properties":{"name":{"type":"STRING"},"phone":{"type":"STRING"}},"required":["name","phone"]}},{"name":"create_booking","description":"Create a confirmed appointment after the customer explicitly confirms an exact service, date and time. starts_at is local business time without timezone offset.","parameters":{"type":"OBJECT","properties":{"service_id":{"type":"STRING"},"starts_at":{"type":"STRING"},"name":{"type":"STRING"},"phone":{"type":"STRING"},"staff_id":{"type":"STRING"},"notes":{"type":"STRING"}},"required":["service_id","starts_at","name","phone"]}}]}]}}
    try:
        async with websockets.connect(ws_url,max_size=8*1024*1024,ping_interval=20,ping_timeout=20) as gemini:
            await gemini.send(json.dumps(setup)); await websocket.send_json({"type":"status","status":"ai_connected"})
            await gemini.send(json.dumps({"clientContent":{"turns":[{"role":"user","parts":[{"text":"Begin the call now."}]}],"turnComplete":True}}))
            async def browser_to_gemini():
                while True:
                    raw=await websocket.receive_text(); msg=json.loads(raw); typ=msg.get("type")
                    if typ=="audio":
                        await gemini.send(json.dumps({"realtimeInput":{"audio":{"data":msg["data"],"mimeType":"audio/pcm;rate=16000"}}}))
                    elif typ=="stop":
                        break
            async def gemini_to_browser():
                while True:
                    raw=await gemini.recv()
                    if isinstance(raw,bytes): raw=raw.decode()
                    msg=json.loads(raw); sc=msg.get("serverContent") or {}
                    if sc.get("inputTranscription",{}).get("text"):
                        txt=sc["inputTranscription"]["text"]; call.transcript=((call.transcript+"\
") if call.transcript else "")+"CUSTOMER: "+txt; db.commit(); await websocket.send_json({"type":"transcript","role":"customer","text":txt})
                    if sc.get("outputTranscription",{}).get("text"):
                        txt=sc["outputTranscription"]["text"]; call.transcript=((call.transcript+"\
") if call.transcript else "")+"AI: "+txt; db.commit(); await websocket.send_json({"type":"transcript","role":"ai","text":txt})
                    if msg.get("toolCall"):
                        responses=[]
                        for fc in msg["toolCall"].get("functionCalls",[]):
                            args=fc.get("args",{})
                            name=fc.get("name")
                            if name=="save_customer_identity":
                                try:
                                    phone=str(args.get("phone","")).strip()
                                    customer_name=str(args.get("name","")).strip()
                                    if not phone or not customer_name:
                                        raise ValueError("Name and mobile number are required")
                                    c=upsert_customer(db,tenant.id,phone,customer_name,False,source="ai_voice")
                                    call.customer_id=c.id
                                    call.status="connected"
                                    db.commit()
                                    route_call(db,tenant.id,call,call.intent)
                                    responses.append({"id":fc.get("id"),"name":name,"response":{"result":{"customer_id":c.id,"verified":True}}})
                                except Exception as exc:
                                    db.rollback()
                                    responses.append({"id":fc.get("id"),"name":name,"response":{"result":{"verified":False,"error":str(exc)}}})
                            elif name=="create_booking":
                                try:
                                    service=db.scalar(select(Service).where(Service.id==str(args.get("service_id","")),Service.tenant_id==tenant.id,Service.is_active==True))
                                    if not service: raise ValueError("Service not found or inactive")
                                    if not call.customer_id: raise ValueError("Customer identity must be verified first")
                                    c=db.get(Customer,call.customer_id)
                                    starts=datetime.fromisoformat(str(args.get("starts_at","")))
                                    a,q=create_appointment(db,tenant,c,service,starts,"ai_voice",str(args.get("staff_id")) if args.get("staff_id") else None,str(args.get("notes")) if args.get("notes") else None,True,False)
                                    db.commit()
                                    responses.append({"id":fc.get("id"),"name":name,"response":{"result":{"booking_id":a.id,"confirmed":True,"starts_at":a.starts_at.isoformat(),"queue_token":q.token if q else None,"estimated_wait_minutes":q.estimated_wait_minutes if q else None}}})
                                except Exception as exc:
                                    db.rollback()
                                    responses.append({"id":fc.get("id"),"name":name,"response":{"result":{"confirmed":False,"error":str(exc)}}})
                        if responses: await gemini.send(json.dumps({"toolResponse":{"functionResponses":responses}}))
                    await websocket.send_text(raw)
            tasks=[asyncio.create_task(browser_to_gemini()),asyncio.create_task(gemini_to_browser())]
            done,_=await asyncio.wait(tasks,return_when=asyncio.FIRST_COMPLETED)
            for task in tasks:
                if not task.done(): task.cancel()
    except Exception as exc:
        try: await websocket.send_json({"type":"error","message":"Voice session ended: "+str(exc)})
        except Exception: pass
    finally:
        db.refresh(call)
        if call.status not in {"handoff_requested","handoff_accepted","connected"}:
            call.status="ended"
        db.commit(); db.close()

class PublicVoiceTurnRequest(BaseModel):
    transcript:str=Field(min_length=1,max_length=4000)
    conversation_id:str|None=None
    call_id:str|None=None
    channel:str="voice"

@app.get("/api/v1/public/business/{slug}/call/{call_id}/handoff")
def public_handoff_status(slug:str, call_id:str, db:Session=Depends(get_db)):
    t=db.scalar(select(Tenant).where(Tenant.slug==slug.lower()))
    if not t: raise HTTPException(404,"Business not found")
    call=db.scalar(select(CallRecord).where(CallRecord.id==call_id,CallRecord.tenant_id==t.id))
    if not call: raise HTTPException(404,"Call not found")
    staff=db.get(StaffMember,call.staff_id) if call.staff_id else None
    return {"call_id":call.id,"status":call.status,"room_id":call.room_id,"room_token":issue_call_room_token(call.id,"call-customer") if call.room_id and call.status in ("handoff_requested","handoff_accepted","connected") else None,"staff":{"id":staff.id,"name":staff.name} if staff else None}

@app.get("/api/v1/public/business/{slug}/voice/ice")
def public_voice_ice(slug:str, db:Session=Depends(get_db)):
    t=db.scalar(select(Tenant).where(Tenant.slug==slug.lower()))
    if not t: raise HTTPException(404,"Business not found")
    servers=[{"urls":"stun:stun.l.google.com:19302"}]
    if settings.turn_url:
        servers.append({"urls":settings.turn_url,"username":settings.turn_username,"credential":settings.turn_credential})
    return {"ice_servers":servers}

@app.post("/api/v1/public/business/{slug}/voice/turn")
async def public_voice_turn(slug:str,payload:PublicVoiceTurnRequest,db:Session=Depends(get_db)):
    t=db.scalar(select(Tenant).where(Tenant.slug==slug.lower()))
    if not t: raise HTTPException(404,"Business not found")
    result=await generate_reply(db,t.id,payload.transcript,payload.conversation_id,payload.channel)
    if payload.call_id:
        call=db.scalar(select(CallRecord).where(CallRecord.id==payload.call_id,CallRecord.tenant_id==t.id))
        if call:
            call.transcript=((call.transcript+"\\n") if call.transcript else "")+"CUSTOMER: "+payload.transcript+"\\nAI: "+result["reply"]
            call.intent=result.get("intent"); db.commit()
    return {**result,"tenant_id":t.id,"call_id":payload.call_id}
@app.post("/api/v1/tenants/{tenant_id}/calls",status_code=201)
def create_call(tenant_id,user=Depends(get_current_user),db:Session=Depends(get_db)):
    require_tenant(user,tenant_id); c=CallRecord(tenant_id=tenant_id,status="created"); db.add(c); db.commit(); db.refresh(c); return {"id":c.id,"status":c.status}
@app.get("/api/v1/tenants/{tenant_id}/loyalty/{customer_id}")
def loyalty_balance(tenant_id,customer_id,user=Depends(get_current_user),db:Session=Depends(get_db)):
    require_tenant(user,tenant_id); rows=db.scalars(select(LoyaltyTransaction).where(LoyaltyTransaction.tenant_id==tenant_id,LoyaltyTransaction.customer_id==customer_id)).all(); return {"points":sum(x.points for x in rows)}

class LoyaltyCreate(BaseModel): points:int; reason:str; reference_id:str|None=None
@app.post("/api/v1/tenants/{tenant_id}/loyalty/{customer_id}",status_code=201)
def add_loyalty(tenant_id,customer_id,payload:LoyaltyCreate,user=Depends(get_current_user),db:Session=Depends(get_db)):
    require_tenant(user,tenant_id); x=LoyaltyTransaction(tenant_id=tenant_id,customer_id=customer_id,**payload.model_dump()); db.add(x); db.commit(); db.refresh(x); return {"id":x.id,"points":x.points}

@app.patch("/api/v1/tenants/{tenant_id}/calls/{call_id}")
def update_call(tenant_id,call_id,payload:dict,user=Depends(get_current_user),db:Session=Depends(get_db)):
    require_tenant(user,tenant_id); c=db.scalar(select(CallRecord).where(CallRecord.id==call_id,CallRecord.tenant_id==tenant_id))
    if not c: raise HTTPException(404,"Call not found")
    for k in ["status","department","transcript","summary","intent"]:
        if k in payload: setattr(c,k,payload[k])
    db.commit(); return {"id":c.id,"status":c.status}
