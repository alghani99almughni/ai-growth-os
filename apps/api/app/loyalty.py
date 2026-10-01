"""Loyalty Wallet - append-only ledger, idempotent, tenant-scoped.

This module is the ONLY place that writes LoyaltyTransaction rows.
Every write is:
    - idempotent (unique reference per event)
    - audit-logged
    - gated on the tenant's loyalty feature flag

Nothing else in the codebase should call db.add(LoyaltyTransaction(...)).
Route through award() / redeem() so every point is traceable.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from sqlalchemy import select, func
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Feature gate
# ---------------------------------------------------------------------------

def _loyalty_enabled(db: Session, tenant_id: str) -> bool:
    """Read the tenant's loyalty flag from the layered feature config."""
    try:
        from .main import _feature_config
        return bool(_feature_config(db, tenant_id).get("loyalty", False))
    except Exception:
        # Conservative default: disabled
        return False


# ---------------------------------------------------------------------------
# Result type
# ---------------------------------------------------------------------------

@dataclass
class LoyaltyResult:
    ok: bool
    points: int = 0
    balance: int = 0
    transaction_id: Optional[str] = None
    reason: str = ""


# ---------------------------------------------------------------------------
# Balance
# ---------------------------------------------------------------------------

def balance(db: Session, tenant_id: str, customer_id: str) -> int:
    """Sum of all ledger entries for a customer. Negative entries are redemptions."""
    from .models_growth import LoyaltyTransaction
    total = db.scalar(
        select(func.coalesce(func.sum(LoyaltyTransaction.points), 0))
        .where(
            LoyaltyTransaction.tenant_id == tenant_id,
            LoyaltyTransaction.customer_id == customer_id,
        )
    )
    return int(total or 0)


def history(db: Session, tenant_id: str, customer_id: str, limit: int = 100) -> list:
    from .models_growth import LoyaltyTransaction
    rows = db.scalars(
        select(LoyaltyTransaction)
        .where(
            LoyaltyTransaction.tenant_id == tenant_id,
            LoyaltyTransaction.customer_id == customer_id,
        )
        .order_by(LoyaltyTransaction.created_at.desc())
        .limit(min(max(limit, 1), 500))
    ).all()
    return [{
        "id": r.id,
        "points": r.points,
        "reason": r.reason,
        "reference_id": r.reference_id,
        "created_at": r.created_at.isoformat() if r.created_at else None,
    } for r in rows]


# ---------------------------------------------------------------------------
# Award (earning)
# ---------------------------------------------------------------------------

def award(
    db: Session,
    tenant_id: str,
    customer_id: str,
    points: int,
    reason: str,
    reference_id: Optional[str] = None,
) -> LoyaltyResult:
    """Credit points to a customer.

    Idempotency: if a LoyaltyTransaction already exists with the same
    (tenant_id, customer_id, reason, reference_id), this returns the existing
    entry without creating a duplicate.

    reference_id should be the ID of the source event:
        order.id          -> "order.completed"
        appointment.id    -> "appointment.completed"
        gamescore.id      -> "game.<name>"
        referral.id       -> "referral"
    """
    from .models_growth import LoyaltyTransaction
    from .models import Customer

    if not customer_id:
        return LoyaltyResult(ok=False, reason="missing_customer")
    if points <= 0:
        return LoyaltyResult(ok=False, reason="invalid_points")

    if not _loyalty_enabled(db, tenant_id):
        return LoyaltyResult(ok=False, reason="loyalty_disabled")

    customer = db.scalar(select(Customer).where(
        Customer.id == customer_id, Customer.tenant_id == tenant_id,
    ))
    if not customer:
        return LoyaltyResult(ok=False, reason="customer_not_found")

    # Idempotency check
    if reference_id:
        existing = db.scalar(select(LoyaltyTransaction).where(
            LoyaltyTransaction.tenant_id == tenant_id,
            LoyaltyTransaction.customer_id == customer_id,
            LoyaltyTransaction.reason == reason,
            LoyaltyTransaction.reference_id == reference_id,
        ))
        if existing:
            return LoyaltyResult(
                ok=True,
                points=existing.points,
                balance=balance(db, tenant_id, customer_id),
                transaction_id=existing.id,
                reason="already_awarded",
            )

    tx = LoyaltyTransaction(
        tenant_id=tenant_id,
        customer_id=customer_id,
        points=int(points),
        reason=reason,
        reference_id=reference_id,
    )
    db.add(tx)
    try:
        db.commit()
        db.refresh(tx)
    except Exception as exc:
        db.rollback()
        logger.exception("loyalty.award failed: %s", exc)
        return LoyaltyResult(ok=False, reason="db_error")

    try:
        from .security import audit
        audit(db, tenant_id=tenant_id, actor_id=None,
              action="loyalty.awarded", target_type="customer",
              target_id=customer_id,
              detail={"points": int(points), "reason": reason,
                      "reference_id": reference_id, "transaction_id": tx.id})
    except Exception:
        pass

    return LoyaltyResult(
        ok=True,
        points=int(points),
        balance=balance(db, tenant_id, customer_id),
        transaction_id=tx.id,
        reason=reason,
    )


