"""Central orchestrator: receives messages, preprocesses, routes through agents, persists state."""

import logging
from core.action_handlers import (
    handle_ask,
    handle_end_chat,
    handle_finish,
    handle_route,
    persist_session,
    resolve_domain,
    validate_route_target,
)
from core.memory import (
    append_turn,
    apply_memory_patch,
    ensure_memory_shape,
    update_global,
)
from core.preprocessors import extract_attachments, process_attachments_ocr, try_silent_nif_lookup
from core.routing.allowlist import build_agent_allowlist, load_routes_config
from core.routing.main_router import route_request
from core.request_context import set_wa_context
from core.session_store import get_session_manager
from infra.timing import start_trace, dump_trace
from services.zoa_client import send_whatsapp_response_sync

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Module-level singletons / constants
# ---------------------------------------------------------------------------
_DEFAULT_AGENT = "receptionist_agent"
_MAX_CHAIN_DEPTH = 10
_ROUTE_BLOCKED_MSG = "No pude derivarte en este momento. ¿Podés intentar de nuevo?"

session_manager = get_session_manager()

_ROUTES_CONFIG = load_routes_config()
_AGENT_ALLOWLIST = build_agent_allowlist(_ROUTES_CONFIG)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _build_session_id(company_id: str, wa_id: str) -> str:
    return f"{company_id}_{wa_id}"


def _preprocess_message(payload: dict, session: dict) -> tuple[dict, dict, str]:
    """Extract attachments, run OCR, NIF lookup, persist identifiers.

    Returns:
        (memory, session, mensaje)
    """
    memory = ensure_memory_shape(session.get("agent_memory", {}))
    mensaje = payload.get("mensaje")
    wa_id = payload.get("wa_id")
    company_id = payload.get("company_id")

    # Attachment extraction + OCR
    attachments = extract_attachments(payload)
    if attachments:
        global_mem = memory.get("global", {})
        existing = global_mem.get("attachments", [])
        if not isinstance(existing, list):
            existing = []
        memory = update_global(memory, attachments=existing + attachments)

    # Silent CRM lookup for NIF (Parallelize with OCR if possible, but for now we keep order)
    memory, _ = try_silent_nif_lookup(memory, wa_id, company_id)

    # Run OCR (now after NIF lookup to potentially use NIF in OCR prompt if needed, 
    # but mainly to keep it separate from the main routing if it's slow)
    memory, ocr_text = process_attachments_ocr(memory)
    if ocr_text:
        mensaje = f"{mensaje}\n\n{ocr_text}" if mensaje else ocr_text
        payload["mensaje"] = mensaje
    elif attachments and not mensaje:
        mensaje = "[adjunto sin contenido extraíble]"
        payload["mensaje"] = mensaje

    # Silent CRM lookup for Name (if not already known)
    global_mem = memory.get("global", {})
    if not global_mem.get("name") and wa_id and company_id:
        try:
            from services.zoa_client import search_contact_by_phone
            contact_response = search_contact_by_phone(wa_id, company_id)
            if contact_response.get("success"):
                data = contact_response.get("data", [])
                if isinstance(data, list) and data:
                    name = data[0].get("name")
                    if name:
                        memory = update_global(memory, name=name)
                        logger.info(f"[ORCHESTRATOR] Found name from CRM: {name}")
        except Exception as e:
            logger.error(f"[ORCHESTRATOR] Name lookup error: {e}")

    # Persist identifiers in global memory
    if wa_id:
        memory = update_global(memory, wa_id=wa_id)
    if company_id:
        memory = update_global(memory, company_id=company_id)

    session["agent_memory"] = memory
    return memory, session, mensaje


def _send_whatsapp(text: str, phone_number_id: str, wa_id: str) -> None:
    """Send WhatsApp message synchronously (Cloud Run kills daemon threads after response)."""
    try:
        send_whatsapp_response_sync(text=text, company_id=phone_number_id, wa_id=wa_id)
        logger.info(f"[ORCHESTRATOR] WhatsApp message sent to {wa_id}")
    except Exception:
        logger.exception("[ORCHESTRATOR] WhatsApp send failed")


# ---------------------------------------------------------------------------
# Routing chain
# ---------------------------------------------------------------------------

