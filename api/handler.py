import json
import logging
import sys
from core.orchestrator import process_message
from core.db import SessionManager
from core.tracing import setup_tracing
from api.wildix_handler import handle_wildix

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
            print(f"\n[WILDIX_FINAL_MESSAGE] session={data.get('sessionId')} text='{text}'\n")
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
