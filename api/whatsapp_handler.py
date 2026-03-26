import json
import logging

from core.orchestrator import process_message
from core.session_hooks import handle_session_reset, session_manager

logger = logging.getLogger(__name__)


def handle_whatsapp(request):
    """Handle incoming ZOA Buffer System messages.

    Status logic:
    - Status='on' (or new user) → process (AI active).
    - Status='off' → ignore (humans handling).
    """
    data = request.get_json(silent=True) or {}

    mensaje = data.get("mensaje", "").strip()
    if mensaje == "BORRAR TODO":
        return _json_response(handle_session_reset(data))

    wa_id = data.get("wa_id")
    company_id = data.get("phone_number_id") or "default"

    status = session_manager.get_session_status(wa_id, company_id)
    logger.info(f"[WHATSAPP] wa_id={wa_id} status={status}")

    if status is None:
        session_manager.set_session_status(wa_id, company_id, "on")
        logger.info(f"[WHATSAPP] New user — created session with status='on' for {wa_id}")
    elif status != "on":
        logger.info(f"[WHATSAPP] Status=off — skipping for {wa_id}")
        return _json_response({"status": "ok", "response": {"skipped": True, "reason": "status_off"}})

    response = process_message(data)
    return _json_response({"status": "ok", "response": response})


def _json_response(data: dict, status_code: int = 200):
    return (
        json.dumps(data, ensure_ascii=False),
        status_code,
        {"Content-Type": "application/json"},
    )
