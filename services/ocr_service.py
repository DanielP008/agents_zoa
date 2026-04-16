"""OCR service for document processing - uses google-genai SDK directly."""

import os
import json
import base64
import logging
from typing import Dict, Any, Optional

from google import genai
from google.genai.types import Part

logger = logging.getLogger(__name__)


def _get_client() -> genai.Client:
    """Return a configured google-genai client."""
    api_key = os.environ.get("GEMINI_API_KEY", "")
    if not api_key:
        raise ValueError("GEMINI_API_KEY environment variable not set")
    return genai.Client(api_key=api_key)


def _get_model_name() -> str:
    return os.environ.get("GEMINI_OCR_MODEL", "gemini-2.0-flash")


def extract_document_data(
    mime_type: str, 
    b64_data: str, 
    prompt_override: Optional[str] = None
) -> Dict[str, Any]:
    """
    Extract structured data from a document using OCR.
    
    Supports images (jpeg, png) and PDFs via google-genai SDK.
    
    Args:
        mime_type: MIME type of the document (e.g., 'application/pdf', 'image/jpeg')
        b64_data: Base64 encoded document data
        prompt_override: Optional custom prompt for extraction
    
    Returns:
        dict with 'data' (extracted JSON) and 'status', or 'error' on failure
    """
    if not b64_data:
        return {"error": "No document data provided", "status": "failed"}

    default_prompt = (
        "Analiza este archivo adjunto. Puede ser un documento (póliza, DNI, factura, recibo) o una fotografía.\n\n"
        "- Si es un DOCUMENTO con texto: extrae TODA la información relevante en un JSON estructurado con claves en español "
        "(ej: 'numero_poliza', 'titular', 'nif', 'coberturas', 'fecha_vencimiento'). Devuelve SOLO el JSON.\n"
        "- Si es una FOTOGRAFÍA (daño en vehículo, hogar, accidente, objeto, etc.): devuelve un JSON con la clave "
        "'descripcion_imagen' con una descripción detallada de lo que ves (2-4 frases), y 'tipo_contenido' indicando "
        "qué tipo de imagen es (ej: 'daño_vehiculo', 'daño_hogar', 'documento', 'foto_personal', 'otro').\n\n"
        "Devuelve SOLO el JSON, sin texto adicional."
    )
    
    prompt = prompt_override or default_prompt
    
    try:
        client = _get_client()
        model_name = _get_model_name()
        
        # Decode base64 to raw bytes
        raw_bytes = base64.b64decode(b64_data)
        
        # Build content with Part.from_bytes (works for images AND PDFs)
        file_part = Part.from_bytes(data=raw_bytes, mime_type=mime_type)
        
        logger.info(f"[OCR_SERVICE] Processing document with mime_type: {mime_type}, model: {model_name}")
        
        response = client.models.generate_content(
            model=model_name,
            contents=[prompt, file_part],
        )
        
        content = response.text.strip()
        
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
            "raw_output": content if 'content' in locals() else None,
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
