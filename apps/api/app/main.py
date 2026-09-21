from fastapi import FastAPI,Depends,HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPAuthorizationCredentials,HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session
from pydantic import BaseModel,Field
from .db import SessionLocal
from .models import Tenant,User,Customer,Lead,Service,Product
from .models_growth import KnowledgeItem,Appointment,LoyaltyTransaction,QrEntry,CallRecord,Campaign
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
import asyncio,json,base64
import websockets
import jwt,secrets

app=FastAPI(title="AI Growth OS API",version="1.0.0")
app.add_middleware(CORSMiddleware,allow_origins=["*"],allow_credentials=False,allow_methods=["*"],allow_headers=["*"])

@app.websocket("/ws/calls/{call_id}")
async def call_signal(websocket,call_id:str):
    await signal(websocket,call_id)

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
    require_tenant(user,payload.tenant_id); c=upsert_customer(db,payload.tenant_id,payload.phone,payload.name,payload.whatsapp_opt_in); return {"id":c.id,"tenant_id":c.tenant_id,"name":c.name,"phone":c.phone}
@app.get("/api/v1/tenants/{tenant_id}/customers")
def customers(tenant_id,user=Depends(get_current_user),db:Session=Depends(get_db)):
    require_tenant(user,tenant_id); rows=db.scalars(select(Customer).where(Customer.tenant_id==tenant_id)).all(); return {"items":[{"id":x.id,"name":x.name,"phone":x.phone,"whatsapp_opt_in":x.whatsapp_opt_in} for x in rows]}
@app.post("/api/v1/leads",status_code=201)
def lead(payload:LeadCreate,user=Depends(get_current_user),db:Session=Depends(get_db)):
    require_tenant(user,payload.tenant_id); l=create_lead(db,payload.tenant_id,payload.source,payload.customer_id,payload.intent,payload.notes); return {"id":l.id,"status":l.status}
@app.get("/api/v1/tenants/{tenant_id}/leads")
def leads(tenant_id,user=Depends(get_current_user),db:Session=Depends(get_db)):
    require_tenant(user,tenant_id); rows=db.scalars(select(Lead).where(Lead.tenant_id==tenant_id)).all(); return {"items":[{"id":x.id,"customer_id":x.customer_id,"source":x.source,"intent":x.intent,"notes":x.notes,"status":x.status} for x in rows]}

class ChatRequest(BaseModel): tenant_id:str; message:str=Field(min_length=1,max_length=4000); name:str|None=None; phone:str|None=None; conversation_id:str|None=None; channel:str="pwa"
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
    return {"id":t.id,"name":t.name,"slug":t.slug,"industry":t.industry,"description":t.description,"phone":t.phone,"whatsapp_number":t.whatsapp_number,"address":t.address}
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
             "After identity is saved, say a short confirmation and ask how you can help. Be concise, natural and multilingual when appropriate.")
    ws_url="wss://generativelanguage.googleapis.com/ws/google.ai.generativelanguage.v1beta.GenerativeService.BidiGenerateContent?key="+settings.gemini_api_key
    setup={"setup":{"model":"models/"+settings.gemini_live_model,"generationConfig":{"responseModalities":["AUDIO"]},"systemInstruction":{"parts":[{"text":system}]},"inputAudioTranscription":{},"outputAudioTranscription":{},"sessionResumption":{ },"tools":[{"functionDeclarations":[{"name":"save_customer_identity","description":"Save and verify the customer's name and mobile number after the customer has stated both during the call.","parameters":{"type":"OBJECT","properties":{"name":{"type":"STRING"},"phone":{"type":"STRING"}},"required":["name","phone"]}}]}]}}
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
