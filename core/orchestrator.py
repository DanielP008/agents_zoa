import logging
from core.db import SessionManager
from core.timing import start_trace, dump_trace

logger = logging.getLogger(__name__)
from core.memory_schema import (
    append_turn,
    apply_memory_patch,
    ensure_memory_shape,
    update_global,
)
from core.routing.main_router import route_request
from services.zoa_client import send_whatsapp_response
from core.routing.allowlist import build_agent_allowlist, load_routes_config
from core.preprocessors import extract_attachments, handle_nif_and_welcome

session_manager = SessionManager()

_ROUTES_CONFIG = load_routes_config()
_AGENT_ALLOWLIST = build_agent_allowlist(_ROUTES_CONFIG)

def process_message(payload: dict) -> dict:
    
    wa_id = payload.get("wa_id")
    mensaje = payload.get("mensaje")
    phone_number_id = payload.get("phone_number_id")
    
    company_id = phone_number_id or "default"
    channel = payload.get("channel", "whatsapp")
    
    # Start timing trace for this request
    session_id = f"{company_id}_{wa_id}"
    start_trace(session_id, channel)
    
    # Add company_id to payload for agents and tools
    payload["company_id"] = company_id

    session = session_manager.get_session(wa_id, company_id)
    target_agent = session.get("target_agent", "receptionist_agent")
    memory = ensure_memory_shape(session.get("agent_memory", {}))

    # Handle attachments
    attachments = extract_attachments(payload)
    if attachments:
        global_mem = memory.get("global", {})
        existing = global_mem.get("attachments", [])
        if not isinstance(existing, list):
            existing = []
        memory = update_global(memory, attachments=existing + attachments)
        session["agent_memory"] = memory

        if not mensaje:
            mensaje = "[imagen adjunta]"
            payload["mensaje"] = mensaje

    # Handle NIF lookup and welcome message
    channel = payload.get("channel", "whatsapp")
    memory, nif_value, should_continue, generated_message = handle_nif_and_welcome(
        memory, 
        mensaje, 
        wa_id, 
        company_id,
        channel
    )
    
    session["agent_memory"] = memory
    
    # If _handle_nif_and_welcome returned should_continue=False, return early
    if not should_continue:
        dump_trace(channel)
        return {
            "type": "text",
            "message": generated_message or memory.get("global", {}).get("last_message", ""),
            "agent": "orchestrator"
        }

    payload["session"] = session

    MAX_CHAIN_DEPTH = 5
    chain_depth = 0
    
    while chain_depth < MAX_CHAIN_DEPTH:
        chain_depth += 1
        
        payload["allowed_next_agents"] = _AGENT_ALLOWLIST.get(target_agent, [])
        response = route_request(target_agent, payload)
        
        action = response.get("action")
        agent_message = response.get("message")
        tool_calls = response.get("tool_calls")

        if action == "end_chat":
            logger.info(f"[ORCHESTRATOR] end_chat action triggered. Cleaning up session for wa_id: {wa_id}")
            deleted = session_manager.delete_session(wa_id, company_id)
            
            if deleted:
                logger.info(f"[ORCHESTRATOR] Session successfully deleted for wa_id: {wa_id}")
            else:
                logger.warning(f"[ORCHESTRATOR] Failed to delete session for wa_id: {wa_id}")

            dump_trace(channel)
            return {
                "type": "text",
                "message": agent_message,
                "agent": "receptionist_agent",
                "status": "completed",
                "session_deleted": deleted
            }

        if action == "route" and not agent_message:
            new_target = response.get("next_agent")
            new_domain = response.get("domain")
            if new_domain is None:
                new_domain = session.get("domain")
            
            if not new_target:
                dump_trace(channel)
                return {"error": "Route action missing next_agent"}
            
            allowed_next = _AGENT_ALLOWLIST.get(target_agent, [])
            if new_target not in allowed_next:
                dump_trace(channel)
                return {
                    "type": "text",
                    "message": "No pude derivarte en este momento. ¿Podés intentar de nuevo?",
                    "agent": target_agent
                }
            
            session["target_agent"] = new_target
            if new_domain:
                session["domain"] = new_domain
            payload["session"] = session
            
            memory = apply_memory_patch(memory, response.get("memory", {}))
            memory = update_global(
                memory,
                last_agent=target_agent,
                last_action="passthrough",
                last_domain=new_domain,
            )
            session["agent_memory"] = memory
            target_agent = new_target
            continue
        
        break
    
    # Append user turn to memory AFTER routing chain resolved
    # (agents already include user_text in their own LLM context,
    #  appending before caused every message to appear twice)
    memory = append_turn(
        memory,
        role="user",
        text=mensaje,
        agent=target_agent,
        domain=session.get("domain"),
        action="input",
    )

    if chain_depth >= MAX_CHAIN_DEPTH:
        # Persist accumulated in-memory state before returning error
        session["agent_memory"] = memory
        session_manager.save_session(
            session_manager._get_composite_id(wa_id, company_id), session
        )
        dump_trace(channel)
        return {"error": "Max routing chain depth exceeded"}
    
    should_send_message = False
    if action in ["ask", "finish", "route"] and agent_message:
        should_send_message = True
    
    # Only send WhatsApp for whatsapp channel (wildix handles its own responses)
    channel = payload.get("channel", "whatsapp")
    if should_send_message and phone_number_id and channel == "whatsapp":
        whatsapp_result = send_whatsapp_response(
            text=agent_message,
            company_id=phone_number_id,
            wa_id=wa_id
        )
        
    elif should_send_message and not phone_number_id:
        pass

    if action == "ask":
        if agent_message:
            memory = append_turn(
                memory,
                role="assistant",
                text=agent_message,
                agent=target_agent,
                domain=session.get("domain"),
                action=action,
                tool_calls=tool_calls,
            )
        memory = apply_memory_patch(memory, response.get("memory", {}))
        memory = update_global(
            memory,
            last_agent=target_agent,
            last_action=action,
            last_domain=session.get("domain"),
        )
        # Persist target_agent + domain (may have changed during routing passthrough)
        session_manager.set_target_agent(wa_id, target_agent, session.get("domain"), company_id)
        session_manager.update_agent_memory(wa_id, memory, company_id)
        dump_trace(channel)
        result = {
            "type": "text",
            "message": agent_message,
            "agent": target_agent
        }
        return result
        
    if action == "route":
        new_target = response.get("next_agent")
        new_domain = response.get("domain")
        if new_domain is None:
            new_domain = session.get("domain")
        
        if not new_target:
            dump_trace(channel)
            return {"error": "Route action missing next_agent"}
        allowed_next = _AGENT_ALLOWLIST.get(target_agent, [])
        if new_target not in allowed_next:
            dump_trace(channel)
            return {
                "type": "text",
                "message": "No pude derivarte en este momento. ¿Podés intentar de nuevo?",
                "agent": target_agent
            }
        
        session_manager.set_target_agent(wa_id, new_target, new_domain, company_id)
        if agent_message:
            memory = append_turn(
                memory,
                role="assistant",
                text=agent_message,
                agent=target_agent,
                domain=new_domain,
                action=action,
                tool_calls=tool_calls,
            )
        memory = apply_memory_patch(memory, response.get("memory", {}))
        memory = update_global(
            memory,
            last_agent=target_agent,
            last_action=action,
            last_domain=new_domain,
        )
        session_manager.update_agent_memory(wa_id, memory, company_id)
        
        dump_trace(channel)
        result = {
            "type": "transition", 
            "message": agent_message,
            "next_agent": new_target
        }
        return result
            
    if action == "finish":
        session_manager.set_target_agent(wa_id, "receptionist_agent", None, company_id)
        
        if agent_message:
            memory = append_turn(
                memory,
                role="assistant",
                text=agent_message,
                agent=target_agent,
                domain=session.get("domain"),
                action=action,
                tool_calls=tool_calls,
            )
        
        memory = update_global(
            memory,
            last_agent=target_agent,
            last_action=action,
            last_domain=session.get("domain"),
            consultation_completed=True,
        )
        session_manager.update_agent_memory(wa_id, memory, company_id)
        
        dump_trace(channel)
        result = {
            "type": "text", 
            "message": agent_message, 
            "status": "completed"
        }
        return result

    dump_trace(channel)
    return {"error": "Unknown action"}