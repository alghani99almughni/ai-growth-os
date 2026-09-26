import httpx
import re
import logging
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
from .voice_language_patterns import language_request, relative_day_from_text, needs_voice_clarification, SPOKEN_CLARIFICATION, LANGUAGE_SWITCH_CONFIRMATIONS, BUSINESS_HOURS_SIMPLE, AVAILABILITY_PROMPTS, DOCTOR_DETAILS_MISSING, is_explicit_confirmation, language_switch_confirmation, voice_feedback_reply

logger = logging.getLogger(__name__)

def agent_gender(db: Session, tenant_id: str) -> str:
    row=db.scalar(select(TenantSetting).where(TenantSetting.tenant_id==tenant_id,TenantSetting.key=="agent_voice"))
    if row:
        try:
            value=json.loads(row.value_json)
            value=value.get("gender") if isinstance(value,dict) else value
            if str(value).lower() in ("male","female"):
                return str(value).lower()
        except Exception:
            pass
    return "female"


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

    booking_terms=("book","booking","appointment","schedule","reserve","reservation")
    if any(x in compact for x in booking_terms):
        return "booking"
    # Native-script booking phrases must enter the deterministic booking router
    # before the generic knowledge/fallback path. Keep these terms specific so
    # ordinary hours/questions are not accidentally classified as bookings.
    native_booking_terms=(
        "अपॉइंटमेंट","अपॉइंट","बुकिंग","बुक","रिजर्व","आरक्षण","स्लॉट",
        "అపాయింట్మెంట్","అపాయింట్","బుకింగ్","బుక్","రిజర్వ్","స్లాట్",
        "அப்பாயிண்ட்மென்ட்","அப்பாயிண்ட்மெண்ட்","புக்கிங்","புக்","முன்பதிவு","ஸ்லாட்",
        "ಅಪಾಯಿಂಟ್ಮೆಂಟ್","ಅಪಾಯಿಂಟ್","ಬುಕಿಂಗ್","ಬುಕ್","ಮೀಸಲಾತಿ","ಸ್ಲಾಟ್",
        "അപ്പോയിന്റ്മെന്റ്","അപ്പോയിന്റ്","ബുക്കിംഗ്","ബുക്ക്","റിസർവ്","സ്ലോട്ട്",
        "अपॉइंटमेंट","बुकिंग","बुक","आरक्षण","रिजर्वेशन",
        "অ্যাপয়েন্টমেন্ট","বুকিং","বুক","রিজার্ভ","স্লট",
        "અપોઇન્ટમેન્ટ","બુકિંગ","બુક","રિઝર્વ","સ્લોટ",
        "ਅਪਾਇੰਟਮੈਂਟ","ਬੁਕਿੰਗ","ਬੁੱਕ","ਰਿਜ਼ਰਵ","ਸਲਾਟ",
        "اپائنٹمنٹ","بکنگ","بک","ریزرو","سلاٹ",
    )
    if any(x in m for x in native_booking_terms):
        return "booking"
    if any(x in compact for x in ("bhukamp","bukamp","buking","boking","bok an")) and any(
        x in compact for x in ("today","tomorrow","kal","repu","naale","time","slot","appointment","schedule","for")
    ):
        return "booking"

    if language_request(message):
        return "language_request"
    if any(x in compact for x in ("bye","goodbye","thank you","thanks","you re welcome","you are welcome","that s all","thats all","leave it","cancel")) or "that's all" in m:
        return "closing"

    if any(x in compact for x in (
        "gender change","voice changed","voice change","voice has changed",
        "awaaz badal","awaz badal","gender badal","voice badal"
    )) or any(x in m for x in ("जेंडर चेंज","आवाज़ बदल","आवाज बदल","ವಾಯ್ಸ್ ಬದಲಾಗಿದೆ","వాయిస్ మారింది")):
        return "voice_feedback"
    if any(x in compact for x in ("call me","human","person","staff","agent","let me speak","speak to someone","talk to someone","connect me")) or any(x in m for x in ("इंसान","व्यक्ति","వ్యక్తి","நபர்","ವ್ಯಕ್ತಿ","వ్యక్తితో")):
        return "human_handoff"

    if (any(x in compact for x in (
        "which doctor","who is the doctor","may i know the doctor","doctor name","doctor's name",
        "provider","physician","doctor peru","doctor hesaru","doctorinte peru","doctoranche naav"
    )) or any(x in m for x in (
        "डॉक्टर का नाम","डॉक्टर कौन","డాక్టర్ పేరు","மருத்துவர் பெயர்","ಡಾಕ್ಟರ್ ಹೆಸರು","ഡോക്ടറിന്റെ പേര്",
        "डॉक्टरांचं नाव","ডাক্তারের নাম","ડોક્ટરનું નામ","ਡਾਕਟਰ ਦਾ ਨਾਮ","ڈاکٹر کا نام"
    ))) and not any(x in compact for x in ("available","availability","slot","appointment")):
        return "doctor_information"

    if any(x in compact for x in (
        "available","availability","is there a slot","is there any slot","can i get a slot",
        "check availability","free time","free slot","any appointment available","are there slots",
        "doctor available","doctor is available","doctor free"
    )):
        return "availability"

    if any(x in m for x in ("price","cost","fee","rate","how much","what do you charge","कीमत","ధర","விலை","ಬೆಲೆ","വില","किती","দাম","કેટલો","ਕਿੰਨਾ")):
        return "pricing"

    if any(x in compact for x in (
        "hour","hours","hourly","timing","timings","time","open","closed","opening","closing",
        "when are you open","what time","when do you start","when do you finish",
        "start in the morning","finish for the day","timings enta","timings enna",
        "timings enu","timings entha","timings kay","timings ki","timings shu","timings ne"
    )) or any(x in m for x in (
        "कितने बजे","समय","समय क्या","సమయాలు","ఎప్పుడు","நேரம்","எப்போது","ಸಮಯ","ಯಾವಾಗ",
        "സമയം","എപ്പോൾ","वेळ","কখন","સમય","ਕਦੋਂ","اوقات"
    )) or re.search(r"\b(man of|man off|manoj)\s+(the\s+)?timings?\b", compact):
        return "business_hours"

    if any(x in m for x in (
        "what day is tomorrow","which day is tomorrow","what day tomorrow","tomorrow which day",
        "what day is day after tomorrow","tomorrow kaun sa din","kal kaun sa din",
        "cal kaun sa din","kal konsa din","kal kaunsa din","cal konsa din","कल कौन सा दिन",
        "कल कौन सा दिन है","repu ye roju","naalai enna kizhamai","naale yaava dina",
        "naale ethu divasam","udya konta vaar","kal kon din","kaale kayo vaar","kal kehra din"
    )) or ("kaun sa din" in m or "kaunsa din" in m or "konsa din" in m):
        return "date_information"

    if any(x in m for x in ("buy","purchase","order","product","stock","available","उत्पाद","ఆర్డర్","பொருள்","ಉತ್ಪನ್ನ","ഉൽപ്പന്നം","उत्पादन","পণ্য","ઉત્પાદન","ਉਤਪਾਦ")):
        return "product"

    if needs_voice_clarification(message):
        return "clarification"

    return "information"

