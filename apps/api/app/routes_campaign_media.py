"""Durable media upload for platform-owned WhatsApp campaigns.

Requires an S3-compatible bucket configured via MEDIA_S3_* environment variables.
Uploads are validated and bounded; local Render disk is never used for persistence.
"""
from __future__ import annotations

import uuid
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from .config import settings
from .db import SessionLocal
from .models import User
from .security import decode_token_strict
from . import jwt

router = APIRouter()
bearer = HTTPBearer(auto_error=False)
MAX_BYTES = 16 * 1024 * 1024
ALLOWED_TYPES = {"image/jpeg", "image/png", "image/webp", "video/mp4", "video/3gpp"}

def db_session():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def require_platform_admin(creds: HTTPAuthorizationCredentials | None = Depends(bearer), db: Session = Depends(db_session)):
    if not creds:
        raise HTTPException(401, "Authentication required")
    try:
        payload = decode_token_strict(creds.credentials, settings.jwt_secret, settings.jwt_algorithm)
    except Exception:
        raise HTTPException(401, "Invalid access token")
    user = db.get(User, payload.get("sub"))
    if not user or not user.is_active:
        raise HTTPException(401, "Invalid user")
    if user.role not in ("platform_admin", "super_admin"):
        raise HTTPException(403, "Platform admin access required")
    return user

@router.post("/api/v1/platform/communications/media")
async def upload_campaign_media(file: UploadFile = File(...), user=Depends(require_platform_admin)):
    if file.content_type not in ALLOWED_TYPES:
        raise HTTPException(415, "Supported formats: JPEG, PNG, WebP, MP4, 3GPP")
    if not all((settings.media_s3_bucket, settings.media_s3_region, settings.media_public_base_url,
                settings.media_s3_access_key_id, settings.media_s3_secret_access_key)):
        raise HTTPException(503, "Durable campaign media storage is not configured. Set MEDIA_S3_BUCKET, MEDIA_S3_REGION, MEDIA_S3_ACCESS_KEY_ID, MEDIA_S3_SECRET_ACCESS_KEY and MEDIA_PUBLIC_BASE_URL in Render.")
    data = await file.read(MAX_BYTES + 1)
    if not data:
        raise HTTPException(400, "Uploaded file is empty")
    if len(data) > MAX_BYTES:
        raise HTTPException(413, "Campaign media limit is 16 MB")
    # Basic signature checks prevent mismatched extensions/content-types.
    signatures = {
        "image/jpeg": data.startswith(b"\\xff\\xd8\\xff"),
        "image/png": data.startswith(b"\\x89PNG\\r\\n\\x1a\\n"),
        "image/webp": len(data) > 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP",
        "video/mp4": len(data) > 12 and data[4:8] == b"ftyp",
        "video/3gpp": len(data) > 12 and data[4:8] == b"ftyp",
    }
    if not signatures.get(file.content_type, False):
        raise HTTPException(415, "File contents do not match the declared media type")
    import boto3
    from botocore.config import Config
    key = "platform-campaigns/" + uuid.uuid4().hex
    try:
        client = boto3.client(
            "s3",
            region_name=settings.media_s3_region,
            endpoint_url=settings.media_s3_endpoint_url or None,
            aws_access_key_id=settings.media_s3_access_key_id,
            aws_secret_access_key=settings.media_s3_secret_access_key,
            config=Config(signature_version="s3v4"),
        )
        client.put_object(
            Bucket=settings.media_s3_bucket, Key=key, Body=data,
            ContentType=file.content_type, CacheControl="public, max-age=86400",
        )
    except Exception:
        raise HTTPException(502, "Campaign media storage upload failed; check S3-compatible storage configuration.")
    public_url = settings.media_public_base_url.rstrip("/") + "/" + key
    return {"uploaded": True, "media_url": public_url, "content_type": file.content_type, "size_bytes": len(data), "storage_key": key}
