@app.get("/api/v1/tenants/{tenant_id}/calls")
def calls(tenant_id, user=Depends(get_current_user), db: Session=Depends(get_db)):
    require_tenant(user, tenant_id)
    rows=db.scalars(select(CallRecord).where(CallRecord.tenant_id==tenant_id).order_by(CallRecord.created_at.desc())).all()
    items=[]
    for x in rows:
        customer=db.get(Customer,x.customer_id) if x.customer_id else None
        items.append({
            "id":x.id,
            "customer_id":x.customer_id,
            "customer_name":customer.name if customer and customer.name else "Customer",
            "customer_phone":customer.phone if customer else "",
            "customer_email":customer.email if customer else None,
            "customer_whatsapp_opt_in":bool(customer.whatsapp_opt_in) if customer else False,
            "customer_created_at":customer.created_at if customer else None,
            "source":x.source,
            "status":x.status,
            "department":x.department,
            "staff_id":x.staff_id,
            "room_id":x.room_id,
            "intent":x.intent,
            "summary":x.summary,
            "transcript":x.transcript,
            "created_at":x.created_at,
        })
    return {"items":items}