def business_hours_reply(db: Session, tenant_id: str, message: str, language: str) -> str|None:
    if local_intent(message) != "business_hours":
        return None

    # Business-hours questions are a zero-model-token path. Repair only missing
    # weekday rows using the platform defaults; never overwrite configured hours.
    rows=db.scalars(select(BusinessHour).where(BusinessHour.tenant_id==tenant_id).order_by(BusinessHour.weekday)).all()
    existing={row.weekday: row for row in rows}
    if len(existing)==7 and all(not existing[d].is_closed and existing[d].open_time.strftime("%H:%M")=="09:00" and existing[d].close_time.strftime("%H:%M")=="18:00" for d in range(5)) and not existing[5].is_closed and existing[5].open_time.strftime("%H:%M")=="09:00" and existing[5].close_time.strftime("%H:%M")=="14:00" and existing[6].is_closed:
        existing[5].close_time=__import__("datetime").time(18,0)
        db.commit()
        rows=list(existing.values())
    if len(existing) < 7:
        from datetime import time as _time
        for weekday in range(7):
            if weekday in existing:
                continue
            if weekday < 5:
                opening, closing, closed = _time(9,0), _time(18,0), False
            elif weekday == 5:
                opening, closing, closed = _time(9,0), _time(18,0), False
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
            return BUSINESS_HOURS_SIMPLE.get(language, BUSINESS_HOURS_SIMPLE["en"]).format(opening=opening, closing=closing)
    parts=[]
    for row in rows:
        label=names[row.weekday] if 0 <= row.weekday < len(names) else str(row.weekday)
        parts.append(f"{label}: closed" if row.is_closed else f"{label}: {row.open_time.strftime('%I:%M %p')}–{row.close_time.strftime('%I:%M %p')}")
    return "We're open " + "; ".join(parts) + "."

def conversation(db: Session, tenant_id: str, message: str, language: str, channel: str, conversation_id: str|None):
    c=db.get(Conversation,conversation_id) if conversation_id else None
    if not c or c.tenant_id != tenant_id:
        c=Conversation(tenant_id=tenant_id,channel=channel,language=language)
        db.add(c); db.flush()
    if not c.language:
        c.language=language
    c.last_user_message=message; c.turns=(c.turns or 0)+1
    return c


