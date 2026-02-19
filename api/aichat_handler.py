"""
AiChat message webhook handler.
Receives messages from AiChat and responds via ZOA AiChat API.

Incoming format (text):
{
    "user_id": "uuid-del-usuario",
    "body_type": "text",
    "body": { "data": "mensaje del usuario" },
    "origin": "ai_chat"
}

Incoming format (with attachments):
{
    "user_id": "uuid-del-usuario",
    "body_type": "text",
    "body": { "data": "mensaje del usuario" },
    "origin": "ai_chat",
    "media": [{ "mime_type": "image/jpeg", "data": "<base64>", "filename": "doc.jpg" }]
}
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
    logger.info(f"[AICHAT] Received webhook payload: {json.dumps(data, ensure_ascii=False)}")
    
    user_id = data.get("user_id")
    company_id = data.get("company_id") or request.args.get("company_id") or "default"
    
    # Extract text from body.data
    body = data.get("body", {})
    text = (body.get("data", "") if isinstance(body, dict) else "").strip()

    # Extract media attachments (images/documents)
    media = data.get("media")

    if not user_id or (not text and not media):
        logger.warning(f"[AICHAT] Missing user_id or content: user_id={user_id}, text={text}, has_media={bool(media)}")
        return _json_response({"status": "ignored", "reason": "missing_data"})

    # Handle session reset
    if text.upper() == "BORRAR TODO":
        return _handle_session_reset(user_id, company_id)
    
    # Try to acquire session lock (use user_id as wa_id for session key)
    if not session_manager.try_lock_session(user_id, company_id):
        logger.info("[AICHAT] Session %s busy, ignoring: '%s'", user_id, text)
        return _json_response({"status": "ignored", "reason": "session_busy"})
    
    try:
        orchestrator_payload = {
            "wa_id": user_id,
            "mensaje": text,
            "company_id": company_id,
            "channel": "aichat",
            "is_aichat": True,
            "aichat_user_id": user_id,
        }

        if media:
            orchestrator_payload["media"] = media
            logger.info(f"[AICHAT] Attachments: {len(media)} file(s)")

        log_payload = {k: v for k, v in orchestrator_payload.items() if k != "media"}
        logger.info(f"[AICHAT] Processing with orchestrator payload: {json.dumps(log_payload, ensure_ascii=False)}")
        
        response = process_message(orchestrator_payload)
        logger.info(f"[AICHAT] Orchestrator response: {json.dumps(response, ensure_ascii=False)}")
        agent_message = response.get("message", "")
        
        if agent_message:
            aichat_response = send_aichat_response(agent_message, company_id, user_id)
            logger.info(f"[AICHAT] Sent response: {agent_message[:50]}... aichat_status={aichat_response}")
        
        return _json_response({
            "status": "ok",
            "response": response,
            "aichat_sent": bool(agent_message)
        })
    finally:
        session_manager.unlock_session(user_id, company_id)

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
