import json
from core.orchestrator import process_message

def handle_whatsapp(request):
    """
    Handler dedicated to the ZOA Buffer System (Source of Truth).
    Receives 'mensaje', 'wa_id', 'phone_number_id'.
    """
    data = request.get_json(silent=True) or {}
    response = process_message(data)
    return (
        json.dumps({"status": "ok", "response": response}, ensure_ascii=False),
        200,
        {"Content-Type": "application/json"},
    )
