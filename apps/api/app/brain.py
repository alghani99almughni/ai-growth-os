import httpx
import re
import json
from sqlalchemy import select
from sqlalchemy.orm import Session
from .models import Tenant, Service, Product
from .models_growth import KnowledgeItem,KnowledgeCandidate,TenantSetting,BusinessHour
from .models_ai import Conversation, ConversationMessage
from .config import settings
from .ai_router import detect_language, faq_match, structured_match, knowledge_match
from .ai_provider_pool import last_resort_reply
from .semantic_knowledge import semantic_match
from .tenant_policy import tenant_policy, capability_enabled, policy_context

def knowledge_context(db: Session, tenant_id: str) -> str:
    tenant=db.get(Tenant,tenant_id)
    services=db.scalars(select(Service).where(Service.tenant_id==tenant_id,Service.is_active==True)).all()
    products=db.scalars(select(Product).where(Product.tenant_id==tenant_id,Product.is_active==True)).all()
    knowledge=db.scalars(select(KnowledgeItem).where(KnowledgeItem.tenant_id==tenant_id,KnowledgeItem.is_active==True,KnowledgeItem.approval_status.in_(["approved","system"]))).all()
    policy=tenant_policy(db,tenant_id)
    feature_text=json.dumps(policy.get("features",{}),ensure_ascii=False)
    business_brain=policy.get("business_brain",{})
    website=policy.get("website",{})
    lines=[f"Business: {tenant.name}",f"Industry: {tenant.industry}",f"Description: {tenant.description or ''}",f"Phone: {tenant.phone or ''}",f"WhatsApp: {tenant.whatsapp_number or ''}",f"Address: {tenant.address or ''}",f"Enabled customer features: {feature_text}"]
    if business_brain.get("instructions"): lines.append(f"Tenant admin instructions: {business_brain['instructions']}")
    if website.get("published",True): lines.append("Tenant-approved website content: " + json.dumps(website,ensure_ascii=False))
    for x in knowledge: lines.append(f"Knowledge ({x.kind}): {x.title}: {x.content}")
    for x in services: lines.append(f"Service ID: {x.id}; name={x.name}; description={x.description or ''}; price={x.price} {x.currency}; duration={x.duration_minutes or ''} minutes")
    for x in products: lines.append(f"Product: {x.name}; description={x.description or ''}; price={x.price} {x.currency}; stock={x.stock_quantity if x.stock_quantity is not None else 'unknown'}")
    return "\n".join(lines)

def local_intent(message:str)->str:
    m=message.casefold()
    compact=re.sub(r"[^a-z0-9\s]"," ",m)
    compact=re.sub(r"\s+"," ",compact).strip()
    booking_terms=("book","booking","appointment","schedule","reserve","reservation","अपॉइंटमेंट","బుకింగ్")
    if any(x in compact for x in booking_terms):
        return "booking"
    if any(x in compact for x in ("bhukamp","bukamp","buking","boking","bok an")) and any(
        x in compact for x in ("today","tomorrow","time","slot","appointment","schedule","for")
    ):
        return "booking"
    if any(x in compact for x in ["hour","hours","hourly","timing","timings","time","open","closed","opening","closing","when are you open","what time","कितने बजे","समय","సమయాలు","ఎప్పుడు","நேரம்","எப்போது"]): return "business_hours"
    if any(x in m for x in ["price","cost","fee","rate","how much","कीमत","ధర","விலை"]): return "pricing"
    if any(x in m for x in ["buy","order","product","stock","available","उत्पाद","ఆర్డర్"]): return "product"
    if any(x in m for x in ["call me","human","person","staff","agent","इंसान","వ్యక్తి"]): return "human_handoff"
    return "information"

