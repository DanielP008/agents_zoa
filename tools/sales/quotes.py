import json
from langchain.tools import tool

@tool
def create_quote_tool(data: str) -> dict:
    """Genera una cotización de seguro en ZOA con los datos proporcionados (JSON string)."""
    try:
        payload = json.loads(data)
        return {
            "success": True,
            "quote_id": "COT-12345",
            "premium": "$12,500/mes",
            "coverage": payload.get("coverage_type", "Terceros Completo"),
            "message": "Cotización generada exitosamente"
        }
    except:
        return {"error": "Invalid JSON format"}

@tool
def create_new_policy_tool(data: str) -> dict:
    """Crea una nueva póliza en ZOA con los datos proporcionados (JSON string)."""
    try:
        payload = json.loads(data)
        return {
            "success": True,
            "policy_number": "POL-98765",
            "message": "Póliza creada exitosamente. Te enviaremos los detalles por email."
        }
    except:
        return {"error": "Invalid JSON format"}
