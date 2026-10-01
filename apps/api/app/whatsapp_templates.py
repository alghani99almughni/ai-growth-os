"""WhatsApp template registry + service-window helper.

Your codebase already has two WhatsApp providers wired end-to-end:
    - OpenWA       (self-hosted, provider="openwa")
    - Meta Cloud   (provider="meta")

OpenWA can already send templates. Meta Cloud currently raises in
integrations.WhatsAppAdapter.send_template. This module supplies:
    1. The list of templates the platform ships with
    2. The Meta Graph API payload builder
    3. The 24-hour service-window check
    4. Per-tenant template-name overrides

Nothing here duplicates the existing adapter. It is a helper library that
the adapter method calls into.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional

logger = logging.getLogger(__name__)


SERVICE_WINDOW_HOURS = 24


# ---------------------------------------------------------------------------
# Service window
# ---------------------------------------------------------------------------

def is_within_service_window(last_inbound_at: Optional[datetime]) -> bool:
    """True when the 24h customer service window is open for this phone.

    Meta Cloud API allows free-form text only inside this window. Outside
    it, business-initiated messages MUST use an approved template.
    """
    if not last_inbound_at:
        return False
    return datetime.utcnow() - last_inbound_at < timedelta(hours=SERVICE_WINDOW_HOURS)


# ---------------------------------------------------------------------------
# Template registry
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class TemplateDef:
    name: str
    category: str
    languages: tuple
    variables: tuple
    description: str


TEMPLATES: tuple = (
    TemplateDef(
        name="booking_confirmation", category="utility",
        languages=("en", "hi", "te", "ta"),
        variables=("customer_name", "business_name", "service_name", "date", "time"),
        description="Sent when an appointment is confirmed.",
    ),
    TemplateDef(
        name="booking_reminder", category="utility",
        languages=("en", "hi", "te", "ta"),
        variables=("customer_name", "business_name", "service_name", "date", "time"),
        description="Sent ~24h before an appointment.",
    ),
    TemplateDef(
        name="order_confirmed", category="utility",
        languages=("en", "hi", "te", "ta"),
        variables=("customer_name", "business_name", "order_id", "total"),
        description="Sent when an order is placed.",
    ),
    TemplateDef(
        name="order_ready", category="utility",
        languages=("en", "hi", "te", "ta"),
        variables=("customer_name", "business_name", "context", "order_id"),
        description="Sent when an order is ready.",
    ),
    TemplateDef(
        name="payment_receipt", category="utility",
        languages=("en", "hi"),
        variables=("customer_name", "business_name", "bill_id", "amount"),
        description="Sent after a successful payment.",
    ),
    TemplateDef(
        name="feedback_request", category="utility",
        languages=("en", "hi", "te", "ta"),
        variables=("customer_name", "business_name"),
        description="Sent after service completion.",
    ),
    TemplateDef(
        name="re_engagement", category="marketing",
        languages=("en", "hi"),
        variables=("customer_name", "business_name", "offer"),
        description="Marketing template; requires customer opt-in.",
    ),
    TemplateDef(
        name="callback_promise", category="utility",
        languages=("en", "hi", "te", "ta"),
        variables=("customer_name", "business_name", "when"),
        description="Sent when a callback is promised.",
    ),
)


def get_template(name: str) -> Optional[TemplateDef]:
    n = (name or "").strip().lower()
    for t in TEMPLATES:
        if t.name == n:
            return t
    return None


def all_templates() -> list:
    return [
        {
            "name": t.name,
            "category": t.category,
            "languages": list(t.languages),
            "variables": list(t.variables),
            "description": t.description,
        }
        for t in TEMPLATES
    ]


def validate(name: str, language: str, variables: dict) -> tuple:
    """Return (ok, error_message)."""
    t = get_template(name)
    if not t:
        return False, f"unknown template: {name}"
    lang = (language or "en").lower()
    if lang not in t.languages:
        return False, f"template {name} does not support language {lang}"
    missing = [v for v in t.variables if not (variables or {}).get(v)]
    if missing:
        return False, f"missing template variables: {', '.join(missing)}"
    return True, ""


# ---------------------------------------------------------------------------
# Meta Cloud API payload
# ---------------------------------------------------------------------------

def build_meta_payload(
    to_phone: str,
    meta_template_name: str,
    language_code: str,
    variables: dict,
) -> dict:
    """Build the JSON body for POST /{phone_number_id}/messages.

    Uses positional parameters ({{1}}, {{2}}, ...) in the order the Meta
    template was approved with, which must match the template's variable
    order in Meta Business Manager.
    """
    params = []
    for key in (variables or {}):
        if key.startswith("_"):
            continue
        params.append({"type": "text", "text": str(variables[key])})

    body = {
        "messaging_product": "whatsapp",
        "to": to_phone.lstrip("+"),
        "type": "template",
        "template": {
            "name": meta_template_name,
            "language": {"code": language_code},
        },
    }
    if params:
        body["template"]["components"] = [
            {"type": "body", "parameters": params}
        ]
    return body


# ---------------------------------------------------------------------------
# Per-tenant overrides
# ---------------------------------------------------------------------------

def resolve_meta_template_name(db, tenant_id: str, logical_name: str) -> str:
    """Return the tenant's Meta-approved template name for a logical name.

    Tenants can override in TenantSetting key 'whatsapp_templates', shape
        {"booking_confirmation": "appt_confirmed_v2"}
    Falls back to the logical name.
    """
    import json as _json
    try:
        from sqlalchemy import select
        from .models_growth import TenantSetting
        row = db.scalar(select(TenantSetting).where(
            TenantSetting.tenant_id == tenant_id,
            TenantSetting.key == "whatsapp_templates",
        ))
        if not row:
            return logical_name
        overrides = _json.loads(row.value_json or "{}")
        return overrides.get(logical_name) or logical_name
    except Exception:
        return logical_name


def resolve_meta_language(db, tenant_id: str, logical_name: str, requested: str) -> str:
    """Return the Meta language code for this template on this tenant.

    Tenants can override in TenantSetting key 'whatsapp_template_languages',
    shape: {template_name: {lang: meta_lang_code}}
    """
    import json as _json
    try:
        from sqlalchemy import select
        from .models_growth import TenantSetting
        row = db.scalar(select(TenantSetting).where(
            TenantSetting.tenant_id == tenant_id,
            TenantSetting.key == "whatsapp_template_languages",
        ))
        if not row:
            return requested
        data = _json.loads(row.value_json or "{}")
        per_template = data.get(logical_name) or {}
        return per_template.get(requested) or requested
    except Exception:
        return requested