def business_hours_reply(db: Session, tenant_id: str, message: str, language: str) -> str|None:
    if local_intent(message) != "business_hours":
        return None

    # Business-hours questions are a zero-model-token path. Repair only missing
    # weekday rows using the platform defaults; never overwrite configured hours.
    rows=db.scalars(select(BusinessHour).where(BusinessHour.tenant_id==tenant_id).order_by(BusinessHour.weekday)).all()
    existing={row.weekday: row for row in rows}
    if len(existing) < 7:
        from datetime import time as _time
        for weekday in range(7):
            if weekday in existing:
                continue
            if weekday < 5:
                opening, closing, closed = _time(9,0), _time(18,0), False
            elif weekday == 5:
                opening, closing, closed = _time(9,0), _time(14,0), False
            else:
                opening, closing, closed = _time(9,0), _time(18,0), True
            db.add(BusinessHour(tenant_id=tenant_id, weekday=weekday, open_time=opening,
                                close_time=closing, is_closed=closed, slot_interval_minutes=30))
        db.flush()
        rows=db.scalars(select(BusinessHour).where(BusinessHour.tenant_id==tenant_id).order_by(BusinessHour.weekday)).all()
    if not rows:
        return None
    names=["Monday","Tuesday","Wednesday","Thursday","Friday","Saturday","Sunday"]
    open_days=[r for r in rows if not r.is_closed]
    if len(open_days)==6:
        weekday_rows=sorted(open_days,key=lambda r:r.weekday)
        first=weekday_rows[0]
        same_hours=all(r.open_time==first.open_time and r.close_time==first.close_time for r in weekday_rows)
        if same_hours and {r.weekday for r in weekday_rows}==set(range(6)):
            opening=first.open_time.strftime('%I:%M %p').lstrip('0')
            closing=first.close_time.strftime('%I:%M %p').lstrip('0')
            return f"We're open Monday to Saturday, {opening} to {closing}. Sunday we're closed. Would you like to book an appointment? If so, what day and time would you prefer?"
    parts=[]
    for row in rows:
        label=names[row.weekday] if 0 <= row.weekday < len(names) else str(row.weekday)
        parts.append(f"{label}: closed" if row.is_closed else f"{label}: {row.open_time.strftime('%I:%M %p')}–{row.close_time.strftime('%I:%M %p')}")
    return "We're open " + "; ".join(parts) + ". Would you like to book an appointment? If so, what day and time would you prefer?"

def conversation(db: Session, tenant_id: str, message: str, language: str, channel: str, conversation_id: str|None):
    c=db.get(Conversation,conversation_id) if conversation_id else None
    if not c or c.tenant_id != tenant_id:
        c=Conversation(tenant_id=tenant_id,channel=channel,language=language)
        db.add(c); db.flush()
    c.language=language; c.last_user_message=message; c.turns=(c.turns or 0)+1
    return c


_WEEKDAYS = ("monday","tuesday","wednesday","thursday","friday","saturday","sunday")
_WEEKDAY_ALIASES = {
    "mon":"monday","tue":"tuesday","tues":"tuesday","wed":"wednesday",
    "thu":"thursday","thur":"thursday","thurs":"thursday","fri":"friday",
    "sat":"saturday","sun":"sunday",
}


def extract_booking_entities(text: str) -> dict:
    """Extract every booking entity present in a turn.

    This deliberately extracts day and time independently. A caller is never
    forced into a one-slot-per-turn flow: "book Thursday at 12" yields both
    entities in the same turn.
    """
    value = text.casefold().strip()
    day = None
    for alias, canonical in sorted(_WEEKDAY_ALIASES.items(), key=lambda x: -len(x[0])):
        if re.search(rf"\b{re.escape(alias)}\\b", value):
            day = canonical
            break
    if day is None:
        for canonical in _WEEKDAYS:
            if re.search(rf"\b{canonical}\\b", value):
                day = canonical
                break

    if "day after tomorrow" in value:
        relative_day = "day_after_tomorrow"
    elif "tomorrow" in value:
        relative_day = "tomorrow"
    elif "today" in value:
        relative_day = "today"
    else:
        relative_day = None

    # Accept spoken/typed AM/PM forms. Noon is unambiguous.
    if re.search(r"\bnoon\\b", value):
        time_value = "12 PM"
    else:
        tm = re.search(
            r"\b(1[0-2]|0?[1-9])(?::([0-5]\\d))?\\s*(a\\.?m\\.?|p\\.?m\\.?)\\b",
            value,
        )
        if tm:
            hour = int(tm.group(1))
            minute = tm.group(2)
            meridiem = "AM" if tm.group(3).replace(".", "").startswith("a") else "PM"
            time_value = f"{hour}:{minute} {meridiem}" if minute else f"{hour} {meridiem}"
        else:
            # 24-hour clock, e.g. "Thursday at 17:00".
            tm24 = re.search(r"\b([01]?\\d|2[0-3]):([0-5]\\d)\\b", value)
            if tm24:
                hour24 = int(tm24.group(1))
                minute24 = tm24.group(2)
                meridiem = "AM" if hour24 < 12 else "PM"
                hour12 = hour24 % 12 or 12
                time_value = f"{hour12}:{minute24} {meridiem}"
            else:
                time_value = None

    return {
        "day": day,
        "relative_day": relative_day,
        "time": time_value,
    }


