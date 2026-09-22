from dataclasses import dataclass
import hashlib
import hmac
import httpx

@dataclass
class WhatsAppAdapter:
    provider: str = "openwa"
    openwa_base_url: str = ""
    openwa_api_key: str = ""
    openwa_session_id: str = ""
    access_token: str = ""
    phone_number_id: str = ""

    async def send_text(self, to: str, text: str) -> dict:
        provider = (self.provider or "openwa").lower()
        if provider == "openwa":
            if not self.openwa_base_url or not self.openwa_api_key or not self.openwa_session_id:
                raise RuntimeError("OpenWA WhatsApp is not configured")
            chat_id = to if "@" in to else to.lstrip("+") + "@c.us"
            url = self.openwa_base_url.rstrip("/") + "/api/sessions/" + self.openwa_session_id + "/messages/send-text"
            async with httpx.AsyncClient(timeout=20) as client:
                r = await client.post(url, headers={"X-API-Key": self.openwa_api_key}, json={"chatId": chat_id, "text": text})
                r.raise_for_status(); return r.json()
        if provider == "meta":
            if not self.access_token or not self.phone_number_id:
                raise RuntimeError("WhatsApp Business Platform is not configured")
            url = "https://graph.facebook.com/v23.0/" + self.phone_number_id + "/messages"
            async with httpx.AsyncClient(timeout=20) as client:
                r = await client.post(url, headers={"Authorization": "Bearer " + self.access_token}, json={"messaging_product":"whatsapp","to":to.lstrip("+"),"type":"text","text":{"body":text}})
                r.raise_for_status(); return r.json()
        raise RuntimeError("Unsupported WhatsApp provider: " + provider)

    async def send_template(self, to: str, template_name: str, variables: dict | None = None) -> dict:
        if (self.provider or "openwa").lower() != "openwa":
            raise RuntimeError("Template sending is provider-specific; use the Meta Cloud adapter for approved templates")
        if not self.openwa_base_url or not self.openwa_api_key or not self.openwa_session_id:
            raise RuntimeError("OpenWA WhatsApp is not configured")
        chat_id = to if "@" in to else to.lstrip("+") + "@c.us"
        url = self.openwa_base_url.rstrip("/") + "/api/sessions/" + self.openwa_session_id + "/messages/send-template"
        async with httpx.AsyncClient(timeout=20) as client:
            r = await client.post(url, headers={"X-API-Key": self.openwa_api_key}, json={"chatId":chat_id,"templateName":template_name,"vars":variables or {}})
            r.raise_for_status(); return r.json()

    @staticmethod
    def verify_webhook(raw_body: bytes, signature: str | None, secret: str) -> bool:
        if not secret: return True
        if not signature: return False
        supplied = signature.replace("sha256=", "")
        expected = hmac.new(secret.encode(), raw_body, hashlib.sha256).hexdigest()
        return hmac.compare_digest(supplied, expected)

@dataclass
class PaymentAdapter:
    key_id:str=""
    key_secret:str=""
    async def create_order(self,amount_paise:int,currency:str="INR",receipt:str="growth-os")->dict:
        if not self.key_id or not self.key_secret: raise RuntimeError("Razorpay is not configured")
        import base64
        auth=base64.b64encode((self.key_id+":"+self.key_secret).encode()).decode()
        async with httpx.AsyncClient(timeout=20) as client:
            r=await client.post("https://api.razorpay.com/v1/orders",headers={"Authorization":"Basic "+auth},json={"amount":amount_paise,"currency":currency,"receipt":receipt})
            r.raise_for_status(); return r.json()
