"""
Wildix Voice Bot webhook handler.
Receives voice transcriptions and responds via Wildix API.
"""
import os
import json
import hmac
import hashlib
import logging
import requests
from core.orchestrator import process_message
from infra.db import SessionManager
from infra.timing import Timer, get_trace
from services.schedule_service import is_within_business_hours

logger = logging.getLogger(__name__)

WILDIX_API_BASE = "https://wim.wildix.com/v2/voicebots/sessions"
WILDIX_API_KEY = os.getenv("WILDIX_API_KEY", "")
WILDIX_WEBHOOK_SECRET = os.getenv("WILDIX_WEBHOOK_SECRET", "")
WILDIX_TRANSFER_CONTEXT = os.getenv("WILDIX_TRANSFER_CONTEXT", "from-internal")

session_manager = SessionManager()


def _verify_signature(request) -> bool:
    """Verify Wildix webhook signature."""
    if not WILDIX_WEBHOOK_SECRET:
        logger.warning("[WILDIX] No webhook secret configured, skipping verification")
        return True
    
    signature = request.headers.get("x-signature", "")
    if not signature:
        logger.warning("[WILDIX] No x-signature header")
        return False
    
    raw_body = request.get_data(as_text=True)
    expected = hmac.new(
        WILDIX_WEBHOOK_SECRET.encode(),
        raw_body.encode(),
        hashlib.sha256
    ).hexdigest()
    
    return hmac.compare_digest(signature, expected)


def handle_wildix(request):
    """Handle incoming Wildix Voice Bot webhook."""
    
    # Verify signature (optional - logs warning but doesn't block)
    if not _verify_signature(request):
        logger.warning("[WILDIX] Invalid or missing signature - proceeding anyway")
    
    data = request.get_json(silent=True) or {}
    
    session_id = data.get("sessionId")
    bot_id = data.get("botId")
    call_id = data.get("callId")
    event = data.get("event", {})
    
    event_type = event.get("type")
    event_id = event.get("id")
    text = event.get("text", "").strip()
    
    # Only process "reply" events (user speech)
    if event_type != "reply":
        return _json_response({"status": "ignored", "reason": f"event_type={event_type}"})
    
    if not text:
        logger.info("[WILDIX] Empty text, ignoring")
        return _json_response({"status": "ignored", "reason": "empty_text"})
    
    # Handle session reset
    if text.upper() == "BORRAR TODO":
        return _handle_session_reset(session_id, bot_id)
    
    # Try to acquire session lock (prevents concurrent processing for same call)
    if not session_manager.try_lock_session(session_id, bot_id or "default"):
        logger.info("[WILDIX] Session %s busy, ignoring: '%s'", session_id, text)
        return _json_response({"status": "ignored", "reason": "session_busy"})
    
    try:
        # Check business hours to decide flow
        # Mapeo manual de bot_id a company_id si es necesario (para pruebas)
        # El usuario indica que su company_id es 521783407682043
        search_id = bot_id or "default"
        if bot_id == "cXTekS0kyn5f":
            search_id = "521783407682043"
            logger.info(f"[WILDIX] Mapping bot_id {bot_id} to company_id {search_id}")

        in_business_hours = is_within_business_hours(search_id)
        
        # Log decision for debugging
        logger.info(f"[WILDIX] Business hours check: search_id={search_id} | in_hours={in_business_hours}")

        # Build payload compatible with orchestrator
        payload = {
            "wa_id": session_id,
            "mensaje": text,
            "phone_number_id": search_id,
            "company_id": search_id,
            "channel": "call",
            "wildix_metadata": {
                "session_id": session_id,
                "bot_id": bot_id,
                "call_id": call_id,
                "event_id": event_id,
            }
        }

        if in_business_hours:
            payload["force_agent"] = "dial_agent"
        else:
            # If outside hours, ensure we don't stay stuck in dial_agent from a previous in-hours call
            payload["force_agent_if_current"] = {"dial_agent": "receptionist_agent"}
        
        # Process through orchestrator
        response = process_message(payload)
        agent_message = response.get("message", "")
        
        # Send response to Wildix
        is_end_chat = response.get("status") == "completed" and response.get("session_deleted")
        is_transfer = response.get("status") == "transfer" and response.get("extension")
        
        if agent_message:
            wildix_response = _send_to_wildix(session_id, agent_message, event_id)
            logger.info(f"[WILDIX] Sent response: {agent_message[:50]}... wildix_status={wildix_response}")

        # Transfer call to PBX extension
        if is_transfer:
            extension = response["extension"]
            transfer_result = _transfer_wildix(session_id, extension)
            logger.info(f"[WILDIX] Transfer to extension {extension}: {transfer_result}")
        
        # If end_chat, hang up the call after sending the final message
        if is_end_chat:
            hangup_result = _hangup_wildix(session_id)
            logger.info(f"[WILDIX] Hangup after end_chat: {hangup_result}")
        
        # Dump timing trace after all wildix API calls
        trace = get_trace()
        if trace:
            try:
                trace.dump()
            except Exception:
                pass
        
        return _json_response({
            "status": "ok",
            "response": response,
            "wildix_sent": bool(agent_message),
            "hangup": is_end_chat,
            "transfer": is_transfer,
        })
    finally:
        session_manager.unlock_session(session_id, bot_id or "default")


