"""Mini games - scoring with anti-abuse.

Rules enforced here:
    - Feature flag: tenant must have "games" enabled
    - Feature flag: rewards require "loyalty" enabled too
    - Daily cap: at most 3 rewarded plays per customer, per game, per day
    - Min score: score must be >= MIN_SCORE_TO_REWARD to earn anything
    - Max reward: hard ceiling of MAX_REWARD_POINTS per play
    - Cooldown: at least MIN_SECONDS_BETWEEN_PLAYS between rewarded plays

Scores are always saved (for analytics). Rewards are gated.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import select, func, and_
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Tunables
# ---------------------------------------------------------------------------

GAME_CATALOG = [
    {"id": "dino",   "name": "Dino Run",       "min_score": 10,  "max_reward": 25},
    {"id": "snake",  "name": "Snake",          "min_score": 10,  "max_reward": 25},
    {"id": "brick",  "name": "Brick Breaker",  "min_score": 5,   "max_reward": 20},
    {"id": "flappy", "name": "Flappy",         "min_score": 5,   "max_reward": 20},
    {"id": "tap",    "name": "Tap Target",     "min_score": 20,  "max_reward": 15},
    {"id": "2048",   "name": "2048",           "min_score": 100, "max_reward": 30},
]

DAILY_REWARD_CAP_PER_GAME = 3
MIN_SECONDS_BETWEEN_PLAYS = 30


def game_by_id(game_id: str) -> Optional[dict]:
    gid = (game_id or "").strip().lower()
    for g in GAME_CATALOG:
        if g["id"] == gid:
            return g
    return None


# ---------------------------------------------------------------------------
# Feature gates
# ---------------------------------------------------------------------------

def _games_enabled(db: Session, tenant_id: str) -> bool:
    try:
        from .main import _feature_config
        return bool(_feature_config(db, tenant_id).get("games", False))
    except Exception:
        return False


def _loyalty_enabled(db: Session, tenant_id: str) -> bool:
    try:
        from .main import _feature_config
        return bool(_feature_config(db, tenant_id).get("loyalty", False))
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Result type
# ---------------------------------------------------------------------------

@dataclass
class ScoreResult:
    ok: bool
    score_id: Optional[str] = None
    score: int = 0
    reward_points: int = 0
    reward_reason: str = ""
    reason: str = ""


# ---------------------------------------------------------------------------
# Score submission
# ---------------------------------------------------------------------------

def submit_score(
    db: Session,
    tenant_id: str,
    game_id: str,
    score: int,
    customer_id: Optional[str] = None,
) -> ScoreResult:
    """Record a game score and (if eligible) award loyalty points.

    Always saves the score. Awards only when all anti-abuse checks pass.
    """
    from .models_growth import GameScore
    from .models import Customer

    g = game_by_id(game_id)
    if not g:
        return ScoreResult(ok=False, reason="unknown_game")

    try:
        score = max(0, int(score))
    except Exception:
        return ScoreResult(ok=False, reason="invalid_score")

    # Cap at a sane ceiling to prevent client spoofing huge numbers
    score = min(score, 1_000_000)

    if not _games_enabled(db, tenant_id):
        return ScoreResult(ok=False, reason="games_disabled")

    customer = None
    if customer_id:
        customer = db.scalar(select(Customer).where(
            Customer.id == customer_id, Customer.tenant_id == tenant_id,
        ))

    reward = 0
    reward_reason = ""

    # Reward eligibility
    if customer and _loyalty_enabled(db, tenant_id):
        if score < g["min_score"]:
            reward_reason = "below_min_score"
        else:
            now = datetime.utcnow()
            day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

            # Daily rewarded plays for this customer + game
            rewarded_today = db.scalar(
                select(func.count(GameScore.id)).where(
                    GameScore.tenant_id == tenant_id,
                    GameScore.customer_id == customer.id,
                    GameScore.game == g["id"],
                    GameScore.reward_points > 0,
                    GameScore.created_at >= day_start,
                )
            ) or 0

            if rewarded_today >= DAILY_REWARD_CAP_PER_GAME:
                reward_reason = "daily_cap_reached"
            else:
                # Cooldown: last rewarded play must be at least N seconds ago
                last = db.scalar(
                    select(GameScore).where(
                        GameScore.tenant_id == tenant_id,
                        GameScore.customer_id == customer.id,
                        GameScore.game == g["id"],
                        GameScore.reward_points > 0,
                    ).order_by(GameScore.created_at.desc()).limit(1)
                )
                if last and last.created_at:
                    elapsed = (now - last.created_at).total_seconds()
                    if elapsed < MIN_SECONDS_BETWEEN_PLAYS:
                        reward_reason = "cooldown"

            if not reward_reason:
                # Compute reward: proportional to score, capped per game
                computed = max(1, score // 20)
                reward = min(computed, g["max_reward"])
                reward_reason = "eligible"

    # Save the score (always)
    row = GameScore(
        tenant_id=tenant_id,
        customer_id=customer.id if customer else None,
        game=g["id"],
        score=score,
        reward_points=reward,
    )
    db.add(row)
    try:
        db.commit()
        db.refresh(row)
    except Exception as exc:
        db.rollback()
        logger.exception("games.submit_score failed: %s", exc)
        return ScoreResult(ok=False, reason="db_error")

    # Award loyalty via the ledger (append-only)
    if reward > 0 and customer:
        try:
            from .loyalty import award as loyalty_award
            loyalty_award(
                db, tenant_id, customer.id,
                points=reward,
                reason=f"game:{g['id']}",
                reference_id=row.id,
            )
        except Exception as exc:
            logger.exception("games loyalty award failed: %s", exc)

    return ScoreResult(
        ok=True,
        score_id=row.id,
        score=score,
        reward_points=reward,
        reward_reason=reward_reason,
    )


# ---------------------------------------------------------------------------
# Leaderboard (per tenant, per game, today)
# ---------------------------------------------------------------------------

def leaderboard(db: Session, tenant_id: str, game_id: str, limit: int = 10) -> list:
    from .models_growth import GameScore
    from .models import Customer
    g = game_by_id(game_id)
    if not g:
        return []
    day_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    rows = db.scalars(
        select(GameScore)
        .where(
            GameScore.tenant_id == tenant_id,
            GameScore.game == g["id"],
            GameScore.created_at >= day_start,
        )
        .order_by(GameScore.score.desc())
        .limit(min(max(limit, 1), 50))
    ).all()
    out = []
    for r in rows:
        name = "Guest"
        if r.customer_id:
            c = db.get(Customer, r.customer_id)
            if c and c.tenant_id == tenant_id:
                name = c.name or "Guest"
        out.append({"name": name, "score": r.score, "at": r.created_at.isoformat()})
    return out