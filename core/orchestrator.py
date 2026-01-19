import json
from core.db import SessionManager
from routers.main_router import route_request

# Managers
session_manager = SessionManager()

def process_message(payload: dict) -> dict:
    user_id = payload.get("from")
    text = payload.get("text")
    
    # 1. Load Session
    session = session_manager.get_session(user_id)
    target_agent = session.get("target_agent", "receptionist_agent")
    
    # 2. Inject context into payload
    payload["session"] = session
    
    # 3. Route to the target agent (State Machine)
    # El router decide a quién llamar basandose en 'target_agent'
    response = route_request(target_agent, payload)
    
    # 4. Handle Agent Response
    action = response.get("action")
    
    if action == "ask":
        # Agent wants to ask user -> Stay on same agent, update memory
        session_manager.update_agent_memory(user_id, response.get("memory", {}))
        return {
            "type": "text",
            "message": response.get("message"),
            "agent": target_agent
        }
        
    if action == "route":
        # Agent finished, route to next -> Update target, clear memory?
        new_target = response.get("next_agent")
        new_domain = response.get("domain")
        
        session_manager.set_target_agent(user_id, new_target, new_domain)
        session_manager.update_agent_memory(user_id, response.get("memory", {})) # Pass context forward?
        
        # Opcional: Ejecutar inmediatamente el nuevo agente con el mismo input?
        # Por simplicidad, devolvemos un mensaje de transición o nada.
        # En este caso, asumimos que el nuevo agente iniciará la charla o esperamos nuevo input.
        # Si queremos chain-of-thought, llamariamos recursivamente a process_message.
        
        return {
            "type": "transition", 
            "message": response.get("message", "Derivando..."),
            "next_agent": new_target
        }
        
    if action == "finish":
         # Flow complete
         session_manager.set_target_agent(user_id, "receptionist_agent", None) # Reset
         return {
             "type": "text", 
             "message": response.get("message"), 
             "status": "completed"
         }

    return {"error": "Unknown action"}
