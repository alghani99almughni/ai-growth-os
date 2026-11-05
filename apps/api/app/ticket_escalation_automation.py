"""Tenant-scoped automatic SLA escalation for support tickets.

The worker is safe to run in multiple API processes: a database unique key claims
each ticket once. Original ticket identity, created_at and sla_due_at are never
changed; the department response deadline is recorded on the escalation event.
"""
from __future__ import annotations

import logging
import threading
import time
from datetime import datetime, timedelta
from uuid import uuid4

from sqlalchemy import String, DateTime, UniqueConstraint, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base, SessionLocal
from .models import User
from .models_ai import Department, StaffMember
from .models_growth import SupportTicket
from .operational_alerts import TicketEscalation, create_operational_alerts
from .routes_team_comms import TeamMessage, TeamRoom, TeamRoomMember

log = logging.getLogger("api.ticket_escalation")


class TicketAutoEscalationClaim(Base):
    __tablename__ = "ticket_auto_escalation_claims"
    __table_args__ = (UniqueConstraint("tenant_id", "ticket_id", name="uq_ticket_auto_escalation_tenant_ticket"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    tenant_id: Mapped[str] = mapped_column(String(36), index=True)
    ticket_id: Mapped[str] = mapped_column(String(36), index=True)
    department_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    department_response_due_at: Mapped[datetime] = mapped_column(DateTime)
    escalated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


def _ensure_escalation_room(db, tenant_id: str, actor: User) -> str:
    key = "escalation"
    room = db.scalar(select(TeamRoom).where(
        TeamRoom.tenant_id == tenant_id, TeamRoom.room_key == key
    ))
    if not room:
        room = TeamRoom(tenant_id=tenant_id, room_key=key, name="Escalation",
                        created_by=actor.id)
        db.add(room)
        db.flush()

    # Keep the permanent room accessible to active tenant users. This is deliberately
    # tenant-scoped; no member from another tenant can be added by this worker.
    users = db.scalars(select(User).where(
        User.tenant_id == tenant_id, User.is_active.is_(True)
    )).all()
    existing = set(db.scalars(select(TeamRoomMember.user_id).where(
        TeamRoomMember.tenant_id == tenant_id, TeamRoomMember.room_key == key
    )).all())
    for user in users:
        if user.id not in existing:
            db.add(TeamRoomMember(tenant_id=tenant_id, room_key=key,
                                  user_id=user.id, added_by=actor.id))
    return key


def _department_for_category(db, tenant_id: str, category: str):
    # Exact category-to-department match only; do not guess at fuzzy routes.
    return db.scalar(select(Department).where(
        Department.tenant_id == tenant_id,
        Department.is_active.is_(True),
        Department.name.ilike(category)
    ))


def process_overdue_tickets(batch_size: int = 100) -> dict:
    """Escalate overdue open tickets once. Returns counters for observability."""
    now = datetime.utcnow()
    db = SessionLocal()
    processed = 0
    skipped = 0
    try:
        tickets = db.scalars(select(SupportTicket).where(
            SupportTicket.sla_due_at.is_not(None),
            SupportTicket.sla_due_at <= now,
            SupportTicket.status.notin_(("resolved", "closed")),
        ).order_by(SupportTicket.sla_due_at.asc()).limit(batch_size)).all()

        for ticket in tickets:
            # Claim inside the same transaction as all side effects. The unique
            # constraint serializes competing workers across Render instances.
            try:
                department = _department_for_category(db, ticket.tenant_id, ticket.category)
                response_hours = max(1, int(ticket.sla_hours or 24))
                claim = TicketAutoEscalationClaim(
                    tenant_id=ticket.tenant_id,
                    ticket_id=ticket.id,
                    department_id=department.id if department else None,
                    department_response_due_at=now + timedelta(hours=response_hours),
                    escalated_at=now,
                )
                db.add(claim)
                db.flush()
            except IntegrityError:
                db.rollback()
                skipped += 1
                continue

            actor = db.scalar(select(User).where(
                User.tenant_id == ticket.tenant_id,
                User.is_active.is_(True),
                User.role.in_(("owner", "tenant_admin", "admin"))
            ).order_by(User.created_at.asc()).limit(1))
            if not actor:
                # No safe chat sender/room owner exists yet. Roll back the claim so
                # the ticket can be retried when an administrator is provisioned.
                db.rollback()
                skipped += 1
                continue

            room_key = _ensure_escalation_room(db, ticket.tenant_id, actor)
            previous_status = ticket.status
            ticket.sla_breached = True
            if ticket.status in ("new", "acknowledged", "waiting_on_tenant"):
                ticket.status = "in_progress"
            ticket.updated_at = now

            reason = "Automatic escalation: original ticket SLA expired"
            db.add(TicketEscalation(
                tenant_id=ticket.tenant_id,
                ticket_id=ticket.id,
                from_status=previous_status,
                to_status=ticket.status,
                department_id=department.id if department else None,
                assigned_staff_id=None,
                room_key=room_key,
                reason=reason,
                escalated_by=actor.id,
                created_at=now,
            ))
            db.add(TeamMessage(
                tenant_id=ticket.tenant_id,
                sender_id=actor.id,
                sender_name="AI Growth OS · Automation",
                recipient_id=None,
                room=room_key,
                message=(
                    f"[AUTO-ESCALATION · Ticket #{ticket.id}] {ticket.subject}\n"
                    f"Category: {ticket.category} · Priority: {ticket.priority}\n"
                    f"Waiting since: {ticket.created_at.isoformat()}Z\n"
                    f"Original SLA expired: {ticket.sla_due_at.isoformat()}Z\n"
                    f"Department route: {department.name if department else 'Unmatched — Escalation group'}"
                ),
                formatting="bold",
                attachment_id=None,
                created_at=now,
            ))
            create_operational_alerts(
                db, ticket.tenant_id, "ticket.auto_escalated",
                "Ticket automatically escalated",
                f"{ticket.subject}: original SLA expired",
                {
                    "ticket_id": ticket.id, "category": ticket.category,
                    "priority": ticket.priority,
                    "department_id": department.id if department else None,
                    "department_name": department.name if department else None,
                    "room_key": room_key,
                    "waiting_since": ticket.created_at.isoformat(),
                    "department_response_due_at": claim.department_response_due_at.isoformat(),
                },
                department_id=department.id if department else None,
            )
            db.commit()
            processed += 1
        return {"processed": processed, "skipped": skipped}
    except Exception:
        db.rollback()
        log.exception("Automatic ticket escalation batch failed")
        raise
    finally:
        db.close()


_worker_lock = threading.Lock()
_worker_started = False


def start_ticket_escalation_worker(interval_seconds: int = 60) -> None:
    """Start one polling thread per API process; DB uniqueness protects multi-instance."""
    global _worker_started
    with _worker_lock:
        if _worker_started:
            return
        _worker_started = True

    def run():
        while True:
            try:
                process_overdue_tickets()
            except Exception:
                log.exception("Automatic ticket escalation worker iteration failed")
            time.sleep(max(30, interval_seconds))

    threading.Thread(target=run, name="ticket-auto-escalation", daemon=True).start()
