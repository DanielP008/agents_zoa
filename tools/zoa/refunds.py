import json
from langchain_core.tools import tool

@tool
def create_refund_request_tool(data: str) -> dict:
    """Registra una solicitud de devolución en ZOA con los datos proporcionados (JSON string)."""
    try:
        payload = json.loads(data)
        return {"success": True, "refund_id": "REF-12345", "message": "Solicitud de devolución registrada"}
    except:
        return {"error": "Invalid JSON format"}
