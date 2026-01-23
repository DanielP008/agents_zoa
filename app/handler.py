import json
from core.orchestrator import process_message
from core.db import SessionManager

def handle_whatsapp(request):
    """
    Handler dedicated to the ZOA Buffer System (Source of Truth).
    Receives 'mensaje', 'wa_id', 'phone_number_id'.
    """
    print("=" * 70)
    print("[HANDLER] 📥 Message received from Buffer System")
    print("=" * 70)
    
    data = request.get_json(silent=True) or {}
    print(f"[HANDLER] Data: {data}")
    
    if data.get("mensaje", "").strip() == "BORRAR_POSTGRESS_INFO":
        return handle_session_reset(data)
    
    print("[HANDLER] → Forwarding to orchestrator...")
    response = process_message(data)
    
    print("[HANDLER] ← Response received from orchestrator")
    print(f"[HANDLER] Response type: {response.get('type')}")
    print(f"[HANDLER] Response message: {response.get('message', '')[:100]}...")
    print("=" * 70)
    
    return (
        json.dumps({"status": "ok", "response": response}, ensure_ascii=False),
        200,
        {"Content-Type": "application/json"},
    )

def handle_session_reset(data):
    # Check for session reset command
    mensaje = data.get("mensaje", "").strip()
    if mensaje == "BORRAR_POSTGRESS_INFO":
        print("[HANDLER] 🗑️ Session reset command received")
        wa_id = data.get("wa_id")
        company_id = data.get("phone_number_id") or "default"
        
        session_manager = SessionManager()
        deleted = session_manager.delete_session(wa_id, company_id)
        
        status = "deleted" if deleted else "not_found"
        print(f"[HANDLER] ✓ Session reset complete: {status}")
        print("=" * 70)
        
        return (
            json.dumps({"status": "ok", "action": "session_reset", "result": status}, ensure_ascii=False),
            200,
            {"Content-Type": "application/json"},
        )