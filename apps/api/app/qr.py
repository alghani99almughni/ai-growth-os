"""QR architecture engine (blueprint Section 8).

Design points:
    - Opaque tokens: never expose tenant slug or DB IDs in the QR URL.
    - Three kinds: business / context / campaign.
    - Every scan is appended to qr_scans (never modified).
    - PNG generation uses the qrcode library locally.
    - Scan recording is idempotent per (qr_id, minute) to prevent accidental
      double-counts on fast reloads.

Endpoints this module powers:
    POST   /tenants/{tid}/qr                create
    GET    /tenants/{tid}/qr                list
    GET    /tenants/{tid}/qr/{id}           detail + recent scans
    GET    /tenants/{tid}/qr/{id}/png       download image
    DELETE /tenants/{tid}/qr/{id}           soft delete
    GET    /tenants/{tid}/qr-analytics      aggregated stats
    GET    /c/{token}                       public resolve + redirect
    POST   /public/business/{slug}/qr-scan  record a scan after PWA loads
"""
from __future__ import annotations

import base64
import hashlib
import io
import json
import logging
import secrets
from datetime import datetime, timedelta

import httpx
from sqlalchemy import select, func
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

QR_KINDS = ("business", "context", "campaign")

CONTEXT_TYPES = (
    "table", "room", "seat", "counter",
    "product", "property", "department", "other",
)


# ---------------------------------------------------------------------------
# Token generation
# ---------------------------------------------------------------------------

def _new_token() -> str:
    """URL-safe opaque token. Not a UUID — no structure leaks."""
    return secrets.token_urlsafe(12)  # ~16 chars, 96 bits


def _hash_ip(ip: str | None) -> str | None:
    """Salted SHA-256 of an IP. Kept short. Never reversible."""
    if not ip:
        return None
    salt = "ago-qr-salt"
    return hashlib.sha256((salt + ip).encode("utf-8")).hexdigest()[:32]


# ---------------------------------------------------------------------------
# Create / read / update
# ---------------------------------------------------------------------------

def create_qr(
    db: Session,
    tenant_id: str,
    *,
    kind: str = "business",
    label: str = "Business QR",
    context_type: str | None = None,
    context_value: str | None = None,
    campaign_id: str | None = None,
    created_by: str | None = None,
    public_base: str = "",
) -> dict:
    """Create a QR entry of one of the three blueprint kinds."""
    from .models_growth import QrEntry

    kind = (kind or "business").strip().lower()
    if kind not in QR_KINDS:
        raise ValueError(f"kind must be one of: {', '.join(QR_KINDS)}")

    label = (label or "").strip()[:160] or {
        "business": "Business QR",
        "context":  "Context QR",
        "campaign": "Campaign QR",
    }[kind]

    if kind == "context":
        if not context_type or context_type not in CONTEXT_TYPES:
            raise ValueError(
                f"context_type is required for context QR and must be one of: "
                f"{', '.join(CONTEXT_TYPES)}"
            )
        if not context_value or not context_value.strip():
            raise ValueError("context_value is required for context QR")
        context_value = context_value.strip()[:120]
    else:
        context_type = None
        context_value = None

    if kind == "campaign":
        if not campaign_id:
            raise ValueError("campaign_id is required for campaign QR")
    else:
        campaign_id = None

    # Ensure token is unique
    for _ in range(5):
        token = _new_token()
        exists = db.scalar(select(QrEntry).where(QrEntry.token == token))
        if not exists:
            break
    else:
        raise RuntimeError("could not allocate unique QR token")

    # Persist new columns if the migration added them
    entry = QrEntry(
        tenant_id=tenant_id,
        token=token,
        kind=kind,
        label=label,
        scans=0,
    )
    # These attributes only exist if the migration ran
    for attr, val in (
        ("context_type", context_type),
        ("context_value", context_value),
        ("campaign_id", campaign_id),
        ("created_by", created_by),
    ):
        try:
            setattr(entry, attr, val)
        except Exception:
            pass

    db.add(entry)
    db.commit()
    db.refresh(entry)

    return _qr_out(entry, public_base)


def list_qrs(db: Session, tenant_id: str, limit: int = 200) -> list:
    from .models_growth import QrEntry
    rows = db.scalars(
        select(QrEntry)
        .where(QrEntry.tenant_id == tenant_id)
        .order_by(QrEntry.created_at.desc())
        .limit(min(max(limit, 1), 500))
    ).all()
    return [_qr_out(r, "") for r in rows]


