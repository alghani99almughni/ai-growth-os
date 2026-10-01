"""Session 9 - Loyalty Wallet + Games installer.

Replaces four endpoints in app/main.py to route through app/loyalty.py and
app/games.py. Idempotent. Safe to rerun.
"""
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent
MAIN = ROOT / "app" / "main.py"

if not MAIN.exists():
    print("ERROR: app/main.py not found. Run from apps/api.")
    sys.exit(1)

text = MAIN.read_text(encoding="utf-8")

if "SESSION9_LOYALTY_WALLET" in text:
    print("SKIP: Session 9 already applied")
    sys.exit(0)


def replace_function(src, decorator, new_body):
    start = src.find(decorator)
    if start < 0:
        return src, False
    end = src.find("\n@app.", start + 10)
    if end < 0:
        end = len(src)
    return src[:start] + new_body + src[end:], True


# ---------------------------------------------------------------------------
# 1. Public order completion -> ledger via loyalty.award_for_order
# ---------------------------------------------------------------------------

NEW_UPDATE_ORDER = '''@app.patch("/api/v1/tenants/{tenant_id}/orders/{order_id}")
def update_order(tenant_id,order_id,payload:OrderStatusUpdate,user=Depends(get_current_user),db:Session=Depends(get_db)):
    require_tenant(user,tenant_id)
    o=db.scalar(select(Order).where(Order.id==order_id,Order.tenant_id==tenant_id))
    if not o: raise HTTPException(404,"Order not found")
    prev=o.status
    o.status=payload.status; o.updated_at=datetime.utcnow()
    if payload.status=="completed" and prev!="completed":
        b=db.scalar(select(Bill).where(Bill.order_id==o.id))
        if not b:
            db.add(Bill(tenant_id=tenant_id,order_id=o.id,subtotal=o.subtotal,tax=o.tax,discount=o.discount,total=o.total))
        db.commit()
        # SESSION9_LOYALTY_WALLET: route awards through the ledger
        try:
            from .loyalty import award_for_order
            awarded = award_for_order(db, tenant_id, o)
            if awarded:
                import logging as _lg
                _lg.getLogger("api.loyalty").info("order=%s awarded=%s", o.id, awarded)
        except Exception:
            pass
    else:
        db.commit()
    db.refresh(o)
    bill=db.scalar(select(Bill).where(Bill.order_id==o.id))
    publish_event_sync(tenant_id,"order.updated",{
        "order_id":o.id,"status":o.status,"total":o.total,
        "payment_status":o.payment_status,
        "bill":{"id":bill.id,"status":bill.status,"total":bill.total} if bill else None
    },context_token=o.context_token)
    return _order_out(o,db)
'''

text, ok = replace_function(
    text,
    '@app.patch("/api/v1/tenants/{tenant_id}/orders/{order_id}")',
    NEW_UPDATE_ORDER,
)
print("  patched update_order (ledger-based loyalty)" if ok else "  WARNING: update_order not found")


# ---------------------------------------------------------------------------
# 2. Game score -> anti-abuse via games.submit_score
# ---------------------------------------------------------------------------

NEW_GAME_SCORE = '''@app.post("/api/v1/public/business/{slug}/games/{game}/score")
def save_game_score(slug,game:str,score:int=Query(ge=0,le=1000000),customer_id:str|None=None,db:Session=Depends(get_db)):
    t=db.scalar(select(Tenant).where(Tenant.slug==slug.lower()))
    if not t: raise HTTPException(404,"Business not found")
    from .games import submit_score
    result=submit_score(db,t.id,game,score,customer_id)
    if not result.ok:
        code={"games_disabled":403,"unknown_game":400,"invalid_score":400}.get(result.reason,400)
        raise HTTPException(code,result.reason.replace("_"," "))
    return {"id":result.score_id,"game":game,"score":result.score,
            "reward_points":result.reward_points,"reward_reason":result.reward_reason}
'''

text, ok = replace_function(
    text,
    '@app.post("/api/v1/public/business/{slug}/games/{game}/score")',
    NEW_GAME_SCORE,
)
print("  patched save_game_score (anti-abuse)" if ok else "  WARNING: save_game_score not found")


# ---------------------------------------------------------------------------
# 3. Loyalty balance -> via ledger
# ---------------------------------------------------------------------------

NEW_LOYALTY_BALANCE = '''@app.get("/api/v1/tenants/{tenant_id}/loyalty/{customer_id}")
def loyalty_balance(tenant_id,customer_id,user=Depends(get_current_user),db:Session=Depends(get_db)):
    require_tenant(user,tenant_id)
    from .loyalty import balance as _bal, history as _hist
    if not _feature_config(db,tenant_id).get("loyalty",False):
        raise HTTPException(403,"Loyalty is disabled for this business")
    return {"points":_bal(db,tenant_id,customer_id),"history":_hist(db,tenant_id,customer_id,50)}
'''

text, ok = replace_function(
    text,
    '@app.get("/api/v1/tenants/{tenant_id}/loyalty/{customer_id}")',
    NEW_LOYALTY_BALANCE,
)
print("  patched loyalty_balance (ledger-based)" if ok else "  WARNING: loyalty_balance not found")


# ---------------------------------------------------------------------------
# 4. Add loyalty manual award -> via ledger
# ---------------------------------------------------------------------------

NEW_LOYALTY_AWARD = '''@app.post("/api/v1/tenants/{tenant_id}/loyalty/{customer_id}",status_code=201)
def add_loyalty(tenant_id,customer_id,payload:LoyaltyCreate,user=Depends(get_current_user),db:Session=Depends(get_db)):
    require_tenant(user,tenant_id)
    from .loyalty import award as _award
    result=_award(db,tenant_id,customer_id,payload.points,payload.reason,payload.reference_id)
    if not result.ok:
        raise HTTPException(400,result.reason.replace("_"," "))
    return {"id":result.transaction_id,"points":result.points,"balance":result.balance}
'''

text, ok = replace_function(
    text,
    '@app.post("/api/v1/tenants/{tenant_id}/loyalty/{customer_id}")',
    NEW_LOYALTY_AWARD,
)
print("  patched add_loyalty (ledger-based)" if ok else "  WARNING: add_loyalty not found")


# ---------------------------------------------------------------------------
# 5. Mark the file
# ---------------------------------------------------------------------------

if "SESSION9_LOYALTY_WALLET" not in text:
    text = text.rstrip() + "\n\n# SESSION9_LOYALTY_WALLET\n"

MAIN.write_text(text, encoding="utf-8")
print()
print(f"Session 9 install complete. main.py now {len(text)} bytes.")