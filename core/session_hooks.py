"""Session management hooks: status toggle, session reset."""

import logging

from core.session_store import get_session_manager

logger = logging.getLogger(__name__)

session_manager = get_session_manager()


def handle_status_toggle(data: dict) -> dict:
    """Toggle session AI status on/off.

    POST body: {"action": "set_status", "conversationId": "{company_id}_{user_id}", "status": "on|off"}

    Returns a plain dict. The API layer is responsible for HTTP response formatting.
    """
    conversation_id = data.get("conversationId", "")
    new_status = data.get("status", "").lower()

    parts = conversation_id.split("_", 1)
    if len(parts) != 2 or not parts[0] or not parts[1]:
        return {"error": "Required: conversationId ({company_id}_{user_id}), status (on|off)", "_status_code": 400}

    company_id, wa_id = parts[0], parts[1]

    if new_status not in ("on", "off"):
        return {"error": "Required: status must be 'on' or 'off'", "_status_code": 400}

    session_manager.set_session_status(wa_id, company_id, new_status)
    logger.info(f"[SESSION] Status toggled: conversationId={conversation_id} → {new_status}")

    return {"status": "ok", "conversationId": conversation_id, "new_status": new_status}


def handle_session_reset(data: dict) -> dict:
    """Reset user session in database.

    Returns a plain dict. The API layer is responsible for HTTP response formatting.
    """
    wa_id = data.get("wa_id")
    company_id = data.get("phone_number_id") or "default"

    deleted = session_manager.delete_session(wa_id, company_id)
    result = "deleted" if deleted else "not_found"

    return {"status": "ok", "action": "session_reset", "result": result}
