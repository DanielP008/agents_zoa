import json
from langchain_core.tools import tool
from services.zoa_client import fetch_policy
from tools.ocr_tools import document_to_json

@tool
def lookup_policy(policy_number: str) -> dict:
    """Busca informacion de una poliza por su numero."""
    return fetch_policy(policy_number)

@tool
def process_document(data: str) -> dict:
    """Procesa un documento (OCR) para extraer información en formato JSON.
    Input: JSON string con mime_type y b64_data."""
    try:
        payload = json.loads(data)
        return document_to_json(payload.get("mime_type"), payload.get("b64_data"))
    except:
        return {"error": "Invalid input format"}
