import json
from core.orchestrator import process_message
from core.db import SessionManager
from core.tracing import setup_tracing

setup_tracing()

def handle_whatsapp(request):
    """Handle incoming ZOA Buffer System messages."""
    
    data = request.get_json(silent=True) or {}
    mensaje = data.get("mensaje", "").strip()
    
    # Handle session reset with "BORRAR TODO"
    if mensaje == "BORRAR TODO":
        return handle_session_reset(data)
    
    response = process_message(data)

    return (
        json.dumps({"status": "ok", "response": response}, ensure_ascii=False),
        200,
        {"Content-Type": "application/json"},
    )

def handle_session_reset(data):
    """Reset user session in database."""
    wa_id = data.get("wa_id")
    company_id = data.get("phone_number_id") or "default"
    
    session_manager = SessionManager()
    deleted = session_manager.delete_session(wa_id, company_id)
    
    status = "deleted" if deleted else "not_found"
    
    return (
        json.dumps({"status": "ok", "action": "session_reset", "result": status}, ensure_ascii=False),
        200,
        {"Content-Type": "application/json"},
    )
