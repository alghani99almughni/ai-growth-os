"""Session 13 — Security Hardening installer.

Idempotent: safe to run more than once. Each patch checks first.
Run from apps/api:
    python apply_session13.py
"""
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent
APP = ROOT / "app"

if not APP.exists():
    print("ERROR: app/ folder not found. Run this from apps/api.")
    sys.exit(1)

def read(p):
    return p.read_text(encoding="utf-8")

def write(p, t):
    p.write_text(t, encoding="utf-8")
    print(f"  wrote {p.relative_to(ROOT)} ({len(t)} bytes)")

# ---------------------------------------------------------------------------
# 1. app/security.py
# ---------------------------------------------------------------------------

SECURITY_PY = '''"""Security primitives shared across the platform.

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
'''

p = APP / "security.py"
if p.exists():
    print("SKIP security.py (already present)")
else:
    write(p, SECURITY_PY)
    print("  created security.py")

# ---------------------------------------------------------------------------
# 2. models_growth.py — append IdempotencyKey + AuditLog
# ---------------------------------------------------------------------------

p = APP / "models_growth.py"
t = read(p)
if "class IdempotencyKey" in t:
    print("SKIP models_growth.py (already has IdempotencyKey)")
else:
    t = t.rstrip() + '''


class IdempotencyKey(Base):
    __tablename__ = "idempotency_keys"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), index=True)
    scope: Mapped[str] = mapped_column(String(80), index=True)
    key: Mapped[str] = mapped_column(String(200), index=True)
    payload_hash: Mapped[str] = mapped_column(String(64))
    response_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime, index=True)


class AuditLog(Base):
    __tablename__ = "audit_logs"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    tenant_id: Mapped[str | None] = mapped_column(ForeignKey("tenants.id"), nullable=True, index=True)
    actor_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    action: Mapped[str] = mapped_column(String(80), index=True)
    target_type: Mapped[str] = mapped_column(String(80), index=True)
    target_id: Mapped[str] = mapped_column(String(120), index=True)
    detail_json: Mapped[str] = mapped_column(Text, default="{}")
    request_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
'''
    write(p, t)
    print("  appended IdempotencyKey + AuditLog")

# ---------------------------------------------------------------------------
# 3. migrations.py — insert SQL for the two new tables
# ---------------------------------------------------------------------------

p = APP / "migrations.py"
t = read(p)
if "idempotency_keys" in t:
    print("SKIP migrations.py (already has idempotency_keys)")
else:
    pg_anchor = '            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_ai_provider_usage_tenant_provider ON ai_provider_usage(tenant_id, provider)"))\n'
    pg_block = pg_anchor + (
        '            conn.execute(text("CREATE TABLE IF NOT EXISTS idempotency_keys (id VARCHAR(36) PRIMARY KEY, tenant_id VARCHAR(36) NOT NULL, scope VARCHAR(80) NOT NULL, key VARCHAR(200) NOT NULL, payload_hash VARCHAR(64) NOT NULL, response_json TEXT NOT NULL DEFAULT \'{}\', created_at TIMESTAMP NOT NULL, expires_at TIMESTAMP NOT NULL)"))\n'
        '            conn.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS ux_idempotency_tenant_scope_key ON idempotency_keys(tenant_id, scope, key)"))\n'
        '            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_idempotency_expires ON idempotency_keys(expires_at)"))\n'
        '            conn.execute(text("CREATE TABLE IF NOT EXISTS audit_logs (id VARCHAR(36) PRIMARY KEY, tenant_id VARCHAR(36), actor_id VARCHAR(36), action VARCHAR(80) NOT NULL, target_type VARCHAR(80) NOT NULL, target_id VARCHAR(120) NOT NULL, detail_json TEXT NOT NULL DEFAULT \'{}\', request_id VARCHAR(64), created_at TIMESTAMP NOT NULL)"))\n'
        '            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_audit_tenant_created ON audit_logs(tenant_id, created_at)"))\n'
        '            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_audit_action ON audit_logs(action)"))\n'
        '            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_audit_target ON audit_logs(target_type, target_id)"))\n'
    )
    if pg_anchor in t:
        t = t.replace(pg_anchor, pg_block, 1)
        print("  inserted postgres idempotency/audit tables")

    sq_anchor = '            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_ai_provider_usage_tenant_provider ON ai_provider_usage(tenant_id, provider)"))\n'
    sq_block = sq_anchor + (
        '            conn.execute(text("CREATE TABLE IF NOT EXISTS idempotency_keys (id VARCHAR(36) PRIMARY KEY, tenant_id VARCHAR(36) NOT NULL, scope VARCHAR(80) NOT NULL, key VARCHAR(200) NOT NULL, payload_hash VARCHAR(64) NOT NULL, response_json TEXT NOT NULL DEFAULT \'{}\', created_at DATETIME NOT NULL, expires_at DATETIME NOT NULL)"))\n'
        '            conn.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS ux_idempotency_tenant_scope_key ON idempotency_keys(tenant_id, scope, key)"))\n'
        '            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_idempotency_expires ON idempotency_keys(expires_at)"))\n'
        '            conn.execute(text("CREATE TABLE IF NOT EXISTS audit_logs (id VARCHAR(36) PRIMARY KEY, tenant_id VARCHAR(36), actor_id VARCHAR(36), action VARCHAR(80) NOT NULL, target_type VARCHAR(80) NOT NULL, target_id VARCHAR(120) NOT NULL, detail_json TEXT NOT NULL DEFAULT \'{}\', request_id VARCHAR(64), created_at DATETIME NOT NULL)"))\n'
        '            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_audit_tenant_created ON audit_logs(tenant_id, created_at)"))\n'
        '            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_audit_action ON audit_logs(action)"))\n'
        '            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_audit_target ON audit_logs(target_type, target_id)"))\n'
    )
    # In sqlite branch the same anchor exists but with PRAGMA-based setup; find second occurrence.
    occurrences = [m.start() for m in re.finditer(re.escape(sq_anchor), t)]
    if len(occurrences) >= 2:
        second = occurrences[1]
        t = t[:second] + sq_block + t[second + len(sq_anchor):]
        print("  inserted sqlite idempotency/audit tables")
    elif len(occurrences) == 1:
        t = t.replace(sq_anchor, sq_block, 1)
        print("  inserted sqlite idempotency/audit tables (single anchor)")
    write(p, t)

