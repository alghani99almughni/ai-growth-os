from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select
from sqlalchemy.orm import Session
from pydantic import BaseModel
from .db import SessionLocal
from .models import Tenant, Customer, Lead
from .schemas import TenantCreate, CustomerCreate, LeadCreate, TenantOut
from .services import create_tenant, upsert_customer, create_lead

app = FastAPI(title="AI Growth OS API", version="0.2.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=False, allow_methods=["*"], allow_headers=["*"])

def get_db():
    db = SessionLocal()
    try: yield db
    finally: db.close()

class Health(BaseModel):
    status: str
    service: str

@app.get("/health", response_model=Health)
def health(): return {"status": "ok", "service": "ai-growth-os-api"}

@app.post("/api/v1/tenants", response_model=TenantOut, status_code=201)
def create_tenant_endpoint(payload: TenantCreate, db: Session = Depends(get_db)):
    if db.scalar(select(Tenant).where(Tenant.slug == payload.slug.lower())):
        raise HTTPException(409, "Tenant slug already exists")
    return create_tenant(db, payload.name, payload.slug, payload.industry)

@app.get("/api/v1/tenants/{tenant_id}", response_model=TenantOut)
def get_tenant(tenant_id: str, db: Session = Depends(get_db)):
    tenant = db.get(Tenant, tenant_id)
    if not tenant: raise HTTPException(404, "Tenant not found")
    return tenant

@app.post("/api/v1/customers", status_code=201)
def identify_customer(payload: CustomerCreate, db: Session = Depends(get_db)):
    if not db.get(Tenant, payload.tenant_id): raise HTTPException(404, "Tenant not found")
    c = upsert_customer(db, payload.tenant_id, payload.phone, payload.name, payload.whatsapp_opt_in)
    return {"id": c.id, "tenant_id": c.tenant_id, "name": c.name, "phone": c.phone, "whatsapp_opt_in": c.whatsapp_opt_in}

@app.get("/api/v1/tenants/{tenant_id}/customers")
def list_customers(tenant_id: str, db: Session = Depends(get_db)):
    if not db.get(Tenant, tenant_id): raise HTTPException(404, "Tenant not found")
    rows = db.scalars(select(Customer).where(Customer.tenant_id == tenant_id).order_by(Customer.created_at.desc())).all()
    return {"items": [{"id":x.id,"name":x.name,"phone":x.phone,"whatsapp_opt_in":x.whatsapp_opt_in} for x in rows]}

@app.post("/api/v1/leads", status_code=201)
def create_lead_endpoint(payload: LeadCreate, db: Session = Depends(get_db)):
    if not db.get(Tenant, payload.tenant_id): raise HTTPException(404, "Tenant not found")
    if payload.customer_id and not db.scalar(select(Customer).where(Customer.id==payload.customer_id, Customer.tenant_id==payload.tenant_id)):
        raise HTTPException(404, "Customer not found for tenant")
    l = create_lead(db, payload.tenant_id, payload.source, payload.customer_id, payload.intent, payload.notes)
    return {"id":l.id,"tenant_id":l.tenant_id,"status":l.status,"intent":l.intent}

@app.get("/api/v1/tenants/{tenant_id}/leads")
def list_leads(tenant_id: str, db: Session = Depends(get_db)):
    if not db.get(Tenant, tenant_id): raise HTTPException(404, "Tenant not found")
    rows = db.scalars(select(Lead).where(Lead.tenant_id==tenant_id).order_by(Lead.created_at.desc())).all()
    return {"items": [{"id":x.id,"customer_id":x.customer_id,"source":x.source,"intent":x.intent,"notes":x.notes,"status":x.status} for x in rows]}

@app.post("/api/v1/ai/chat")
def chat(payload: dict):
    message = str(payload.get("message","")).strip()
    return {"reply":"AI provider adapter is not configured yet. Message received safely.","message":message,"intent":"unknown","lead":False}
