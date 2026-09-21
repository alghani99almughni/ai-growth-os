import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session
from .models import Tenant, Service, Product\nfrom .models_growth import KnowledgeItem
from .config import settings

def knowledge_context(db: Session, tenant_id: str) -> str:
    tenant=db.get(Tenant,tenant_id)
    services=db.scalars(select(Service).where(Service.tenant_id==tenant_id,Service.is_active==True)).all()
    products=db.scalars(select(Product).where(Product.tenant_id==tenant_id,Product.is_active==True)).all()\n    knowledge=db.scalars(select(KnowledgeItem).where(KnowledgeItem.tenant_id==tenant_id,KnowledgeItem.is_active==True)).all()
    lines=[f"Business: {tenant.name}",f"Industry: {tenant.industry}",f"Description: {tenant.description or ''}",f"Phone: {tenant.phone or ''}",f"WhatsApp: {tenant.whatsapp_number or ''}",f"Address: {tenant.address or ''}"]
    for x in knowledge: lines.append(f"Knowledge ({x.kind}): {x.title}: {x.content}")\n    for x in services: lines.append(f"Service: {x.name}; description={x.description or ''}; price={x.price} {x.currency}; duration={x.duration_minutes or ''} minutes")
    for x in products: lines.append(f"Product: {x.name}; description={x.description or ''}; price={x.price} {x.currency}; stock={x.stock_quantity if x.stock_quantity is not None else 'unknown'}")
    return "\n".join(lines)

def local_intent(message:str)->str:
    m=message.lower()
    if any(x in m for x in ["book","appointment","schedule","reserve"]): return "booking"
    if any(x in m for x in ["price","cost","fee","rate"]): return "pricing"
    if any(x in m for x in ["buy","order","product","stock","available"]): return "product"
    if any(x in m for x in ["call me","human","person","staff","agent"]): return "human_handoff"
    return "information"

async def generate_reply(db:Session,tenant_id:str,message:str)->dict:
    context=knowledge_context(db,tenant_id); intent=local_intent(message)
    if not settings.gemini_api_key:
        return {"reply":"I can help with this business's verified services, products and general information. The AI provider is not configured yet.","intent":intent,"provider":"local"}
    prompt=("You are a customer assistant. Answer ONLY from the approved business context. Never invent prices, availability, policies, discounts, bookings or payment success. If unknown, say staff can help. Keep concise.\n\nAPPROVED CONTEXT:\n"+context+"\n\nCUSTOMER:\n"+message)
    url="https://generativelanguage.googleapis.com/v1beta/models/"+settings.gemini_model+":generateContent?key="+settings.gemini_api_key
    async with httpx.AsyncClient(timeout=30) as client:
        response=await client.post(url,json={"contents":[{"parts":[{"text":prompt}]}]})
        response.raise_for_status()
        data=response.json()
    text=data.get("candidates",[{}])[0].get("content",{}).get("parts",[{}])[0].get("text") or "A staff member can help with that."
    return {"reply":text,"intent":intent,"provider":"gemini"}
