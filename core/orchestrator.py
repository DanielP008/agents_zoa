import json
import os
from core.db import SessionManager
from routers.main_router import route_request
from tools.zoa_client import send_whatsapp_response

# Managers
session_manager = SessionManager()

def process_message(payload: dict) -> dict:
    print("\n[ORCHESTRATOR] 🎯 Starting message processing")
    
    # Use Buffer System names (Source of Truth)
    wa_id = payload.get("wa_id")
    mensaje = payload.get("mensaje")
    company_id = payload.get("phone_number_id")
    
    print(f"[ORCHESTRATOR] User: {wa_id} | Company: {company_id}")
    print(f"[ORCHESTRATOR] Message: {mensaje[:100]}...")
    
    # 1. Load Session
    print("[ORCHESTRATOR] 📂 Loading session from database...")
    safe_company_id = company_id or "default"
    session = session_manager.get_session(wa_id, safe_company_id)
    target_agent = session.get("target_agent", "receptionist_agent")
    print(f"[ORCHESTRATOR] ✓ Session loaded | Current agent: {target_agent}")
    print(f"[ORCHESTRATOR]   Domain: {session.get('domain')} | Memory keys: {list(session.get('agent_memory', {}).keys())}")
    
    payload["session"] = session
    
    # 2. Route to the target agent (State Machine)
    print(f"[ORCHESTRATOR] 🤖 Routing to agent: {target_agent}")
    response = route_request(target_agent, payload)
    
    # 3. Handle Agent Response
    action = response.get("action")
    agent_message = response.get("message")
    
    print(f"[ORCHESTRATOR] ← Agent response received")
    print(f"[ORCHESTRATOR]   Action: {action}")
    print(f"[ORCHESTRATOR]   Message: {agent_message[:100] if agent_message else 'None'}...")
    
    # Decide if we need to send a message back to WhatsApp
    should_send_message = False
    if action in ["ask", "finish"] and agent_message:
        should_send_message = True
    elif action == "route" and agent_message:
        # Transition messages ("Te paso con...")
        should_send_message = True
    
    print(f"[ORCHESTRATOR] 📤 Should send WhatsApp message: {should_send_message}")
        
    # Send the message if needed
    if should_send_message and company_id:
        print("[ORCHESTRATOR] 📱 SENDING MESSAGE TO WHATSAPP...")
        print(f"[ORCHESTRATOR]   To: {wa_id}")
        print(f"[ORCHESTRATOR]   Company: {company_id}")
        print(f"[ORCHESTRATOR]   Text: {agent_message[:100]}...")
        
        whatsapp_result = send_whatsapp_response(
            text=agent_message,
            company_id=company_id,
            wa_id=wa_id
        )
        
        print(f"[ORCHESTRATOR] ✓ WhatsApp message sent | Result: {whatsapp_result}")
    elif should_send_message and not company_id:
        print("[ORCHESTRATOR] ⚠️  Skipping WhatsApp send: company_id missing")

    if action == "ask":
        # Agent wants to ask user -> Stay on same agent, update memory
        print(f"[ORCHESTRATOR] 💾 Updating agent memory (staying on {target_agent})")
        session_manager.update_agent_memory(wa_id, response.get("memory", {}), safe_company_id)
        print("[ORCHESTRATOR] ✓ Memory updated")
        result = {
            "type": "text",
            "message": agent_message,
            "agent": target_agent
        }
        print(f"[ORCHESTRATOR] ✅ Returning ASK response")
        return result
        
    if action == "route":
        # Agent finished, route to next -> Update target, clear memory?
        new_target = response.get("next_agent")
        new_domain = response.get("domain")
        
        print(f"[ORCHESTRATOR] 🔀 Routing to new agent: {new_target} (domain: {new_domain})")
        session_manager.set_target_agent(wa_id, new_target, new_domain, safe_company_id)
        session_manager.update_agent_memory(wa_id, response.get("memory", {}), safe_company_id) # Pass context forward
        print("[ORCHESTRATOR] ✓ Agent changed and memory updated")
        
        result = {
            "type": "transition", 
            "message": agent_message,
            "next_agent": new_target
        }
        print(f"[ORCHESTRATOR] ✅ Returning ROUTE response")
        return result
        
    if action == "finish":
        # Flow complete
        print("[ORCHESTRATOR] 🏁 Flow completed, resetting to receptionist")
        session_manager.set_target_agent(wa_id, "receptionist_agent", None, safe_company_id) # Reset
        print("[ORCHESTRATOR] ✓ Session reset")
        result = {
            "type": "text", 
            "message": agent_message, 
            "status": "completed"
        }
        print(f"[ORCHESTRATOR] ✅ Returning FINISH response")
        return result

    print(f"[ORCHESTRATOR] ❌ Unknown action: {action}")
    return {"error": "Unknown action"}
