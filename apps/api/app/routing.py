from sqlalchemy import select
from sqlalchemy.orm import Session
from .models_ai import Department, StaffMember
from .models_growth import CallRecord
INTENT_DEPARTMENT={"pricing":"Sales","booking":"Reception","human_handoff":"Reception","product":"Sales","information":"Reception","support":"Support","payment":"Accounts"}
def route_call(db:Session,tenant_id:str,call:CallRecord,intent:str|None=None):
    target=INTENT_DEPARTMENT.get(intent or call.intent or "information","Reception")
    departments=db.scalars(select(Department).where(Department.tenant_id==tenant_id,Department.is_active==True)).all()
    department=next((d for d in departments if d.name.lower()==target.lower()),None) or next((d for d in departments if target.lower() in (d.skills or "").lower()),None)
    assigned=None
    if department:
        staff=db.scalars(select(StaffMember).where(StaffMember.tenant_id==tenant_id,StaffMember.department_id==department.id,StaffMember.is_active==True,StaffMember.is_available==True).order_by(StaffMember.name)).first()
        if staff:
            assigned=staff
            call.staff_id=staff.id
        call.department=department.name
        db.commit()
    return {"department":department.name if department else target,"department_id":department.id if department else None,"routed":bool(department),"staff":{"id":assigned.id,"name":assigned.name,"department_id":assigned.department_id} if assigned else None}
def available_staff(db:Session,tenant_id:str,department_id:str|None=None):
    q=select(StaffMember).where(StaffMember.tenant_id==tenant_id,StaffMember.is_active==True,StaffMember.is_available==True)
    if department_id:q=q.where(StaffMember.department_id==department_id)
    return [{"id":x.id,"name":x.name,"skills":x.skills,"available":x.is_available} for x in db.scalars(q).all()]
