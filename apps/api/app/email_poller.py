"""Background poller: every 60 seconds, check each active tenant mailbox,
fetch unread mail, generate an AI reply, send it, and log the outcome.

Runs as an asyncio task started at FastAPI startup. Uses the tenant's own
AI provider key (the one they configured in Integrations).
"""
from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime

from sqlalchemy import select

from .db import SessionLocal
from .models_email import TenantEmailAccount, EmailLog
from .email_integration import (
    decrypt_email_config,
    fetch_new_messages_sync,
    send_reply_smtp,
)

logger = logging.getLogger("api.email.poller")

POLL_INTERVAL_SECONDS = 60
MAX_PER_CYCLE = 10

_poller_task: asyncio.Task | None = None


async def _handle_account(account_row: TenantEmailAccount) -> None:
    db = SessionLocal()
    try:
        # Reload inside this session so the ORM object is bound
        account = db.get(TenantEmailAccount, account_row.id)
        if not account or not account.is_active or not account.auto_reply_enabled:
            return

        try:
            cfg = decrypt_email_config(account.config_encrypted)
        except Exception as exc:
            account.last_error = f"decrypt failed: {exc}"
            account.last_checked_at = datetime.utcnow()
            db.commit()
            return

        # IMAP is blocking — run in a thread to avoid stalling the event loop
        try:
            messages = await asyncio.to_thread(fetch_new_messages_sync, cfg, MAX_PER_CYCLE)
        except Exception as exc:
            account.last_error = f"imap fetch failed: {exc}"
            account.last_checked_at = datetime.utcnow()
            db.commit()
            return

        account.last_error = None
        account.last_checked_at = datetime.utcnow()
        db.commit()

        for msg in messages:
            await _process_message(db, account, cfg, msg)

    finally:
        db.close()


async def _process_message(db, account: TenantEmailAccount, cfg: dict, msg: dict) -> None:
    # Skip obvious system / newsletter mail — customers don't want replies to these
    from_addr = (msg.get("from") or "").lower()
    subject = (msg.get("subject") or "").lower()
    text_lower = (msg.get("text") or "").lower()

    skip_prefixes = (
        "mailer-daemon@", "postmaster@", "no-reply@", "noreply@",
        "donotreply@", "do-not-reply@", "notifications@", "notification@",
        "bounce@", "bounces@", "alerts@",
    )
    if any(from_addr.startswith(p) or p in from_addr for p in skip_prefixes):
        return

    skip_subject_markers = (
        "delivery status notification",
        "undelivered mail",
        "out of office",
        "auto-reply",
        "automatic reply",
        "returned mail",
    )
    if any(m in subject for m in skip_subject_markers):
        return

    # Newsletters and marketing all include a List-Unsubscribe header
    # or an "unsubscribe" link in the body
    if "unsubscribe" in text_lower[:2000]:
        return
    # Deduplicate by Message-Id
    existing = db.scalar(
        select(EmailLog).where(
            EmailLog.tenant_id == account.tenant_id,
            EmailLog.message_id == (msg["message_id"] or msg["uid"]),
        )
    )
    if existing:
        return

    log = EmailLog(
        id=str(uuid.uuid4()),
        tenant_id=account.tenant_id,
        account_id=account.id,
        message_id=msg["message_id"] or msg["uid"],
        from_address=msg["from"],
        to_address=msg["to"],
        subject=msg["subject"],
        outcome="skipped",
    )

    try:
        # Lazy import — brain is heavy and depends on many modules
        from .brain import generate_reply

        body = msg["text"] or "(no body)"
        prompt = (
            f"Incoming email from {msg['from']}.\n"
            f"Subject: {msg['subject']}\n\n"
            f"{body}\n\n"
            "Write a short, warm, professional reply. "
            "Sign off as the business team. "
            "Do not invent policies, prices, or availability."
        )

        reply_result = await generate_reply(
            db, account.tenant_id, prompt, None, "email"
        )
        reply_text = reply_result.get("reply") or "Thank you for your email. Our team will get back to you shortly."

        await send_reply_smtp(cfg, msg["from"], msg["subject"], reply_text)

        log.outcome = "replied"
        log.reply_text = reply_text

        # support@ -> auto-create a ticket
        if account.role == "support":
            try:
                from .tickets import create_ticket
                ticket = create_ticket(
                    db,
                    tenant_id=account.tenant_id,
                    subject=msg["subject"] or "(no subject)",
                    body=body,
                    category="support",
                    priority="normal",
                    created_by=None,
                )
                log.ticket_id = ticket["id"]
                log.outcome = "ticket_created"
            except Exception as exc:
                logger.warning("support ticket creation failed: %s", exc)

    except Exception as exc:
        log.outcome = "failed"
        log.error = str(exc)
        logger.exception("email auto-reply failed for account=%s", account.id)

    db.add(log)
    db.commit()


async def _poller_loop() -> None:
    logger.info("email poller started, interval=%ss", POLL_INTERVAL_SECONDS)
    while True:
        try:
            db = SessionLocal()
            try:
                accounts = db.scalars(
                    select(TenantEmailAccount).where(
                        TenantEmailAccount.is_active == True,  # noqa: E712
                        TenantEmailAccount.auto_reply_enabled == True,  # noqa: E712
                    )
                ).all()
            finally:
                db.close()

            for a in accounts:
                try:
                    await _handle_account(a)
                except Exception:
                    logger.exception("account poll failed for %s", a.id)

        except Exception:
            logger.exception("email poller cycle failed")

        await asyncio.sleep(POLL_INTERVAL_SECONDS)


def start_email_poller() -> None:
    global _poller_task
    if _poller_task and not _poller_task.done():
        return
    _poller_task = asyncio.create_task(_poller_loop())


def stop_email_poller() -> None:
    global _poller_task
    if _poller_task and not _poller_task.done():
        _poller_task.cancel()
    _poller_task = None