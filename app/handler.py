import json

from core.orchestrator import process_message


def handle_whatsapp(request):
    payload = request.get_json(silent=True) or {}
    
    # New Orchestrator Flow
    response = process_message(payload)
    
    return (
        json.dumps({"status": "ok", "response": response}, ensure_ascii=False),
        200,
        {"Content-Type": "application/json"},
    )