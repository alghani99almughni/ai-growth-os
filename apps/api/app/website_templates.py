"""Industry website templates.

Replaces the single DEFAULT_WEBSITE_CONTENT with per-industry defaults.
The public site endpoint picks the template by tenant.industry, then
merges the tenant's own overrides on top.

Every field is optional; the renderer falls back gracefully.
"""
from __future__ import annotations


# Shared fallback when industry is unknown
_GENERIC = {
    "eyebrow": "",
    "hero_title": "Welcome.",
    "hero_emphasis": "We're here to help.",
    "hero_description": "Get in touch, book a service, or ask us anything — our AI assistant is available 24/7.",
    "about_title": "About us.",
    "about_text": "We're a local business focused on serving our community.",
    "whatsapp_number": "",
    "contact_heading": "Let's talk.",
    "contact_text": "Reach out by phone, WhatsApp, or start a call right from this page.",
    "quote": "",
    "hours_title": "Opening hours",
    "hours_text": "",
    "published": True,
    # Grid section
    "grid_eyebrow": "WHAT WE OFFER",
    "grid_title": "How we can help.",
    "grid_subtitle": "Explore the services we offer.",
    "grid_cards": [
        {"icon": "📞", "title": "Call us anytime", "body": "Our AI answers instantly, 24/7."},
        {"icon": "💬", "title": "Chat with us", "body": "Ask questions, get answers, book in seconds."},
        {"icon": "📅", "title": "Easy booking", "body": "Pick a time that suits you."},
        {"icon": "⭐", "title": "Real reviews", "body": "See what our customers say."},
    ],
    # Hero illustration
    "hero_emoji_primary": "⭐",
    "hero_emoji_secondary": "✨",
    "hero_badge_title": "Small steps.",
    "hero_badge_subtitle": "Real results.",
    # Trust badges
    "trust_badges": ["✓ Trusted locally", "✓ Fast response", "✓ Friendly team"],
    # Theme (used by frontend for color tuning)
    "theme": "generic",
}


_RESTAURANT = {
    **_GENERIC,
    "eyebrow": "FRESH · LOCAL · DELICIOUS",
    "hero_title": "Real food.",
    "hero_emphasis": "Made fresh daily.",
    "hero_description": "A neighbourhood kitchen serving honest food, cooked to order with quality ingredients.",
    "about_title": "Cooked with care, served with pride.",
    "about_text": "Every dish is prepared fresh when you order. Whether you're dining in or taking away, we want every meal to feel like home.",
    "contact_heading": "Hungry? Let's get you sorted.",
    "contact_text": "Browse our menu, place an order, or call us directly. Our AI can take your order in seconds.",
    "quote": "Good food is the foundation of genuine happiness.",
    "grid_eyebrow": "WHY US",
    "grid_title": "Freshly made, every time.",
    "grid_subtitle": "What makes us different.",
    "grid_cards": [
        {"icon": "🍽️", "title": "Fresh ingredients", "body": "Sourced daily, never frozen."},
        {"icon": "👨‍🍳", "title": "Made to order", "body": "Cooked the moment you order."},
        {"icon": "⚡", "title": "Fast service", "body": "Quick table service, quick takeaway."},
        {"icon": "📱", "title": "Order from your table", "body": "Scan, browse, order — no waiting."},
    ],
    "hero_emoji_primary": "🍽️",
    "hero_emoji_secondary": "🔥",
    "hero_badge_title": "Made fresh.",
    "hero_badge_subtitle": "Served hot.",
    "trust_badges": ["✓ Fresh daily", "✓ Family recipes", "✓ Local favourite"],
    "theme": "restaurant",
}


