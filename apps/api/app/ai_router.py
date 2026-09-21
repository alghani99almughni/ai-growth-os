import re
from difflib import SequenceMatcher
from sqlalchemy import select
from sqlalchemy.orm import Session
from .models_ai import GlobalFaq
from .models import Tenant, Service, Product

LANGUAGE_PATTERNS = {
    "en": r"[a-z]",
    "hi": r"[\u0900-\u097f]",
    "te": r"[\u0c00-\u0c7f]",
    "ta": r"[\u0b80-\u0bff]",
    "kn": r"[\u0c80-\u0cff]",
    "ml": r"[\u0d00-\u0d7f]",
    "mr": r"[\u0900-\u097f]",
    "bn": r"[\u0980-\u09ff]",
    "gu": r"[\u0a80-\u0aff]",
    "pa": r"[\u0a00-\u0a7f]",
    "or": r"[\u0b00-\u0b7f]",
    "as": r"[\u0980-\u09ff]",
    "ur": r"[\u0600-\u06ff]",
}

def detect_language(text: str) -> str:
    scores = {k: len(re.findall(p, text)) for k,p in LANGUAGE_PATTERNS.items()}
    if max(scores.values(), default=0) == 0:
        return "en"
    winner=max(scores, key=scores.get)
    # Hindi/Marathi share script; Marathi marker words improve routing.
    if winner=="hi" and re.search(r"\b(आहे|मला|काय|कुठे)\b", text): return "mr"
    if winner=="bn" and re.search(r"[অআইঈউএও]", text): return "bn"
    return winner

def normalize(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]{2,}", text.lower()))

def faq_match(db: Session, industry: str, message: str, language: str) -> GlobalFaq | None:
    rows=db.scalars(select(GlobalFaq).where(GlobalFaq.is_active==True, GlobalFaq.language.in_([language,"en"]), GlobalFaq.industry.in_([industry,"general"]))).all()
    incoming=normalize(message)
    best=None; best_score=0.0
    for row in rows:
        tokens=normalize(row.question+" "+row.keywords)
        overlap=len(incoming & tokens) / max(1,len(incoming))
        similarity=SequenceMatcher(None, message.lower(), row.question.lower()).ratio()
        score=max(overlap, similarity*0.8)
        if score>best_score:
            best_score=score; best=row
    return best if best_score >= 0.55 else None

def structured_match(db: Session, tenant_id: str, message: str) -> str | None:
    m=message.lower()
    if any(x in m for x in ("price","cost","fee","rate","how much","कीमत","ధర","விலை")):
        services=db.scalars(select(Service).where(Service.tenant_id==tenant_id,Service.is_active==True)).all()
        if services:
            return "Here are the currently configured services and prices: " + "; ".join(f"{s.name}: {s.price} {s.currency}" for s in services if s.price is not None)
    if any(x in m for x in ("product","buy","order","stock","available","उत्पाद","ధర")):
        products=db.scalars(select(Product).where(Product.tenant_id==tenant_id,Product.is_active==True)).all()
        if products:
            return "Here are the currently configured products: " + "; ".join(f"{p.name}: {p.price} {p.currency}" for p in products if p.price is not None)
    return None