def _handle_session_reset(session_id: str, bot_id: str):
    """Reset user session."""
    deleted = session_manager.delete_session(session_id, bot_id or "default")
    status = "deleted" if deleted else "not_found"
    
    return _json_response({
        "status": "ok",
        "action": "session_reset",
        "result": status
    })


def _send_to_wildix(session_id: str, text: str, reply_id: str = None, interruptible: bool = False) -> dict:
    """Send response to Wildix Voice Bot API."""
    
    if not WILDIX_API_KEY:
        logger.error("[WILDIX] No API key configured")
        return {"error": "no_api_key"}
    
    url = f"{WILDIX_API_BASE}/{session_id}/say"
    
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "Authorization": f"Bearer {WILDIX_API_KEY}"
    }
    
    body = {
        "text": text,
        "interruptible": interruptible
    }
    
    if reply_id:
        body["replyId"] = reply_id
    
    with Timer("wildix", "wildix_say"):
        try:
            resp = requests.post(url, headers=headers, json=body, timeout=10)
            resp.raise_for_status()
            return {"status": "sent", "code": resp.status_code}
        except requests.exceptions.RequestException as e:
            logger.error(f"[WILDIX] API error: {e}")
            return {"error": str(e)}


def _hangup_wildix(session_id: str) -> dict:
    """Hang up the Wildix Voice Bot call."""
    if not WILDIX_API_KEY:
        return {"error": "no_api_key"}
    
    url = f"{WILDIX_API_BASE}/{session_id}/hangup"
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "Authorization": f"Bearer {WILDIX_API_KEY}"
    }
    
    with Timer("wildix", "wildix_hangup"):
        try:
            resp = requests.post(url, headers=headers, timeout=10)
            resp.raise_for_status()
            return {"status": "hangup", "code": resp.status_code}
        except requests.exceptions.RequestException as e:
            logger.error(f"[WILDIX] Hangup error: {e}")
            return {"error": str(e)}


def _transfer_wildix(session_id: str, extension: str) -> dict:
    """Transfer a Wildix Voice Bot call to a PBX extension."""
    if not WILDIX_API_KEY:
        return {"error": "no_api_key"}

    url = f"{WILDIX_API_BASE}/{session_id}/transfer"
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "Authorization": f"Bearer {WILDIX_API_KEY}",
    }
    body = {
        "context": WILDIX_TRANSFER_CONTEXT,
        "extension": extension,
    }

    with Timer("wildix", "wildix_transfer"):
        try:
            resp = requests.post(url, headers=headers, json=body, timeout=10)
            resp.raise_for_status()
            logger.info(f"[WILDIX] Transfer OK → ext {extension} (context={WILDIX_TRANSFER_CONTEXT})")
            return {"status": "transferred", "code": resp.status_code, "extension": extension}
        except requests.exceptions.RequestException as e:
            logger.error(f"[WILDIX] Transfer error to ext {extension}: {e}")
            return {"error": str(e)}


def _json_response(data: dict, status_code: int = 200):
    """Return JSON response tuple."""
    return (
        json.dumps(data, ensure_ascii=False),
        status_code,
        {"Content-Type": "application/json"}
    )
