import json
import os
from core.db import SessionManager
from routers.main_router import route_request
from tools.zoa_client import send_whatsapp_response

# Managers
session_manager = SessionManager()

def process_message(payload: dict) -> dict:
    # Use Buffer System names (Source of Truth)
    wa_id = payload.get("wa_id")
    mensaje = payload.get("mensaje")
    company_id = payload.get("phone_number_id")
    
    # 1. Load Session
    safe_company_id = company_id or "default"
    session = session_manager.get_session(wa_id, safe_company_id)
    target_agent = session.get("target_agent", "receptionist_agent")
    payload["session"] = session
    
    # 2. Route to the target agent (State Machine)
    response = route_request(target_agent, payload)
    
    # 3. Handle Agent Response
    action = response.get("action")
    agent_message = response.get("message")
    
    # Decide if we need to send a message back to WhatsApp
    should_send_message = False
    if action in ["ask", "finish"] and agent_message:
        should_send_message = True
    elif action == "route" and agent_message:
        # Transition messages ("Te paso con...")
        should_send_message = True
        
    # Send the message if needed
    if should_send_message and company_id:
        send_whatsapp_response(
            text=agent_message,
            company_id=company_id,
            wa_id=wa_id
        )

    if action == "ask":
        # Agent wants to ask user -> Stay on same agent, update memory
        session_manager.update_agent_memory(wa_id, response.get("memory", {}), safe_company_id)
        return {
            "type": "text",
            "message": agent_message,
            "agent": target_agent
        }
        
    if action == "route":
        # Agent finished, route to next -> Update target, clear memory?
        new_target = response.get("next_agent")
        new_domain = response.get("domain")
        
        session_manager.set_target_agent(wa_id, new_target, new_domain, safe_company_id)
        session_manager.update_agent_memory(wa_id, response.get("memory", {}), safe_company_id) # Pass context forward
        
        return {
            "type": "transition", 
            "message": agent_message,
            "next_agent": new_target
        }
        
    if action == "finish":
        # Flow complete
        session_manager.set_target_agent(wa_id, "receptionist_agent", None, safe_company_id) # Reset
        return {
            "type": "text", 
            "message": agent_message, 
            "status": "completed"
        }

    return {"error": "Unknown action"}