def get_qr(db: Session, tenant_id: str, qr_id: str) -> dict | None:
    from .models_growth import QrEntry
    row = db.scalar(select(QrEntry).where(QrEntry.id == qr_id, QrEntry.tenant_id == tenant_id))
    if not row:
        return None
    out = _qr_out(row, "")
    # attach recent scans
    try:
        from .models_qr import QrScan
        scans = db.scalars(
            select(QrScan)
            .where(QrScan.qr_id == qr_id)
            .order_by(QrScan.created_at.desc())
            .limit(50)
        ).all()
        out["recent_scans"] = [
            {
                "id": s.id,
                "created_at": s.created_at.isoformat() if s.created_at else None,
                "customer_id": s.customer_id,
                "context": f"{s.context_type}:{s.context_value}" if s.context_type else None,
                "campaign_id": s.campaign_id,
                "referrer": s.referrer,
            }
            for s in scans
        ]
    except Exception:
        out["recent_scans"] = []
    return out


def delete_qr(db: Session, tenant_id: str, qr_id: str) -> bool:
    from .models_growth import QrEntry
    row = db.scalar(select(QrEntry).where(QrEntry.id == qr_id, QrEntry.tenant_id == tenant_id))
    if not row:
        return False
    db.delete(row)
    db.commit()
    return True


def _qr_out(entry, public_base: str) -> dict:
    """Serialize a QrEntry. Tolerates missing new columns."""
    token = getattr(entry, "token", "")
    base = (public_base or "").rstrip("/")
    url = f"{base}/c/{token}" if base else f"/c/{token}"
    return {
        "id": entry.id,
        "tenant_id": entry.tenant_id,
        "kind": getattr(entry, "kind", "business"),
        "label": getattr(entry, "label", ""),
        "token": token,
        "scans": getattr(entry, "scans", 0),
        "context_type": getattr(entry, "context_type", None),
        "context_value": getattr(entry, "context_value", None),
        "campaign_id": getattr(entry, "campaign_id", None),
        "created_at": entry.created_at.isoformat() if getattr(entry, "created_at", None) else None,
        "url": url,
    }


# ---------------------------------------------------------------------------
# Public resolve (used by /c/{token})
# ---------------------------------------------------------------------------

def resolve_token(db: Session, token: str) -> dict | None:
    """Return tenant + QR metadata for an opaque token.

    Does NOT record a scan; the caller decides when to record.
    """
    from .models_growth import QrEntry
    from .models import Tenant

    if not token:
        return None
    entry = db.scalar(select(QrEntry).where(QrEntry.token == token))
    if not entry:
        return None
    tenant = db.get(Tenant, entry.tenant_id)
    if not tenant or getattr(tenant, "status", "active") != "active":
        return None
    return {
        "qr_id": entry.id,
        "token": entry.token,
        "kind": getattr(entry, "kind", "business"),
        "context_type": getattr(entry, "context_type", None),
        "context_value": getattr(entry, "context_value", None),
        "campaign_id": getattr(entry, "campaign_id", None),
        "tenant_slug": tenant.slug,
        "tenant_name": tenant.name,
    }


# ---------------------------------------------------------------------------
# Scan recording
# ---------------------------------------------------------------------------

def record_scan(
    db: Session,
    *,
    tenant_id: str,
    qr_id: str,
    token: str,
    kind: str,
    context_type: str | None = None,
    context_value: str | None = None,
    campaign_id: str | None = None,
    customer_id: str | None = None,
    user_agent: str | None = None,
    referrer: str | None = None,
    ip: str | None = None,
) -> dict:
    """Append a scan row and bump the QrEntry counter.

    Idempotent per (qr_id, customer_id or ip_hash, minute) to prevent
    accidental double-counts from a fast page reload or preflight.
    """
    from .models_growth import QrEntry
    from .models_qr import QrScan

    entry = db.scalar(select(QrEntry).where(QrEntry.id == qr_id))
    if not entry:
        return {"recorded": False, "reason": "qr_not_found"}

    ip_hash = _hash_ip(ip)
    one_min_ago = datetime.utcnow() - timedelta(minutes=1)
    dedupe = db.scalar(
        select(QrScan)
        .where(
            QrScan.qr_id == qr_id,
            QrScan.created_at >= one_min_ago,
            (QrScan.customer_id == customer_id) if customer_id else (QrScan.ip_hash == ip_hash),
        )
        .limit(1)
    )
    if dedupe:
        return {"recorded": False, "reason": "duplicate_within_minute"}

    scan = QrScan(
        tenant_id=tenant_id,
        qr_id=qr_id,
        token=token,
        kind=kind,
        context_type=context_type,
        context_value=context_value,
        campaign_id=campaign_id,
        customer_id=customer_id,
        user_agent=(user_agent or "")[:300] or None,
        referrer=(referrer or "")[:500] or None,
        ip_hash=ip_hash,
    )
    db.add(scan)
    try:
        entry.scans = (entry.scans or 0) + 1
    except Exception:
        pass
    db.commit()
    db.refresh(scan)
    return {"recorded": True, "scan_id": scan.id}


