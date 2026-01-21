import json

from core.orchestrator import process_message


def handle_whatsapp(request):
    payload = request.get_json(silent=True) or {}
    
    # Adapter for Buffer Script
    if "mensaje" in payload and "text" not in payload:
        payload["text"] = payload["mensaje"]
    if "wa_id" in payload and "from" not in payload:
        payload["from"] = payload["wa_id"]
    
    # New Orchestrator Flow
    response = process_message(payload)
    
    return (
        json.dumps({"status": "ok", "response": response}, ensure_ascii=False),
        200,
        {"Content-Type": "application/json"},
    )