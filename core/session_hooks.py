import json
import logging

from infra.db import SessionManager

logger = logging.getLogger(__name__)

session_manager = SessionManager()


def handle_status_toggle(data: dict):
    """Toggle session AI status on/off.

    POST body: {"action": "set_status", "conversationId": "{company_id}_{user_id}", "status": "on|off"}
    """
    conversation_id = data.get("conversationId", "")
    new_status = data.get("status", "").lower()

    parts = conversation_id.split("_", 1)
    if len(parts) != 2 or not parts[0] or not parts[1]:
        return _json_response({"error": "Required: conversationId ({company_id}_{user_id}), status (on|off)"}, 400)

    company_id, wa_id = parts[0], parts[1]

    if new_status not in ("on", "off"):
        return _json_response({"error": "Required: status must be 'on' or 'off'"}, 400)

    session_manager.set_session_status(wa_id, company_id, new_status)
    logger.info(f"[SESSION] Status toggled: conversationId={conversation_id} → {new_status}")

    return _json_response({"status": "ok", "conversationId": conversation_id, "new_status": new_status})


def handle_session_reset(data: dict):
    """Reset user session in database."""
    wa_id = data.get("wa_id")
    company_id = data.get("phone_number_id") or "default"

    deleted = session_manager.delete_session(wa_id, company_id)
    result = "deleted" if deleted else "not_found"

    return _json_response({"status": "ok", "action": "session_reset", "result": result})


def _json_response(data: dict, status_code: int = 200):
    return (
        json.dumps(data, ensure_ascii=False),
        status_code,
        {"Content-Type": "application/json"},
    )
