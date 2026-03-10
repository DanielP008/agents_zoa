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
    option = data.get("option", "process")
    ramo_signal = data.get("ramo", "")

    logger.info(
        f"[WILDIX_CARD_HANDLER] Received: call_id={call_id}, "
        f"company_id={company_id}, option={option}, ramo={ramo_signal}, "
        f"msg_len={len(message)}, msg_preview={message[:200]!r}"
    )

    # --- IMMEDIATE CREATION SIGNAL ---
    if option == "create_empty" and ramo_signal:
        logger.info(f"[WILDIX_CARD_HANDLER] Processing CREATE_EMPTY signal for {ramo_signal}")
        try:
            from tools.sales.card_tools import create_card_tool, get_card_state
            
            # Determine sheet type
            sheet_type = "auto_sheet" if ramo_signal.upper() == "AUTO" else "home_sheet"
            
            # Prepare empty data structure with placeholders
            empty_data = {}
            if sheet_type == "auto_sheet":
                empty_data = {
                    "vehiculo": {"matricula": "-"},
                    "tomador": {
                        "nombre": "-", "apellido1": "-", "apellido2": "-", 
                        "dni": "-", "fecha_nacimiento": "-", "fecha_carnet": "-", 
                        "sexo": "-", "estado_civil": "-", "codigo_postal": "-"
                    },
                    "poliza_actual": {"numero_poliza": "-", "company": "-", "fecha_efecto": "-"}
                }
            elif sheet_type == "home_sheet":
                empty_data = {
                    "tomador": {
                        "nombre": "-", "apellido1": "-", "apellido2": "-", 
                        "dni": "-", "fecha_nacimiento": "-", "sexo": "-", 
                        "estado_civil": "-", "codigo_postal": "-", "telefono": "-", "email": "-"
                    },
                    "inmueble": {"direccion": "-", "tipo_vivienda": "-"},
                    "uso": {"tipo_uso": "-", "regimen": "-"},
                    "poliza_actual": {"fecha_efecto": "-"}
                }

            # Call tool directly with empty data
            result_str = create_card_tool(
                body_type=sheet_type,
                company_id=company_id,
                user_id=user_id,
                call_id=call_id,
                data=empty_data
            )
            
            # FIX: Save state to session so next request knows card exists
            session = session_manager.get_session(call_id, company_id)
            if "agent_memory" not in session: session["agent_memory"] = {}
            if "global" not in session["agent_memory"]: session["agent_memory"]["global"] = {}
            
            new_state = get_card_state()
            
            session["agent_memory"]["global"]["ramo_activo"] = new_state.get("ramo_activo")
            session["agent_memory"]["global"]["card_created"] = True
            session["agent_memory"]["global"]["card_data"] = empty_data
            
            session_manager.save_session(session["session_id"], session)
            logger.info(f"[WILDIX_CARD_HANDLER] Session saved after empty card creation for call_id={call_id}")
            
            logger.info(f"[WILDIX_CARD_HANDLER] Immediate card created: {result_str}")
            return _json_response({"status": "ok", "estado": "created_empty", "ramo": ramo_signal})
            
        except Exception as e:
            logger.exception(f"[WILDIX_CARD_HANDLER] Failed to create empty card: {e}")
            return _json_response({"status": "error", "reason": str(e)}, 500)

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