# ---------------------------------------------------------------------------
# Redeem (spending)
# ---------------------------------------------------------------------------

def redeem(
    db: Session,
    tenant_id: str,
    customer_id: str,
    points: int,
    reason: str,
    reference_id: Optional[str] = None,
) -> LoyaltyResult:
    """Debit points. Writes a negative LoyaltyTransaction.

    Idempotency: same (reason, reference_id) that already exists will not
    be re-debited.
    """
    from .models_growth import LoyaltyTransaction
    from .models import Customer

    if not customer_id or points <= 0:
        return LoyaltyResult(ok=False, reason="invalid_request")

    if not _loyalty_enabled(db, tenant_id):
        return LoyaltyResult(ok=False, reason="loyalty_disabled")

    customer = db.scalar(select(Customer).where(
        Customer.id == customer_id, Customer.tenant_id == tenant_id,
    ))
    if not customer:
        return LoyaltyResult(ok=False, reason="customer_not_found")

    if reference_id:
        existing = db.scalar(select(LoyaltyTransaction).where(
            LoyaltyTransaction.tenant_id == tenant_id,
            LoyaltyTransaction.customer_id == customer_id,
            LoyaltyTransaction.reason == reason,
            LoyaltyTransaction.reference_id == reference_id,
        ))
        if existing:
            return LoyaltyResult(
                ok=True,
                points=existing.points,
                balance=balance(db, tenant_id, customer_id),
                transaction_id=existing.id,
                reason="already_redeemed",
            )

    current = balance(db, tenant_id, customer_id)
    if current < points:
        return LoyaltyResult(ok=False, balance=current, reason="insufficient_points")

    tx = LoyaltyTransaction(
        tenant_id=tenant_id,
        customer_id=customer_id,
        points=-int(points),
        reason=reason,
        reference_id=reference_id,
    )
    db.add(tx)
    try:
        db.commit()
        db.refresh(tx)
    except Exception as exc:
        db.rollback()
        logger.exception("loyalty.redeem failed: %s", exc)
        return LoyaltyResult(ok=False, reason="db_error")

    try:
        from .security import audit
        audit(db, tenant_id=tenant_id, actor_id=None,
              action="loyalty.redeemed", target_type="customer",
              target_id=customer_id,
              detail={"points": int(points), "reason": reason,
                      "reference_id": reference_id, "transaction_id": tx.id})
    except Exception:
        pass

    return LoyaltyResult(
        ok=True,
        points=-int(points),
        balance=balance(db, tenant_id, customer_id),
        transaction_id=tx.id,
        reason=reason,
    )


# ---------------------------------------------------------------------------
# Auto-award for a completed order (uses LoyaltyRule rows)
# ---------------------------------------------------------------------------

def award_for_order(db: Session, tenant_id: str, order) -> list:
    """Apply every active 'purchase' LoyaltyRule that qualifies for this order.

    Returns a list of {"rule": name, "points": N} for what was awarded.
    Idempotent: reruns do not double-award.
    """
    from .models_growth import LoyaltyRule
    import json as _json

    if not order or not order.customer_id:
        return []

    if not _loyalty_enabled(db, tenant_id):
        return []

    rules = db.scalars(select(LoyaltyRule).where(
        LoyaltyRule.tenant_id == tenant_id,
        LoyaltyRule.event_type == "purchase",
        LoyaltyRule.is_active == True,
    )).all()

    awarded = []
    total = int(order.total or 0)

    for rule in rules:
        try:
            cfg = _json.loads(rule.config_json or "{}")
        except Exception:
            cfg = {}

        minimum = int(cfg.get("minimum_bill", 0))
        if total < minimum:
            continue

        result = award(
            db, tenant_id, order.customer_id,
            points=rule.points,
            reason=rule.name,
            reference_id=order.id,
        )
        if result.ok and result.reason != "already_awarded":
            awarded.append({"rule": rule.name, "points": rule.points})

    return awarded