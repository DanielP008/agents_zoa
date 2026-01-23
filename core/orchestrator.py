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
        print(f"[ORCHESTRATOR] 🤖 Routing to agent: {target_agent} (chain depth: {chain_depth})")
        response = route_request(target_agent, payload)
        
        # 3. Handle Agent Response
        action = response.get("action")
        agent_message = response.get("message")
        
        print(f"[ORCHESTRATOR] ← Agent response received")
        print(f"[ORCHESTRATOR]   Action: {action}")
        print(f"[ORCHESTRATOR]   Message: {agent_message[:100] if agent_message else 'None'}...")
        
        # Check for passthrough route (route without message)
        if action == "route" and not agent_message:
            new_target = response.get("next_agent")
            new_domain = response.get("domain")
            if new_domain is None:
                new_domain = session.get("domain")
            
            if not new_target:
                print("[ORCHESTRATOR] ❌ Passthrough route missing next_agent")
                return {"error": "Route action missing next_agent"}
            
            allowed_next = _AGENT_ALLOWLIST.get(target_agent, [])
            if new_target not in allowed_next:
                print(f"[ORCHESTRATOR] ❌ Invalid passthrough route: {target_agent} -> {new_target}")
                return {
                    "type": "text",
                    "message": "No pude derivarte en este momento. ¿Podés intentar de nuevo?",
                    "agent": target_agent
                }
            
            print(f"[ORCHESTRATOR] ⏩ Passthrough to: {new_target} (domain: {new_domain})")
            
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
        print(f"[ORCHESTRATOR] ❌ Max chain depth reached ({MAX_CHAIN_DEPTH})")
        return {"error": "Max routing chain depth exceeded"}
    
    # Decide if we need to send a message back to WhatsApp
    should_send_message = False
    if action in ["ask", "finish", "route"] and agent_message:
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
        print("[ORCHESTRATOR] ✓ Memory updated")
        result = {
            "type": "text",
            "message": agent_message,
            "agent": target_agent
        }
        print(f"[ORCHESTRATOR] ✅ Returning ASK response")
        return result
        
    if action == "route":
        # Agent finished, route to next (next turn)
        new_target = response.get("next_agent")
        new_domain = response.get("domain")
        if new_domain is None:
            new_domain = session.get("domain")
        
        if not new_target:
            print("[ORCHESTRATOR] ❌ Route action missing next_agent")
            return {"error": "Route action missing next_agent"}
        allowed_next = _AGENT_ALLOWLIST.get(target_agent, [])
        if new_target not in allowed_next:
            print(f"[ORCHESTRATOR] ❌ Invalid route: {target_agent} -> {new_target}")
            return {
                "type": "text",
                "message": "No pude derivarte en este momento. ¿Podés intentar de nuevo?",
                "agent": target_agent
            }
        
        print(f"[ORCHESTRATOR] 🔀 Routing to new agent: {new_target} (domain: {new_domain})")
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
        if agent_message:
            memory = append_turn(
                memory,
                role="assistant",
                text=agent_message,
                agent=target_agent,
                domain=session.get("domain"),
                action=action,
            )
        memory = update_global(
            memory,
            last_agent=target_agent,
            last_action=action,
            last_domain=session.get("domain"),
        )
        session_manager.update_agent_memory(wa_id, memory, safe_company_id)
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
