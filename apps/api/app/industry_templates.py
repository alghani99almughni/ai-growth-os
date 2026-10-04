"""Industry template defaults.

Seeds a freshly provisioned tenant with starter data so the customer PWA is
usable immediately, without the tenant having to configure anything.

Called once from provision_defaults() in main.py.

Design:
    - Pure data + one entry function
    - Idempotent: if rows already exist for the tenant, no duplicates are created
    - Never overwrites tenant edits
    - No HTTP routes, no imports from main.py
"""
from __future__ import annotations

import json
import logging
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import Tenant, Service
from .models_growth import (
    KnowledgeItem,
    MenuCategory,
    MenuItem,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Industry catalogs
# ---------------------------------------------------------------------------

INDUSTRIES: dict[str, dict] = {
    "restaurant": {
        "label": "Restaurant",
        "services": [
            {"name": "Table reservation", "description": "Reserve a table for your party.", "duration_minutes": 90, "price": 0},
            {"name": "Takeaway order", "description": "Order food for pickup.", "duration_minutes": 30, "price": 0},
        ],
        "menu_categories": [
            {"name": "Starters", "items": [
                {"name": "Veg Soup", "description": "Chef's soup of the day", "price": 120},
                {"name": "Paneer Tikka", "description": "Grilled cottage cheese", "price": 220},
            ]},
            {"name": "Main Course", "items": [
                {"name": "Veg Biryani", "description": "Aromatic rice with vegetables", "price": 280},
                {"name": "Butter Chicken", "description": "Creamy tomato curry", "price": 340},
            ]},
            {"name": "Beverages", "items": [
                {"name": "Masala Chai", "description": "Spiced Indian tea", "price": 60},
                {"name": "Fresh Lime Soda", "description": "Sweet or salted", "price": 90},
            ]},
        ],
        "knowledge": [
            {"title": "Do you take reservations?", "content": "Yes. Tables can be reserved through our QR menu or by calling the front desk. Walk-ins are welcome, subject to availability.", "kind": "faq"},
            {"title": "Do you have vegetarian options?", "content": "Yes. We offer vegetarian, vegan, and Jain options across the menu. Please ask the AI assistant for specific dishes.", "kind": "faq"},
            {"title": "Do you deliver?", "content": "We offer takeaway. Delivery through our own team is limited to nearby areas. Please ask the team for details.", "kind": "faq"},
        ],
    },
    "cafe": {
        "label": "Cafe",
        "services": [
            {"name": "Table reservation", "description": "Reserve a table at the cafe.", "duration_minutes": 60, "price": 0},
        ],
        "menu_categories": [
            {"name": "Coffee & Tea", "items": [
                {"name": "Cappuccino", "description": "Espresso with steamed milk", "price": 160},
                {"name": "Filter Coffee", "description": "South Indian filter coffee", "price": 90},
                {"name": "Green Tea", "description": "Loose-leaf green tea", "price": 120},
            ]},
            {"name": "Snacks", "items": [
                {"name": "Cheese Sandwich", "description": "Grilled with cheese and herbs", "price": 180},
                {"name": "Banana Bread", "description": "Freshly baked", "price": 140},
            ]},
        ],
        "knowledge": [
            {"title": "Do you have Wi-Fi?", "content": "Yes, free Wi-Fi is available for all guests. Ask the team for the current password.", "kind": "faq"},
            {"title": "Do you have vegan options?", "content": "Yes. We offer oat, almond, and soy milk alternatives, plus vegan snacks.", "kind": "faq"},
        ],
    },
    "hotel": {
        "label": "Hotel",
        "services": [
            {"name": "Room booking enquiry", "description": "Enquiry about room availability and rates.", "duration_minutes": 30, "price": 0},
            {"name": "Airport pickup", "description": "Arrange airport transfer.", "duration_minutes": 60, "price": 0},
        ],
        "menu_categories": [
            {"name": "Room Service", "items": [
                {"name": "Continental Breakfast", "description": "Served in-room", "price": 450},
                {"name": "Club Sandwich", "description": "Triple-decker", "price": 380},
            ]},
        ],
        "knowledge": [
            {"title": "What is check-in time?", "content": "Check-in is 2:00 PM, check-out is 12:00 PM. Early check-in and late check-out are subject to availability.", "kind": "faq"},
            {"title": "Do you have parking?", "content": "Yes, complimentary parking is available for in-house guests.", "kind": "faq"},
        ],
    },
    "salon": {
        "label": "Salon",
        "services": [
            {"name": "Haircut (Women)", "description": "Cut, wash, and blow dry.", "duration_minutes": 60, "price": 800},
            {"name": "Haircut (Men)", "description": "Cut and style.", "duration_minutes": 30, "price": 400},
            {"name": "Facial", "description": "Classic facial treatment.", "duration_minutes": 45, "price": 1200},
            {"name": "Hair Colour", "description": "Full-head colour.", "duration_minutes": 90, "price": 2500},
        ],
        "menu_categories": [],
        "knowledge": [
            {"title": "Do I need to book in advance?", "content": "We recommend booking in advance, especially on weekends. Walk-ins are welcome subject to availability.", "kind": "faq"},
            {"title": "What products do you use?", "content": "We use professional salon-grade products. Please let us know if you have specific allergies or preferences.", "kind": "faq"},
        ],
    },
    "dental": {
        "label": "Dental Clinic",
        "services": [
            {"name": "Consultation", "description": "First visit with the dentist.", "duration_minutes": 20, "price": 500},
            {"name": "Cleaning & Scaling", "description": "Routine cleaning.", "duration_minutes": 45, "price": 1500},
            {"name": "Root Canal", "description": "Root canal treatment.", "duration_minutes": 60, "price": 5000},
            {"name": "Tooth Extraction", "description": "Simple extraction.", "duration_minutes": 30, "price": 2000},
        ],
        "menu_categories": [],
        "knowledge": [
            {"title": "What are your timings?", "content": "Monday to Saturday 9 AM to 6 PM. Sunday closed. Emergency appointments are available by arrangement.", "kind": "faq"},
            {"title": "Do you accept insurance?", "content": "We accept most major dental insurance plans. Please bring your policy details to your appointment.", "kind": "faq"},
            {"title": "Is the treatment painful?", "content": "We use local anaesthesia for all procedures. Most patients experience little to no discomfort.", "kind": "faq"},
        ],
    },
    "gym": {
        "label": "Gym / Fitness",
        "services": [
            {"name": "Day Pass", "description": "Single-day access.", "duration_minutes": 120, "price": 300},
            {"name": "Personal Training", "description": "One-on-one session.", "duration_minutes": 60, "price": 1500},
            {"name": "Monthly Membership", "description": "Unlimited access for one month.", "duration_minutes": 60, "price": 2500},
        ],
        "menu_categories": [],
        "knowledge": [
            {"title": "What are your timings?", "content": "We are open Monday to Saturday 5 AM to 10 PM. Sunday 6 AM to 12 PM.", "kind": "faq"},
            {"title": "Do you have a trial?", "content": "Yes, we offer a free one-day trial. Please carry a valid ID and sports shoes.", "kind": "faq"},
        ],
    },
    "health": {
        "label": "Health / Clinic",
        "services": [
            {"name": "Doctor consultation", "description": "Consult with the doctor.", "duration_minutes": 20, "price": 500},
            {"name": "Follow-up consultation", "description": "Follow-up visit.", "duration_minutes": 15, "price": 300},
        ],
        "menu_categories": [],
        "knowledge": [
            {"title": "Do I need an appointment?", "content": "Appointments are recommended. Walk-ins are welcome subject to availability.", "kind": "faq"},
            {"title": "What should I bring?", "content": "Please bring a valid ID, any previous prescriptions, and your insurance card if applicable.", "kind": "faq"},
        ],
    },
    "wellness": {
        "label": "Wellness",
        "services": [
            {"name": "Consultation", "description": "Initial consultation.", "duration_minutes": 30, "price": 500},
            {"name": "Personalised plan", "description": "Customised wellness plan.", "duration_minutes": 45, "price": 1500},
        ],
        "menu_categories": [],
        "knowledge": [
            {"title": "How does the programme work?", "content": "We begin with a consultation, understand your goals, then design a personalised plan. Follow-ups track progress.", "kind": "faq"},
            {"title": "Do you offer online consultations?", "content": "Yes, online consultations are available on request.", "kind": "faq"},
        ],
    },
    "real-estate": {
        "label": "Real Estate",
        "services": [
            {"name": "Property enquiry", "description": "Discuss your property needs.", "duration_minutes": 30, "price": 0},
            {"name": "Site visit", "description": "Schedule a site visit.", "duration_minutes": 60, "price": 0},
        ],
        "menu_categories": [],
        "knowledge": [
            {"title": "How do I schedule a site visit?", "content": "Share your preferred date and time with us. Our team will confirm the visit within a few hours.", "kind": "faq"},
            {"title": "Do you handle rentals?", "content": "Yes, we handle both sales and rentals. Please specify your requirement when enquiring.", "kind": "faq"},
        ],
    },
    "education": {
        "label": "Education",
        "services": [
            {"name": "Course enquiry", "description": "Discuss course options.", "duration_minutes": 20, "price": 0},
            {"name": "Counselling session", "description": "One-on-one counselling.", "duration_minutes": 30, "price": 0},
        ],
        "menu_categories": [],
        "knowledge": [
            {"title": "How do I enrol?", "content": "Enquire through the customer PWA, then our counsellor will get in touch with the course details and fees.", "kind": "faq"},
            {"title": "Do you offer demo classes?", "content": "Yes. We offer one free demo class for most courses.", "kind": "faq"},
        ],
    },
}


# ---------------------------------------------------------------------------
# Seeding
# ---------------------------------------------------------------------------

def _already_seeded(db: Session, tenant_id: str) -> bool:
    """True if any Service or KnowledgeItem already exists for the tenant."""
    existing_service = db.scalar(select(Service.id).where(Service.tenant_id == tenant_id).limit(1))
    if existing_service:
        return True
    existing_knowledge = db.scalar(select(KnowledgeItem.id).where(KnowledgeItem.tenant_id == tenant_id).limit(1))
    if existing_knowledge:
        return True
    return False


def seed_industry_defaults(db: Session, tenant: Tenant, industry: str | None = None) -> dict:
    """Seed the tenant with starter data for its industry.

    Idempotent. Safe to call multiple times. Never raises.
    Returns a summary dict: {"seeded": bool, "industry": str, "services": n, "menu_items": n, "knowledge": n}
    """
    key = (industry or tenant.industry or "").strip().lower()
    if key not in INDUSTRIES:
        logger.info("seed_industry_defaults: no template for industry=%r, skipping", key)
        return {"seeded": False, "reason": "unknown_industry", "industry": key}

    summary = {"seeded": False, "industry": key, "services": 0, "menu_items": 0, "knowledge": 0}

    try:
        if _already_seeded(db, tenant.id):
            logger.info("seed_industry_defaults: tenant=%s already has data, skipping", tenant.id)
            return {"seeded": False, "reason": "already_seeded", "industry": key}

        spec = INDUSTRIES[key]

        # 1. Services
        for s in spec.get("services", []):
            row = Service(
                id=str(uuid.uuid4()),
                tenant_id=tenant.id,
                name=s["name"],
                description=s.get("description", ""),
                price=int(s.get("price", 0)),
                currency="INR",
                duration_minutes=int(s.get("duration_minutes", 30)),
                is_active=True,
            )
            db.add(row)
            summary["services"] += 1

        # 2. Menu categories + items
        for idx, cat in enumerate(spec.get("menu_categories", [])):
            cat_row = MenuCategory(
                id=str(uuid.uuid4()),
                tenant_id=tenant.id,
                name=cat["name"],
                sort_order=idx,
                is_active=True,
            )
            db.add(cat_row)
            db.flush()  # need category id
            for j, item in enumerate(cat.get("items", [])):
                item_row = MenuItem(
                    id=str(uuid.uuid4()),
                    tenant_id=tenant.id,
                    category_id=cat_row.id,
                    name=item["name"],
                    description=item.get("description", ""),
                    price=int(item.get("price", 0)),
                    currency="INR",
                    is_active=True,
                    is_available=True,
                    sort_order=j,
                )
                db.add(item_row)
                summary["menu_items"] += 1

        # 3. Knowledge items
        for k in spec.get("knowledge", []):
            row = KnowledgeItem(
                id=str(uuid.uuid4()),
                tenant_id=tenant.id,
                title=k["title"],
                content=k["content"],
                kind=k.get("kind", "faq"),
                language="en",
                source="industry_template",
                approval_status="system",
                is_active=True,
            )
            db.add(row)
            summary["knowledge"] += 1

        db.commit()
        summary["seeded"] = True
        logger.info("seed_industry_defaults: tenant=%s industry=%s %s", tenant.id, key, summary)
        return summary

    except Exception as exc:
        db.rollback()
        logger.exception("seed_industry_defaults failed for tenant=%s industry=%s: %s", tenant.id, key, exc)
        return {"seeded": False, "reason": "exception", "industry": key, "error": str(exc)}


def available_industries() -> list[dict]:
    """Return list of industry templates for API clients."""
    return [{"key": k, "label": v["label"]} for k, v in INDUSTRIES.items()]