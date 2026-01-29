import json
from langchain_core.tools import tool

@tool
def update_policy_tool(data: str) -> dict:
    """Actualiza datos de una póliza en ZOA con los cambios proporcionados (JSON string)."""
    try:
        payload = json.loads(data)
        return {
            "success": True,
            "policy_number": payload.get("policy_number"),
            "updated_fields": list(payload.get("changes", {}).keys()),
            "message": "Póliza actualizada correctamente"
        }
    except:
        return {"error": "Invalid JSON format"}
