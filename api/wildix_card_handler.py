"""Handler for insurance_agent action from zoa_buffer (call transcriptions).

This is a background processor — no user-facing response is sent.
It receives concatenated call text, runs the wildix_card_agent to classify
and extract data, then persists the card state in the session.
"""

import json
import logging

from infra.db import SessionManager
from agents.domains.ventas.wildix_card_agent import wildix_card_agent

logger = logging.getLogger(__name__)

session_manager = SessionManager()


def handle_insurance_agent(request) -> tuple:
    """Entry point for action=insurance_agent from zoa_buffer.

    Expected payload:
        {
            "action": "insurance_agent",
            "option": "process",
            "company_id": "...",
            "user_id": "...",
            "call_id": "...",
            "message": "concatenated transcription text"
        }
    """
    data = request.get_json(silent=True) or {}

    company_id = data.get("company_id", "")
    user_id = data.get("user_id", "")
    call_id = data.get("call_id", "")
    message = data.get("message", "").strip()
    full_transcript = data.get("full_transcript", "")

    logger.info(
        f"[WILDIX_CARD_HANDLER] Received: call_id={call_id}, "
        f"company_id={company_id}, msg_len={len(message)}, "
        f"transcript_len={len(full_transcript)}, "
        f"msg_preview={message[:200]!r}"
    )

    if not message:
        return _json_response({"status": "ok", "estado": "ignored", "reason": "empty_message"})

    session = session_manager.get_session(call_id, company_id)
    existing_global = session.get("agent_memory", {}).get("global", {})
    logger.info(
        f"[WILDIX_CARD_HANDLER] Session loaded: ramo_activo={existing_global.get('ramo_activo')}, "
        f"card_created={existing_global.get('card_created', False)}"
    )

    payload = {
        "company_id": company_id,
        "user_id": user_id,
        "call_id": call_id,
        "message": message,
        "full_transcript": full_transcript,
        "session": session,
    }

    try:
        result = wildix_card_agent(payload)
    except Exception:
        logger.exception("[WILDIX_CARD_HANDLER] Agent execution failed")
        return _json_response({"status": "error", "reason": "agent_error"}, 500)

    tool_calls = result.get("tool_calls")
    logger.info(
        f"[WILDIX_CARD_HANDLER] Agent result: estado={result.get('estado')}, "
        f"ramo={result.get('ramo')}, "
        f"tools={[tc['name'] for tc in tool_calls] if tool_calls else 'none'}"
    )

    memory_patch = result.get("memory_patch", {})
    if memory_patch:
        agent_memory = session.get("agent_memory", {})
        global_mem = agent_memory.get("global", {})
        global_mem.update(memory_patch.get("global", {}))
        agent_memory["global"] = global_mem
        session["agent_memory"] = agent_memory

        session_manager.save_session(session["session_id"], session)
        logger.info(f"[WILDIX_CARD_HANDLER] Session saved for call_id={call_id}")

    return _json_response({
        "status": "ok",
        "estado": result.get("estado", "unknown"),
        "ramo": result.get("ramo"),
    })


def _json_response(data: dict, status_code: int = 200) -> tuple:
    return (
        json.dumps(data, ensure_ascii=False),
        status_code,
        {"Content-Type": "application/json"},
    )
