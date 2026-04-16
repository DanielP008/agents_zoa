"""Business-hours checker against the ``scheduler`` field stored in Firestore.

Firestore layout (collection ``clientIDs``):
    documentId: "0000-test"
    {
      ids: ["521783407682043", "+34960135890", "bf7eb..."],
      scheduler: {
        morning:   "9:00 - 14:30",
        afternoon: "15:30 - 18:00"
      },
      ...
    }

The *bot_id* received from Wildix is matched against the ``ids`` array to
locate the right company document.  If the current Spanish time falls inside
**any** of the time windows the company is considered "in business hours" and
the call should be routed to the human dial-agent.
"""

import logging
import os
import re
from datetime import datetime, timezone, timedelta
from typing import Optional

import firebase_admin
from firebase_admin import credentials, firestore

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Firebase singleton
# ---------------------------------------------------------------------------
_FIREBASE_APP: Optional[firebase_admin.App] = None
_FIRESTORE_DB = None

SPAIN_TZ_WINTER = timezone(timedelta(hours=1))   # CET
SPAIN_TZ_SUMMER = timezone(timedelta(hours=2))    # CEST

_TIME_RANGE_RE = re.compile(
    r"^\s*(\d{1,2}):(\d{2})\s*-\s*(\d{1,2}):(\d{2})\s*$"
)

# In-memory cache: bot_id → scheduler dict  (cleared on each cold start)
_SCHEDULE_CACHE: dict[str, dict | None] = {}


def _init_firebase() -> None:
    global _FIREBASE_APP, _FIRESTORE_DB
    if firebase_admin._apps:
        _FIREBASE_APP = firebase_admin.get_app()
        _FIRESTORE_DB = firestore.client()
        return

    cred_path = os.getenv("FIREBASE_CREDENTIALS_PATH", "")
    project_id = os.getenv("FIREBASE_PROJECT_ID", "")

    try:
        if cred_path and os.path.exists(cred_path):
            cred = credentials.Certificate(cred_path)
            _FIREBASE_APP = firebase_admin.initialize_app(cred)
        elif project_id:
            _FIREBASE_APP = firebase_admin.initialize_app(options={"projectId": project_id})
        else:
            _FIREBASE_APP = firebase_admin.initialize_app()
        _FIRESTORE_DB = firestore.client()
        logger.info("[SCHEDULE] Firebase initialised")
    except Exception as exc:
        logger.error(f"[SCHEDULE] Firebase init failed: {exc}")
        _FIREBASE_APP = None
        _FIRESTORE_DB = None


# ---------------------------------------------------------------------------
# Firestore helpers
# ---------------------------------------------------------------------------

def _find_scheduler_by_id(bot_id: str) -> dict | None:
    """Look up the ``scheduler`` map for the company whose ``ids`` contain *bot_id*."""
    _init_firebase()
    if _FIRESTORE_DB is None:
        return None

    try:
        query = (
            _FIRESTORE_DB
            .collection("clientIDs")
            .where(filter=firestore.FieldFilter("ids", "array_contains", bot_id))
            .limit(1)
        )
        docs = query.get()
        if docs:
            data = docs[0].to_dict()
            scheduler = data.get("scheduler")
            if isinstance(scheduler, dict):
                logger.info(f"[SCHEDULE] Found scheduler for bot_id={bot_id}: {scheduler}")
                return scheduler
            logger.warning(f"[SCHEDULE] Document found but no scheduler field for bot_id={bot_id}")
            return None

        logger.info(f"[SCHEDULE] No clientIDs document matched bot_id={bot_id}")
        return None
    except Exception as exc:
        logger.error(f"[SCHEDULE] Firestore query error: {exc}")
        return None


# ---------------------------------------------------------------------------
# Time helpers
# ---------------------------------------------------------------------------

def _get_spain_now() -> datetime:
    utc_now = datetime.now(timezone.utc)
    is_summer = 4 <= utc_now.month <= 10
    tz = SPAIN_TZ_SUMMER if is_summer else SPAIN_TZ_WINTER
    return utc_now.astimezone(tz)


def _parse_time_range(raw: str) -> tuple[int, int] | None:
    """Parse ``"9:00 - 14:30"`` → ``(540, 870)`` (minutes from midnight)."""
    m = _TIME_RANGE_RE.match(raw)
    if not m:
        return None
    open_min = int(m.group(1)) * 60 + int(m.group(2))
    close_min = int(m.group(3)) * 60 + int(m.group(4))
    return open_min, close_min


def _is_in_any_window(now_minutes: int, scheduler: dict) -> bool:
    """Return True if *now_minutes* falls inside any window in *scheduler*."""
    for key, raw_range in scheduler.items():
        if not isinstance(raw_range, str):
            continue
        parsed = _parse_time_range(raw_range)
        if parsed is None:
            logger.warning(f"[SCHEDULE] Could not parse range '{raw_range}' in key '{key}'")
            continue
        open_min, close_min = parsed
        if open_min <= now_minutes < close_min:
            return True
    return False


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def is_within_business_hours(bot_id: str = "default") -> bool:
    """Check whether the current time in Spain falls within the company's
    configured business hours stored in Firestore.

    Returns ``True`` when within hours → call should go to **dial_agent**
    (human transfer).  Returns ``False`` → AI agents handle the call.
    """
    # Try cache first
    if bot_id in _SCHEDULE_CACHE:
        scheduler = _SCHEDULE_CACHE[bot_id]
    else:
        scheduler = _find_scheduler_by_id(bot_id)
        _SCHEDULE_CACHE[bot_id] = scheduler

    if not scheduler:
        logger.info(f"[SCHEDULE] No scheduler for bot_id={bot_id} — treating as outside hours")
        return False

    now = _get_spain_now()
    now_minutes = now.hour * 60 + now.minute
    in_hours = _is_in_any_window(now_minutes, scheduler)

    logger.info(
        f"[SCHEDULE] bot_id={bot_id} | {now.strftime('%H:%M')} ({now_minutes}min) | "
        f"windows={scheduler} | in_hours={in_hours}"
    )
    return in_hours
