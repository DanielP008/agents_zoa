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
import base64
import requests
from core.orchestrator import process_message
from core.session_store import get_session_manager
from services.zoa_client import send_aichat_response

logger = logging.getLogger(__name__)
session_manager = get_session_manager()

def _download_and_encode_media(url):
    """Download file from URL and encode to base64 for OCR."""
    try:
        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            content_type = response.headers.get('Content-Type', 'application/octet-stream')
            encoded_data = base64.b64encode(response.content).decode('utf-8')
            filename = url.split('/')[-1]
            return {
                "mime_type": content_type,
                "data": encoded_data,
                "filename": filename
            }
        logger.error(f"[AICHAT] Failed to download media: {response.status_code}")
    except Exception as e:
        logger.error(f"[AICHAT] Error downloading media: {e}")
    return None

def handle_aichat(request):
    """Handle incoming AiChat webhook."""
    data = request.get_json(silent=True) or {}
    logger.info(f"[AICHAT] Received webhook payload: {json.dumps(data, ensure_ascii=False)}")
    
    user_id = data.get("user_id")
    company_id = data.get("company_id") or data.get("office_id") or request.args.get("company_id") or "default"
    
    # Ensure user_id is treated as string for consistency
    if user_id:
        user_id = str(user_id)
    
    # Extract text from body.data
    body = data.get("body", {})
    text = (body.get("data", "") if isinstance(body, dict) else "").strip()

    # Extract media attachments (images/documents)
    media = data.get("media") or []
    
    # Check if text is actually a Google Storage URL (ZOA sends attachments as links in text)
    if text.startswith("https://storage.googleapis.com/") and not media:
        logger.info(f"[AICHAT] Detected URL in text, attempting to download: {text}")
        media_obj = _download_and_encode_media(text)
        if media_obj:
            media = [media_obj]
            text = "" # Clear text so agent treats it as just an attachment
            logger.info("[AICHAT] Successfully converted URL to media attachment")

    if not user_id or (not text and not media):
        logger.warning(f"[AICHAT] Missing user_id or content: user_id={user_id}, text={text}, has_media={bool(media)}")
        return _json_response({"status": "ignored", "reason": "missing_data"})

    # Handle manual session reset
    if text.upper() == "BORRAR TODO":
        session_manager.delete_session(user_id, company_id)
        logger.info(f"[AICHAT] Session deleted manually via BORRAR TODO: user={user_id}, company={company_id}")
        
        reset_msg = "Sesión reiniciada."
        send_aichat_response(reset_msg, company_id, user_id)
        return _json_response({"status": "ok", "action": "session_reset", "session_deleted": True})
    
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
        
        # Auto-reset session if action is end_chat
        if response.get("action") == "end_chat":
            session_manager.delete_session(user_id, company_id)
            logger.info(f"[AICHAT] Session deleted automatically after end_chat: user={user_id}, company={company_id}")
        
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

def _json_response(data: dict, status_code: int = 200):
    """Return JSON response tuple."""
    return (
        json.dumps(data, ensure_ascii=False),
        status_code,
        {"Content-Type": "application/json"}
    )