_WEEKDAYS = ("monday","tuesday","wednesday","thursday","friday","saturday","sunday")
_WEEKDAY_ALIASES = {
    "mon":"monday","tue":"tuesday","tues":"tuesday","wed":"wednesday",
    "thu":"thursday","thur":"thursday","thurs":"thursday","fri":"friday",
    "sat":"saturday","sun":"sunday",\n    "सोमवार":"monday","सोम":"monday","मंगलवार":"tuesday","मंगल":"tuesday","बुधवार":"wednesday","बुध":"wednesday","गुरुवार":"thursday","गुरु":"thursday","शुक्रवार":"friday","शुक्र":"friday","शनिवार":"saturday","शनि":"saturday","रविवार":"sunday","रवि":"sunday",
}
_RELATIVE_DAYS = ("today", "tomorrow", "day after tomorrow")

def extract_booking_entities(text: str) -> dict:
    """Extract booking entities while tolerating natural Indian-language speech and STT variants."""
    value = text.casefold().strip()
    day = None
    for alias, canonical in sorted(_WEEKDAY_ALIASES.items(), key=lambda x: -len(x[0])):
        if re.search(rf"\b{re.escape(alias)}\b", value):
            day = canonical
            break
    if day is None:
        for canonical in _WEEKDAYS:
            if re.search(rf"\b{canonical}\b", value):
                day = canonical
                break

    relative_day = relative_day_from_text(value)

    time_value = None
    if re.search(r"\bnoon\b|\b12\s*(noon|baje|vajje|vagye|mani|am|pm|a\.m\.|p\.m\.)\b", value):
        time_value = "12 PM"
    else:
        tm = re.search(r"\b(1[0-2]|0?[1-9])(?::([0-5]\d))?\s*(a\.?m\.?|p\.?m\.?|o['’]?clock|oclock)\b", value)
        if tm:
            hour = int(tm.group(1)); minute = tm.group(2)
            suffix=tm.group(3).replace(".","").casefold()
            meridiem = "AM" if suffix.startswith("a") else "PM"
            time_value = f"{hour}:{minute} {meridiem}" if minute else f"{hour} {meridiem}"
        else:
            tm24 = re.search(r"\b([01]?\d|2[0-3]):([0-5]\d)\b", value)
            if tm24:
                hour24=int(tm24.group(1)); minute24=tm24.group(2)
                hour12=hour24%12 or 12
                # A bare 1–11 time is intentionally left without AM/PM.
                # booking_reply_from_state resolves it against the tenant's
                # actual business hours instead of silently assuming AM.
                if hour24 >= 12:
                    time_value=f"{hour12}:{minute24} PM"
                elif hour24 == 0:
                    time_value=f"12:{minute24} AM"
                else:
                    time_value=f"{hour12}:{minute24}"
            else:
                number_words={"one":1,"two":2,"three":3,"four":4,"five":5,"six":6,"seven":7,"eight":8,"nine":9,"ten":10,"eleven":11,"twelve":12}
                word_hour=next((n for w,n in number_words.items() if re.search(rf"\b{w}\b",value)),None)
                digit_hour=re.search(r"\b(?:at|by|around|about|baje|vajje|vagye|gantlaki|manikku)\s+(1[0-2]|0?[1-9])\b",value) or re.search(r"\b(1[0-2]|0?[1-9])\s+(?:baje|vajje|vagye|gantlaki|manikku|gantige|vajta)\b",value)
                hour=int(digit_hour.group(1)) if digit_hour else word_hour
                if hour:
                    if re.search(r"\b(morning|subah|savere|am|a\.m\.|uday|sakal)\b",value):
                        meridiem="AM"
                    elif re.search(r"\b(evening|night|shaam|pm|p\.m\.|sanje|saayantram|maalai)\b",value):
                        meridiem="PM"
                    else:
                        meridiem="PM" if re.search(r"\b(?:baje|vajje|vagye|gantlaki|manikku|gantige|vajta)\b",value) else None
                    time_value=f"{hour} {meridiem}" if meridiem else None

    time_hint = next((label for label in ("morning","afternoon","evening","night") if re.search(rf"\b{label}\b",value)),None)
    date_hint = None
    dm=re.search(r"\b(3[01]|[12]\d|[1-9])(?:st|nd|rd|th)?\b",value)
    if dm:
        date_hint=int(dm.group(1))

    return {"day":day,"relative_day":relative_day,"time":time_value,"time_hint":time_hint,"date_hint":date_hint}

def previous_booking_context(db: Session, conversation_id: str, current_message: str) -> dict:
    """Recover useful booking entities from the active booking conversation."""
    rows = db.scalars(
        select(ConversationMessage)
        .where(ConversationMessage.conversation_id == conversation_id)
        .order_by(ConversationMessage.created_at.desc())
        .limit(20)
    ).all()
    ctx = {"day": None, "relative_day": None, "time": None, "time_hint": None, "date_hint": None}
    for row in reversed(rows):
        if row.role != "user":
            continue
        extracted = extract_booking_entities(row.content)
        for key in ctx:
            if extracted.get(key) is not None:
                ctx[key] = extracted[key]
    return ctx


