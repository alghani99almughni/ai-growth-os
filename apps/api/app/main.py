from fastapi import FastAPI,Depends,HTTPException,Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPAuthorizationCredentials,HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session
from pydantic import BaseModel,Field
from .db import SessionLocal
from .models import Tenant,User,Customer,Lead,Service,Product
from .models_growth import KnowledgeItem,Appointment,LoyaltyTransaction,QrEntry,CallRecord,Campaign,BusinessHour,QueueEntry,ServiceRequest,TenantSetting,MenuCategory,MenuItem,Order,OrderItem,Bill,Feedback,LoyaltyRule,LoyaltyReward,GameScore
from .models_ai import GlobalFaq,Conversation,ConversationMessage,Department,StaffMember
from .schemas import *
from .services import *
from .brain import generate_reply,knowledge_context
from .config import settings
from .signaling import signal
from .integrations import WhatsAppAdapter,PaymentAdapter
from .migrations import ensure_schema
from .faq_seed import FAQS
from .ai_router import detect_language
from .routing import route_call, available_staff
from .booking import ensure_default_hours, available_slots, create_appointment, queue_snapshot
import asyncio,json,base64
from datetime import datetime,date,time,timedelta
import websockets
import jwt,secrets

app=FastAPI(title="AI Growth OS API",version="1.0.0")
app.add_middleware(CORSMiddleware,allow_origins=["*"],allow_credentials=False,allow_methods=["*"],allow_headers=["*"])

@app.websocket("/ws/calls/{call_id}")
async def call_signal(websocket,call_id:str,access_token:str|None=Query(default=None)):
    db=SessionLocal()
    call=db.get(CallRecord,call_id)
    if not call:
        await websocket.close(code=4404); db.close(); return
    allow_staff=False
    if access_token:
        try:
            p=jwt.decode(access_token,settings.jwt_secret,algorithms=[settings.jwt_algorithm])
            uid=p.get("sub")
            user=db.get(User,uid)
            allow_staff=bool(user and user.is_active and user.tenant_id==call.tenant_id)
        except jwt.InvalidTokenError:
            allow_staff=False
    db.close()
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
    return u
FEATURE_DEFAULTS={"digital_menu":True,"online_ordering":True,"order_tracking":True,"call_waiter":True,"service_requests":True,"games":True,"auto_bill":True,"online_payment":True,"ai_chat":True,"ai_voice":True,"loyalty":True,"referrals":True,"feedback":True,"google_review":True,"bookings":True,"queue":True}
GAME_CATALOG=[{"id":"dino","name":"Dino Run"},{"id":"snake","name":"Snake"},{"id":"brick","name":"Brick Breaker"},{"id":"flappy","name":"Flappy"},{"id":"tap","name":"Tap Target"},{"id":"2048","name":"2048"}]
def _feature_config(db,tenant_id):
    row=db.scalar(select(TenantSetting).where(TenantSetting.tenant_id==tenant_id,TenantSetting.key=="features"))
    cfg=dict(FEATURE_DEFAULTS)
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
def customer(payload:CustomerCreate,user=Depends(get_current_user),db:Session=Depends(get_db)):
    require_tenant(user,payload.tenant_id); c=upsert_customer(db,payload.tenant_id,payload.phone,payload.name,payload.whatsapp_opt_in,email=payload.email,address=payload.address,notes=payload.notes,tags=payload.tags,source=payload.source); return {"id":c.id,"tenant_id":c.tenant_id,"name":c.name,"phone":c.phone,"email":c.email,"address":c.address,"notes":c.notes,"tags":c.tags,"source":c.source,"portal_token":c.portal_token}
@app.get("/api/v1/tenants/{tenant_id}/customers")
def customers(tenant_id,user=Depends(get_current_user),db:Session=Depends(get_db)):
    require_tenant(user,tenant_id); rows=db.scalars(select(Customer).where(Customer.tenant_id==tenant_id)).all(); return {"items":[{"id":x.id,"name":x.name,"phone":x.phone,"email":x.email,"address":x.address,"notes":x.notes,"tags":x.tags,"source":x.source,"whatsapp_opt_in":x.whatsapp_opt_in,"portal_token":x.portal_token} for x in rows]}

