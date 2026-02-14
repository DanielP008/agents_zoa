import json
import logging
import sys
from datetime import datetime, timezone, timedelta

from core.orchestrator import process_message
from infra.db import SessionManager
from infra.tracing import setup_tracing
from api.wildix_handler import handle_wildix
from services.zoa_client import is_business_open

# Configure logging to stdout
logging.basicConfig(
    stream=sys.stdout, 
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s'
)
logger = logging.getLogger(__name__)

setup_tracing()


def handle_request(request):
    """Main entry point - routes to appropriate handler based on request."""
    data = request.get_json(silent=True) or {}
    
    # Wildix webhook detection
    if "sessionId" in data and "botId" in data and "event" in data:
        event = data.get("event", {})
        event_type = event.get("type")
        text = event.get("text", "").strip()
        if event_type == "reply" and text:
            logger.info("[WILDIX_FINAL_MESSAGE] session=%s text='%s'", data.get("sessionId"), text)
        return handle_wildix(request)
    
    # Default to WhatsApp handler
    return handle_whatsapp(request)


def handle_whatsapp(request):
    """Handle incoming ZOA Buffer System messages."""
    
    data = request.get_json(silent=True) or {}
    
    mensaje = data.get("mensaje", "").strip()
    
    # Handle session reset with "BORRAR TODO"
    if mensaje == "BORRAR TODO":
        return handle_session_reset(data)
    
    # Check business hours — AI only processes when the office is closed
    # Weekends (Sat/Sun) are always treated as closed → AI processes
    company_id = data.get("phone_number_id") or "default"
    now_madrid = datetime.now(timezone(timedelta(hours=1)))
    is_weekend = now_madrid.weekday() >= 5  # 5=Saturday, 6=Sunday

    if not is_weekend:
        try:
            if is_business_open(company_id):
                return (
                    json.dumps({"status": "ok", "response": {"skipped": True, "reason": "business_open"}}, ensure_ascii=False),
                    200,
                    {"Content-Type": "application/json"},
                )
        except Exception as e:
            logger.error(f"[HANDLER] Scheduler check failed: {e}, proceeding with AI processing")
    
    response = process_message(data)

    return (
        json.dumps({"status": "ok", "response": response}, ensure_ascii=False),
        200,
        {"Content-Type": "application/json"},
    )

def handle_session_reset(data):
    """Reset user session in database."""
    wa_id = data.get("wa_id")
    company_id = data.get("phone_number_id") or "default"
    
    session_manager = SessionManager()
    deleted = session_manager.delete_session(wa_id, company_id)
    
    status = "deleted" if deleted else "not_found"
    
    return (
        json.dumps({"status": "ok", "action": "session_reset", "result": status}, ensure_ascii=False),
        200,
        {"Content-Type": "application/json"},
    )
