"""Monitoring + Tier 1 self-healing.

Every 60 seconds a background task:
  1. Collects health snapshots for each category
  2. Runs safe self-healers if a category is unhealthy
  3. Writes every action to SelfHealAction
  4. Queues a MonitoringAlert after 3 consecutive failures

Also runs the hourly database backup loop with 48-hour retention.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import shutil
import time
import uuid
from datetime import datetime, timedelta
from pathlib import Path

from sqlalchemy import select, func

from .db import SessionLocal, engine
from .models_monitoring import (
    HealthSnapshot,
    SelfHealAction,
    MonitoringAlert,
    BackupRecord,
)

logger = logging.getLogger("api.monitoring")

CHECK_INTERVAL_SECONDS = 60
SELF_HEAL_MAX_ATTEMPTS = 3
BACKUP_INTERVAL_SECONDS = 3600
BACKUP_RETENTION_HOURS = 48

_monitor_task: asyncio.Task | None = None
_backup_task: asyncio.Task | None = None

_self_heal_failures: dict[str, int] = {}


def _write_snapshot(db, category: str, status: str, detail: dict, latency_ms: int | None = None):
    db.add(HealthSnapshot(
        id=str(uuid.uuid4()),
        category=category,
        status=status,
        detail_json=json.dumps(detail),
        latency_ms=latency_ms,
    ))


def _write_action(db, component: str, action: str, outcome: str, detail: str = ""):
    db.add(SelfHealAction(
        id=str(uuid.uuid4()),
        component=component,
        action=action,
        outcome=outcome,
        detail=detail,
    ))


def _queue_alert(db, severity: str, component: str, title: str, body: str = "") -> None:
    db.add(MonitoringAlert(
        id=str(uuid.uuid4()),
        severity=severity,
        component=component,
        title=title,
        body=body,
    ))


def _check_database(db) -> tuple[str, dict, int]:
    t0 = time.time()
    try:
        db.execute(select(1))
        latency = int((time.time() - t0) * 1000)
        return "ok", {"reachable": True}, latency
    except Exception as exc:
        return "down", {"reachable": False, "error": str(exc)}, int((time.time() - t0) * 1000)


def _check_email_poller() -> tuple[str, dict]:
    from .models_email import TenantEmailAccount
    db = SessionLocal()
    try:
        active = db.scalar(
            select(func.count(TenantEmailAccount.id)).where(TenantEmailAccount.is_active == True)  # noqa: E712
        ) or 0
        if active == 0:
            return "ok", {"active_mailboxes": 0, "note": "no mailboxes configured"}
        last = db.scalar(select(func.max(TenantEmailAccount.last_checked_at)))
        if not last:
            return "degraded", {"active_mailboxes": active, "last_checked_at": None, "note": "never checked"}
        age_seconds = (datetime.utcnow() - last).total_seconds()
        status = "ok" if age_seconds < 600 else "degraded"
        return status, {"active_mailboxes": active, "last_checked_at": last.isoformat(), "age_seconds": int(age_seconds)}
    finally:
        db.close()


def _check_whatsapp() -> tuple[str, dict]:
    from .models import Tenant
    from .whatsapp_channels import all_channels
    db = SessionLocal()
    try:
        tenants = db.scalars(select(Tenant).where(Tenant.status == "active")).all()
        openwa_ok = 0
        meta_ok = 0
        checked = 0
        for t in tenants[:50]:
            try:
                info = all_channels(db, t.id)
                checked += 1
                if info.get("openwa", {}).get("connected"):
                    openwa_ok += 1
                if info.get("meta", {}).get("connected"):
                    meta_ok += 1
            except Exception:
                continue
        status = "ok" if (openwa_ok + meta_ok) > 0 or checked == 0 else "degraded"
        return status, {"tenants_checked": checked, "openwa_connected": openwa_ok, "meta_connected": meta_ok}
    finally:
        db.close()


def _check_ai_providers() -> tuple[str, dict]:
    from .models_integrations import PlatformAIProvider, TenantIntegration
    db = SessionLocal()
    try:
        platform_count = db.scalar(
            select(func.count(PlatformAIProvider.id)).where(PlatformAIProvider.enabled == True)  # noqa: E712
        ) or 0
        tenant_count = db.scalar(
            select(func.count(TenantIntegration.id)).where(
                TenantIntegration.integration_key.in_(["gemini", "openai", "openrouter", "anthropic"]),
                TenantIntegration.status == "connected",
            )
        ) or 0
        status = "ok" if (platform_count + tenant_count) > 0 else "degraded"
        return status, {"platform_providers": platform_count, "tenant_providers": tenant_count}
    finally:
        db.close()


def _check_disk() -> tuple[str, dict]:
    try:
        usage = shutil.disk_usage(os.getcwd())
        pct = round((usage.used / usage.total) * 100, 1)
        status = "ok" if pct < 85 else ("degraded" if pct < 95 else "down")
        return status, {"used_percent": pct, "used_gb": round(usage.used / (1024 ** 3), 2), "total_gb": round(usage.total / (1024 ** 3), 2)}
    except Exception as exc:
        return "unknown", {"error": str(exc)}


def _check_backup_age() -> tuple[str, dict]:
    db = SessionLocal()
    try:
        last = db.scalar(
            select(BackupRecord).where(BackupRecord.ok == True)  # noqa: E712
            .order_by(BackupRecord.created_at.desc())
        )
        if not last:
            return "degraded", {"last_backup_at": None, "note": "no backup yet"}
        age_hours = (datetime.utcnow() - last.created_at).total_seconds() / 3600
        status = "ok" if age_hours < 2 else ("degraded" if age_hours < 6 else "down")
        return status, {"last_backup_at": last.created_at.isoformat(), "age_hours": round(age_hours, 2), "last_backup_path": last.backup_path}
    finally:
        db.close()


async def _heal_email_poller(db, status: str, detail: dict):
    if status == "ok":
        _self_heal_failures.pop("email_poller", None)
        return
    from .email_poller import start_email_poller, stop_email_poller, _poller_task
    try:
        running = _poller_task is not None and not _poller_task.done()
        if not running:
            stop_email_poller()
            start_email_poller()
            _write_action(db, "email_poller", "restart poller", "success")
            _self_heal_failures.pop("email_poller", None)
        else:
            _write_action(db, "email_poller", "poll-check", "skipped", "poller running but mailbox not checked recently")
            _self_heal_failures["email_poller"] = _self_heal_failures.get("email_poller", 0) + 1
    except Exception as exc:
        _write_action(db, "email_poller", "restart poller", "failed", str(exc))
        _self_heal_failures["email_poller"] = _self_heal_failures.get("email_poller", 0) + 1
    if _self_heal_failures.get("email_poller", 0) >= SELF_HEAL_MAX_ATTEMPTS:
        _queue_alert(db, "critical", "email_poller", "Email poller cannot be recovered automatically", json.dumps(detail))
        _self_heal_failures["email_poller"] = 0


async def _heal_database(db, status: str, detail: dict):
    if status == "ok":
        _self_heal_failures.pop("database", None)
        return
    try:
        engine.dispose()
        _write_action(db, "database", "engine.dispose", "success", "recycled connection pool")
        _self_heal_failures.pop("database", None)
    except Exception as exc:
        _write_action(db, "database", "engine.dispose", "failed", str(exc))
        _self_heal_failures["database"] = _self_heal_failures.get("database", 0) + 1
    if _self_heal_failures.get("database", 0) >= SELF_HEAL_MAX_ATTEMPTS:
        _queue_alert(db, "critical", "database", "Database connection cannot be recovered", json.dumps(detail))
        _self_heal_failures["database"] = 0


async def _heal_whatsapp(db, status: str, detail: dict):
    if status == "ok":
        _self_heal_failures.pop("whatsapp", None)
        return
    _self_heal_failures["whatsapp"] = _self_heal_failures.get("whatsapp", 0) + 1
    if _self_heal_failures["whatsapp"] >= SELF_HEAL_MAX_ATTEMPTS:
        _queue_alert(db, "warning", "whatsapp", "No WhatsApp channel connected", json.dumps(detail))
        _self_heal_failures["whatsapp"] = 0


async def _monitor_cycle() -> None:
    db = SessionLocal()
    try:
        status, detail, latency = _check_database(db)
        _write_snapshot(db, "database", status, detail, latency)
        await _heal_database(db, status, detail)

        _write_snapshot(db, "backend", "ok", {"running": True, "pid": os.getpid()})

        status, detail = _check_email_poller()
        _write_snapshot(db, "email_poller", status, detail)
        await _heal_email_poller(db, status, detail)

        status, detail = _check_whatsapp()
        _write_snapshot(db, "whatsapp", status, detail)
        await _heal_whatsapp(db, status, detail)

        status, detail = _check_ai_providers()
        _write_snapshot(db, "ai_provider", status, detail)

        status, detail = _check_disk()
        _write_snapshot(db, "disk", status, detail)

        status, detail = _check_backup_age()
        _write_snapshot(db, "backup", status, detail)

        db.commit()
    except Exception:
        db.rollback()
        logger.exception("monitor cycle failed")
    finally:
        db.close()


async def _monitor_loop() -> None:
    logger.info("monitoring started, interval=%ss", CHECK_INTERVAL_SECONDS)
    while True:
        try:
            await _monitor_cycle()
        except Exception:
            logger.exception("monitor loop error")
        await asyncio.sleep(CHECK_INTERVAL_SECONDS)


def _do_backup_sync() -> BackupRecord:
    from .config import settings
    db_url = settings.database_url or ""
    if not db_url.startswith("sqlite:///"):
        return BackupRecord(id=str(uuid.uuid4()), source_path=db_url, backup_path="", size_bytes=0, ok=False, error="Only SQLite backups supported")
    src_path = db_url.replace("sqlite:///", "", 1)
    src = Path(src_path).resolve()
    backup_dir = src.parent / "backups"
    backup_dir.mkdir(exist_ok=True)
    stamp = datetime.utcnow().strftime("%Y-%m-%d-%H")
    dst = backup_dir / f"{src.stem}.{stamp}.db"
    try:
        shutil.copy2(src, dst)
        size = dst.stat().st_size
        return BackupRecord(id=str(uuid.uuid4()), source_path=str(src), backup_path=str(dst), size_bytes=size, ok=True)
    except Exception as exc:
        return BackupRecord(id=str(uuid.uuid4()), source_path=str(src), backup_path=str(dst), size_bytes=0, ok=False, error=str(exc))


def _prune_backups_sync(keep_hours: int = BACKUP_RETENTION_HOURS) -> int:
    from .config import settings
    db_url = settings.database_url or ""
    if not db_url.startswith("sqlite:///"):
        return 0
    src = Path(db_url.replace("sqlite:///", "", 1)).resolve()
    backup_dir = src.parent / "backups"
    if not backup_dir.exists():
        return 0
    cutoff = datetime.utcnow() - timedelta(hours=keep_hours)
    removed = 0
    for f in backup_dir.iterdir():
        try:
            if f.is_file() and f.suffix == ".db":
                if datetime.utcfromtimestamp(f.stat().st_mtime) < cutoff:
                    f.unlink()
                    removed += 1
        except Exception:
            continue
    return removed


async def _backup_loop() -> None:
    logger.info("backup task started, interval=%ss retention=%sh", BACKUP_INTERVAL_SECONDS, BACKUP_RETENTION_HOURS)
    first = True
    while True:
        try:
            if not first:
                await asyncio.sleep(BACKUP_INTERVAL_SECONDS)
            first = False
            rec = await asyncio.to_thread(_do_backup_sync)
            rec_ok = bool(rec.ok)
            rec_path = str(rec.backup_path)
            db = SessionLocal()
            try:
                db.add(rec)
                db.commit()
            finally:
                db.close()
            removed = await asyncio.to_thread(_prune_backups_sync)
            logger.info("backup ok=%s path=%s pruned=%s", rec_ok, rec_path, removed)
        except Exception:
            logger.exception("backup loop error")


def start_monitoring() -> None:
    global _monitor_task, _backup_task
    if not _monitor_task or _monitor_task.done():
        _monitor_task = asyncio.create_task(_monitor_loop())
    if not _backup_task or _backup_task.done():
        _backup_task = asyncio.create_task(_backup_loop())


def stop_monitoring() -> None:
    global _monitor_task, _backup_task
    for t in (_monitor_task, _backup_task):
        if t and not t.done():
            t.cancel()
    _monitor_task = None
    _backup_task = None