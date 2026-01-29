import json
from langchain_core.tools import tool
from services.zoa_client import create_claim as zoa_create_claim

@tool
def create_claim_tool(data: str) -> dict:
    """Registra un siniestro en ZOA (JSON string)."""
    try:
        payload_data = json.loads(data)
        claim_result = zoa_create_claim(payload_data)
        return claim_result
    except Exception as e:
        return {"error": f"Invalid JSON format or processing error: {str(e)}"}
