from urllib.parse import urlsplit

import httpx
from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models import CloudSyncOutbox
from app.time_utils import utc_iso


router = APIRouter(prefix="/api/cloud", tags=["Cloud Sync"])


def _health_url() -> str:
    parsed = urlsplit(settings.CLOUD_API_URL)
    if not parsed.scheme or not parsed.netloc:
        return ""
    return f"{parsed.scheme}://{parsed.netloc}/health"


@router.get("/status")
async def cloud_sync_status(db: Session = Depends(get_db)):
    pending = db.query(func.count(CloudSyncOutbox.id)).filter(
        CloudSyncOutbox.status == "PENDING"
    ).scalar() or 0
    failed = db.query(func.count(CloudSyncOutbox.id)).filter(
        CloudSyncOutbox.status == "FAILED"
    ).scalar() or 0
    last_uploaded_at = db.query(func.max(CloudSyncOutbox.uploaded_at)).scalar()

    if not settings.CLOUD_UPLOAD_ENABLED:
        return {
            "status": "disabled",
            "reachable": False,
            "pending": pending,
            "failed": failed,
            "last_uploaded_at": utc_iso(last_uploaded_at) if last_uploaded_at else None,
        }

    reachable = False
    error = None
    health_url = _health_url()
    try:
        if not health_url:
            raise ValueError("CLOUD_API_URL is not configured")
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(health_url)
            reachable = response.status_code == 200
            if not reachable:
                error = f"HTTP {response.status_code}"
    except Exception as exc:
        error = str(exc)[:300]

    if not reachable or failed > 0:
        status = "error"
    elif pending > 0:
        status = "pending"
    else:
        status = "healthy"

    return {
        "status": status,
        "reachable": reachable,
        "pending": pending,
        "failed": failed,
        "last_uploaded_at": utc_iso(last_uploaded_at) if last_uploaded_at else None,
        "error": error,
    }
