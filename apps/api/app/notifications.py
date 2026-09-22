import httpx
from .config import settings
from .integrations import WhatsAppAdapter

def _platform_whatsapp() -> WhatsAppAdapter | None:
    provider=(settings.notification_whatsapp_provider or settings.whatsapp_provider or "").lower()
    if provider=="meta":
        return WhatsAppAdapter(
            provider="meta",
            access_token=settings.notification_whatsapp_access_token or settings.whatsapp_access_token,
            phone_number_id=settings.notification_whatsapp_phone_number_id or settings.whatsapp_phone_number_id,
        )
    if provider=="openwa":
        return WhatsAppAdapter(
            provider="openwa",
            openwa_base_url=settings.notification_whatsapp_openwa_base_url or settings.openwa_base_url,
            openwa_api_key=settings.notification_whatsapp_openwa_api_key or settings.openwa_api_key,
            openwa_session_id=settings.notification_whatsapp_openwa_session_id or settings.openwa_session_id,
        )
    return None

async def send_email(to:str,subject:str,text:str,html:str|None=None)->dict:
    if not settings.resend_api_key or not settings.notification_from_email:
        return {"sent":False,"status":"not_configured","channel":"email"}
    payload={
        "from": f"{settings.notification_from_name} <{settings.notification_from_email}>",
        "to":[to],
        "subject":subject,
        "text":text,
    }
    if html: payload["html"]=html
    async with httpx.AsyncClient(timeout=20) as client:
        r=await client.post(
            "https://api.resend.com/emails",
            headers={"Authorization":"Bearer "+settings.resend_api_key,"Content-Type":"application/json"},
            json=payload,
        )
        r.raise_for_status()
        return {"sent":True,"status":"sent","channel":"email","provider_id":r.json().get("id")}

async def send_platform_whatsapp(to:str,text:str)->dict:
    adapter=_platform_whatsapp()
    if not adapter:
        return {"sent":False,"status":"not_configured","channel":"whatsapp"}
    try:
        result=await adapter.send_text(to,text)
        return {"sent":True,"status":"sent","channel":"whatsapp","provider_result":result}
    except Exception as exc:
        return {"sent":False,"status":"failed","channel":"whatsapp","error":str(exc)}

async def send_owner_credentials(tenant,owner,temp_password:str)->dict:
    login_url=settings.public_app_url.rstrip("/")+"/login"
    body=(
        f"Welcome to AI Growth OS, {owner.name}.\\n\\n"
        f"Your business workspace is ready.\\n\\n"
        f"Business: {tenant.name}\\n"
        f"Login email: {owner.email}\\n"
        f"Temporary password: {temp_password}\\n"
        f"Login: {login_url}\\n\\n"
        "Please sign in and change your password if you want a new private credential. "
        "If you forget it, use Forgot password on the login page."
    )
    html=(
        f"<h2>Welcome to AI Growth OS</h2>"
        f"<p>Your <strong>{tenant.name}</strong> workspace is ready.</p>"
        f"<p><strong>Login email:</strong> {owner.email}<br>"
        f"<strong>Temporary password:</strong> {temp_password}</p>"
        f"<p><a href='{login_url}'>Open your secure login</a></p>"
        "<p>If you forget the password, use <strong>Forgot password</strong> on the login page.</p>"
    )
    email_result=await send_email(owner.email,"Your AI Growth OS account is ready",body,html)
    whatsapp_result={"sent":False,"status":"not_configured","channel":"whatsapp"}
    if tenant.phone:
        whatsapp_result=await send_platform_whatsapp(tenant.phone,body)
    return {"email":email_result,"whatsapp":whatsapp_result}

async def send_password_reset(user,token:str)->dict:
    reset_url=settings.public_app_url.rstrip("/")+"/reset-password?token="+token
    body=(
        f"Password reset requested for {user.email}.\\n\\n"
        f"Reset your AI Growth OS password here: {reset_url}\\n\\n"
        f"This link expires in {settings.password_reset_ttl_minutes} minutes and can be used once."
    )
    html=(
        "<h2>Reset your AI Growth OS password</h2>"
        f"<p><a href='{reset_url}'>Reset password</a></p>"
        f"<p>This link expires in {settings.password_reset_ttl_minutes} minutes and can be used once.</p>"
    )
    email_result=await send_email(user.email,"Reset your AI Growth OS password",body,html)
    whatsapp_result={"sent":False,"status":"not_configured","channel":"whatsapp"}
    return {"email":email_result,"whatsapp":whatsapp_result,"reset_url":reset_url}
