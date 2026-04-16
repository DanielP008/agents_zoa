"""OCR tools for user-uploaded documents - thin wrappers around OCR service."""

import json
from langchain.tools import tool
from services.ocr_service import extract_document_data

@tool
def process_document(data: str) -> dict:
    """
    Procesa un documento enviado por el usuario (foto, PDF) y extrae su información.
    
    Args:
        data: JSON string con 'mime_type' y 'b64_data'
              Ejemplo: {"mime_type": "image/jpeg", "b64_data": "...base64..."}
    
    Returns:
        dict con la información extraída del documento o error
    """
    try:
        payload = json.loads(data)
        mime_type = payload.get("mime_type", "application/octet-stream")
        b64_data = payload.get("b64_data")
        
        if not b64_data:
            return {"error": "b64_data es requerido", "status": "failed"}
        
        return extract_document_data(mime_type, b64_data)
    except json.JSONDecodeError:
        return {"error": "Formato JSON inválido", "status": "failed"}
    except Exception as e:
        return {"error": str(e), "status": "failed"}
