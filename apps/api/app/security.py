"""Security primitives shared across the platform.

Single source of truth for idempotency, tenant isolation, signed webhooks,
audit logging, strict JWT decoding, and secret strength checks.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

IDEMPOTENCY_TTL_HOURS = 24


def _hash_payload(payload: dict) -> str:
    try:
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    except Exception:
        canonical = repr(payload)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


@dataclass
class IdempotencyResult:
    first_seen: bool
    conflict: bool
    cached_response: Optional[dict] = None


def check_idempotency(db, tenant_id, scope, key, payload):
    from .models_growth import IdempotencyKey
    if not tenant_id or not scope or not key:
        raise ValueError("tenant_id, scope and key are required")
    payload_hash = _hash_payload(payload)
    now = datetime.utcnow()
    existing = db.scalar(select(IdempotencyKey).where(
        IdempotencyKey.tenant_id == tenant_id,
        IdempotencyKey.scope == scope,
        IdempotencyKey.key == key,
    ))
    if existing:
        if existing.payload_hash != payload_hash:
            logger.warning("idempotency conflict tenant=%s scope=%s key=%s", tenant_id, scope, key)
            return IdempotencyResult(False, True)
        try:
            cached = json.loads(existing.response_json or "{}")
        except Exception:
            cached = {}
        return IdempotencyResult(False, False, cached)
    row = IdempotencyKey(
        id=str(uuid.uuid4()), tenant_id=tenant_id, scope=scope, key=key,
        payload_hash=payload_hash, response_json="{}",
        created_at=now, expires_at=now + timedelta(hours=IDEMPOTENCY_TTL_HOURS),
    )
    db.add(row)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        existing = db.scalar(select(IdempotencyKey).where(
            IdempotencyKey.tenant_id == tenant_id,
            IdempotencyKey.scope == scope,
            IdempotencyKey.key == key,
        ))
        if existing and existing.payload_hash != payload_hash:
            return IdempotencyResult(False, True)
        try:
            cached = json.loads(existing.response_json or "{}") if existing else {}
        except Exception:
            cached = {}
        return IdempotencyResult(False, False, cached)
    return IdempotencyResult(True, False)


def store_idempotent_response(db, tenant_id, scope, key, response):
    from .models_growth import IdempotencyKey
    try:
        row = db.scalar(select(IdempotencyKey).where(
            IdempotencyKey.tenant_id == tenant_id,
            IdempotencyKey.scope == scope,
            IdempotencyKey.key == key,
        ))
        if row is None:
            return
        row.response_json = json.dumps(response, default=str)[:20000]
        db.commit()
    except Exception as exc:
        try:
            db.rollback()
        except Exception:
            pass
        logger.debug("store_idempotent_response failed: %s", exc)


def cleanup_expired_idempotency(db):
    from .models_growth import IdempotencyKey
    try:
        now = datetime.utcnow()
        rows = db.scalars(select(IdempotencyKey).where(IdempotencyKey.expires_at < now)).all()
        for r in rows:
            db.delete(r)
        db.commit()
        return len(rows)
    except Exception as exc:
        try:
            db.rollback()
        except Exception:
            pass
        logger.debug("cleanup_expired_idempotency failed: %s", exc)
        return 0


def require_tenant_match(user_tenant_id, target_tenant_id):
    from fastapi import HTTPException
    if not user_tenant_id or not target_tenant_id or user_tenant_id != target_tenant_id:
        raise HTTPException(403, "Tenant access denied")


def ensure_tenant_owns(db, model, row_id, tenant_id):
    try:
        row = db.get(model, row_id)
    except Exception:
        return None
    if row is None:
        return None
    if getattr(row, "tenant_id", None) != tenant_id:
        return None
    return row


def tenant_scoped_select(model, tenant_id):
    if not hasattr(model, "tenant_id"):
        raise ValueError(f"{model.__name__} has no tenant_id column")
    return select(model).where(model.tenant_id == tenant_id)


def verify_hmac_sha256(raw_body, signature_header, secret):
    if not secret or not signature_header:
        return False
    supplied = signature_header.strip()
    if supplied.startswith("sha256="):
        supplied = supplied[len("sha256="):]
    expected = hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(supplied, expected)


def verify_razorpay_signature(order_id, payment_id, signature, secret):
    if not (order_id and payment_id and signature and secret):
        return False
    expected = hmac.new(
        secret.encode("utf-8"),
        (order_id + "|" + payment_id).encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(expected, signature)


def audit(db, *, tenant_id, actor_id, action, target_type, target_id,
          detail=None, request_id=None):
    try:
        from .models_growth import AuditLog
        db.add(AuditLog(
            id=str(uuid.uuid4()), tenant_id=tenant_id, actor_id=actor_id,
            action=action, target_type=target_type, target_id=target_id,
            detail_json=json.dumps(detail or {}, default=str)[:8000],
            request_id=request_id, created_at=datetime.utcnow(),
        ))
        db.commit()
    except Exception as exc:
        try:
            db.rollback()
        except Exception:
            pass
        logger.debug("audit write failed: %s", exc)


def decode_token_strict(token, secret, algorithm="HS256"):
    import jwt
    try:
        payload = jwt.decode(
            token, secret, algorithms=[algorithm],
            options={
                "require": ["exp", "iat", "sub", "tenant_id"],
                "verify_exp": True,
                "verify_iat": True,
            },
            leeway=10,
        )
    except jwt.ExpiredSignatureError:
        raise ValueError("token expired")
    except jwt.InvalidTokenError as exc:
        raise ValueError(f"invalid token: {exc}")
    return payload


_WEAK_SECRETS = {"", "change-me-in-production", "secret", "changeme", "test",
                 "dev", "development", "password"}


def check_secret(name, value, min_length=32):
    warnings = []
    if not value:
        warnings.append(f"{name}: not set")
        return warnings
    if value.lower() in _WEAK_SECRETS:
        warnings.append(f"{name}: weak/placeholder value")
    if len(value) < min_length:
        warnings.append(f"{name}: shorter than {min_length} chars")
    return warnings
