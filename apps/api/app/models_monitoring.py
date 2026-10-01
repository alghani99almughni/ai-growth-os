"""Monitoring tables: health snapshots, self-heal action log, alerts, approvals.

Every 60s the monitoring task writes one HealthSnapshot per category:
  backend, database, email_poller, whatsapp, ai_provider, disk, backup

Every self-heal attempt (success or failure) is written to SelfHealAction.

Every alert sent (or queued) is written to MonitoringAlert. Alerts are sent
by email and/or WhatsApp. When all automated recovery fails, an alert is the
final escalation.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import Column, String, Boolean, DateTime, Integer, Float, Text

from .db import Base


class HealthSnapshot(Base):
    __tablename__ = "monitoring_health_snapshots"

    id = Column(String, primary_key=True)
    category = Column(String, nullable=False, index=True)
    # "ok" | "degraded" | "down" | "unknown"
    status = Column(String, nullable=False, default="unknown")
    # free-form JSON of category-specific measurements
    detail_json = Column(Text, nullable=False, default="{}")
    # milliseconds, only for checks where latency matters
    latency_ms = Column(Integer, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)


class SelfHealAction(Base):
    __tablename__ = "monitoring_self_heal_actions"

    id = Column(String, primary_key=True)
    # which component the action targets
    component = Column(String, nullable=False, index=True)
    # human description, e.g. "restart email poller"
    action = Column(String, nullable=False)
    # "success" | "failed" | "skipped"
    outcome = Column(String, nullable=False, default="skipped")
    detail = Column(Text, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)


class MonitoringAlert(Base):
    __tablename__ = "monitoring_alerts"

    id = Column(String, primary_key=True)
    severity = Column(String, nullable=False, default="warning")  # info|warning|critical
    component = Column(String, nullable=False)
    title = Column(String, nullable=False)
    body = Column(Text, nullable=False, default="")
    # whether it went out by email / whatsapp
    email_sent = Column(Boolean, nullable=False, default=False)
    whatsapp_sent = Column(Boolean, nullable=False, default=False)
    # error text if either channel failed
    delivery_error = Column(Text, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)


class BackupRecord(Base):
    __tablename__ = "monitoring_backups"

    id = Column(String, primary_key=True)
    source_path = Column(String, nullable=False)
    backup_path = Column(String, nullable=False)
    size_bytes = Column(Integer, nullable=False, default=0)
    ok = Column(Boolean, nullable=False, default=True)
    error = Column(Text, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)