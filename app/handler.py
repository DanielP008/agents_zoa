import json

from agents.router import route_message


def handle_whatsapp(request):
    payload = request.get_json(silent=True) or {}
    response = route_message(payload)
    return (
        json.dumps({"status": "ok", "response": response}, ensure_ascii=False),
        200,
        {"Content-Type": "application/json"},
    )
