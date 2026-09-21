from dataclasses import dataclass
import httpx

@dataclass
class WhatsAppAdapter:
    access_token:str=""
    phone_number_id:str=""
    async def send_text(self,to:str,text:str)->dict:
        if not self.access_token or not self.phone_number_id: raise RuntimeError("WhatsApp Business Platform is not configured")
        url="https://graph.facebook.com/v23.0/"+self.phone_number_id+"/messages"
        async with httpx.AsyncClient(timeout=20) as client:
            r=await client.post(url,headers={"Authorization":"Bearer "+self.access_token},json={"messaging_product":"whatsapp","to":to,"type":"text","text":{"body":text}})
            r.raise_for_status(); return r.json()

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
