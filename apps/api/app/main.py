from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session
from pydantic import BaseModel
from .db import SessionLocal
from .models import Tenant, User, Customer, Lead, Service, Product
from .schemas import *
from .services import *
from .config import settings
import jwt

app = FastAPI(title="AI Growth OS API", version="0.4.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=False, allow_methods=["*"], allow_headers=["*"])
security = HTTPBearer(auto_error=False)

def get_db():
    db = SessionLocal()
    try: yield db
    finally: db.close()

class Health(BaseModel):
    status: str
    service: str

@app.get("/health", response_model=Health)
def health(): return {"status":"ok","service":"ai-growth-os-api"}

def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security), db: Session = Depends(get_db)) -> User:
    if not credentials or credentials.scheme.lower() != "bearer": raise HTTPException(401,"Authentication required")
    try:
        payload=jwt.decode(credentials.credentials,settings.jwt_secret,algorithms=[settings.jwt_algorithm]); user_id=payload.get("sub")
        if not user_id: raise ValueError()
    except (jwt.InvalidTokenError,ValueError): raise HTTPException(401,"Invalid or expired token")
    user=db.get(User,user_id)
    if not user or not user.is_active: raise HTTPException(401,"User not found or inactive")
    if payload.get("tenant_id") != user.tenant_id: raise HTTPException(401,"Invalid tenant context")
    return user

def require_tenant(user: User, tenant_id: str):
    if user.tenant_id != tenant_id: raise HTTPException(403,"Tenant access denied")

def user_out(user: User): return UserOut(id=user.id,email=user.email,name=user.name,tenant_id=user.tenant_id,role=user.role)

@app.post("/api/v1/auth/register",response_model=AuthResponse,status_code=201)
def register(payload:RegisterRequest,db:Session=Depends(get_db)):
    if db.scalar(select(User).where(User.email==payload.email.lower())): raise HTTPException(409,"Email already registered")
    if db.scalar(select(Tenant).where(Tenant.slug==payload.slug.lower())): raise HTTPException(409,"Business slug already exists")
    tenant=create_tenant(db,payload.business_name,payload.slug,payload.industry); user=create_owner(db,payload.name,payload.email,payload.password,tenant)
    return {"access_token":create_access_token(user),"token_type":"bearer","user":user_out(user),"tenant":tenant}

@app.post("/api/v1/auth/login",response_model=AuthResponse)
def login(payload:LoginRequest,db:Session=Depends(get_db)):
    user=db.scalar(select(User).where(User.email==payload.email.lower()))
    if not user or not user.is_active or not verify_password(payload.password,user.password_hash): raise HTTPException(401,"Invalid email or password")
    tenant=db.get(Tenant,user.tenant_id)
    if not tenant: raise HTTPException(401,"Tenant not found")
    return {"access_token":create_access_token(user),"token_type":"bearer","user":user_out(user),"tenant":tenant}

@app.get("/api/v1/auth/me",response_model=AuthResponse)
def me(user:User=Depends(get_current_user),db:Session=Depends(get_db)):
    tenant=db.get(Tenant,user.tenant_id)
    if not tenant: raise HTTPException(404,"Tenant not found")
    return {"access_token":"","token_type":"bearer","user":user_out(user),"tenant":tenant}

@app.get("/api/v1/tenants/{tenant_id}",response_model=TenantOut)
def get_tenant(tenant_id:str,user:User=Depends(get_current_user),db:Session=Depends(get_db)):
    require_tenant(user,tenant_id); tenant=db.get(Tenant,tenant_id)
    if not tenant: raise HTTPException(404,"Tenant not found")
    return tenant

@app.put("/api/v1/tenants/{tenant_id}/profile",response_model=TenantOut)
def update_profile(tenant_id:str,payload:TenantProfileUpdate,user:User=Depends(get_current_user),db:Session=Depends(get_db)):
    require_tenant(user,tenant_id); tenant=db.get(Tenant,tenant_id)
    if not tenant: raise HTTPException(404,"Tenant not found")
    return update_tenant_profile(db,tenant,payload.model_dump())

