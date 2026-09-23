import json
from sqlalchemy import select
from sqlalchemy.orm import Session
from .models import Tenant, Service, Product
from .models_growth import TenantSetting, BusinessHour

CAPABILITY_LABELS = {
    "digital_menu": "digital menu",
    "online_ordering": "online ordering",
    "order_tracking": "order tracking",
    "call_waiter": "call waiter",
    "service_requests": "service requests",
    "games": "mini games",
    "auto_bill": "automatic billing",
    "online_payment": "online payments",
    "ai_chat": "AI chat",
    "ai_voice": "AI voice",
    "loyalty": "loyalty program",
    "referrals": "referrals",
    "feedback": "feedback",
    "google_review": "Google reviews",
    "bookings": "appointments",
    "queue": "queue management",
}

def tenant_policy(db: Session, tenant_id: str) -> dict:
    tenant = db.get(Tenant, tenant_id)
    feature_row = db.scalar(select(TenantSetting).where(
        TenantSetting.tenant_id == tenant_id,
        TenantSetting.key == "features",
    ))
    brain_row = db.scalar(select(TenantSetting).where(
        TenantSetting.tenant_id == tenant_id,
        TenantSetting.key == "business_brain",
    ))
    website_row = db.scalar(select(TenantSetting).where(
        TenantSetting.tenant_id == tenant_id,
        TenantSetting.key == "website_content",
    ))
    try:
        features = json.loads(feature_row.value_json) if feature_row else {}
    except Exception:
        features = {}
    try:
        brain = json.loads(brain_row.value_json) if brain_row else {}
    except Exception:
        brain = {}
    try:
        website = json.loads(website_row.value_json) if website_row else {}
    except Exception:
        website = {}

    services = db.scalars(select(Service).where(Service.tenant_id == tenant_id, Service.is_active == True)).all()
    products = db.scalars(select(Product).where(Product.tenant_id == tenant_id, Product.is_active == True)).all()
    hours = db.scalars(select(BusinessHour).where(BusinessHour.tenant_id == tenant_id).order_by(BusinessHour.weekday)).all()

    return {
        "tenant": tenant,
        "features": features,
        "business_brain": brain,
        "website": website,
        "services": services,
        "products": products,
        "hours": hours,
    }

def capability_enabled(policy: dict, capability: str, default: bool = False) -> bool:
    return bool(policy.get("features", {}).get(capability, default))

def policy_context(policy: dict) -> str:
    tenant = policy.get("tenant")
    features = policy.get("features", {})
    brain = policy.get("business_brain", {})
    website = policy.get("website", {})
    services = policy.get("services", [])
    products = policy.get("products", [])
    hours = policy.get("hours", [])

    enabled = [CAPABILITY_LABELS.get(k, k) for k, v in features.items() if v]
    disabled = [CAPABILITY_LABELS.get(k, k) for k, v in features.items() if not v]

    lines = [
        "TENANT POLICY — authoritative for this business",
        "Enabled capabilities: " + (", ".join(enabled) if enabled else "none"),
        "Disabled capabilities: " + (", ".join(disabled) if disabled else "none"),
        "Never perform, promise, or expose a disabled capability.",
    ]
    instructions = brain.get("instructions", "")
    if instructions:
        lines.append("TENANT ADMIN INSTRUCTIONS:\n" + instructions)
    if website:
        published = website.get("published", True)
        if published:
            lines.append("TENANT-APPROVED WEBSITE CONTENT:\n" + json.dumps(website, ensure_ascii=False))
    if services:
        lines.append("CURRENT SERVICES / PRICING:")
        for x in services:
            lines.append(f"- {x.name}: {x.description or ''}; price={x.price} {x.currency}; duration={x.duration_minutes or ''} minutes")
    if products:
        lines.append("CURRENT PRODUCTS / PRICING:")
        for x in products:
            lines.append(f"- {x.name}: {x.description or ''}; price={x.price} {x.currency}; stock={x.stock_quantity if x.stock_quantity is not None else 'unknown'}")
    if hours:
        lines.append("CURRENT BUSINESS HOURS:")
        for x in hours:
            lines.append(f"- weekday={x.weekday}; closed={x.is_closed}; open={x.open_time}; close={x.close_time}")
    return "\n".join(lines)
