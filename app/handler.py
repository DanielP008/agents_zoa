import json
from core.orchestrator import process_message

def handle_whatsapp(request):
    """
    Handler dedicated to the ZOA Buffer System (Source of Truth).
    Receives 'mensaje', 'wa_id', 'phone_number_id'.
    """
    print("=" * 70)
    print("[HANDLER] 📥 Message received from Buffer System")
    print("=" * 70)
    
    data = request.get_json(silent=True) or {}
    print(f"[HANDLER] Raw payload keys: {list(data.keys())}")
    print(f"[HANDLER] wa_id: {data.get('wa_id')}")
    print(f"[HANDLER] mensaje: {data.get('mensaje', '')[:100]}...")
    print(f"[HANDLER] phone_number_id: {data.get('phone_number_id')}")
    
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