def resolve_booking_date(tenant: Tenant, day: str|None, relative_day: str|None, date_hint: int|None = None):
    """Resolve natural-language booking dates against the tenant's local calendar."""
    from datetime import date as _date, timedelta as _timedelta
    from zoneinfo import ZoneInfo as _ZoneInfo
    now_local=__import__("datetime").datetime.now(_ZoneInfo(tenant.timezone)).date()
    if relative_day=="yesterday":
        return now_local - _timedelta(days=1)
    if relative_day=="today":
        return now_local
    if relative_day=="tomorrow":
        return now_local + _timedelta(days=1)
    if relative_day=="day_after_tomorrow":
        return now_local + _timedelta(days=2)
    if day in _WEEKDAYS:
        target=_WEEKDAYS.index(day)
        delta=(target-now_local.weekday()) % 7
        if delta==0:
            delta=7
        return now_local + _timedelta(days=delta)
    if date_hint:
        for offset in range(0, 370):
            candidate=now_local + _timedelta(days=offset)
            if candidate.day==date_hint:
                return candidate
    return None

def booking_calendar_status(db: Session, tenant: Tenant, booking_date, time_value: str|None):
    """Check the owned calendar before presenting an appointment as confirmable."""
    if not booking_date or not time_value:
        return {"checked":False,"available":None,"date":booking_date.isoformat() if booking_date else None}
    hours=db.scalar(select(BusinessHour).where(
        BusinessHour.tenant_id==tenant.id,
        BusinessHour.weekday==booking_date.weekday()
    ))
    if hours and hours.is_closed:
        return {"checked":True,"available":False,"reason":"closed","date":booking_date.isoformat()}
    tm=re.match(r"^(\d{1,2})(?::(\d{2}))?\s*(AM|PM)$",time_value, re.I)
    if not tm:
        return {"checked":False,"available":None,"date":booking_date.isoformat()}
    hour=int(tm.group(1)); minute=int(tm.group(2) or 0); mer=tm.group(3).upper()
    if mer=="PM" and hour!=12: hour+=12
    if mer=="AM" and hour==12: hour=0
    requested=__import__("datetime").datetime.combine(booking_date,__import__("datetime").time(hour,minute))
    if hours and (requested.time()<hours.open_time or requested.time()>=hours.close_time):
        return {"checked":True,"available":False,"reason":"outside_hours","date":booking_date.isoformat()}
    from zoneinfo import ZoneInfo as _ZoneInfo
    now_local=__import__("datetime").datetime.now(_ZoneInfo(tenant.timezone))
    if booking_date < now_local.date():
        return {"checked":True,"available":False,"reason":"past_date","date":booking_date.isoformat()}
    if booking_date == now_local.date() and requested <= now_local.replace(tzinfo=None):
        return {"checked":True,"available":False,"reason":"past","date":booking_date.isoformat()}
    service=db.scalar(select(Service).where(Service.tenant_id==tenant.id,Service.is_active==True).order_by(Service.name)).one_or_none() if False else db.scalar(select(Service).where(Service.tenant_id==tenant.id,Service.is_active==True).order_by(Service.name).limit(1))
    duration=(service.duration_minutes if service and service.duration_minutes else 30)
    from .booking import local_to_utc_naive, slot_is_available
    start_utc=local_to_utc_naive(requested,tenant.timezone)
    end_utc=local_to_utc_naive(requested+__import__("datetime").timedelta(minutes=duration),tenant.timezone)
    available=slot_is_available(db,tenant.id,start_utc,end_utc,None)
    return {
        "checked":True,"available":available,"date":booking_date.isoformat(),
        "service_id":service.id if service else None,
        "service_name":service.name if service else None,
        "duration_minutes":duration
    }