def _run_routing_chain(payload: dict, session: dict, memory: dict,
                       target_agent: str) -> tuple[dict, dict, str, int]:
    """Execute the silent-passthrough routing loop.

    Returns:
        (response, memory, target_agent, chain_depth)
    """
    response = {}
    chain_depth = 0

    while chain_depth < _MAX_CHAIN_DEPTH:
        chain_depth += 1

        payload["allowed_next_agents"] = _AGENT_ALLOWLIST.get(target_agent, [])
        response = route_request(target_agent, payload)

        action = response.get("action")
        agent_message = response.get("message")

        if action == "end_chat":
            break

        if action == "transfer_call":
            break

        # Silent passthrough: route with no user-facing message
        if action == "route":
            new_target = response.get("next_agent")
            new_domain = resolve_domain(response, session)

            error = validate_route_target(target_agent, new_target, _AGENT_ALLOWLIST)
            if error:
                response = {"_routing_error": error}
                break

            # If there is a message, send it and record it
            if agent_message:
                # 1. Send to WhatsApp
                if payload.get("phone_number_id") and payload.get("channel") == "whatsapp":
                     _send_whatsapp(agent_message, payload["phone_number_id"], payload.get("wa_id"))
                
                # 2. Record in memory
                memory = append_turn(
                    memory,
                    role="assistant",
                    text=agent_message,
                    agent=target_agent,
                    domain=new_domain,
                    action="route",
                    tool_calls=response.get("tool_calls")
                )

            session["target_agent"] = new_target
            session["domain"] = new_domain
            payload["session"] = session

            memory = apply_memory_patch(memory, response.get("memory", {}))
            memory = update_global(
                memory,
                last_agent=target_agent,
                last_action="route" if agent_message else "passthrough",
                last_domain=new_domain,
            )
            session["agent_memory"] = memory
            target_agent = new_target
            continue

        break

    return response, memory, target_agent, chain_depth


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def process_message(payload: dict) -> dict:
    """Process an incoming message end-to-end.

    1. Load/create session
    2. Preprocess (attachments, OCR, NIF)
    3. Route through agent chain
    4. Handle resulting action (ask / route / finish / end_chat)
    5. Persist session and return response
    """
    wa_id = payload.get("wa_id")
    phone_number_id = payload.get("phone_number_id")
    company_id = payload.get("company_id") or phone_number_id or "default"
    channel = payload.get("channel", "whatsapp")

    session_id = _build_session_id(company_id, wa_id)
    start_trace(session_id, channel)

    payload["company_id"] = company_id

    # 1. Session
    session = session_manager.get_session(wa_id, company_id)
    
    # Use specialized receptionist for AiChat
    is_aichat = payload.get("is_aichat", False)
    default_agent = "aichat_receptionist_agent" if is_aichat else _DEFAULT_AGENT
    target_agent = session.get("target_agent") or default_agent

    # Override agent if force_agent is set (e.g. dial_agent during business hours)
    force_agent = payload.get("force_agent")
    if force_agent:
        target_agent = force_agent
    
    # Optional override if current agent matches a specific key (e.g. force exit dial_agent if out of hours)
    force_agent_if_current = payload.get("force_agent_if_current", {})
    if target_agent in force_agent_if_current:
        target_agent = force_agent_if_current[target_agent]

    if is_aichat:
        logger.info(f"[ORCHESTRATOR] Processing AiChat message for user {wa_id}. Target agent: {target_agent}")

    # If AiChat but session has the WhatsApp receptionist (stale/default), override
    if is_aichat and target_agent == _DEFAULT_AGENT:
        target_agent = default_agent

    # 2. Preprocessing
    memory, session, mensaje = _preprocess_message(payload, session)
    payload["session"] = session
    
    # Update mensaje if it was changed during preprocessing (OCR/NIF)
    if payload.get("mensaje"):
        mensaje = payload["mensaje"]
    
    # If NIF was extracted in this turn, ensure it's available for routing
    global_mem = memory.get("global", {})
    nif_value = global_mem.get("nif")

    # Set WhatsApp context so agent_runner can send "please wait" on tool use
    client_name = global_mem.get("client_name", "")
    set_wa_context(wa_id, phone_number_id, channel, client_name=client_name)

    # 3. Routing chain
    response, memory, target_agent, chain_depth = _run_routing_chain(
        payload, session, memory, target_agent,
    )
    
    if is_aichat:
        logger.info(f"[ORCHESTRATOR] Routing chain finished for AiChat. Final agent: {target_agent}, Action: {response.get('action')}")

    # Handle routing-loop validation errors
    if "_routing_error" in response:
        error_msg = response["_routing_error"]
        dump_trace(channel)
        if error_msg == _ROUTE_BLOCKED_MSG:
            return {"type": "text", "message": error_msg, "agent": target_agent}
        return {"error": error_msg}

    action = response.get("action")
    agent_message = response.get("message")

    # Guard: if agent returned ask/finish with empty message, use fallback
    if action in ("ask", "finish") and (not agent_message or not agent_message.strip()):
        logger.warning(f"[ORCHESTRATOR] Agent '{target_agent}' returned empty message with action='{action}'. Using fallback.")
        agent_message = "Disculpa, no he podido procesar tu mensaje. ¿Podrías repetírmelo?"
        response["message"] = agent_message

    # 3a. end_chat can happen inside the loop
    if action == "end_chat":
        return handle_end_chat(wa_id, company_id, agent_message, channel,
                               session_manager, is_aichat=payload.get("is_aichat", False))

    # 3b. transfer_call: dial_agent wants to transfer to a PBX extension
    if action == "transfer_call":
        extension = response.get("extension", "")
        logger.info(f"[ORCHESTRATOR] transfer_call to extension={extension} for wa_id={wa_id}")
        deleted = session_manager.delete_session(wa_id, company_id)
        dump_trace(channel)
        return {
            "type": "transfer",
            "message": agent_message,
            "extension": extension,
            "agent": target_agent,
            "status": "transfer",
            "session_deleted": deleted,
        }

    # Append user turn AFTER routing chain resolved
    memory = append_turn(
        memory, role="user", text=mensaje,
        agent=target_agent, domain=session.get("domain"), action="input",
    )

    # Max depth guard
    if chain_depth >= _MAX_CHAIN_DEPTH:
        persist_session(session, session_id, target_agent=target_agent,
                        domain=session.get("domain"), memory=memory,
                        session_manager=session_manager)
        dump_trace(channel)
        return {"error": "Max routing chain depth exceeded"}

    # 4. Send WhatsApp (fire-and-forget)
    if agent_message and action in ("ask", "finish", "route"):
        if phone_number_id and channel == "whatsapp":
            _send_whatsapp(agent_message, phone_number_id, wa_id)

    # 5. Dispatch to action handler
    common = dict(
        response=response, session=session, session_id=session_id,
        memory=memory, target_agent=target_agent, channel=channel,
        session_manager=session_manager, is_aichat=payload.get("is_aichat", False),
    )

    if action == "ask":
        return handle_ask(**common)
    if action == "route":
        return handle_route(**common, allowlist=_AGENT_ALLOWLIST)
    if action == "finish":
        return handle_finish(**common)

    dump_trace(channel)
    return {"error": f"Unknown action: {action}"}
