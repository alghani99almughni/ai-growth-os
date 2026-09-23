from datetime import datetime, date, time, timedelta, timezone
from zoneinfo import ZoneInfo
from sqlalchemy import select, func, and_
from sqlalchemy.orm import Session
from .models import Tenant, Customer, Service
from .models_ai import StaffMember
from .models_growth import Appointment, BusinessHour, QueueEntry
import uuid

UTC = timezone.utc

def uid():
    return str(uuid.uuid4())

def local_to_utc_naive(dt: datetime, tz_name: str) -> datetime:
    local = dt.replace(tzinfo=ZoneInfo(tz_name))
    return local.astimezone(UTC).replace(tzinfo=None)

def utc_naive_to_local(dt: datetime, tz_name: str) -> datetime:
    return dt.replace(tzinfo=UTC).astimezone(ZoneInfo(tz_name)).replace(tzinfo=None)

def get_hours(db: Session, tenant_id: str):
    rows = db.scalars(select(BusinessHour).where(BusinessHour.tenant_id == tenant_id).order_by(BusinessHour.weekday)).all()
    by_day = {x.weekday: x for x in rows}
    return by_day

def ensure_default_hours(db: Session, tenant_id: str):
    rows = db.scalars(select(BusinessHour).where(BusinessHour.tenant_id == tenant_id)).all()
    if rows:
        return rows
    for weekday in range(7):
        # Monday-Saturday 09:00-18:00; Sunday closed.
        if weekday < 5:
            opening, closing, closed = time(9,0), time(18,0), False
        elif weekday == 5:
            opening, closing, closed = time(9,0), time(14,0), False
        else:
            opening, closing, closed = time(9,0), time(18,0), True
        db.add(BusinessHour(tenant_id=tenant_id, weekday=weekday, open_time=opening, close_time=closing, is_closed=closed, slot_interval_minutes=30))
    db.commit()
    return db.scalars(select(BusinessHour).where(BusinessHour.tenant_id == tenant_id).order_by(BusinessHour.weekday)).all()

def overlapping_appointments(db: Session, tenant_id: str, start_utc: datetime, end_utc: datetime, staff_id: str | None = None):
    q = select(Appointment).where(
        Appointment.tenant_id == tenant_id,
        Appointment.status.in_(["requested", "confirmed", "checked_in", "serving"]),
        Appointment.starts_at < end_utc,
        Appointment.ends_at > start_utc,
    )
    if staff_id:
        q = q.where(Appointment.staff_id == staff_id)
    return db.scalars(q).all()

def slot_is_available(db: Session, tenant_id: str, start_utc: datetime, end_utc: datetime, staff_id: str | None = None):
    return len(overlapping_appointments(db, tenant_id, start_utc, end_utc, staff_id)) == 0

def available_slots(db: Session, tenant: Tenant, service_id: str, day: date, staff_id: str | None = None):
    service = db.scalar(select(Service).where(Service.id == service_id, Service.tenant_id == tenant.id, Service.is_active == True))
    if not service:
        raise ValueError("Service not found or inactive")
    duration = service.duration_minutes or 30
    hours = get_hours(db, tenant.id)
    rule = hours.get(day.weekday())
    if not rule:
        ensure_default_hours(db, tenant.id)
        hours = get_hours(db, tenant.id)
        rule = hours.get(day.weekday())
    if not rule or rule.is_closed:
        return []
    interval = max(5, rule.slot_interval_minutes or 30)
    cursor = datetime.combine(day, rule.open_time)
    close = datetime.combine(day, rule.close_time)
    slots = []
    while cursor + timedelta(minutes=duration) <= close:
        end = cursor + timedelta(minutes=duration)
        start_utc = local_to_utc_naive(cursor, tenant.timezone)
        end_utc = local_to_utc_naive(end, tenant.timezone)
        assigned_staff = staff_id
        if assigned_staff:
            staff = db.scalar(select(StaffMember).where(StaffMember.id == assigned_staff, StaffMember.tenant_id == tenant.id, StaffMember.is_active == True))
            ok_staff = bool(staff and staff.is_available and slot_is_available(db, tenant.id, start_utc, end_utc, assigned_staff))
        else:
            staff_pool = db.scalars(select(StaffMember).where(StaffMember.tenant_id == tenant.id, StaffMember.is_active == True)).all()
            if staff_pool:
                free = [s for s in staff_pool if s.is_available and slot_is_available(db, tenant.id, start_utc, end_utc, s.id)]
                ok_staff = bool(free)
                if free:
                    assigned_staff = free[0].id
            else:
                ok_staff = slot_is_available(db, tenant.id, start_utc, end_utc, None)
        if ok_staff:
            slots.append({"start": cursor.isoformat(timespec="minutes"), "end": end.isoformat(timespec="minutes"), "staff_id": assigned_staff})
        cursor += timedelta(minutes=interval)
    return slots

