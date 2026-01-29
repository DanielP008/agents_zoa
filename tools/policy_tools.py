import json
from langchain_core.tools import tool
from services.zoa_client import fetch_policy
from services.ocr_client import extract_text

@tool
def lookup_policy(policy_number: str) -> dict:
    """Busca informacion de una poliza por su numero."""
    return fetch_policy(policy_number)

@tool
def process_document(doc_type: str) -> dict:
    """Procesa un documento (OCR) para extraer texto. Simulado."""
    return extract_text({"type": doc_type})
