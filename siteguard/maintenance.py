import hmac
import logging
import os

from fastapi import APIRouter, Header, HTTPException

from .db import transaction

router = APIRouter()
logger = logging.getLogger("siteguard.maintenance")


def cleanup():
    with transaction() as db:
        deleted = db.execute("SELECT * FROM purge_expired_evidence()").fetchone()
        db.execute("DELETE FROM sessions WHERE expires_at<=clock_timestamp()")
        # Using the largest allowed interval keeps every step that a current offline lease could reference.
        db.execute("DELETE FROM dynamic_uses WHERE step < floor(extract(epoch FROM now()-interval '72 hours')/120)")
        db.execute("DELETE FROM attempt_limits WHERE window_start < extract(epoch FROM now()-interval '1 day')")
    logger.info("Expired image retention cleanup scan=%d badge=%d", deleted["scan_images"], deleted["badge_images"])
    return deleted


@router.get("/internal/daily", include_in_schema=False)
def daily_maintenance(authorization: str = Header(default="", max_length=1024)):
    cron_secret = os.getenv("CRON_SECRET", "")
    if len(cron_secret) < 16 or not hmac.compare_digest(authorization.encode(), ("Bearer " + cron_secret).encode()):
        raise HTTPException(401, "Unauthorized")
    return cleanup()