def next_queue_token(db: Session, tenant_id: str, queue_date: date):
    prefix = queue_date.strftime("%y%m%d")
    last = db.scalar(select(QueueEntry).where(QueueEntry.tenant_id == tenant_id, QueueEntry.queue_date == queue_date).order_by(QueueEntry.sequence.desc()).limit(1))
    sequence = (last.sequence + 1) if last else 1
    return sequence, f"Q{prefix}-{sequence:03d}"

def queue_snapshot(db: Session, tenant: Tenant, queue_date: date):
    rows = db.scalars(select(QueueEntry).where(QueueEntry.tenant_id == tenant.id, QueueEntry.queue_date == queue_date).order_by(QueueEntry.sequence)).all()
    avg = max(1, tenant.queue_avg_service_minutes or 15)
    waiting = [x for x in rows if x.status == "waiting"]
    serving = next((x for x in rows if x.status == "serving"), None)
    now = datetime.utcnow()
    serving_remaining = 0
    if serving and serving.called_at:
        elapsed = max(0, int((now - serving.called_at).total_seconds() / 60))
        serving_remaining = max(0, avg - elapsed)
    for index, item in enumerate(waiting):
        ahead = index + (1 if serving else 0)
        item.people_ahead = ahead
        item.estimated_wait_minutes = serving_remaining + index * avg
    db.commit()
    return rows

def create_appointment(db: Session, tenant: Tenant, customer: Customer, service: Service, starts_at_local: datetime,
                       source: str, staff_id: str | None = None, notes: str | None = None,
                       queue_if_busy: bool = False, force_queue: bool = False):
    duration = service.duration_minutes or 30
    starts_utc = local_to_utc_naive(starts_at_local, tenant.timezone)
    ends_utc = starts_utc + timedelta(minutes=duration)
    if starts_utc < datetime.utcnow() - timedelta(minutes=1):
        raise ValueError("Appointment time must be in the future")
    overlaps = overlapping_appointments(db, tenant.id, starts_utc, ends_utc, staff_id)
    if staff_id and not db.scalar(select(StaffMember).where(StaffMember.id == staff_id, StaffMember.tenant_id == tenant.id, StaffMember.is_active == True)):
        raise ValueError("Staff member not found or inactive")
    if overlaps and not queue_if_busy and not force_queue:
        raise ValueError("Selected time is no longer available")
    appointment = Appointment(
        tenant_id=tenant.id, customer_id=customer.id, service_id=service.id, staff_id=staff_id,
        starts_at=starts_utc, ends_at=ends_utc, status="confirmed", source=source, notes=notes
    )
    db.add(appointment)
    db.flush()
    queue = None
    waiting_count = db.scalar(select(func.count(QueueEntry.id)).where(QueueEntry.tenant_id == tenant.id, QueueEntry.queue_date == starts_at_local.date(), QueueEntry.status.in_(["waiting", "serving"]))) or 0
    huge_queue = bool(tenant.queue_enabled and waiting_count >= (tenant.queue_threshold or 5))
    if force_queue or (queue_if_busy and (len(overlaps) >= (tenant.queue_threshold or 5) or huge_queue)):
        seq, token = next_queue_token(db, tenant.id, starts_at_local.date())
        queue = QueueEntry(tenant_id=tenant.id, appointment_id=appointment.id, customer_id=customer.id,
                           queue_date=starts_at_local.date(), sequence=seq, token=token, status="waiting")
        appointment.queue_token = token
        appointment.queue_status = "waiting"
        db.add(queue)
    db.commit()
    db.refresh(appointment)
    if queue:
        db.refresh(queue)
    return appointment, queue