class CustomerUpdate(BaseModel):
    name: Optional[str] = None
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
    caller_phone: str = Field(min_length=3,max_length=32)
    department: str = "Reception"
    staff_id: str | None = None
    notes: str | None = None

@app.post("/api/v1/tenants/{tenant_id}/telephony/inbound-call",status_code=201)
def inbound_landline_call(tenant_id,payload:LandlineCallRequest,user=Depends(get_current_user),db:Session=Depends(get_db)):
    require_tenant(user,tenant_id)
    c=upsert_customer(db,tenant_id,payload.caller_phone,None,False,source="landline")
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
        result=await WhatsAppAdapter(settings.whatsapp_access_token,settings.whatsapp_phone_number_id).send_text(c.phone,message)
    except RuntimeError as exc:
        raise HTTPException(503,str(exc))
    return {"sent":True,"pwa_url":url,"whatsapp":result}
@app.post("/api/v1/leads",status_code=201)
def lead(payload:LeadCreate,user=Depends(get_current_user),db:Session=Depends(get_db)):
    require_tenant(user,payload.tenant_id); l=create_lead(db,payload.tenant_id,payload.source,payload.customer_id,payload.intent,payload.notes); return {"id":l.id,"status":l.status}
@app.get("/api/v1/tenants/{tenant_id}/leads")
def leads(tenant_id,user=Depends(get_current_user),db:Session=Depends(get_db)):
    require_tenant(user,tenant_id); rows=db.scalars(select(Lead).where(Lead.tenant_id==tenant_id)).all(); return {"items":[{"id":x.id,"customer_id":x.customer_id,"source":x.source,"intent":x.intent,"notes":x.notes,"status":x.status} for x in rows]}

class ChatRequest(BaseModel): tenant_id:str; message:str=Field(min_length=1,max_length=4000); name:str|None=None; phone:str|None=None; conversation_id:str|None=None; channel:str="pwa"