def previous_booking_context(db: Session, conversation_id: str, current_message: str) -> dict:
    """Recover booking entities from the active conversation without adding
    another schema dependency.

    We only inherit old values while the conversation is already in a booking
    state. This prevents an unrelated earlier time (for example business
    hours) from accidentally becoming an appointment time.
    """
    rows = db.scalars(
        select(ConversationMessage)
        .where(ConversationMessage.conversation_id == conversation_id)
        .order_by(ConversationMessage.created_at.desc())
        .limit(12)
    ).all()
    ctx = {"day": None, "relative_day": None, "time": None}
    for row in reversed(rows):
        if row.role != "user":
            continue
        extracted = extract_booking_entities(row.content)
        for key in ("day", "relative_day", "time"):
            if extracted.get(key):
                ctx[key] = extracted[key]
    return ctx


def booking_reply_from_state(db: Session, c: Conversation, message: str) -> tuple[str|None, dict]:
    """Resolve a booking turn by merging current entities with prior booking
    context. Never discard a useful entity just because the current state asks
    for a different one.
    """
    current = extract_booking_entities(message)
    prior = previous_booking_context(db, c.id, message) if c.state.startswith("booking") else {
        "day": None, "relative_day": None, "time": None
    }

    # Current turn always wins over previous values.
    day = current["day"] or prior["day"]
    relative_day = current["relative_day"] or prior["relative_day"]
    time_value = current["time"] or prior["time"]

    if relative_day and not current["day"]:
        day_label = relative_day.replace("_", " ")
    else:
        day_label = day

    if day_label and time_value:
        c.state = "booking_confirmation"
        return (
            f"Great. I have {day_label} at {time_value}. Shall I confirm that appointment?",
            {"day": day_label, "time": time_value, "complete": True},
        )

    if day_label:
        c.state = "booking_day"
        return f"Sure. What time would you prefer on {day_label}?", {
            "day": day_label, "time": None, "complete": False
        }

    if time_value:
        c.state = "booking_day"
        return "Sure. What day would you prefer for the appointment?", {
            "day": None, "time": time_value, "complete": False
        }

    c.state = "booking_day"
    return "Sure. Which day and time would you prefer?", {
        "day": None, "time": None, "complete": False
    }


