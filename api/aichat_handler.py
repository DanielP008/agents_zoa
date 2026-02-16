"""
AiChat message webhook handler.
Receives messages from AiChat source and responds via ZOA AiChat API.
"""
import json
import logging
from core.orchestrator import process_message
from infra.db import SessionManager
from services.zoa_client import send_aichat_response

logger = logging.getLogger(__name__)
session_manager = SessionManager()

def handle_aichat(request):
    """Handle incoming AiChat webhook."""
    data = request.get_json(silent=True) or {}
    
    wa_id = data.get("wa_id")
    company_id = data.get("phone_number_id") or "default"
    text = data.get("mensaje", "").strip()
    
    if not wa_id or not text:
        logger.warning(f"[AICHAT] Missing wa_id or text: wa_id={wa_id}, text={text}")
        return _json_response({"status": "ignored", "reason": "missing_data"})

    # Handle session reset
    if text.upper() == "BORRAR TODO":
        return _handle_session_reset(wa_id, company_id)
    
    # Try to acquire session lock
    if not session_manager.try_lock_session(wa_id, company_id):
        logger.info("[AICHAT] Session %s busy, ignoring: '%s'", wa_id, text)
        return _json_response({"status": "ignored", "reason": "session_busy"})
    
    try:
        # Build payload compatible with orchestrator
        # We use a NEW dict to avoid modifying the original request data in a way that could affect routing
        orchestrator_payload = {
            "wa_id": wa_id,
            "mensaje": text,
            "phone_number_id": company_id,
            "company_id": company_id,
            "channel": "aichat",
            "is_aichat": True
        }
        
        # Process through orchestrator
        response = process_message(orchestrator_payload)
        agent_message = response.get("message", "")
        
        if agent_message:
            aichat_response = send_aichat_response(agent_message, company_id, wa_id)
            logger.info(f"[AICHAT] Sent response: {agent_message[:50]}... aichat_status={aichat_response}")
        
        return _json_response({
            "status": "ok",
            "response": response,
            "aichat_sent": bool(agent_message)
        })
    finally:
        session_manager.unlock_session(wa_id, company_id)

def _handle_session_reset(wa_id: str, company_id: str):
    """Reset user session."""
    deleted = session_manager.delete_session(wa_id, company_id)
    status = "deleted" if deleted else "not_found"
    
    return _json_response({
        "status": "ok",
        "action": "session_reset",
        "result": status
    })

def _json_response(data: dict, status_code: int = 200):
    """Return JSON response tuple."""
    return (
        json.dumps(data, ensure_ascii=False),
        status_code,
        {"Content-Type": "application/json"}
    )