@app.post("/api/v1/tenants/{tenant_id}/services",status_code=201)
def add_service(tenant_id:str,payload:ServiceCreate,user:User=Depends(get_current_user),db:Session=Depends(get_db)):
    require_tenant(user,tenant_id); return create_service(db,tenant_id,payload.model_dump())

@app.get("/api/v1/tenants/{tenant_id}/services")
def list_services(tenant_id:str,user:User=Depends(get_current_user),db:Session=Depends(get_db)):
    require_tenant(user,tenant_id)
    rows=db.scalars(select(Service).where(Service.tenant_id==tenant_id).order_by(Service.created_at.desc())).all()
    return {"items":[{"id":x.id,"name":x.name,"description":x.description,"price":float(x.price) if x.price is not None else None,"currency":x.currency,"duration_minutes":x.duration_minutes,"is_active":x.is_active} for x in rows]}

@app.post("/api/v1/tenants/{tenant_id}/products",status_code=201)
def add_product(tenant_id:str,payload:ProductCreate,user:User=Depends(get_current_user),db:Session=Depends(get_db)):
    require_tenant(user,tenant_id); return create_product(db,tenant_id,payload.model_dump())

@app.get("/api/v1/tenants/{tenant_id}/products")
def list_products(tenant_id:str,user:User=Depends(get_current_user),db:Session=Depends(get_db)):
    require_tenant(user,tenant_id)
    rows=db.scalars(select(Product).where(Product.tenant_id==tenant_id).order_by(Product.created_at.desc())).all()
    return {"items":[{"id":x.id,"name":x.name,"description":x.description,"price":float(x.price) if x.price is not None else None,"currency":x.currency,"sku":x.sku,"stock_quantity":x.stock_quantity,"is_active":x.is_active} for x in rows]}

@app.post("/api/v1/customers",status_code=201)
def identify_customer(payload:CustomerCreate,user:User=Depends(get_current_user),db:Session=Depends(get_db)):
    require_tenant(user,payload.tenant_id); c=upsert_customer(db,payload.tenant_id,payload.phone,payload.name,payload.whatsapp_opt_in)
    return {"id":c.id,"tenant_id":c.tenant_id,"name":c.name,"phone":c.phone,"whatsapp_opt_in":c.whatsapp_opt_in}

@app.get("/api/v1/tenants/{tenant_id}/customers")
def list_customers(tenant_id:str,user:User=Depends(get_current_user),db:Session=Depends(get_db)):
    require_tenant(user,tenant_id); rows=db.scalars(select(Customer).where(Customer.tenant_id==tenant_id).order_by(Customer.created_at.desc())).all()
    return {"items":[{"id":x.id,"name":x.name,"phone":x.phone,"whatsapp_opt_in":x.whatsapp_opt_in} for x in rows]}

@app.post("/api/v1/leads",status_code=201)
def create_lead_endpoint(payload:LeadCreate,user:User=Depends(get_current_user),db:Session=Depends(get_db)):
    require_tenant(user,payload.tenant_id)
    if payload.customer_id and not db.scalar(select(Customer).where(Customer.id==payload.customer_id,Customer.tenant_id==payload.tenant_id)): raise HTTPException(404,"Customer not found for tenant")
    l=create_lead(db,payload.tenant_id,payload.source,payload.customer_id,payload.intent,payload.notes)
    return {"id":l.id,"tenant_id":l.tenant_id,"status":l.status,"intent":l.intent}

@app.get("/api/v1/tenants/{tenant_id}/leads")
def list_leads(tenant_id:str,user:User=Depends(get_current_user),db:Session=Depends(get_db)):
    require_tenant(user,tenant_id); rows=db.scalars(select(Lead).where(Lead.tenant_id==tenant_id).order_by(Lead.created_at.desc())).all()
    return {"items":[{"id":x.id,"customer_id":x.customer_id,"source":x.source,"intent":x.intent,"notes":x.notes,"status":x.status} for x in rows]}

@app.post("/api/v1/ai/chat")
def chat(payload:dict,user:User=Depends(get_current_user)):
    message=str(payload.get("message","")).strip()
    return {"reply":"AI provider adapter is not configured yet. Message received safely.","message":message,"intent":"unknown","lead":False,"tenant_id":user.tenant_id}
