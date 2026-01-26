import os
from core.db import SessionManager
from core.memory_schema import (
    append_turn,
    apply_memory_patch,
    ensure_memory_shape,
    update_global,
)
from routers.main_router import route_request
from tools.zoa_client import send_whatsapp_response
from core.agent_allowlist import build_agent_allowlist, load_routes_config

# Managers
session_manager = SessionManager()

# Routes config for allowlist validation
_ROUTES_CONFIG = load_routes_config()
_AGENT_ALLOWLIST = build_agent_allowlist(_ROUTES_CONFIG)

def process_message(payload: dict) -> dict:
    
    # Use Buffer System names (Source of Truth)
    wa_id = payload.get("wa_id")
    mensaje = payload.get("mensaje")
    company_id = payload.get("phone_number_id")
    
    
    # 1. Load Session
    safe_company_id = company_id or "default"
    session = session_manager.get_session(wa_id, safe_company_id)
    target_agent = session.get("target_agent", "receptionist_agent")
    
    memory = ensure_memory_shape(session.get("agent_memory", {}))
    memory = append_turn(
        memory,
        role="user",
        text=mensaje,
        agent=target_agent,
        domain=session.get("domain"),
        action="input",
    )
    session["agent_memory"] = memory
    payload["session"] = session

    # Agent processing loop (supports passthrough routing)
    MAX_CHAIN_DEPTH = 5  # Prevent infinite loops
    chain_depth = 0
    
    while chain_depth < MAX_CHAIN_DEPTH:
        chain_depth += 1
        
        payload["allowed_next_agents"] = _AGENT_ALLOWLIST.get(target_agent, [])
        # 2. Route to the target agent (State Machine)
        response = route_request(target_agent, payload)
        
        # 3. Handle Agent Response
        action = response.get("action")
        agent_message = response.get("message")


        # Check if agent used end_chat_tool
        if action == "end_chat":
            # Delete session from postgres (this will clear all session data including agent_memory)
            # No need to reset target_agent first - deletion will clear everything
            deleted = session_manager.delete_session(wa_id, safe_company_id)
            
            if not deleted:
                logger.warning(f"Failed to delete session for wa_id: {wa_id}, company_id: {safe_company_id}")

            # Return final message to user
            return {
                "type": "text",
                "message": agent_message,
                "agent": "receptionist_agent",
                "status": "completed"
            }


        # Check for passthrough route (route without message)
        if action == "route" and not agent_message:
            new_target = response.get("next_agent")
            new_domain = response.get("domain")
            if new_domain is None:
                new_domain = session.get("domain")
            
            if not new_target:
                return {"error": "Route action missing next_agent"}
            
            allowed_next = _AGENT_ALLOWLIST.get(target_agent, [])
            if new_target not in allowed_next:
                return {
                    "type": "text",
                    "message": "No pude derivarte en este momento. ¿Podés intentar de nuevo?",
                    "agent": target_agent
                }
            
            
            # Update session for next agent in chain
            session["target_agent"] = new_target
            if new_domain:
                session["domain"] = new_domain
            payload["session"] = session
            
            # Update memory with route info (no message to log)
            memory = apply_memory_patch(memory, response.get("memory", {}))
            memory = update_global(
                memory,
                last_agent=target_agent,
                last_action="passthrough",
                last_domain=new_domain,
            )
            session["agent_memory"] = memory
            
            # Persist the routing change
            session_manager.set_target_agent(wa_id, new_target, new_domain, safe_company_id)
            session_manager.update_agent_memory(wa_id, memory, safe_company_id)
            
            # Continue loop with new target
            target_agent = new_target
            continue
        
        # Not a passthrough, break loop and process normally
        break
    
    if chain_depth >= MAX_CHAIN_DEPTH:
        return {"error": "Max routing chain depth exceeded"}
    
    # Decide if we need to send a message back to WhatsApp
    should_send_message = False
    if action in ["ask", "finish", "route"] and agent_message:
        should_send_message = True
    
        
    # Send the message if needed
    if should_send_message and company_id:
        
        whatsapp_result = send_whatsapp_response(
            text=agent_message,
            company_id=company_id,
            wa_id=wa_id
        )
        
    elif should_send_message and not company_id:
        pass

    if action == "ask":
        # Agent wants to ask user -> Stay on same agent, update memory
        if agent_message:
            memory = append_turn(
                memory,
                role="assistant",
                text=agent_message,
                agent=target_agent,
                domain=session.get("domain"),
                action=action,
            )
        memory = apply_memory_patch(memory, response.get("memory", {}))
        memory = update_global(
            memory,
            last_agent=target_agent,
            last_action=action,
            last_domain=session.get("domain"),
        )
        session_manager.update_agent_memory(wa_id, memory, safe_company_id)
        result = {
            "type": "text",
            "message": agent_message,
            "agent": target_agent
        }
        return result
        
    if action == "route":
        # Agent finished, route to next (next turn)
        new_target = response.get("next_agent")
        new_domain = response.get("domain")
        if new_domain is None:
            new_domain = session.get("domain")
        
        if not new_target:
            return {"error": "Route action missing next_agent"}
        allowed_next = _AGENT_ALLOWLIST.get(target_agent, [])
        if new_target not in allowed_next:
            return {
                "type": "text",
                "message": "No pude derivarte en este momento. ¿Podés intentar de nuevo?",
                "agent": target_agent
            }
        
        session_manager.set_target_agent(wa_id, new_target, new_domain, safe_company_id)
        if agent_message:
            memory = append_turn(
                memory,
                role="assistant",
                text=agent_message,
                agent=target_agent,
                domain=new_domain,
                action=action,
            )
        memory = apply_memory_patch(memory, response.get("memory", {}))
        memory = update_global(
            memory,
            last_agent=target_agent,
            last_action=action,
            last_domain=new_domain,
        )
        session_manager.update_agent_memory(wa_id, memory, safe_company_id) # Pass context forward
        
        result = {
            "type": "transition", 
            "message": agent_message,
            "next_agent": new_target
        }
        return result
            
    if action == "finish":
        # Flow complete - mark as resolved and prepare for cleanup
        session_manager.set_target_agent(wa_id, "receptionist_agent", None, safe_company_id) # Reset to receptionist
        
        if agent_message:
            memory = append_turn(
                memory,
                role="assistant",
                text=agent_message,
                agent=target_agent,
                domain=session.get("domain"),
                action=action,
            )
        
        # Mark that the last interaction was completed
        memory = update_global(
            memory,
            last_agent=target_agent,
            last_action=action,
            last_domain=session.get("domain"),
            consultation_completed=True,  # Flag to indicate completion
        )
        session_manager.update_agent_memory(wa_id, memory, safe_company_id)
        
        result = {
            "type": "text", 
            "message": agent_message, 
            "status": "completed"
        }
        return result

    return {"error": "Unknown action"}
