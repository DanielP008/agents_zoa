import json
import logging
import sys
from datetime import datetime, timezone, timedelta

from core.orchestrator import process_message
from infra.db import SessionManager
from infra.tracing import setup_tracing
from api.wildix_handler import handle_wildix
from api.aichat_handler import handle_aichat
from services.zoa_client import is_business_open

# Configure logging to stdout
logging.basicConfig(
    stream=sys.stdout, 
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s'
)
logger = logging.getLogger(__name__)

setup_tracing()


session_manager = SessionManager()


def handle_request(request):
    """Main entry point - routes to appropriate handler based on request."""
    logger.info(f"[HANDLER] Incoming request: {request.method} {request.url}")
    logger.info(f"[HANDLER] Headers: {dict(request.headers)}")
    
    # Handle CORS preflight
    if request.method == 'OPTIONS':
        return ('', 204, {
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Methods': 'POST, GET, OPTIONS',
            'Access-Control-Allow-Headers': 'Content-Type, Authorization',
            'Access-Control-Max-Age': '3600'
        })

    data = request.get_json(silent=True) or {}

    # Status toggle endpoint
    if data.get("action") == "set_status":
        return handle_status_toggle(data)
    
    # Wildix webhook detection
    if "sessionId" in data and "botId" in data and "event" in data:
        event = data.get("event", {})
        event_type = event.get("type")
        text = event.get("text", "").strip()
        if event_type == "reply" and text:
            logger.info("[WILDIX_FINAL_MESSAGE] session=%s text='%s'", data.get("sessionId"), text)
        return handle_wildix(request)
    
    # AiChat webhook detection
    if data.get("origin") == "ai_chat" or data.get("source") == "ai-chat" or data.get("is_aichat"):
        logger.info(f"[HANDLER] Routing to AiChat handler. Origin: {data.get('origin')}, Source: {data.get('source')}")
        return handle_aichat(request)
    
    # Default to WhatsApp handler
    return handle_whatsapp(request)


def handle_whatsapp(request):
    """Handle incoming ZOA Buffer System messages.

    Business hours + status logic:
    - Outside hours → always process. Flip status to 'on' if it was 'off'.
    - Inside hours + status='on'  → process (AI active).
    - Inside hours + status='off' → ignore (humans handling).
    """
    data = request.get_json(silent=True) or {}

    mensaje = data.get("mensaje", "").strip()
    if mensaje == "BORRAR TODO":
        return handle_session_reset(data)

    wa_id = data.get("wa_id")
    company_id = data.get("phone_number_id") or "default"

    # Step 1: Determine if we're outside business hours
    now_madrid = datetime.now(timezone(timedelta(hours=1)))
    is_weekend = now_madrid.weekday() >= 5

    if is_weekend:
        outside_hours = True
    else:
        try:
            outside_hours = not is_business_open(company_id)
        except Exception as e:
            logger.error(f"[HANDLER] Scheduler check failed: {e}, treating as outside hours")
            outside_hours = True

    # Step 2: Apply status logic
    status = session_manager.get_session_status(wa_id, company_id)
    logger.info(f"[HANDLER] wa_id={wa_id} outside_hours={outside_hours} status={status}")

    if status is None:
        # New user — create session with status='on'
        session_manager.set_session_status(wa_id, company_id, "on")
        logger.info(f"[HANDLER] New user — created session with status='on' for {wa_id}")
    elif outside_hours:
        if status != "on":
            session_manager.set_session_status(wa_id, company_id, "on")
            logger.info(f"[HANDLER] Outside hours — flipped status to 'on' for {wa_id}")
    else:
        if status != "on":
            logger.info(f"[HANDLER] In hours & status=off — skipping for {wa_id}")
            return _json_response({"status": "ok", "response": {"skipped": True, "reason": "in_hours_status_off"}})

    response = process_message(data)
    return _json_response({"status": "ok", "response": response})

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
    logger.info(f"[HANDLER] Status toggled: conversationId={conversation_id} → {new_status}")

    return _json_response({"status": "ok", "conversationId": conversation_id, "new_status": new_status})


def handle_session_reset(data):
    """Reset user session in database."""
    wa_id = data.get("wa_id")
    company_id = data.get("phone_number_id") or "default"

    deleted = session_manager.delete_session(wa_id, company_id)
    status = "deleted" if deleted else "not_found"

    return _json_response({"status": "ok", "action": "session_reset", "result": status})


def _json_response(data: dict, status_code: int = 200):
    return (
        json.dumps(data, ensure_ascii=False),
        status_code,
        {"Content-Type": "application/json"},
    )
