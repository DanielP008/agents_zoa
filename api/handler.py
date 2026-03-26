import json
import logging
import sys

from infra.tracing import setup_tracing
from api.wildix_handler import handle_wildix
from api.aichat_handler import handle_aichat
from api.wildix_card_handler import handle_insurance_agent
from core.session_hooks import handle_status_toggle
from api.whatsapp_handler import handle_whatsapp

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
        result = handle_status_toggle(data)
        status_code = result.pop("_status_code", 200)
        return _json_response(result, status_code)
    
    # Health check endpoint
    if request.path == "/health":
        return _json_response({"status": "ok", "message": "Service is healthy"})
    
    # Insurance agent (buffered call transcriptions from zoa_buffer)
    if data.get("action") == "insurance_agent":
        logger.info("[HANDLER] Routing to insurance_agent (wildix card handler)")
        return handle_insurance_agent(request)

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


def _json_response(data: dict, status_code: int = 200):
    return (
        json.dumps(data, ensure_ascii=False),
        status_code,
        {"Content-Type": "application/json"},
    )
