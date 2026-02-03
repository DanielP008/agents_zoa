"""OCR service for document processing - internal use only, not an agent tool."""

import os
import json
import logging
from typing import Dict, Any, Optional

from langchain_core.messages import HumanMessage
from langchain_google_genai import ChatGoogleGenerativeAI

logger = logging.getLogger(__name__)


def _get_ocr_model() -> ChatGoogleGenerativeAI:
    """Return the configured Gemini model instance for OCR."""
    api_key = os.environ.get("GEMINI_API_KEY", "")
    if not api_key:
        raise ValueError("GEMINI_API_KEY environment variable not set")
    
    model_name = os.environ.get("GEMINI_OCR_MODEL", "gemini-1.5-flash")
    
    return ChatGoogleGenerativeAI(
        model=model_name,
        google_api_key=api_key,
        temperature=0.0
    )


def extract_document_data(
    mime_type: str, 
    b64_data: str, 
    prompt_override: Optional[str] = None
) -> Dict[str, Any]:
    """
    Extract structured data from a document using OCR.
    
    This is the core OCR service function - called internally by tools,
    NOT exposed as an agent tool.
    
    Args:
        mime_type: MIME type of the document (e.g., 'application/pdf', 'image/jpeg')
        b64_data: Base64 encoded document data
        prompt_override: Optional custom prompt for extraction
    
    Returns:
        dict with 'data' (extracted JSON) and 'status', or 'error' on failure
    """
    if not b64_data:
        return {"error": "No document data provided", "status": "failed"}

    llm = _get_ocr_model()
    
    default_prompt = (
        "Analyze this document and extract ALL relevant information into a well-structured JSON object. "
        "Include names, dates, numbers, addresses, policy details, coverage information, and any other specific data points found. "
        "Use descriptive keys in Spanish (e.g., 'numero_poliza', 'titular', 'coberturas'). "
        "If the document has multiple sections, reflect that in the JSON structure. "
        "Return ONLY the JSON object, no other text."
    )
    
    prompt = prompt_override or default_prompt
    
    message = HumanMessage(
        content=[
            {"type": "text", "text": prompt},
            {
                "type": "image_url",
                "image_url": f"data:{mime_type};base64,{b64_data}"
            }
        ]
    )

    try:
        logger.info(f"[OCR_SERVICE] Processing document with mime_type: {mime_type}")
        response = llm.invoke([message])
        content = response.content.strip()
        
        # Clean up markdown code blocks if present
        if content.startswith("```json"):
            content = content[7:-3].strip()
        elif content.startswith("```"):
            content = content[3:-3].strip()
        
        parsed_data = json.loads(content)
        logger.info(f"[OCR_SERVICE] Successfully extracted document data")
        
        return {
            "data": parsed_data,
            "status": "success"
        }
    except json.JSONDecodeError as e:
        logger.error(f"[OCR_SERVICE] Failed to parse OCR output as JSON: {e}")
        return {
            "error": f"Failed to parse OCR output as JSON: {str(e)}",
            "raw_output": response.content if 'response' in locals() else None,
            "status": "failed"
        }
    except Exception as e:
        logger.error(f"[OCR_SERVICE] OCR processing failed: {e}")
        return {
            "error": str(e),
            "status": "failed"
        }


def extract_policy_data(mime_type: str, b64_data: str) -> Dict[str, Any]:
    """
    Extract policy-specific data from a document.
    
    Specialized prompt for insurance policy documents.
    """
    policy_prompt = (
        "Analiza este documento de póliza de seguro y extrae TODA la información relevante en un JSON estructurado. "
        "Incluye obligatoriamente si están presentes: "
        "- numero_poliza: Número de la póliza "
        "- titular: Nombre del asegurado/titular "
        "- nif_titular: NIF/DNI del titular "
        "- tipo_seguro: Tipo de seguro (auto, hogar, vida, etc.) "
        "- compania: Compañía aseguradora "
        "- fecha_efecto: Fecha de inicio de vigencia "
        "- fecha_vencimiento: Fecha de vencimiento "
        "- prima_total: Prima total anual "
        "- forma_pago: Forma de pago "
        "- coberturas: Lista de coberturas con sus límites "
        "- franquicias: Franquicias aplicables "
        "- datos_riesgo: Datos del bien asegurado (vehículo, vivienda, etc.) "
        "- mediador: Datos del mediador/corredor "
        "Devuelve SOLO el JSON, sin texto adicional."
    )
    
    return extract_document_data(mime_type, b64_data, prompt_override=policy_prompt)
