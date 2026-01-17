import time

_STATE = {}
_TTL_SECONDS = 900


def _purge_expired(now: float) -> None:
    expired = [key for key, value in _STATE.items() if value["expires_at"] <= now]
    for key in expired:
        _STATE.pop(key, None)


def get_state(session_id: str) -> dict:
    now = time.time()
    _purge_expired(now)
    entry = _STATE.get(session_id)
    if not entry:
        return {}
    return entry["data"]


def set_state(session_id: str, data: dict) -> None:
    now = time.time()
    _purge_expired(now)
    _STATE[session_id] = {
        "data": data,
        "expires_at": now + _TTL_SECONDS,
    }