BOOKING_TEXT={
"en":{"day_time":"Sure. What time would you prefer on {day}?","day":"Sure. What day would you prefer for the appointment?","both":"Sure. Which day and time would you prefer?","confirm":"Great. I have {date} at {time}. Shall I confirm that appointment?","closed":"{day} is closed. Please choose another day.","outside":"{time} is outside our hours on {day}. Please choose another time.","unavailable":"{time} is not available on {day}. Please choose another time.","past":"{time} has already passed today. Please choose a later time.","past_date":"That date has already passed. Please choose a future date.","ampm":"Do you mean {hour} AM or {hour} PM?","hint":"Sure. I have {day} in the {hint}. What exact time would you prefer?","date":"Got it, the {date}th. Which month and time would you prefer?"},
"hi":{"day_time":"ज़रूर। {day} को आप किस समय अपॉइंटमेंट चाहते हैं?","day":"ज़रूर। आप किस दिन का अपॉइंटमेंट चाहते हैं?","both":"ज़रूर। आप किस दिन और किस समय का अपॉइंटमेंट चाहते हैं?","confirm":"ठीक है। मैंने {date} को {time} का अपॉइंटमेंट रखा है। क्या मैं इसे कन्फर्म कर दूँ?","closed":"{day} को हम बंद रहते हैं। कृपया दूसरा दिन चुनिए।","outside":"{time} हमारे {day} के काम के समय के बाहर है। कृपया दूसरा समय चुनिए।","unavailable":"{day} को {time} का स्लॉट उपलब्ध नहीं है। कृपया दूसरा समय चुनिए।","past":"{time} का समय आज निकल चुका है। कृपया बाद का समय चुनिए।","past_date":"यह तारीख निकल चुकी है। कृपया आगे की तारीख चुनिए।","ampm":"आप {hour} AM कहना चाहते हैं या {hour} PM?","hint":"ज़रूर। {day} को {hint} का समय है। कृपया सही समय बताइए।","date":"ठीक है, {date} तारीख। किस महीने और किस समय का अपॉइंटमेंट चाहिए?"},
"te":{"day_time":"తప్పకుండా. {day} ఏ సమయంలో అపాయింట్‌మెంట్ కావాలి?","day":"తప్పకుండా. ఏ రోజు అపాయింట్‌మెంట్ కావాలి?","both":"తప్పకుండా. ఏ రోజు మరియు ఏ సమయంలో అపాయింట్‌మెంట్ కావాలి?","confirm":"సరే. {date} న {time} అపాయింట్‌మెంట్ ఉంది. నేను కన్ఫర్మ్ చేయనా?","closed":"{day} రోజు మేము మూసి ఉంటాము. మరో రోజు ఎంచుకోండి.","outside":"{time} {day} మా పని సమయానికి బయట ఉంది. మరో సమయం ఎంచుకోండి.","unavailable":"{day} {time} స్లాట్ అందుబాటులో లేదు. మరో సమయం ఎంచుకోండి.","past":"{time} ఈరోజు గడిచిపోయింది. దయచేసి తర్వాతి సమయం ఎంచుకోండి.","past_date":"ఆ తేదీ గడిచిపోయింది. దయచేసి భవిష్యత్ తేదీ ఎంచుకోండి.","ampm":"మీరు {hour} AM అంటున్నారా లేదా {hour} PM అంటున్నారా?","hint":"సరే. {day} {hint} సమయం. ఖచ్చితమైన సమయం చెప్పండి.","date":"సరే, {date} తేదీ. ఏ నెల మరియు ఏ సమయం కావాలి?"}}
def booking_text(language,key,**values):
    return BOOKING_TEXT.get(language,BOOKING_TEXT["en"]).get(key,BOOKING_TEXT["en"][key]).format(**values)
def booking_day_label(language,value):
    if language=="hi":
        return {"today":"आज","tomorrow":"कल","day after tomorrow":"परसों"}.get(value,value or "उस दिन")
    if language=="te":
        return {"today":"ఈ రోజు","tomorrow":"రేపు","day after tomorrow":"ఎల్లుండి"}.get(value,value or "ఆ రోజు")
    return value or "that day"

