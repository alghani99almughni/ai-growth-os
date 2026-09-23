import httpx
import re
from sqlalchemy import select
from sqlalchemy.orm import Session
from .models import Tenant, Service, Product
from .models_growth import KnowledgeItem,KnowledgeCandidate,TenantSetting,BusinessHour
from .models_ai import Conversation, ConversationMessage
from .config import settings
from .ai_router import detect_language, faq_match, structured_match, knowledge_match
from .ai_provider_pool import last_resort_reply
from .semantic_knowledge import semantic_match

def knowledge_context(db: Session, tenant_id: str) -> str:
    tenant=db.get(Tenant,tenant_id)
    services=db.scalars(select(Service).where(Service.tenant_id==tenant_id,Service.is_active==True)).all()
    products=db.scalars(select(Product).where(Product.tenant_id==tenant_id,Product.is_active==True)).all()
    knowledge=db.scalars(select(KnowledgeItem).where(KnowledgeItem.tenant_id==tenant_id,KnowledgeItem.is_active==True,KnowledgeItem.approval_status.in_(["approved","system"]))).all()
    feature_row=db.scalar(select(TenantSetting).where(TenantSetting.tenant_id==tenant_id,TenantSetting.key=="features"))
    feature_text=feature_row.value_json if feature_row else "{}"
    lines=[f"Business: {tenant.name}",f"Industry: {tenant.industry}",f"Description: {tenant.description or ''}",f"Phone: {tenant.phone or ''}",f"WhatsApp: {tenant.whatsapp_number or ''}",f"Address: {tenant.address or ''}",f"Enabled customer features: {feature_text}"]
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
    if intent=="booking":
        m=message.casefold()
        # Keep appointment conversations stateful without putting provider-specific
        # memory in the model. Conversation.state is our durable workflow state.
        if "today" in m or "today's" in m:
            c.state="booking_time_today"
            booking="Absolutely. I can help with an appointment for today. What time would you prefer?"
        elif "tomorrow" in m:
            c.state="booking_time_tomorrow"
            booking="Absolutely. I can help with an appointment for tomorrow. What time would you prefer?"
        else:
            c.state="booking_day"
            booking="Sure, I can help with an appointment. What day and time would you prefer?"
    elif c.state in ("booking_day","booking_time_today","booking_time_tomorrow","booking_service","booking_confirmation"):
        # Do not abandon an active booking workflow just because speech
        # recognition produced a short or imperfect next turn.
        text=m if 'm' in locals() else message.casefold()
        time_match=re.search(r"\b(1[0-2]|0?[1-9])(?::([0-5]\d))?\s*(am|pm)\b",text)
        if c.state in ("booking_time_today","booking_time_tomorrow") and time_match:
            requested_day="today" if c.state=="booking_time_today" else "tomorrow"
            c.state="booking_confirmation"
            booking=f"Great. I have {requested_day} at {time_match.group(1)}{(':'+time_match.group(2)) if time_match.group(2) else ''} {time_match.group(3).upper()}. Shall I confirm that appointment?"
        elif c.state=="booking_day":
            if "today" in text:
                c.state="booking_time_today"; booking="Absolutely. What time would you prefer today?"
            elif "tomorrow" in text:
                c.state="booking_time_tomorrow"; booking="Absolutely. What time would you prefer tomorrow?"
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
    return {"reply":reply,"intent":intent,"provider":provider,"language":language,"conversation_id":c.id,"knowledge_hit":knowledge_hit,"handoff_required":handoff_required,"generation_used":not knowledge_hit,"retrieval_stage":retrieval_stage}