async def generate_reply(db:Session,tenant_id:str,message:str,conversation_id:str|None=None,channel:str="pwa")->dict:
    tenant=db.get(Tenant,tenant_id)
    if not tenant: raise ValueError("Tenant not found")
    language=detect_language(message)
    intent=local_intent(message)
    c=conversation(db,tenant_id,message,language,channel,conversation_id)
    db.add(ConversationMessage(conversation_id=c.id,role="user",content=message,language=language,intent=intent))
    
    # Library-first policy: these paths consume zero model tokens.
    hours=business_hours_reply(db,tenant_id,message,language)
    booking=None
    policy=tenant_policy(db,tenant_id)
    m=message.casefold()
    # Keep short conversational turns deterministic: greetings should never
    # fall through to the model/handoff path.
    greeting_words={"hello","hi","hey","hiya","good morning","good afternoon","good evening","namaste"}
    if any(re.fullmatch(r"\s*"+re.escape(g)+r"\s*[.!?]*\\s*",m) for g in greeting_words):
        booking="Hello! How can I help you today?"
    elif intent=="booking" and not capability_enabled(policy,"bookings",True):
        booking="Appointments are not enabled for this business right now. I can help with another question or arrange a message for the team."
    elif intent=="booking":
        # Extract ALL booking entities from the current turn. If the caller
        # says "book Thursday at 12", both values survive in the same turn.
        booking, booking_data = booking_reply_from_state(db, c, message)
    elif c.state.startswith("booking"):
        # A follow-up may contain only the missing entity, or may contain both
        # entities again. Always merge it with the active booking context.
        booking, booking_data = booking_reply_from_state(db, c, message)
    else:
        booking_data = {"day": None, "time": None, "complete": False}

    direct=hours or booking or structured_match(db,tenant_id,message)
    semantic=await semantic_match(db,tenant_id,message,language) if not direct else None
    library=semantic["content"] if semantic else (knowledge_match(db,tenant_id,message) if not direct else None)
    faq=faq_match(db,tenant.industry,message,language) if not direct and not library else None
    knowledge_hit = False
    handoff_required = False
    retrieval_stage="structured"
    if direct:
        reply=direct; provider="deterministic"
        knowledge_hit=True; retrieval_stage="structured"
    elif semantic:
        reply=semantic["content"]; provider="semantic_library"
        knowledge_hit=True; retrieval_stage="semantic"
    elif library:
        reply=library; provider="tenant_library"
        knowledge_hit=True; retrieval_stage="lexical_library"
    elif faq:
        reply=faq.answer; provider="global_faq"
        knowledge_hit=True; retrieval_stage="global_faq"
    else:
        context=knowledge_context(db,tenant_id)
        history_rows=db.scalars(
            select(ConversationMessage)
            .where(ConversationMessage.conversation_id==c.id)
            .order_by(ConversationMessage.created_at.desc())
            .limit(8)
        ).all()
        history="\n".join(f"{row.role.upper()}: {row.content}" for row in reversed(history_rows))
        prompt=(
            "You are the AI customer engagement agent. Reply in the customer's language when possible. "
            "Use ONLY the approved business context below. Never invent prices, availability, policies, discounts, bookings or payment success. "
            "If an action is needed, say it will be confirmed by the system. Keep concise and conversational. "
            "Do not ask for information already provided in this conversation. "
            "If the approved context does not contain enough information, say you need a human team member to follow up instead of guessing.\n\n"
            "APPROVED CONTEXT:\n" + context +
            "\n\nRECENT CONVERSATION:\n" + history +
            "\n\nCUSTOMER LANGUAGE: " + language +
            "\nCUSTOMER:\n" + message
        )
        reply,provider=await last_resort_reply(db,tenant_id,prompt)
        retrieval_stage="generation"
        if not reply or any(x in (reply or "").casefold() for x in ("i don't have enough information","i need a human","human team","call you back","team member to follow up","i cannot verify")):
            handoff_required=True
            reply="I don't want to give you an unverified answer. I'll arrange for our team to call you back."
            provider="none"
        else:
            now=__import__("datetime").datetime.utcnow()
            candidate=db.scalar(select(KnowledgeCandidate).where(
                KnowledgeCandidate.tenant_id==tenant_id,
                KnowledgeCandidate.question==message,
                KnowledgeCandidate.language==language,
                KnowledgeCandidate.status.in_(["pending","approved"])
            ))
            if candidate:
                candidate.times_asked=(candidate.times_asked or 0)+1
                candidate.last_asked_at=now
                if candidate.status=="pending":
                    candidate.answer=reply
            else:
                db.add(KnowledgeCandidate(
                    tenant_id=tenant_id,question=message,answer=reply,language=language,
                    intent=intent,status="pending",source=channel,provider=provider,
                    times_asked=1,first_asked_at=now,last_asked_at=now
                ))
    if knowledge_hit and library:
        matched=db.scalar(select(KnowledgeItem).where(
            KnowledgeItem.tenant_id==tenant_id,KnowledgeItem.is_active==True,
            KnowledgeItem.content==library
        ))
        if matched:
            matched.usage_count=(matched.usage_count or 0)+1
            matched.last_used_at=__import__("datetime").datetime.utcnow()
    c.intent=intent; c.last_assistant_message=reply; c.updated_at=__import__("datetime").datetime.utcnow()
    db.add(ConversationMessage(conversation_id=c.id,role="assistant",content=reply,language=language,intent=intent))
    db.commit()
    return {"reply":reply,"intent":intent,"provider":provider,"language":language,"conversation_id":c.id,"knowledge_hit":knowledge_hit,"handoff_required":handoff_required,"generation_used":not knowledge_hit,"retrieval_stage":retrieval_stage,"booking":booking_data}
