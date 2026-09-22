import hashlib
import hmac
import re
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from sqlalchemy import select
from sqlalchemy.orm import Session
from .config import settings
from .models import Tenant, User, Customer, Lead, Service, Product
import jwt

def normalize_phone(phone: str) -> str:
    value = re.sub(r"[^0-9+]", "", phone.strip())
    if value.startswith("00"): value = "+" + value[2:]
    return value

def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 310000).hex()
    return "pbkdf2_sha256$310000$" + salt + "$" + digest

def verify_password(password: str, encoded: str) -> bool:
    try:
        scheme, rounds, salt, expected = encoded.split("$", 3)
        if scheme != "pbkdf2_sha256": return False
        actual = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), int(rounds)).hex()
        return hmac.compare_digest(actual, expected)
    except (ValueError, TypeError): return False

def create_access_token(user: User) -> str:
    now = datetime.now(timezone.utc)
    payload = {"sub": user.id, "tenant_id": user.tenant_id, "role": user.role, "iat": now, "exp": now + timedelta(minutes=settings.access_token_minutes)}
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)

def create_tenant(db: Session, name: str, slug: str, industry: str) -> Tenant:
    tenant = Tenant(id=str(uuid.uuid4()), name=name.strip(), slug=slug.lower(), industry=industry.lower())
    db.add(tenant); db.commit(); db.refresh(tenant); return tenant

def create_owner(db: Session, name: str, email: str, password: str, tenant: Tenant) -> User:
    user = User(id=str(uuid.uuid4()), name=name.strip(), email=email.lower().strip(), password_hash=hash_password(password), tenant_id=tenant.id, role="owner")
    db.add(user); db.commit(); db.refresh(user); return user

def upsert_customer(db: Session, tenant_id: str, phone: str, name: str | None, whatsapp_opt_in: bool, **fields) -> Customer:
    normalized = normalize_phone(phone)
    if not normalized: raise ValueError("Customer mobile number is required")
    if not name or not name.strip(): raise ValueError("Customer name is required")
    customer = db.scalar(select(Customer).where(Customer.tenant_id == tenant_id, Customer.phone == normalized))
    if customer:
        if name: customer.name = name.strip()
        customer.whatsapp_opt_in = whatsapp_opt_in or customer.whatsapp_opt_in
    else:
        customer = Customer(id=str(uuid.uuid4()), tenant_id=tenant_id, phone=normalized, name=name, whatsapp_opt_in=whatsapp_opt_in, source=fields.get('source','manual'))
        db.add(customer)
    for key in ('email','address','notes','tags','source'):
        if key in fields and fields[key] is not None: setattr(customer,key,fields[key])
    db.commit(); db.refresh(customer); return customer
def create_lead(db: Session, tenant_id: str, source: str, customer_id: str | None, intent: str | None, notes: str | None) -> Lead:
    lead = Lead(id=str(uuid.uuid4()), tenant_id=tenant_id, source=source, customer_id=customer_id, intent=intent, notes=notes)
    db.add(lead); db.commit(); db.refresh(lead); return lead

def update_tenant_profile(db: Session, tenant: Tenant, data: dict) -> Tenant:
    for key, value in data.items():
        setattr(tenant, key, value)
    db.commit(); db.refresh(tenant); return tenant

def create_service(db: Session, tenant_id: str, data: dict) -> Service:
    item = Service(id=str(uuid.uuid4()), tenant_id=tenant_id, **data)
    db.add(item); db.commit(); db.refresh(item); return item

def create_product(db: Session, tenant_id: str, data: dict) -> Product:
    item = Product(id=str(uuid.uuid4()), tenant_id=tenant_id, **data)
    db.add(item); db.commit(); db.refresh(item); return item