class HoursUpdate(BaseModel):
    items: list[BusinessHourInput]

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
    x=LoyaltyRule(tenant_id=tenant_id,event_type=payload.event_type,name=payload.name,points=payload.points,is_active=payload.is_active,config_json=json.dumps(payload.config))
    db.add(x); db.commit(); db.refresh(x); return {"id":x.id}

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
    if payload.request_type=="waiter" and t.industry.lower() not in ("restaurant","cafe","hotel","hospitality","food"):
        raise HTTPException(400,"Waiter calling is not enabled for this business type")
    staff=None
    dept=db.scalar(select(Department).where(Department.tenant_id==t.id,Department.name.ilike("%service%"),Department.is_active==True))
    if not dept: dept=db.scalar(select(Department).where(Department.tenant_id==t.id,Department.name.ilike("%reception%"),Department.is_active==True))
    if dept: staff=db.scalar(select(StaffMember).where(StaffMember.tenant_id==t.id,StaffMember.department_id==dept.id,StaffMember.is_active==True,StaffMember.is_available==True))
    r=ServiceRequest(tenant_id=t.id,customer_id=payload.customer_id,context_token=payload.context_token,request_type=payload.request_type,message=payload.message,status="requested",assigned_staff_id=staff.id if staff else None)
    db.add(r); db.commit(); db.refresh(r)
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
    r.status=payload.status
    if payload.status=="acknowledged": r.acknowledged_at=datetime.utcnow()
    if payload.status in ("completed","cancelled"): r.completed_at=datetime.utcnow()
    db.commit(); db.refresh(r)
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
    # Reward is deliberately capped and based on completed play, not score inflation.
    reward=0 if not customer else min(25,max(1,score//20))
    row=GameScore(tenant_id=t.id,customer_id=customer.id if customer else None,game=game,score=score,reward_points=reward)
    db.add(row)
    if customer and reward and _feature_config(db,t.id).get("loyalty",True):
        db.add(LoyaltyTransaction(tenant_id=t.id,customer_id=customer.id,points=reward,reason="game:"+game,reference_id=row.id))
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
        result=asyncio.run(PaymentAdapter(settings.razorpay_key_id,settings.razorpay_key_secret).create_order(int(bill.total)*100,"INR","bill-"+bill.id[:24]))
    except RuntimeError as exc: raise HTTPException(503,str(exc))
    except Exception as exc: raise HTTPException(502,"Unable to create payment order")
    return {"bill_id":bill.id,"key_id":settings.razorpay_key_id,"amount":result.get("amount"),"currency":result.get("currency"),"razorpay_order_id":result.get("id")}

@app.post("/api/v1/public/business/{slug}/bills/{bill_id}/verify-payment")
def verify_bill_payment(slug,bill_id,payload:PaymentVerify,db:Session=Depends(get_db)):
    import hmac,hashlib
    t=db.scalar(select(Tenant).where(Tenant.slug==slug.lower()))
    bill=db.scalar(select(Bill).where(Bill.id==bill_id,Bill.tenant_id==t.id)) if t else None
    if not bill: raise HTTPException(404,"Bill not found")
    expected=hmac.new(settings.razorpay_key_secret.encode(),(payload.razorpay_order_id+"|"+payload.razorpay_payment_id).encode(),hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected,payload.razorpay_signature): raise HTTPException(400,"Invalid payment signature")
    bill.payment_id=payload.razorpay_payment_id; bill.status="paid"; bill.paid_at=datetime.utcnow()
    order=db.get(Order,bill.order_id)
    if order: order.payment_status="paid"; order.updated_at=datetime.utcnow()
    db.commit()
    return {"paid":True,"bill_id":bill.id,"payment_id":bill.payment_id}

@app.post("/api/v1/webhooks/razorpay")
async def razorpay_webhook(payload:dict,signature:str|None=None,db:Session=Depends(get_db)):
    import hmac,hashlib,json as _json
    raw=_json.dumps(payload,separators=(",",":"),sort_keys=True).encode()
    if not settings.razorpay_key_secret or not signature: raise HTTPException(401,"Webhook signature required")
    expected=hmac.new(settings.razorpay_key_secret.encode(),raw,hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected,signature): raise HTTPException(400,"Invalid webhook signature")
    entity=payload.get("payload",{}).get("payment",{}).get("entity",{})
    order_id=entity.get("order_id")
    if order_id:
        # Razorpay order receipt is bill-<bill id>; resolve safely through bill id.
        receipt=entity.get("notes",{}).get("receipt") or entity.get("description","")
        if receipt.startswith("bill-"):
            bill=db.scalar(select(Bill).where(Bill.id==receipt[5:]))
            if bill:
                bill.status="paid"; bill.payment_id=entity.get("id"); bill.paid_at=datetime.utcnow()
                order=db.get(Order,bill.order_id)
                if order: order.payment_status="paid"
                db.commit()
    return {"received":True}

@app.get("/api/v1/public/business/{slug}/service-requests/{request_id}")
def public_service_request(slug,request_id,db:Session=Depends(get_db)):
    t=db.scalar(select(Tenant).where(Tenant.slug==slug.lower()))
    if not t: raise HTTPException(404,"Business not found")
    r=db.scalar(select(ServiceRequest).where(ServiceRequest.id==request_id,ServiceRequest.tenant_id==t.id))
    if not r: raise HTTPException(404,"Service request not found")
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
    return {"items":[{"id":x.id,"name":x.name,"department_id":x.department_id,"skills":x.skills,"is_active":x.is_active,"is_available":x.is_available} for x in rows]}

@app.post("/api/v1/tenants/{tenant_id}/staff", status_code=201)
def add_staff(tenant_id, payload: StaffCreate, user=Depends(get_current_user), db: Session=Depends(get_db)):
    require_tenant(user, tenant_id)
    from .models_ai import StaffMember
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
    return {**routed,"call_id":call.id,"status":call.status,"room_id":call.room_id}

class HandoffDecision(BaseModel):
    decision: str = Field(pattern="^(accept|decline)$")

@app.post("/api/v1/tenants/{tenant_id}/calls/{call_id}/handoff/decision")
def handoff_decision(tenant_id, call_id, payload: HandoffDecision, user=Depends(get_current_user), db: Session=Depends(get_db)):
    require_tenant(user, tenant_id)
    call=db.scalar(select(CallRecord).where(CallRecord.id==call_id, CallRecord.tenant_id==tenant_id))
    if not call: raise HTTPException(404, "Call not found")
    if not call.staff_id: raise HTTPException(409, "No staff assigned")
    staff=db.get(StaffMember, call.staff_id)
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
    db.commit(); db.refresh(o); return _order_out(o,db)

@app.get("/api/v1/public/business/{slug}/orders/{order_id}")
def public_order_status(slug,order_id,db:Session=Depends(get_db)):
    t=db.scalar(select(Tenant).where(Tenant.slug==slug.lower()))
    o=db.scalar(select(Order).where(Order.id==order_id,Order.tenant_id==t.id)) if t else None
    if not o: raise HTTPException(404,"Order not found")
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
        if o.customer_id:
            rules=db.scalars(select(LoyaltyRule).where(LoyaltyRule.tenant_id==tenant_id,LoyaltyRule.event_type=="purchase",LoyaltyRule.is_active==True)).all()
            for rule in rules:
                cfg=json.loads(rule.config_json or "{}")
                if int(cfg.get("minimum_bill",0))<=o.total:
                    db.add(LoyaltyTransaction(tenant_id=tenant_id,customer_id=o.customer_id,points=rule.points,reason=rule.name,reference_id=o.id))
    db.commit(); db.refresh(o); return _order_out(o,db)

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
    result=await generate_reply(db,t.id,payload.message,payload.conversation_id,payload.channel)
    if payload.phone:
        c=upsert_customer(db,t.id,payload.phone,payload.name,False)
        if result["intent"] in ("booking","human_handoff","pricing"): create_lead(db,t.id,"customer_pwa",c.id,result["intent"],payload.message)
    return {**result,"tenant_id":t.id}

@app.post("/api/v1/tenants/{tenant_id}/qr",status_code=201)
def create_qr(tenant_id,kind:str="business",label:str="Business QR",user=Depends(get_current_user),db:Session=Depends(get_db)):
    require_tenant(user,tenant_id); q=QrEntry(tenant_id=tenant_id,token=secrets.token_urlsafe(18),kind=kind,label=label); db.add(q); db.commit(); db.refresh(q)
    return {"id":q.id,"token":q.token,"url":settings.public_app_url+"/customer?qr="+q.token,"kind":q.kind,"label":q.label}
@app.get("/api/v1/public/qr/{token}")
def scan_qr(token,db:Session=Depends(get_db)):
    q=db.scalar(select(QrEntry).where(QrEntry.token==token))
    if not q: raise HTTPException(404,"QR not found")
    q.scans+=1; db.commit(); t=db.get(Tenant,q.tenant_id); return {"tenant_id":t.id,"slug":t.slug,"url":settings.public_app_url+"/customer","kind":q.kind}

class PublicCallStartRequest(BaseModel):
    name:str|None=None
    phone:str|None=None

@app.post("/api/v1/public/business/{slug}/call",status_code=201)
def start_public_call(slug:str,payload:PublicCallStartRequest,db:Session=Depends(get_db)):
    t=db.scalar(select(Tenant).where(Tenant.slug==slug.lower()))
    if not t: raise HTTPException(404,"Business not found")
    customer=None
    if payload.phone and payload.name:
        customer=upsert_customer(db,t.id,payload.phone.strip(),payload.name.strip(),False)
    call=CallRecord(tenant_id=t.id,customer_id=customer.id if customer else None,source="pwa_voice",status="ringing")
    db.add(call); db.commit(); db.refresh(call)
    return {"call_id":call.id,"customer_id":customer.id if customer else None,"status":"ringing","business_name":t.name}

@app.websocket("/ws/public/voice/{call_id}")
async def public_voice(websocket,call_id:str):
    await websocket.accept()
    db=SessionLocal(); call=db.get(CallRecord,call_id)
    if not call:
        await websocket.close(code=4404); db.close(); return
    tenant=db.get(Tenant,call.tenant_id)
    if not tenant or not settings.gemini_api_key:
        await websocket.send_json({"type":"error","message":"AI voice is not configured for this business."}); await websocket.close(); db.close(); return
    context=knowledge_context(db,tenant.id)
    system=(f"You are the AI customer engagement voice agent for {tenant.name}.\\n\\nAPPROVED BUSINESS CONTEXT:\\n{context}\\n\\n"
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
                        txt=sc["inputTranscription"]["text"]; call.transcript=((call.transcript+"\\n") if call.transcript else "")+"CUSTOMER: "+txt; db.commit(); await websocket.send_json({"type":"transcript","role":"customer","text":txt})
                    if sc.get("outputTranscription",{}).get("text"):
                        txt=sc["outputTranscription"]["text"]; call.transcript=((call.transcript+"\\n") if call.transcript else "")+"AI: "+txt; db.commit(); await websocket.send_json({"type":"transcript","role":"ai","text":txt})
                    if msg.get("toolCall"):
                        responses=[]
                        for fc in msg["toolCall"].get("functionCalls",[]):
                            if fc.get("name")=="save_customer_identity":
                            elif fc.get("name")=="create_booking":
                                args=fc.get("args",{}); service=db.scalar(select(Service).where(Service.id==str(args.get("service_id","")),Service.tenant_id==tenant.id,Service.is_active==True))
                                try:
                                    if not service: raise ValueError("Service not found or inactive")
                                    c=db.get(Customer,call.customer_id) if call.customer_id else upsert_customer(db,tenant.id,str(args.get("phone","")).strip(),str(args.get("name","")).strip(),False,source="ai_voice")
                                    starts=datetime.fromisoformat(str(args.get("starts_at","")))
                                    a,q=create_appointment(db,tenant,c,service,starts,"ai_voice",str(args.get("staff_id")) if args.get("staff_id") else None,str(args.get("notes")) if args.get("notes") else None,True,False)
                                    responses.append({"id":fc.get("id"),"name":fc.get("name"),"response":{"result":{"booking_id":a.id,"confirmed":True,"starts_at":a.starts_at.isoformat(),"queue_token":q.token if q else None,"estimated_wait_minutes":q.estimated_wait_minutes if q else None}}})
                                except Exception as exc:
                                    responses.append({"id":fc.get("id"),"name":fc.get("name"),"response":{"result":{"confirmed":False,"error":str(exc)}}})
                                args=fc.get("args",{}); c=upsert_customer(db,tenant.id,str(args.get("phone","")).strip(),str(args.get("name","")).strip(),False); call.customer_id=c.id; call.status="connected"; db.commit(); route_call(db,tenant.id,call,call.intent); responses.append({"id":fc.get("id"),"name":fc.get("name"),"response":{"result":{"customer_id":c.id,"verified":True}}})
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
    return {"call_id":call.id,"status":call.status,"room_id":call.room_id,"staff":{"id":staff.id,"name":staff.name} if staff else None}

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
            call.transcript=((call.transcript+"\n") if call.transcript else "")+"CUSTOMER: "+payload.transcript+"\nAI: "+result["reply"]
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
