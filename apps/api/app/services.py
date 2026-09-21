import re
import uuid
from sqlalchemy import select
from sqlalchemy.orm import Session
from .models import Tenant, Customer, Lead

def normalize_phone(phone: str) -> str:
    value = re.sub(r"[^0-9+]", "", phone.strip())
    if value.startswith("00"):
        value = "+" + value[2:]
    return value

def create_tenant(db: Session, name: str, slug: str, industry: str) -> Tenant:
    tenant = Tenant(id=str(uuid.uuid4()), name=name.strip(), slug=slug.lower(), industry=industry.lower())
    db.add(tenant)
    db.commit()
    db.refresh(tenant)
    return tenant

def upsert_customer(db: Session, tenant_id: str, phone: str, name: str | None, whatsapp_opt_in: bool) -> Customer:
    normalized = normalize_phone(phone)
    customer = db.scalar(select(Customer).where(Customer.tenant_id == tenant_id, Customer.phone == normalized))
    if customer:
        if name:
            customer.name = name.strip()
        customer.whatsapp_opt_in = whatsapp_opt_in or customer.whatsapp_opt_in
    else:
        customer = Customer(id=str(uuid.uuid4()), tenant_id=tenant_id, phone=normalized, name=name, whatsapp_opt_in=whatsapp_opt_in)
        db.add(customer)
    db.commit()
    db.refresh(customer)
    return customer

def create_lead(db: Session, tenant_id: str, source: str, customer_id: str | None, intent: str | None, notes: str | None) -> Lead:
    lead = Lead(id=str(uuid.uuid4()), tenant_id=tenant_id, source=source, customer_id=customer_id, intent=intent, notes=notes)
    db.add(lead)
    db.commit()
    db.refresh(lead)
    return lead