_WELLNESS = {
    **_GENERIC,
    "eyebrow": "HEALTH · BALANCE · WELLBEING",
    "hero_title": "Feel better.",
    "hero_emphasis": "Live consciously.",
    "hero_description": "Practical wellness for modern life, with an organic-focused approach to healthier everyday choices.",
    "about_title": "Health consciousness starts with what you do every day.",
    "about_text": "A local wellness brand focused on helping people make informed, sustainable lifestyle choices.",
    "contact_heading": "Your wellness journey can start with one conversation.",
    "contact_text": "Tell us what you are looking for and our team can guide you on the next step.",
    "quote": "Wellness is not about changing everything overnight. It is about making better choices, consistently.",
    "grid_eyebrow": "WELLNESS AT OUR STUDIO",
    "grid_title": "A simpler way to work on your wellbeing.",
    "grid_subtitle": "Explore the areas where we can support your journey.",
    "grid_cards": [
        {"icon": "🥗", "title": "Nutrition guidance", "body": "Understand everyday food choices and build practical routines."},
        {"icon": "🌱", "title": "Organic-focused living", "body": "Mindful ways to bring natural choices into daily life."},
        {"icon": "🧘", "title": "Healthy habits", "body": "Turn small, consistent decisions into lasting routines."},
        {"icon": "🤝", "title": "Personal support", "body": "Have a conversation about your needs and find your approach."},
    ],
    "hero_emoji_primary": "🥗",
    "hero_emoji_secondary": "🌿",
    "hero_badge_title": "Small choices.",
    "hero_badge_subtitle": "Better everyday habits.",
    "trust_badges": ["✓ Personal guidance", "✓ Everyday wellness", "✓ Organic-focused"],
    "theme": "wellness",
}


_DENTAL = {
    **_GENERIC,
    "eyebrow": "GENTLE DENTISTRY · MODERN CARE",
    "hero_title": "Healthy smiles.",
    "hero_emphasis": "For every age.",
    "hero_description": "Modern dentistry with a gentle touch. From routine checkups to cosmetic work, we treat every patient like family.",
    "about_title": "Dentistry that puts you at ease.",
    "about_text": "Our clinic combines modern equipment with a calm, patient-first approach. We explain every step and never rush.",
    "contact_heading": "Book your visit — it takes seconds.",
    "contact_text": "Our AI receptionist can check availability, schedule your appointment, and answer any questions you have.",
    "quote": "A healthy smile is a small daily habit that lasts a lifetime.",
    "grid_eyebrow": "OUR SERVICES",
    "grid_title": "Complete dental care.",
    "grid_subtitle": "From routine to restorative.",
    "grid_cards": [
        {"icon": "🦷", "title": "Checkups & cleaning", "body": "Routine exams to keep your smile healthy."},
        {"icon": "😁", "title": "Cosmetic dentistry", "body": "Whitening, veneers, and smile design."},
        {"icon": "🩺", "title": "Root canal therapy", "body": "Gentle treatment that saves your tooth."},
        {"icon": "🚨", "title": "Emergency care", "body": "Same-day slots when you need them most."},
    ],
    "hero_emoji_primary": "🦷",
    "hero_emoji_secondary": "✨",
    "hero_badge_title": "Gentle care.",
    "hero_badge_subtitle": "Modern technology.",
    "trust_badges": ["✓ Experienced team", "✓ Modern clinic", "✓ Same-day appointments"],
    "theme": "dental",
}


_SALON = {
    **_GENERIC,
    "eyebrow": "STYLE · CARE · CONFIDENCE",
    "hero_title": "Look sharp.",
    "hero_emphasis": "Feel great.",
    "hero_description": "A modern salon where skilled stylists help you look and feel your best — every visit.",
    "about_title": "Beauty that fits your life.",
    "about_text": "We take time to understand what works for you. No rushed appointments, no one-size-fits-all advice.",
    "contact_heading": "Book your next appointment.",
    "contact_text": "Choose a service, pick a time, and you're set. Our AI handles the details.",
    "quote": "Confidence starts with feeling comfortable in your own skin.",
    "grid_eyebrow": "OUR SERVICES",
    "grid_title": "Services for every look.",
    "grid_subtitle": "Browse what we offer.",
    "grid_cards": [
        {"icon": "✂️", "title": "Haircuts & styling", "body": "Precision cuts, blow-dries, and event styling."},
        {"icon": "🎨", "title": "Colour & highlights", "body": "Balayage, ombre, and full colour work."},
        {"icon": "💆", "title": "Treatments", "body": "Deep conditioning and scalp care."},
        {"icon": "💅", "title": "Nails & beauty", "body": "Manicures, pedicures, and add-ons."},
    ],
    "hero_emoji_primary": "💇",
    "hero_emoji_secondary": "✨",
    "hero_badge_title": "Your style.",
    "hero_badge_subtitle": "Our craft.",
    "trust_badges": ["✓ Expert stylists", "✓ Premium products", "✓ Easy booking"],
    "theme": "salon",
}


