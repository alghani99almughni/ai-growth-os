"""Router orchestrator.

Single entry point for every customer message. Enforces the 5-layer
zero-token-first policy so the AI never stops and never burns tokens
unnecessarily.

Layer order (stops at the first successful layer):
    1. Deterministic handlers       (0 tokens)
    2. Tenant knowledge library     (0 tokens)
    3. Global FAQ library           (0 tokens)
    4. Graceful callback/handoff    (0 tokens)
    5. LLM fallback                 (optional, tenant-paid)

The LLM layer only fires if the tenant has explicitly enabled it AND has
at least one provider configured (own key OR platform pool).

Every message is recorded to telemetry with the path taken, latency, tokens
used, and the intent. Nothing is swallowed.

Never raises: any internal error is caught and returns the Layer 4 reply
so the customer always hears a real answer.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Result type
# ---------------------------------------------------------------------------

@dataclass
class RouteResult:
    reply: str
    intent: str
    confidence: float
    language: str
    source: str                    # handler | knowledge | faq | llm | callback | error
    handler: Optional[str] = None
    latency_ms: int = 0
    tokens_used: int = 0
    cost_usd: float = 0.0
    conversation_id: Optional[str] = None
    agent_gender: str = "female"
    entities: dict = field(default_factory=dict)
    handoff_required: bool = False
    callback_created: bool = False
    extra: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "reply": self.reply,
            "intent": self.intent,
            "confidence": self.confidence,
            "language": self.language,
            "source": self.source,
            "handler": self.handler,
            "latency_ms": self.latency_ms,
            "tokens_used": self.tokens_used,
            "cost_usd": self.cost_usd,
            "conversation_id": self.conversation_id,
            "agent_gender": self.agent_gender,
            "entities": self.entities,
            "handoff_required": self.handoff_required,
            "callback_created": self.callback_created,
        }


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_CALLBACK_REPLY_EN = (
    "I'll have the team call you back shortly. "
    "May I confirm the best number to reach you on?"
)
_CALLBACK_REPLY_BY_LANG = {
    "hi": "मैं टीम से आपको कॉलबैक करवाऊंगी। कृपया अपना सही नंबर बताइए।",
    "te": "బృందం మీకు త్వరలో కాల్ చేస్తుంది. దయచేసి మీ నంబర్ నిర్ధారించండి.",
    "ta": "குழு விரைவில் உங்களை அழைக்கும். உங்கள் எண்ணை உறுதிப்படுத்துங்கள்.",
    "kn": "ತಂಡ ಶೀಘ್ರವಾಗಿ ಕರೆ ಮಾಡುತ್ತದೆ. ದಯವಿಟ್ಟು ನಿಮ್ಮ ಸಂಖ್ಯೆಯನ್ನು ದೃಢಪಡಿಸಿ.",
    "ml": "ടീം ഉടൻ വിളിക്കും. ദയവായി നിങ്ങളുടെ നമ്പർ സ്ഥിരീകരിക്കുക.",
    "mr": "टीम तुम्हाला लवकर कॉल करेल. कृपया तुमचा नंबर द्या.",
    "bn": "টিম শীঘ্রই কল করবে। অনুগ্রহ করে আপনার নম্বর দিন।",
    "gu": "ટીમ જલદી કૉલ કરશે. કૃપા કરીને તમારો નંબર આપો.",
    "pa": "ਟੀਮ ਜਲਦੀ ਕਾਲ ਕਰੇਗੀ। ਕਿਰਪਾ ਕਰਕੇ ਆਪਣਾ ਨੰਬਰ ਦਿਓ।",
    "ur": "ٹیم جلد کال کرے گی۔ براہ کرم اپنا نمبر دیں۔",
}

_MIN_CONFIDENCE = 0.35    # below this, don't trust the handler


# ---------------------------------------------------------------------------
# Tenant LLM enablement
# ---------------------------------------------------------------------------

def _tenant_llm_enabled(db: Session, tenant) -> tuple:
    """Return (enabled: bool, reason: str).

    Enabled when either:
      1. Explicit flag on Tenant row is True, OR
      2. At least one active TenantIntegration for an AI provider exists.

    Disabled otherwise.
    """
    # Explicit flag
    flag = getattr(tenant, "llm_fallback_enabled", None)
    if flag is True:
        return True, "explicit_flag"

    # Implicit — check TenantIntegration table
    try:
        from .models_integrations import TenantIntegration
        row = db.scalar(
            select(TenantIntegration).where(
                TenantIntegration.tenant_id == tenant.id,
                TenantIntegration.status == "connected",
            ).limit(1)
        )
        if row is not None:
            return True, "integration_present"
    except Exception:
        pass

    return False, "not_configured"


# ---------------------------------------------------------------------------
# Context builder
# ---------------------------------------------------------------------------

def _build_context(db, tenant, customer, conversation_id, channel, language, gender):
    return {
        "customer": customer,
        "conversation_id": conversation_id,
        "channel": channel,
        "language": language,
        "agent_gender": gender or getattr(tenant, "agent_gender", "female") or "female",
    }


# ---------------------------------------------------------------------------
# Persistence helpers
# ---------------------------------------------------------------------------

def _persist_turn(db: Session, conversation_id: Optional[str], role: str, content: str,
                  language: str, intent: str, tenant_id: str):
    """Best-effort write of a conversation message."""
    if not conversation_id:
        return
    try:
        from .models_ai import ConversationMessage
        db.add(ConversationMessage(
            conversation_id=conversation_id,
            role=role,
            content=content or "",
            language=language or "en",
            intent=intent or "",
        ))
        db.commit()
    except Exception as exc:
        try:
            db.rollback()
        except Exception:
            pass
        logger.debug("persist_turn failed: %s", exc)


def _get_or_create_conversation(db: Session, tenant, conversation_id: Optional[str],
                                channel: str, language: str):
    """Return an existing conversation or create one."""
    try:
        from .models_ai import Conversation
        c = None
        if conversation_id:
            c = db.get(Conversation, conversation_id)
        if not c or c.tenant_id != tenant.id:
            c = Conversation(tenant_id=tenant.id, channel=channel, language=language)
            db.add(c)
            db.commit()
            db.refresh(c)
        return c
    except Exception as exc:
        logger.debug("conversation create failed: %s", exc)
        try:
            db.rollback()
        except Exception:
            pass
        return None


# ---------------------------------------------------------------------------
# Layer 1 — handler dispatch
# ---------------------------------------------------------------------------

async def _try_handler(db, tenant, intent, message, language, entities, context):
    """Return (reply, handler_name) if a registered handler answers, else (None, None)."""
    try:
        from .intent_registry import get_handler
    except Exception as exc:
        logger.debug("registry import failed: %s", exc)
        return None, None

    handler_fn = get_handler(intent)
    if handler_fn is None:
        return None, None

    try:
        reply = await handler_fn(db, tenant, message, language, entities, context)
    except Exception as exc:
        logger.exception("handler %s raised: %s", intent, exc)
        return None, None

    if reply and isinstance(reply, str) and reply.strip():
        return reply.strip(), intent
    return None, None


# ---------------------------------------------------------------------------
# Layer 2 — tenant knowledge library
# ---------------------------------------------------------------------------

def _try_knowledge(db, tenant, message, language):
    try:
        from .semantic_knowledge import semantic_match
    except Exception:
        semantic_match = None
    if semantic_match is not None:
        try:
            result = semantic_match(db, tenant.id, message, language)
            if result and result.get("content"):
                return result["content"]
        except Exception as exc:
            logger.debug("semantic_match failed: %s", exc)

    try:
        from .ai_router import knowledge_match
        answer = knowledge_match(db, tenant.id, message)
        if answer:
            return answer
    except Exception as exc:
        logger.debug("knowledge_match failed: %s", exc)
    return None


# ---------------------------------------------------------------------------
# Layer 3 — global FAQ
# ---------------------------------------------------------------------------

def _try_global_faq(db, tenant, message, language):
    try:
        from .ai_router import faq_match
        row = faq_match(db, getattr(tenant, "industry", "general"), message, language)
        if row is not None and getattr(row, "answer", None):
            return row.answer
    except Exception as exc:
        logger.debug("faq_match failed: %s", exc)
    return None


# ---------------------------------------------------------------------------
# Layer 4 — graceful callback
# ---------------------------------------------------------------------------

def _create_callback_lead(db, tenant, customer, message, language, reason):
    """Create a Lead so staff can follow up. Never raises."""
    try:
        from .models import Lead
        lead = Lead(
            tenant_id=tenant.id,
            customer_id=customer.id if customer else None,
            customer_name=(customer.name if customer else "Guest") or "Guest",
            mobile=(customer.mobile if customer else "") or "",
            intent=reason or "callback",
            source="ai_voice",
            status="new",
            notes=(message or "")[:500],
        )
        db.add(lead)
        db.commit()
        return True
    except Exception as exc:
        try:
            db.rollback()
        except Exception:
            pass
        logger.debug("callback lead creation failed: %s", exc)
        return False


def _callback_reply(language: str, gender: str) -> str:
    """Return the Layer 4 catch-all reply in the customer's language."""
    try:
        from .agent_voice import AgentVoice
        v = AgentVoice(language=language or "en", gender=gender or "female")
        rendered = v.render("not_configured")
        if rendered and not rendered.startswith("not_configured"):
            return rendered
    except Exception:
        pass
    return _CALLBACK_REPLY_BY_LANG.get(language, _CALLBACK_REPLY_EN)


