"""Call audio storage.

Abstracts where audio files live:
    - Local disk (default for dev)
    - S3 / Cloudflare R2 (if configured)

Interface:
    save_audio(audio_bytes, call_id, turn_id, side) -> url
    load_audio(url) -> bytes
    delete_audio(url) -> bool

URL format:
    local://recordings/{call_id}/{turn_id}_{side}.webm
    s3://bucket/recordings/{call_id}/{turn_id}_{side}.webm

Storage backend is chosen by env vars:
    STORAGE_BACKEND=local (default) or s3
    S3_BUCKET, S3_REGION, S3_ACCESS_KEY, S3_SECRET_KEY (for s3)
"""
from __future__ import annotations

import logging
import os
import pathlib
import shutil
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

STORAGE_BACKEND = (os.getenv("STORAGE_BACKEND") or "local").lower()
LOCAL_ROOT = pathlib.Path(os.getenv("LOCAL_RECORDINGS_DIR", "recordings"))


def _local_path(call_id: str, turn_id: str, side: str) -> pathlib.Path:
    folder = LOCAL_ROOT / call_id
    folder.mkdir(parents=True, exist_ok=True)
    return folder / f"{turn_id}_{side}.webm"


def _s3_client():
    try:
        import boto3
        return boto3.client(
            "s3",
            region_name=os.getenv("S3_REGION"),
            aws_access_key_id=os.getenv("S3_ACCESS_KEY"),
            aws_secret_access_key=os.getenv("S3_SECRET_KEY"),
            endpoint_url=os.getenv("S3_ENDPOINT"),  # for R2 or MinIO
        )
    except Exception as exc:
        logger.debug("s3 client unavailable: %s", exc)
        return None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def save_audio(
    audio_bytes: bytes,
    call_id: str,
    turn_id: str,
    side: str,  # "customer" or "ai"
) -> Optional[str]:
    """Persist audio and return its URL.

    Returns None if the write failed.
    """
    if not audio_bytes:
        return None

    if STORAGE_BACKEND == "s3":
        return _save_s3(audio_bytes, call_id, turn_id, side)
    return _save_local(audio_bytes, call_id, turn_id, side)


def load_audio(url: str) -> Optional[bytes]:
    """Load audio bytes for a given URL."""
    if not url:
        return None
    if url.startswith("local://"):
        return _load_local(url)
    if url.startswith("s3://"):
        return _load_s3(url)
    return None


def delete_audio(url: str) -> bool:
    """Delete audio. Returns True if gone."""
    if not url:
        return False
    try:
        if url.startswith("local://"):
            path = LOCAL_ROOT / url[len("local://"):]
            if path.exists():
                path.unlink()
            return True
        if url.startswith("s3://"):
            return _delete_s3(url)
    except Exception as exc:
        logger.debug("delete_audio failed: %s", exc)
    return False


# ---------------------------------------------------------------------------
# Local backend
# ---------------------------------------------------------------------------

def _save_local(audio_bytes: bytes, call_id: str, turn_id: str, side: str) -> Optional[str]:
    try:
        path = _local_path(call_id, turn_id, side)
        path.write_bytes(audio_bytes)
        rel = path.relative_to(LOCAL_ROOT)
        return f"local://{rel.as_posix()}"
    except Exception as exc:
        logger.debug("save_local failed: %s", exc)
        return None


def _load_local(url: str) -> Optional[bytes]:
    try:
        rel = url[len("local://"):]
        path = LOCAL_ROOT / rel
        if not path.exists():
            return None
        return path.read_bytes()
    except Exception as exc:
        logger.debug("load_local failed: %s", exc)
        return None


# ---------------------------------------------------------------------------
# S3 backend
# ---------------------------------------------------------------------------

def _save_s3(audio_bytes: bytes, call_id: str, turn_id: str, side: str) -> Optional[str]:
    client = _s3_client()
    bucket = os.getenv("S3_BUCKET")
    if client is None or not bucket:
        return _save_local(audio_bytes, call_id, turn_id, side)

    key = f"recordings/{call_id}/{turn_id}_{side}.webm"
    try:
        client.put_object(
            Bucket=bucket,
            Key=key,
            Body=audio_bytes,
            ContentType="audio/webm",
        )
        return f"s3://{bucket}/{key}"
    except Exception as exc:
        logger.debug("save_s3 failed: %s", exc)
        return _save_local(audio_bytes, call_id, turn_id, side)


def _load_s3(url: str) -> Optional[bytes]:
    client = _s3_client()
    if client is None:
        return None
    try:
        without = url[len("s3://"):]
        bucket, key = without.split("/", 1)
        resp = client.get_object(Bucket=bucket, Key=key)
        return resp["Body"].read()
    except Exception as exc:
        logger.debug("load_s3 failed: %s", exc)
        return None


def _delete_s3(url: str) -> bool:
    client = _s3_client()
    if client is None:
        return False
    try:
        without = url[len("s3://"):]
        bucket, key = without.split("/", 1)
        client.delete_object(Bucket=bucket, Key=key)
        return True
    except Exception as exc:
        logger.debug("delete_s3 failed: %s", exc)
        return False


# ---------------------------------------------------------------------------
# Signed URL for dashboard playback
# ---------------------------------------------------------------------------

def signed_playback_url(url: str, expires_seconds: int = 3600) -> Optional[str]:
    """Return a signed URL the dashboard can use to stream the audio.

    For local storage, returns the raw url (dashboards will serve it via
    the /api/v1/calls/audio endpoint). For S3, generates a presigned GET.
    """
    if not url:
        return None
    if url.startswith("local://"):
        return url
    if url.startswith("s3://"):
        client = _s3_client()
        if client is None:
            return None
        try:
            without = url[len("s3://"):]
            bucket, key = without.split("/", 1)
            return client.generate_presigned_url(
                "get_object",
                Params={"Bucket": bucket, "Key": key},
                ExpiresIn=expires_seconds,
            )
        except Exception as exc:
            logger.debug("presign failed: %s", exc)
    return None


# ---------------------------------------------------------------------------
# Cleanup
# ---------------------------------------------------------------------------

def cleanup_old_local(days: int = 30) -> int:
    """Delete local recordings older than N days. Returns count deleted."""
    deleted = 0
    try:
        import time
        cutoff = time.time() - days * 86400
        if not LOCAL_ROOT.exists():
            return 0
        for folder in LOCAL_ROOT.iterdir():
            if not folder.is_dir():
                continue
            if folder.stat().st_mtime < cutoff:
                shutil.rmtree(folder, ignore_errors=True)
                deleted += 1
    except Exception as exc:
        logger.debug("cleanup_old_local failed: %s", exc)
    return deleted