# ---------------------------------------------------------------------------
# PNG generation
# ---------------------------------------------------------------------------

def build_qr_png(url: str, size: int = 400) -> bytes:
    """Generate a QR code PNG. Local first, HTTPS service as fallback."""
    try:
        import qrcode
        qr = qrcode.QRCode(
            version=None,
            error_correction=qrcode.constants.ERROR_CORRECT_M,
            box_size=max(4, size // 33),
            border=2,
        )
        qr.add_data(url)
        qr.make(fit=True)
        img = qr.make_image(fill_color="#14382c", back_color="white")
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()
    except Exception as exc:
        logger.debug("local qrcode failed (%s); using external service", exc)

    fallback = (
        "https://api.qrserver.com/v1/create-qr-code/"
        f"?size={size}x{size}&margin=8&color=14382c&data={httpx.URL(url)}"
    )
    with httpx.Client(timeout=15) as client:
        r = client.get(fallback)
        r.raise_for_status()
        return r.content


def generate_qr_png_for_entry(
    db: Session, tenant_id: str, qr_id: str, size: int = 400, public_base: str = "",
) -> tuple:
    """Return (png_bytes, url). Bumps the qr_generated stat."""
    from .models_growth import QrEntry
    entry = db.scalar(select(QrEntry).where(QrEntry.id == qr_id, QrEntry.tenant_id == tenant_id))
    if not entry:
        raise ValueError("QR not found")
    base = (public_base or "").rstrip("/")
    url = f"{base}/c/{entry.token}"
    png = build_qr_png(url, size=size)
    return png, url


# ---------------------------------------------------------------------------
# Analytics
# ---------------------------------------------------------------------------

def qr_analytics(db: Session, tenant_id: str, days: int = 30) -> dict:
    """Aggregate scans by day, kind, context, and campaign for the tenant."""
    from .models_qr import QrScan
    days = min(max(int(days), 1), 365)
    since = datetime.utcnow() - timedelta(days=days)

    # Per day
    rows = db.execute(
        select(
            func.date(QrScan.created_at).label("d"),
            func.count(QrScan.id).label("n"),
        )
        .where(QrScan.tenant_id == tenant_id, QrScan.created_at >= since)
        .group_by("d")
        .order_by("d")
    ).all()
    per_day = [{"date": str(r[0]), "scans": int(r[1])} for r in rows]

    # By kind
    rows = db.execute(
        select(QrScan.kind, func.count(QrScan.id))
        .where(QrScan.tenant_id == tenant_id, QrScan.created_at >= since)
        .group_by(QrScan.kind)
    ).all()
    by_kind = {str(r[0] or "unknown"): int(r[1]) for r in rows}

    # By context
    rows = db.execute(
        select(
            QrScan.context_type, QrScan.context_value, func.count(QrScan.id)
        )
        .where(
            QrScan.tenant_id == tenant_id,
            QrScan.created_at >= since,
            QrScan.context_type.isnot(None),
        )
        .group_by(QrScan.context_type, QrScan.context_value)
    ).all()
    by_context = [
        {"type": str(r[0]), "value": str(r[1]), "scans": int(r[2])}
        for r in rows
    ]

    # By campaign
    rows = db.execute(
        select(QrScan.campaign_id, func.count(QrScan.id))
        .where(
            QrScan.tenant_id == tenant_id,
            QrScan.created_at >= since,
            QrScan.campaign_id.isnot(None),
        )
        .group_by(QrScan.campaign_id)
    ).all()
    by_campaign = [
        {"campaign_id": str(r[0]), "scans": int(r[1])}
        for r in rows
    ]

    total = sum(x["scans"] for x in per_day)
    return {
        "days": days,
        "total_scans": total,
        "per_day": per_day,
        "by_kind": by_kind,
        "by_context": by_context,
        "by_campaign": by_campaign,
    }


# ---------------------------------------------------------------------------
# Migration helper
# ---------------------------------------------------------------------------

def ensure_qr_schema(engine) -> None:
    """Add the new nullable columns to qr_entries and create qr_scans.

    Safe to run on every startup.
    """
    from sqlalchemy import text
    dialect = engine.dialect.name

    try:
        with engine.begin() as conn:
            if dialect == "postgresql":
                conn.execute(text("ALTER TABLE qr_entries ADD COLUMN IF NOT EXISTS context_type VARCHAR(40)"))
                conn.execute(text("ALTER TABLE qr_entries ADD COLUMN IF NOT EXISTS context_value VARCHAR(120)"))
                conn.execute(text("ALTER TABLE qr_entries ADD COLUMN IF NOT EXISTS campaign_id VARCHAR(36)"))
                conn.execute(text("ALTER TABLE qr_entries ADD COLUMN IF NOT EXISTS created_by VARCHAR(36)"))
                conn.execute(text("CREATE INDEX IF NOT EXISTS ix_qr_entries_context ON qr_entries(context_type, context_value)"))
                conn.execute(text("CREATE INDEX IF NOT EXISTS ix_qr_entries_campaign ON qr_entries(campaign_id)"))

                conn.execute(text("""
                    CREATE TABLE IF NOT EXISTS qr_scans (
                        id VARCHAR(36) PRIMARY KEY,
                        tenant_id VARCHAR(36) NOT NULL,
                        qr_id VARCHAR(36) NOT NULL,
                        token VARCHAR(100) NOT NULL,
                        kind VARCHAR(40) NOT NULL,
                        context_type VARCHAR(40),
                        context_value VARCHAR(120),
                        campaign_id VARCHAR(36),
                        customer_id VARCHAR(36),
                        user_agent VARCHAR(300),
                        referrer VARCHAR(500),
                        ip_hash VARCHAR(64),
                        created_at TIMESTAMP NOT NULL
                    )
                """))
                for idx in (
                    "CREATE INDEX IF NOT EXISTS ix_qr_scans_tenant ON qr_scans(tenant_id)",
                    "CREATE INDEX IF NOT EXISTS ix_qr_scans_qr ON qr_scans(qr_id)",
                    "CREATE INDEX IF NOT EXISTS ix_qr_scans_token ON qr_scans(token)",
                    "CREATE INDEX IF NOT EXISTS ix_qr_scans_kind ON qr_scans(kind)",
                    "CREATE INDEX IF NOT EXISTS ix_qr_scans_context ON qr_scans(context_type, context_value)",
                    "CREATE INDEX IF NOT EXISTS ix_qr_scans_campaign ON qr_scans(campaign_id)",
                    "CREATE INDEX IF NOT EXISTS ix_qr_scans_created ON qr_scans(created_at)",
                ):
                    conn.execute(text(idx))

            elif dialect == "sqlite":
                cols = {r[1] for r in conn.execute(text("PRAGMA table_info(qr_entries)"))}
                for col, definition in (
                    ("context_type", "VARCHAR(40)"),
                    ("context_value", "VARCHAR(120)"),
                    ("campaign_id", "VARCHAR(36)"),
                    ("created_by", "VARCHAR(36)"),
                ):
                    if col not in cols:
                        conn.execute(text(f"ALTER TABLE qr_entries ADD COLUMN {col} {definition}"))
                conn.execute(text("CREATE INDEX IF NOT EXISTS ix_qr_entries_context ON qr_entries(context_type, context_value)"))
                conn.execute(text("CREATE INDEX IF NOT EXISTS ix_qr_entries_campaign ON qr_entries(campaign_id)"))

                conn.execute(text("""
                    CREATE TABLE IF NOT EXISTS qr_scans (
                        id VARCHAR(36) PRIMARY KEY,
                        tenant_id VARCHAR(36) NOT NULL,
                        qr_id VARCHAR(36) NOT NULL,
                        token VARCHAR(100) NOT NULL,
                        kind VARCHAR(40) NOT NULL,
                        context_type VARCHAR(40),
                        context_value VARCHAR(120),
                        campaign_id VARCHAR(36),
                        customer_id VARCHAR(36),
                        user_agent VARCHAR(300),
                        referrer VARCHAR(500),
                        ip_hash VARCHAR(64),
                        created_at DATETIME NOT NULL
                    )
                """))
                for idx in (
                    "CREATE INDEX IF NOT EXISTS ix_qr_scans_tenant ON qr_scans(tenant_id)",
                    "CREATE INDEX IF NOT EXISTS ix_qr_scans_qr ON qr_scans(qr_id)",
                    "CREATE INDEX IF NOT EXISTS ix_qr_scans_created ON qr_scans(created_at)",
                ):
                    conn.execute(text(idx))
    except Exception as exc:
        logger.warning("ensure_qr_schema failed: %s", exc)