# ---------------------------------------------------------------------------
# Layer 5 — LLM fallback
# ---------------------------------------------------------------------------

async def _try_llm(db, tenant, customer, message, language, gender, conversation_id):
    """Attempt LLM. Return (reply, tokens, cost, provider) or (None, 0, 0.0, None).

    Uses ai_provider_pool.last_resort_reply which already handles the
    ordered fallback across tenant key → platform pool.
    """
    try:
        from .ai_provider_pool import last_resort_reply
        from .brain import knowledge_context
    except Exception as exc:
        logger.debug("LLM imports failed: %s", exc)
        return None, 0, 0.0, None

    # Build the prompt with tenant context.
    try:
        ctx = knowledge_context(db, tenant.id)
    except Exception as exc:
        logger.debug("knowledge_context failed: %s", exc)
        ctx = ""

    history = ""
    try:
        from .models_ai import ConversationMessage
        rows = db.scalars(
            select(ConversationMessage)
            .where(ConversationMessage.conversation_id == conversation_id)
            .order_by(ConversationMessage.created_at.desc())
            .limit(8)
        ).all()
        history = "\n".join(
            f"{r.role.upper()}: {r.content}" for r in reversed(rows)
        )
    except Exception:
        pass

    prompt = (
        "You are an AI receptionist. Reply in the customer's language. "
        "Use ONLY the approved business context below. Never invent prices, "
        "availability, policies, bookings, or payment success. "
        "Keep replies short and conversational. "
        f"The current receptionist persona is {gender}. In gendered languages, "
        "use first-person grammar that matches that gender. "
        "If the context does not contain enough information, say you will have "
        "the team follow up instead of guessing.\n\n"
        "APPROVED CONTEXT:\n" + ctx +
        "\n\nRECENT CONVERSATION:\n" + history +
        f"\n\nCUSTOMER LANGUAGE: {language}\nCUSTOMER:\n" + message
    )

    try:
        reply, provider = await last_resort_reply(db, tenant.id, prompt)
    except Exception as exc:
        logger.debug("LLM call failed: %s", exc)
        return None, 0, 0.0, None

    if not reply:
        return None, 0, 0.0, None

    # Rough token estimate. Used only for telemetry.
    approx_tokens = int((len(prompt) + len(reply)) / 4)
    cost = approx_tokens * 0.0000005

    return reply, approx_tokens, cost, provider


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

