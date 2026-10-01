from sqlalchemy import select,func
from sqlalchemy.orm import Session
from .models_ai import Department, StaffMember, RoutingRule
from .models_growth import CallRecord
INTENT_DEPARTMENT={"pricing":"Sales","booking":"Reception","human_handoff":"Reception","product":"Sales","information":"Reception","support":"Support","payment":"Accounts"}
ACTIVE_CALL_STATUSES=("handoff_requested","handoff_accepted","connecting","connected")
def route_call(db:Session,tenant_id:str,call:CallRecord,intent:str|None=None):
    current_intent=intent or call.intent or "information"
    message=(call.summary or "")+" "+(call.transcript or "")
    rules=db.scalars(select(RoutingRule).where(RoutingRule.tenant_id==tenant_id,RoutingRule.is_active==True).order_by(RoutingRule.priority.asc())).all()
    matched=next((rule for rule in rules if (rule.intent and rule.intent==current_intent) or any(k.strip().casefold() in message.casefold() for k in (rule.trigger_keywords or "").split(",") if k.strip())),None)
    target=INTENT_DEPARTMENT.get(current_intent,"Reception")
    department_id=matched.department_id if matched else None
    forced_staff_id=matched.staff_id if matched else None
    urgency=matched.urgency if matched else "normal"
    departments=db.scalars(select(Department).where(Department.tenant_id==tenant_id,Department.is_active==True)).all()
    department=db.get(Department,department_id) if department_id else next((d for d in departments if d.name.lower()==target.lower()),None) or next((d for d in departments if target.lower() in (d.skills or "").lower()),None)
    assigned=None
    if forced_staff_id:
        assigned=db.scalar(select(StaffMember).where(StaffMember.id==forced_staff_id,StaffMember.tenant_id==tenant_id,StaffMember.is_active==True,StaffMember.is_available==True))
    if department and not assigned:
        candidates=db.scalars(select(StaffMember).where(StaffMember.tenant_id==tenant_id,StaffMember.department_id==department.id,StaffMember.is_active==True,StaffMember.is_available==True).order_by(StaffMember.name)).all()
        for staff in candidates:
            active=db.scalar(select(func.count(CallRecord.id)).where(CallRecord.tenant_id==tenant_id,CallRecord.staff_id==staff.id,CallRecord.status.in_(ACTIVE_CALL_STATUSES))) or 0
            if active < staff.max_concurrent_calls:
                assigned=staff
                break
    call.department=department.name if department else target
    call.staff_id=assigned.id if assigned else None
    db.commit()
    return {"department":call.department,"department_id":department.id if department else None,"routed":bool(department),"urgency":urgency,"rule_id":matched.id if matched else None,"rule_name":matched.name if matched else None,"staff":{"id":assigned.id,"name":assigned.name,"department_id":assigned.department_id} if assigned else None}
def available_staff(db:Session,tenant_id:str,department_id:str|None=None):
    q=select(StaffMember).where(StaffMember.tenant_id==tenant_id,StaffMember.is_active==True,StaffMember.is_available==True)
    if department_id:q=q.where(StaffMember.department_id==department_id)
    result=[]
    for x in db.scalars(q).all():
        active=db.scalar(select(func.count(CallRecord.id)).where(CallRecord.tenant_id==tenant_id,CallRecord.staff_id==x.id,CallRecord.status.in_(ACTIVE_CALL_STATUSES))) or 0
        if active < x.max_concurrent_calls: result.append({"id":x.id,"name":x.name,"skills":x.skills,"available":x.is_available,"active_calls":active,"max_concurrent_calls":x.max_concurrent_calls})
    return result