# ---------------------------------------------------------------------------
# 4. main.py — wire security imports + startup validation + strict JWT
# ---------------------------------------------------------------------------

p = APP / "main.py"
t = read(p)

if "from .security import" in t:
    print("SKIP main.py security import (already there)")
else:
    anchor = "from .health import router as health_router\n"
    if anchor in t:
        t = t.replace(anchor, anchor + "from .security import check_secret, cleanup_expired_idempotency, decode_token_strict, verify_hmac_sha256, audit\n", 1)
        write(p, t)
        print("  added security import to main.py")
    else:
        print("WARNING: could not find health_router anchor in main.py")

t = read(p)

if "SECURITY CONFIG ERRORS IN PRODUCTION" in t:
    print("SKIP startup security validation (already there)")
else:
    old = '''@app.on_event("startup")
async def startup():
    ensure_schema()
    db=SessionLocal()
    try:
        if db.scalar(select(GlobalFaq.id).limit(1)) is None:'''
    new = '''@app.on_event("startup")
async def startup():
    ensure_schema()
    if settings.environment == "production":
        warnings = []
        warnings.extend(check_secret("JWT_SECRET", settings.jwt_secret, 32))
        if settings.whatsapp_credential_encryption_key:
            warnings.extend(check_secret("WHATSAPP_CREDENTIAL_ENCRYPTION_KEY",
                                         settings.whatsapp_credential_encryption_key, 40))
        if settings.integration_credential_encryption_key:
            warnings.extend(check_secret("INTEGRATION_CREDENTIAL_ENCRYPTION_KEY",
                                         settings.integration_credential_encryption_key, 40))
        if warnings:
            import logging as _lg
            _lg.getLogger("api.security").error(
                "SECURITY CONFIG ERRORS IN PRODUCTION: %s", "; ".join(warnings))
            raise RuntimeError("refusing to start: " + "; ".join(warnings))
    db=SessionLocal()
    try:
        if db.scalar(select(GlobalFaq.id).limit(1)) is None:'''
    if old in t:
        t = t.replace(old, new, 1)
        write(p, t)
        print("  added production secret validation to startup()")
    else:
        print("WARNING: startup() body did not match - manual patch needed")

t = read(p)

# Strict JWT in get_current_user
if "decode_token_strict(credentials.credentials" in t:
    print("SKIP strict JWT in get_current_user (already there)")
else:
    old = '''    try:
        p=jwt.decode(credentials.credentials,settings.jwt_secret,algorithms=[settings.jwt_algorithm]); uid=p.get("sub")
    except jwt.InvalidTokenError: raise HTTPException(401,"Invalid or expired token")'''
    new = '''    try:
        p=decode_token_strict(credentials.credentials,settings.jwt_secret,settings.jwt_algorithm); uid=p.get("sub")
    except ValueError as exc: raise HTTPException(401,str(exc))'''
    if old in t:
        t = t.replace(old, new, 1)
        write(p, t)
        print("  replaced get_current_user JWT decode with strict version")
    else:
        print("WARNING: get_current_user JWT block did not match - manual patch needed")

t = read(p)

# Webhook verification replacement (Razorpay)
if "verify_hmac_sha256(raw,signature,settings.razorpay_key_secret)" in t or "verify_hmac_sha256(raw, signature, settings.razorpay_key_secret)" in t:
    print("SKIP razorpay webhook verify (already strict)")
else:
    old = '''    if not settings.razorpay_key_secret or not signature: raise HTTPException(401,"Webhook signature required")
    expected=hmac.new(settings.razorpay_key_secret.encode(),raw,hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected,signature): raise HTTPException(400,"Invalid webhook signature")'''
    new = '''    if not settings.razorpay_key_secret or not signature: raise HTTPException(401,"Webhook signature required")
    if not verify_hmac_sha256(raw, signature, settings.razorpay_key_secret): raise HTTPException(400,"Invalid webhook signature")'''
    if old in t:
        t = t.replace(old, new, 1)
        write(p, t)
        print("  hardened razorpay webhook signature check")
    else:
        print("WARNING: razorpay webhook block did not match - manual patch needed")

print()
print("Session 13 install complete.")
print()
print("Next: run the verification:")
print("  python -c \"from app import security; print('ok')\"")
print("  python -c \"from app.main import app; print('routes:', len(app.routes))\"")