async def route_message(
    db: Session,
    tenant,
    customer,
    message: str,
    conversation_id: Optional[str] = None,
    channel: str = "pwa",
) -> RouteResult:
    """Route one message through all 5 layers. Never raises."""
    started = time.time()
    gender = getattr(tenant, "agent_gender", "female") or "female"
    language = "en"
    intent = "unknown"
    confidence = 0.0
    entities = {}

    try:
        # ---- Classify -----------------------------------------------------
        try:
            from .intent_classifier import classify
            result = classify(message or "", None)
            intent = result.intent
            confidence = result.confidence
            language = result.language
            entities = result.entities
        except Exception as exc:
            logger.debug("classifier failed: %s", exc)

        # ---- Conversation persistence ------------------------------------
        conv = _get_or_create_conversation(db, tenant, conversation_id, channel, language)
        conv_id = conv.id if conv else conversation_id
        _persist_turn(db, conv_id, "user", message, language, intent, tenant.id)

        # ---- Context ------------------------------------------------------
        context = _build_context(db, tenant, customer, conv_id, channel, language, gender)

        # ---- Layer 1: handlers --------------------------------------------
        reply, handler_name = await _try_handler(
            db, tenant, intent, message, language, entities, context
        )
        if reply:
            _persist_turn(db, conv_id, "assistant", reply, language, intent, tenant.id)
            _record_telemetry(db, tenant, conv_id, message, intent, confidence,
                              language, "handler", handler_name, started, 0, 0.0)
            return _finalize(RouteResult(
                reply=reply, intent=intent, confidence=confidence,
                language=language, source="handler", handler=handler_name,
                conversation_id=conv_id, agent_gender=gender,
                entities=entities,
            ), started)

        # ---- Layer 2: tenant knowledge ------------------------------------
        knowledge = _try_knowledge(db, tenant, message, language)
        if knowledge:
            _persist_turn(db, conv_id, "assistant", knowledge, language, intent, tenant.id)
            _record_telemetry(db, tenant, conv_id, message, intent, confidence,
                              language, "knowledge", None, started, 0, 0.0)
            return _finalize(RouteResult(
                reply=knowledge, intent=intent, confidence=confidence,
                language=language, source="knowledge",
                conversation_id=conv_id, agent_gender=gender, entities=entities,
            ), started)

        # ---- Layer 3: global FAQ ------------------------------------------
        faq = _try_global_faq(db, tenant, message, language)
        if faq:
            _persist_turn(db, conv_id, "assistant", faq, language, intent, tenant.id)
            _record_telemetry(db, tenant, conv_id, message, intent, confidence,
                              language, "faq", None, started, 0, 0.0)
            return _finalize(RouteResult(
                reply=faq, intent=intent, confidence=confidence,
                language=language, source="faq",
                conversation_id=conv_id, agent_gender=gender, entities=entities,
            ), started)

        # ---- Layer 5 (optional): LLM --------------------------------------
        # Only fires if the tenant has explicitly enabled LLM fallback.
        # If LLM returns nothing OR is disabled, we drop straight to Layer 4.
        llm_enabled, _reason = _tenant_llm_enabled(db, tenant)
        if llm_enabled:
            llm_reply, tokens, cost, provider = await _try_llm(
                db, tenant, customer, message, language, gender, conv_id
            )
            if llm_reply:
                _persist_turn(db, conv_id, "assistant", llm_reply, language, intent, tenant.id)
                _record_telemetry(db, conv_id and tenant, conv_id, message, intent,
                                  confidence, language, "llm",
                                  provider, started, tokens, cost)
                return _finalize(RouteResult(
                    reply=llm_reply, intent=intent, confidence=confidence,
                    language=language, source="llm", handler=provider,
                    latency_ms=int((time.time() - started) * 1000),
                    tokens_used=tokens, cost_usd=cost,
                    conversation_id=conv_id, agent_gender=gender, entities=entities,
                ), started)

        # ---- Layer 4: graceful callback -----------------------------------
        reply = _callback_reply(language, gender)
        created = _create_callback_lead(db, tenant, customer, message, language, intent)
        _persist_turn(db, conv_id, "assistant", reply, language, intent, tenant.id)
        _record_telemetry(db, tenant, conv_id, message, intent, confidence,
                          language, "callback", None, started, 0, 0.0)
        return _finalize(RouteResult(
            reply=reply, intent=intent, confidence=confidence,
            language=language, source="callback",
            conversation_id=conv_id, agent_gender=gender, entities=entities,
            callback_created=created, handoff_required=True,
        ), started)

    except Exception as exc:
        logger.exception("route_message crashed: %s", exc)
        # Absolute last-resort reply. Never lets the customer hear silence.
        fallback = _callback_reply(language, gender)
        return RouteResult(
            reply=fallback,
            intent=intent or "unknown",
            confidence=0.0,
            language=language or "en",
            source="error",
            latency_ms=int((time.time() - started) * 1000),
            conversation_id=conversation_id,
            agent_gender=gender,
            handoff_required=True,
        )


def _finalize(result: RouteResult, started: float) -> RouteResult:
    if result.latency_ms == 0:
        result.latency_ms = int((time.time() - started) * 1000)
    return result


def _record_telemetry(db, tenant, conversation_id, message, intent, confidence,
                      language, source, handler, started, tokens, cost):
    try:
        from .intent_telemetry import record
        record(
            tenant_id=getattr(tenant, "id", ""),
            conversation_id=conversation_id or "",
            message=message or "",
            intent=intent or "unknown",
            confidence=float(confidence or 0.0),
            language=language or "en",
            source=source,
            handler=handler,
            latency_ms=int((time.time() - started) * 1000),
            tokens_used=tokens,
            cost_usd=cost,
            db=db,
        )
    except Exception as exc:
        logger.debug("telemetry record failed: %s", exc)