def booking_reply_from_state(db: Session, tenant: Tenant, c: Conversation, message: str) -> tuple[str|None, dict]:
    """Merge current-turn entities with active booking context."""
    current = extract_booking_entities(message)
    logger.info(
        "VOICE_BOOKING_EXTRACTION conversation_id=%s state_before=%s message=%r entities=%s",
        c.id, c.state, message, current,
    )
    prior = previous_booking_context(db, c.id, message) if c.state.startswith("booking") else {
        "day": None, "relative_day": None, "time": None, "time_hint": None, "date_hint": None
    }

    # Current turn always wins. A correction therefore replaces the old value.
    day = current["day"] or prior["day"]
    relative_day = current["relative_day"] or (None if current["day"] else prior["relative_day"])
    time_value = current["time"] or prior["time"]
    time_hint = current["time_hint"] or prior["time_hint"]
    date_hint = current["date_hint"] or prior["date_hint"]

    day_label = relative_day.replace("_", " ") if relative_day and not current["day"] else day

    # Resolve a bare spoken time against the requested day's actual hours.
    # Example: "Monday ... 2:30" in a 09:00–18:00 business means 2:30 PM;
    # do not reject it as 2:30 AM merely because the transcript had no marker.
    if time_value and day_label and not re.search(r"\b(?:AM|PM)\b", time_value, re.I):
        tm_bare=re.match(r"^(\d{1,2})(?::(\d{2}))?$", time_value.strip())
        if tm_bare:
            hour=int(tm_bare.group(1)); minute=int(tm_bare.group(2) or 0)
            if 1 <= hour <= 11:
                from datetime import time as _time
                am_time=_time(hour,minute)
                pm_time=_time(hour+12,minute)
                target_date=resolve_booking_date(tenant, day, relative_day, date_hint)
                hours_row=db.scalar(select(BusinessHour).where(
                    BusinessHour.tenant_id==tenant.id,
                    BusinessHour.weekday==target_date.weekday()
                )) if target_date else None
                if hours_row and not hours_row.is_closed:
                    am_inside=hours_row.open_time <= am_time < hours_row.close_time
                    pm_inside=hours_row.open_time <= pm_time < hours_row.close_time
                    if pm_inside and not am_inside:
                        time_value=f"{hour}:{minute:02d} PM" if minute else f"{hour} PM"
                    elif am_inside and not pm_inside:
                        time_value=f"{hour}:{minute:02d} AM" if minute else f"{hour} AM"
                    elif am_inside and pm_inside:
                        c.state="booking_time_clarification"
                        return (
                            f"Do you mean {hour}:{minute:02d} AM or {hour}:{minute:02d} PM?" if minute else
                            f"Do you mean {hour} AM or {hour} PM?",
                            {"day":day_label,"time":None,"complete":False}
                        )

    resolved_date=resolve_booking_date(tenant, day, relative_day, date_hint)
    if day_label and time_value:
        calendar=booking_calendar_status(db,tenant,resolved_date,time_value)
        if calendar.get("available") is False:
            if calendar.get("reason")=="past_date":
                c.state="booking_time_clarification"
                return (booking_text(c.language,"past_date"), {"day":day_label,"time":None,"date":resolved_date.isoformat() if resolved_date else None,"complete":False})
            if calendar.get("reason")=="past":
                c.state="booking_time_clarification"
                return (booking_text(c.language,"past",time=time_value), {"day":day_label,"time":None,"date":resolved_date.isoformat() if resolved_date else None,"complete":False})
            if calendar.get("reason")=="closed":
                c.state="booking_time_clarification"
                return (booking_text(c.language,"closed",day=booking_day_label(c.language,day_label)), {"day":day_label,"time":None,"date":resolved_date.isoformat() if resolved_date else None,"complete":False})
            if calendar.get("reason")=="outside_hours":
                c.state="booking_time_clarification"
                return (booking_text(c.language,"outside",time=time_value,day=booking_day_label(c.language,day_label)), {"day":day_label,"time":None,"date":resolved_date.isoformat() if resolved_date else None,"complete":False})
            c.state="booking_time_clarification"
            return (booking_text(c.language,"unavailable",time=time_value,day=booking_day_label(c.language,day_label)), {"day":day_label,"time":None,"date":resolved_date.isoformat() if resolved_date else None,"complete":False})
        c.state = "booking_confirmation"
        date_phrase=resolved_date.strftime("%A, %B %-d, %Y") if resolved_date else day_label
        return (
            booking_text(c.language,"confirm",date=date_phrase,time=time_value),
            {"day": day_label, "time": time_value, "date": resolved_date.isoformat() if resolved_date else None, "service_id":calendar.get("service_id"), "complete": True},
        )

    if day_label and time_hint:
        c.state = "booking_time_clarification"
        return (
            booking_text(c.language,"hint",day=booking_day_label(c.language,day_label),hint=time_hint),
            {"day": day_label, "time": None, "time_hint": time_hint, "date_hint": date_hint, "complete": False},
        )

    if day_label:
        c.state = "booking_day"
        return booking_text(c.language,"day_time",day=booking_day_label(c.language,day_label)), {
            "day": day_label, "time": None, "time_hint": time_hint, "date_hint": date_hint, "complete": False
        }

    if time_value:
        c.state = "booking_day"
        return "Sure. What day would you prefer for the appointment?", {
            "day": None, "time": time_value, "time_hint": time_hint, "date_hint": date_hint, "complete": False
        }

    if date_hint:
        c.state = "booking_date"
        return booking_text(c.language,"date",date=date_hint), {
            "day": None, "time": None, "time_hint": time_hint, "date_hint": date_hint, "complete": False
        }

    c.state = "booking_day"
    return "Sure. Which day and time would you prefer?", {
        "day": None, "time": None, "time_hint": time_hint, "date_hint": date_hint, "complete": False
    }


def is_booking_cancellation(message: str) -> bool:
    value=" ".join(message.casefold().split())
    phrases=("cancel","leave it","don't want","do not want","not needed",
             "nahi chahiye","nahin chahiye","cancel kar do","बुक नहीं चाहिए",
             "नहीं चाहिए","मत चाहिए","रद्द","रद्द कर")
    return any(p in value for p in phrases)