_HOTEL = {
    **_GENERIC,
    "eyebrow": "REST · COMFORT · HOSPITALITY",
    "hero_title": "Welcome home.",
    "hero_emphasis": "Away from home.",
    "hero_description": "Thoughtfully designed rooms, attentive service, and everything you need for a restful stay.",
    "about_title": "Hospitality done right.",
    "about_text": "From the moment you arrive, we want you to feel looked after. Our team is available around the clock.",
    "contact_heading": "Ready to book your stay?",
    "contact_text": "Check availability, request a room, or ask any question. Our AI is available 24/7.",
    "quote": "The best journeys start with a warm welcome.",
    "grid_eyebrow": "THE STAY",
    "grid_title": "Everything for a comfortable stay.",
    "grid_subtitle": "From check-in to checkout.",
    "grid_cards": [
        {"icon": "🛏️", "title": "Comfortable rooms", "body": "Fresh linen, quiet spaces, and quality bedding."},
        {"icon": "🍽️", "title": "Room service", "body": "Order food and drinks to your room."},
        {"icon": "🧺", "title": "Housekeeping", "body": "Daily service and fresh towels."},
        {"icon": "🎯", "title": "Local guidance", "body": "Recommendations for dining and activities."},
    ],
    "hero_emoji_primary": "🏨",
    "hero_emoji_secondary": "🌙",
    "hero_badge_title": "Rest easy.",
    "hero_badge_subtitle": "We handle the rest.",
    "trust_badges": ["✓ 24/7 front desk", "✓ Central location", "✓ Trusted hospitality"],
    "theme": "hotel",
}


_RETAIL = {
    **_GENERIC,
    "eyebrow": "QUALITY · VARIETY · SERVICE",
    "hero_title": "Shop smart.",
    "hero_emphasis": "Find what you need.",
    "hero_description": "A curated selection of products with helpful staff who know their stock inside and out.",
    "about_title": "Products worth buying.",
    "about_text": "We stock items we'd use ourselves. If we don't have it, we'll help you find it.",
    "contact_heading": "Need help finding something?",
    "contact_text": "Ask our AI assistant — it knows our catalogue and can point you in the right direction.",
    "quote": "Good products speak for themselves. Great service is why you come back.",
    "grid_eyebrow": "BROWSE",
    "grid_title": "Our current range.",
    "grid_subtitle": "Selected with care.",
    "grid_cards": [
        {"icon": "🛍️", "title": "Wide selection", "body": "Curated products for every need."},
        {"icon": "💳", "title": "Easy payment", "body": "Cash, card, UPI — your choice."},
        {"icon": "🚚", "title": "Local delivery", "body": "Same-day in selected areas."},
        {"icon": "🎁", "title": "Loyalty rewards", "body": "Earn points on every purchase."},
    ],
    "hero_emoji_primary": "🛍️",
    "hero_emoji_secondary": "💫",
    "hero_badge_title": "Quality picks.",
    "hero_badge_subtitle": "Fair prices.",
    "trust_badges": ["✓ Curated range", "✓ Fair prices", "✓ Loyalty rewards"],
    "theme": "retail",
}


TEMPLATES = {
    "restaurant": _RESTAURANT,
    "cafe": _RESTAURANT,
    "food": _RESTAURANT,
    "hospitality": _HOTEL,
    "hotel": _HOTEL,
    "wellness": _WELLNESS,
    "health": _WELLNESS,
    "nutrition": _WELLNESS,
    "dental": _DENTAL,
    "clinic": _DENTAL,
    "doctor": _DENTAL,
    "salon": _SALON,
    "spa": _SALON,
    "beauty": _SALON,
    "retail": _RETAIL,
    "shop": _RETAIL,
    "store": _RETAIL,
}


def get_template(industry: str) -> dict:
    """Return the template for an industry, falling back to generic."""
    if not industry:
        return dict(_GENERIC)
    key = industry.lower().replace("_", "-").strip()
    return dict(TEMPLATES.get(key, _GENERIC))


def merge_with_tenant(template: dict, tenant_content: dict) -> dict:
    """Merge tenant overrides on top of the template. Tenant wins."""
    merged = dict(template)
    if tenant_content:
        merged.update({k: v for k, v in tenant_content.items() if v not in (None, "")})
    return merged


def list_industries() -> list:
    """Return unique industry keys."""
    return sorted(set(TEMPLATES.keys()))