"""Append the 5 missing gender-aware handlers to intent_handlers.py.

Handlers added:
    handle_human_handoff  -> voice.render('handoff_requested')
    handle_complaint      -> voice.render('complaint_received')
    handle_policy         -> reads knowledge library (no gender)
    handle_refund         -> voice.render('refund_forwarded')
    handle_emergency      -> voice.render('emergency_flagged')
"""

import pathlib

path = pathlib.Path("intent_handlers.py")
text = path.read_text(encoding="utf-8")

if "handle_human_handoff" in text:
    print("SKIP: handlers already present")
    raise SystemExit(0)

NEW_HANDLERS = '''


# ---------------------------------------------------------------------------
# 11. human_handoff
# ---------------------------------------------------------------------------

async def handle_human_handoff(db: Session, tenant, message: str, language: str, entities: dict, context: dict) -> Optional[str]:
    """Create a CallRecord so staff can pick up the conversation."""
    try:
        from .models_growth import CallRecord

        customer = context.get("customer") if isinstance(context, dict) else None

        record = CallRecord(
            tenant_id=tenant.id,
            customer_id=customer.id if customer else None,
            customer_name=(customer.name if customer else "Guest") or "Guest",
            mobile=(customer.mobile if customer else "") or "",
            language=language,
            intent="human_handoff",
            summary=(message or "")[:300],
            status="waiting",
        )
        db.add(record)
        db.commit()

        voice = _voice_for(language, context)
        if voice is not None:
            return voice.render("handoff_requested")
        return "I've passed this to the team. A member will join shortly."
    except Exception as exc:
        logger.debug("human_handoff handler failed: %s", exc)
        try:
            db.rollback()
        except Exception:
            pass
        return None


# ---------------------------------------------------------------------------
# 12. complaint
# ---------------------------------------------------------------------------

async def handle_complaint(db: Session, tenant, message: str, language: str, entities: dict, context: dict) -> Optional[str]:
    """Log complaint as a Lead and return an empathetic reply."""
    try:
        from .models import Lead

        customer = context.get("customer") if isinstance(context, dict) else None

        lead = Lead(
            tenant_id=tenant.id,
            customer_id=customer.id if customer else None,
            customer_name=(customer.name if customer else "Guest") or "Guest",
            mobile=(customer.mobile if customer else "") or "",
            intent="complaint",
            source="ai_voice",
            status="new",
            notes=(message or "")[:500],
        )
        db.add(lead)
        db.commit()

        voice = _voice_for(language, context)
        if voice is not None:
            return voice.render("complaint_received")
        return "I'm sorry you had that experience. I've shared this with the team and they'll reach out shortly."
    except Exception as exc:
        logger.debug("complaint handler failed: %s", exc)
        try:
            db.rollback()
        except Exception:
            pass
        return None


# ---------------------------------------------------------------------------
# 13. policy
# ---------------------------------------------------------------------------

async def handle_policy(db: Session, tenant, message: str, language: str, entities: dict, context: dict) -> Optional[str]:
    """Answer policy questions from the tenant knowledge library."""
    try:
        from .ai_router import knowledge_match

        answer = knowledge_match(db, tenant.id, message)
        if answer:
            return answer
        return None
    except Exception as exc:
        logger.debug("policy handler failed: %s", exc)
        return None


# ---------------------------------------------------------------------------
# 14. refund
# ---------------------------------------------------------------------------

async def handle_refund(db: Session, tenant, message: str, language: str, entities: dict, context: dict) -> Optional[str]:
    """Try tenant knowledge library for refund policy; else log a Lead."""
    try:
        from .ai_router import knowledge_match

        answer = knowledge_match(db, tenant.id, message)
        if answer:
            return answer

        from .models import Lead
        customer = context.get("customer") if isinstance(context, dict) else None
        lead = Lead(
            tenant_id=tenant.id,
            customer_id=customer.id if customer else None,
            customer_name=(customer.name if customer else "Guest") or "Guest",
            mobile=(customer.mobile if customer else "") or "",
            intent="refund",
            source="ai_voice",
            status="new",
            notes=(message or "")[:300],
        )
        db.add(lead)
        db.commit()

        voice = _voice_for(language, context)
        if voice is not None:
            return voice.render("refund_forwarded")
        return "I've passed this to the team to confirm the refund policy. They'll reach out shortly."
    except Exception as exc:
        logger.debug("refund handler failed: %s", exc)
        try:
            db.rollback()
        except Exception:
            pass
        return None


# ---------------------------------------------------------------------------
# 15. emergency
# ---------------------------------------------------------------------------

async def handle_emergency(db: Session, tenant, message: str, language: str, entities: dict, context: dict) -> Optional[str]:
    """Log an urgent Lead and CallRecord so staff is alerted immediately."""
    try:
        from .models import Lead
        from .models_growth import CallRecord

        customer = context.get("customer") if isinstance(context, dict) else None

        lead = Lead(
            tenant_id=tenant.id,
            customer_id=customer.id if customer else None,
            customer_name=(customer.name if customer else "Guest") or "Guest",
            mobile=(customer.mobile if customer else "") or "",
            intent="emergency",
            source="ai_voice",
            status="new",
            notes=(message or "")[:500],
        )
        db.add(lead)

        call = CallRecord(
            tenant_id=tenant.id,
            customer_id=customer.id if customer else None,
            customer_name=(customer.name if customer else "Guest") or "Guest",
            mobile=(customer.mobile if customer else "") or "",
            language=language,
            intent="emergency",
            summary="URGENT: " + (message or "")[:280],
            status="waiting",
        )
        db.add(call)
        db.commit()

        voice = _voice_for(language, context)
        if voice is not None:
            return voice.render("emergency_flagged")
        return "I've flagged this as urgent. The team will reach out immediately."
    except Exception as exc:
        logger.debug("emergency handler failed: %s", exc)
        try:
            db.rollback()
        except Exception:
            pass
        return None
'''

text = text.rstrip() + "\n" + NEW_HANDLERS + "\n"

path.write_text(text, encoding="utf-8")
print("Appended 5 handlers")
print("New size:", len(text), "bytes")
print("Total voice.render calls:", text.count("voice.render"))