async def generate_reply(db:Session,tenant_id:str,message:str,conversation_id:str|None=None,channel:str="pwa")->dict:
    tenant=db.get(Tenant,tenant_id)
    if not tenant: raise ValueError("Tenant not found")
    detected_language=detect_language(message)
    intent=local_intent(message)
    c=conversation(db,tenant_id,message,detected_language,channel,conversation_id)
    requested_language=language_request(message)
    if requested_language:
        language=requested_language
    elif c.turns > 1 and c.language and detected_language == "en" and c.language != "en":
        language=c.language
    else:
        language=detected_language
    c.language=language
    logger.info(
        "VOICE_REPLY_ENTRY conversation_id=%s tenant_id=%s channel=%s message=%r state=%s",
        c.id, tenant_id, channel, message, c.state,
    )
    logger.info(
        "VOICE_INTENT_RESULT conversation_id=%s message=%r intent=%s state=%s",
        c.id, message, intent, c.state,
    )
    db.add(ConversationMessage(conversation_id=c.id,role="user",content=message,language=language,intent=intent))
    
    # Library-first policy: these paths consume zero model tokens.
    hours=business_hours_reply(db,tenant_id,message,language)
    booking=None
    booking_data={"day": None, "time": None, "date": None, "complete": False}
    policy=tenant_policy(db,tenant_id)
    m=message.casefold()
    # Keep short conversational turns deterministic: greetings should never
    # fall through to the model/handoff path.
    greeting_words={"hello","hi","hey","hiya","good morning","good afternoon","good evening","namaste"}
    current_entities=extract_booking_entities(message)
    has_booking_entities=any(current_entities.get(k) is not None for k in ("day","relative_day","time","time_hint","date_hint"))
    active_booking=c.state.startswith("booking")
    if any(re.fullmatch(r"\s*"+re.escape(g)+r"\s*[.!?]*\s*",m) for g in greeting_words):
        booking="Hello! How can I help you today?"
    elif intent=="language_request":
        requested_language=language_request(message) or "en"
        previous_booking_state=c.state if active_booking else None
        booking=language_switch_confirmation(requested_language,agent_gender(db,tenant_id))
        c.language=requested_language
        if previous_booking_state:
            c.state=previous_booking_state
    elif intent=="closing" and not active_booking:
        booking="You're welcome. If you need anything else, I'm here to help."
        if any(x in m for x in ("bye","goodbye","leave it","cancel","that's all","thats all")):
            c.state="closed"
    elif intent=="voice_feedback" and not active_booking:
        feedback_replies={
            "en":"I understand. I'll continue with the same language and keep the conversation natural.",
            "hi":"Samajh gayi. Main Hindi mein hi continue karungi aur conversation naturally rakhoongi.",
            "te":"Ardham ayyindi. Nenu Telugu lo continue chestanu.",
            "ta":"Purinjukitten. Naan Tamil-la continue panren.",
            "kn":"Artha aayitu. Naanu Kannada dalli continue maaduttene.",
            "ml":"Manassilaayi. Njan Malayalam-il thanne continue cheyyam.",
            "mr":"Samajla. Mi Marathi madhyech continue karen.",
            "bn":"Bujhte perechi. Ami Banglayi continue korbo.",
            "gu":"Samajyu. Hu Gujarati ma j continue karish.",
            "pa":"Samajh gayi. Main Punjabi vich hi gal jari rakhangi.",
            "ur":"Samajh gayi. Main Urdu mein hi baat jari rakhungi.",
        }
        booking=voice_feedback_reply(language,agent_gender(db,tenant_id))
        c.state="information"
    elif intent=="human_handoff":
        booking="Of course. I'll arrange for our team to speak with you. I'll pass along what we've discussed so you don't have to repeat it."
        c.state="handoff_requested"
    elif c.state=="booking_confirmation" and is_explicit_confirmation(message):
        # The browser voice path uses /voice/turn rather than the realtime
        # provider WebSocket. Preserve the booking state here so the public
        # endpoint can execute the owned booking transaction.
        prior=previous_booking_context(db,c.id,message)
        booking_date=resolve_booking_date(
            tenant, prior.get("day"), prior.get("relative_day"), prior.get("date_hint")
        )
        calendar=booking_calendar_status(db,tenant,booking_date,prior.get("time"))
        if booking_date and prior.get("time") and calendar.get("available") is True:
            booking="Perfect. I'll confirm that appointment now."
            booking_data={
                "day":prior.get("day") or prior.get("relative_day"),
                "time":prior.get("time"),
                "date":booking_date.isoformat(),
                "service_id":calendar.get("service_id"),
                "complete":True,
                "confirmation_requested":True,
            }
            c.state="booking_confirmation_requested"
        else:
            reason=calendar.get("reason") if isinstance(calendar,dict) else None
            if reason=="closed":
                booking=booking_text(c.language,"closed",day=booking_day_label(c.language,prior.get("day") or prior.get("relative_day")))
            elif reason=="outside_hours":
                booking=booking_text(c.language,"outside",time=prior.get("time") or "That time",day=booking_day_label(c.language,prior.get("day") or prior.get("relative_day")))
            elif reason=="past":
                booking=booking_text(c.language,"past",time=prior.get("time") or "That time")
            else:
                booking=booking_text(c.language,"unavailable",time=prior.get("time") or "That time",day=booking_day_label(c.language,prior.get("day") or prior.get("relative_day")))
            booking_data={
                "day":prior.get("day") or prior.get("relative_day"),
                "time":prior.get("time"),
                "date":booking_date.isoformat() if booking_date else None,
                "complete":False,
                "confirmation_requested":False,
            }
            c.state="booking_time_clarification"
    elif active_booking and is_booking_cancellation(message):
        booking={"hi":"ठीक है। मैंने अपॉइंटमेंट की प्रक्रिया रोक दी है। अगर बाद में बुक करना हो तो बताइए。",
                 "te":"సరే. అపాయింట్‌మెంట్ బుకింగ్‌ను ఆపేశాను. తర్వాత బుక్ చేయాలంటే చెప్పండి."}.get(
                 language,"Okay. I’ve stopped the appointment booking. If you want to book later, just let me know.")
        c.state="information"
        booking_data={"complete":False,"cancelled":True}
    elif intent=="availability" and active_booking:
        prior=previous_booking_context(db,c.id,message)
        requested_day=current_entities.get("day") or prior.get("day")
        requested_relative=current_entities.get("relative_day") or (None if current_entities.get("day") else prior.get("relative_day"))
        booking_date=resolve_booking_date(tenant,requested_day,requested_relative)
        service=db.scalar(select(Service).where(Service.tenant_id==tenant.id,Service.is_active==True).order_by(Service.name).limit(1))
        if booking_date and service:
            slots=available_slots(db,tenant,service.id,booking_date)
            if slots:
                times=[datetime.fromisoformat(x["start"]).strftime("%-I:%M %p") for x in slots[:4]]
                booking=(f"{booking_date.strftime('%A, %B %-d')}, available times are {', '.join(times)}. Which time would you like?"
                         if language=="en" else
                         f"{booking_date.strftime('%A, %B %-d')} को उपलब्ध समय {', '.join(times)} हैं। इनमें से कौन सा समय चाहिए?"
                         if language=="hi" else
                         f"{booking_date.strftime('%A, %B %-d')} అందుబాటులో ఉన్న సమయాలు {', '.join(times)}. ఏ సమయం కావాలి?"
                         if language=="te" else
                         f"Available times are {', '.join(times)}. Which time would you like?")
            else:
                booking=booking_text(language,"unavailable",time="A slot",day=booking_date.strftime("%A"))
        else:
            booking=AVAILABILITY_PROMPTS.get(language,AVAILABILITY_PROMPTS["en"])
        c.state="booking_day"
    elif active_booking:
        booking, booking_data = booking_reply_from_state(db, tenant, c, message)
    elif intent=="doctor_information":
        doctor_answer=knowledge_match(db,tenant_id,message)
        if doctor_answer:
            booking=doctor_answer
            c.state="information"
        else:
            booking=DOCTOR_DETAILS_MISSING.get(language, DOCTOR_DETAILS_MISSING["en"])
            c.state="information"

    elif intent=="availability":
        booking=AVAILABILITY_PROMPTS.get(language, AVAILABILITY_PROMPTS["en"])
        c.state="availability_request"
    elif intent=="date_information":
        from datetime import timedelta
        from zoneinfo import ZoneInfo
        now_local=datetime.now(ZoneInfo(tenant.timezone))
        target=now_local.date()+timedelta(days=2 if "day after tomorrow" in m or "परसों" in m else 1)
        booking=f"{target.strftime('%A, %B %-d, %Y')}."
        c.state="information"
    elif intent=="clarification":
        booking=SPOKEN_CLARIFICATION.get(language, SPOKEN_CLARIFICATION["en"])
        c.state="information"
    elif intent=="booking" and not capability_enabled(policy,"bookings",True):
        booking="Appointments are not enabled for this business right now. I can help with another question or arrange a message for the team."

    else:
        # Contextual booking continuation: a short answer such as "Saturday" is
        # a booking response when the immediately preceding AI turn explicitly
        # asked for a booking day/time. This is contextual, not a global keyword rule.
        previous_assistant = db.scalar(
            select(ConversationMessage)
            .where(ConversationMessage.conversation_id==c.id, ConversationMessage.role=="assistant")
            .order_by(ConversationMessage.created_at.desc())
            .limit(1)
        )
        previous_text=(previous_assistant.content.casefold() if previous_assistant else "")
        booking_invitation = (
            "book an appointment" in previous_text or
            "what day and time" in previous_text or
            "what day would you prefer" in previous_text or
            "what time would you prefer" in previous_text
        )
        contextual_booking = booking_invitation and has_booking_entities and intent in {"information","business_hours","closing"}
        if contextual_booking or intent=="booking" or c.state.startswith("booking"):
            booking, booking_data = booking_reply_from_state(db, tenant, c, message)
        elif c.state.startswith("booking"):
            booking_data = {"day": None, "time": None, "complete": False}
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
            "Do not ask for information already provided in this conversation. " + f"The current agent persona is {agent_gender(db,tenant_id)}. In gendered languages, use first-person grammar that matches that gender consistently; never switch gender mid-conversation. "
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
