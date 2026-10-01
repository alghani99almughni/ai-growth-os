"""Session 11 - Payment Idempotency installer.

Replaces verify_bill_payment and razorpay_webhook in app/main.py with
idempotent versions. Safe to run more than once.
"""
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent
MAIN = ROOT / "app" / "main.py"

if not MAIN.exists():
    print("ERROR: app/main.py not found. Run from apps/api.")
    sys.exit(1)

text = MAIN.read_text(encoding="utf-8")

if "SESSION11_PAYMENT_IDEMPOTENCY" in text:
    print("SKIP: Session 11 already applied")
    sys.exit(0)

NEW_VERIFY = '''@app.post("/api/v1/public/business/{slug}/bills/{bill_id}/verify-payment")
def verify_bill_payment(slug,bill_id,payload:PaymentVerify,db:Session=Depends(get_db)):
    from .security import check_idempotency, store_idempotent_response, audit, verify_razorpay_signature
    t=db.scalar(select(Tenant).where(Tenant.slug==slug.lower()))
    if not t: raise HTTPException(404,"Bill not found")
    idem_key=f"{bill_id}:{payload.razorpay_order_id}:{payload.razorpay_payment_id}"
    idem_payload={"bill_id":bill_id,"order_id":payload.razorpay_order_id,"payment_id":payload.razorpay_payment_id}
    idem=check_idempotency(db,t.id,"payment.verify",idem_key,idem_payload)
    if idem.conflict:
        raise HTTPException(409,"Payment does not match a previous attempt for the same bill")
    if not idem.first_seen:
        return idem.cached_response or {"paid":True,"bill_id":bill_id,"payment_id":payload.razorpay_payment_id}
    bill=db.scalar(select(Bill).where(Bill.id==bill_id,Bill.tenant_id==t.id))
    if not bill:
        store_idempotent_response(db,t.id,"payment.verify",idem_key,{"error":"bill_not_found"})
        raise HTTPException(404,"Bill not found")
    if bill.status=="paid":
        if bill.payment_id and bill.payment_id!=payload.razorpay_payment_id:
            raise HTTPException(409,"Bill is already paid with another payment")
        response={"paid":True,"bill_id":bill.id,"payment_id":bill.payment_id}
        store_idempotent_response(db,t.id,"payment.verify",idem_key,response)
        return response
    adapter=tenant_payment_adapter(db,t.id,settings)
    if not adapter.key_secret:
        raise HTTPException(503,"Razorpay is not configured")
    if not verify_razorpay_signature(payload.razorpay_order_id,payload.razorpay_payment_id,payload.razorpay_signature,adapter.key_secret):
        raise HTTPException(400,"Invalid payment signature")
    bill.payment_id=payload.razorpay_payment_id
    bill.status="paid"
    bill.paid_at=datetime.utcnow()
    o=db.get(Order,bill.order_id)
    if o:
        o.payment_status="paid"
        o.updated_at=datetime.utcnow()
    db.commit()
    audit(db,tenant_id=t.id,actor_id=None,action="payment.captured",target_type="bill",target_id=bill.id,detail={"order_id":bill.order_id,"payment_id":bill.payment_id,"amount":bill.total})
    response={"paid":True,"bill_id":bill.id,"payment_id":bill.payment_id}
    store_idempotent_response(db,t.id,"payment.verify",idem_key,response)
    return response
'''

NEW_WEBHOOK = '''@app.post("/api/v1/webhooks/razorpay")
async def razorpay_webhook(request:Request,db:Session=Depends(get_db)):
    from .security import check_idempotency, store_idempotent_response, audit
    raw=await request.body()
    signature=request.headers.get("X-Razorpay-Signature","")
    if not settings.razorpay_key_secret or not signature:
        raise HTTPException(401,"Webhook signature required")
    if not verify_hmac_sha256(raw,signature,settings.razorpay_key_secret):
        raise HTTPException(400,"Invalid webhook signature")
    try:
        payload=json.loads(raw.decode("utf-8"))
    except Exception:
        raise HTTPException(400,"Invalid webhook JSON")
    entity=payload.get("payload",{}).get("payment",{}).get("entity",{}) or {}
    event_id=payload.get("event_id") or payload.get("id") or ""
    payment_id=entity.get("id") or ""
    receipt=(entity.get("notes") or {}).get("receipt") or ""
    if not (event_id or payment_id):
        return {"received":True,"ignored":True}
    idem_key=event_id or f"payment:{payment_id}"
    idem_payload={"event_id":event_id,"payment_id":payment_id,"receipt":receipt,"status":entity.get("status")}
    idem=check_idempotency(db,"__platform__","payment.webhook",idem_key,idem_payload)
    if idem.conflict:
        raise HTTPException(409,"Idempotency conflict for webhook event")
    if not idem.first_seen:
        return idem.cached_response or {"received":True,"replayed":True}
    if receipt.startswith("bill-") and entity.get("status") in ("captured","authorized"):
        bill=db.scalar(select(Bill).where(Bill.id==receipt[5:]))
        if bill and bill.status!="paid":
            bill.status="paid"
            bill.payment_id=entity.get("id")
            bill.paid_at=datetime.utcnow()
            o=db.get(Order,bill.order_id)
            if o:
                o.payment_status="paid"
            db.commit()
            audit(db,tenant_id=bill.tenant_id,actor_id=None,action="payment.webhook_captured",target_type="bill",target_id=bill.id,detail={"payment_id":entity.get("id"),"event_id":event_id,"amount":entity.get("amount")})
    response={"received":True}
    store_idempotent_response(db,"__platform__","payment.webhook",idem_key,response)
    return response
'''


def replace_function(src, decorator, new_body):
    start = src.find(decorator)
    if start < 0:
        return src, False
    end = src.find("\n@app.", start + 10)
    if end < 0:
        end = len(src)
    return src[:start] + new_body + src[end:], True


changed = 0

text, ok = replace_function(
    text,
    '@app.post("/api/v1/public/business/{slug}/bills/{bill_id}/verify-payment")',
    NEW_VERIFY,
)
if ok:
    print("  patched verify_bill_payment")
    changed += 1
else:
    print("  WARNING: verify_bill_payment not found")

text, ok = replace_function(
    text,
    '@app.post("/api/v1/webhooks/razorpay")',
    NEW_WEBHOOK,
)
if ok:
    print("  patched razorpay_webhook")
    changed += 1
else:
    print("  WARNING: razorpay_webhook not found")

text = text.rstrip() + "\n\n# SESSION11_PAYMENT_IDEMPOTENCY\n"

MAIN.write_text(text, encoding="utf-8")
print()
print(f"Session 11 install complete. Patched {changed}/2 endpoints.")
print(f"main.py now {len(text)} bytes.")