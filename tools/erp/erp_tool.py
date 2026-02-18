"""All ERP tools consolidated in one file."""
import logging
from langchain.tools import tool
from services.erp_client import (
    get_assistance_phones_from_erp,
    get_client_policys,
    get_policy_document_from_erp,
    get_claims_from_erp,
)
from services.ocr_service import extract_policy_data

logger = logging.getLogger(__name__)

# ============================================================================
# ASSISTANCE TOOLS
# ============================================================================

@tool
def get_assistance_phones(nif: str, ramo: str, company_id: str) -> dict:
    """
    Obtiene las pólizas activas del cliente para un ramo específico (AUTO, HOGAR, etc.) con sus teléfonos de asistencia.
    
    Args:
        nif: NIF/DNI del cliente
        ramo: Tipo de seguro (AUTO, HOGAR, PYME, COMERCIOS, TRANSPORTES, COMUNIDADES, ACCIDENTES, RC)
        company_id: ID de la compañía (se obtiene automáticamente del contexto)
    
    Returns:
        dict con las pólizas (number, company_name, risk, phones) del cliente.
        IMPORTANTE: Si la lista 'policies' está vacía, DEBES llamar a create_task_activity_tool.
    """
    return get_assistance_phones_from_erp(nif=nif, ramo=ramo, company_id=company_id)

# ============================================================================
# POLICY TOOLS
# ============================================================================

@tool
def get_client_policys_tool(nif: str, ramo: str, company_id: str) -> dict:
    """
    Devuelve las pólizas del cliente para un ramo específico.
    
    Args:
        nif: NIF/DNI del cliente
        ramo: Tipo de seguro (AUTO, HOGAR, etc.)
        company_id: ID de la compañía (se obtiene automáticamente del contexto)
    
    Returns:
        dict con las pólizas del cliente (number, company_name, risk, phones)
    """
    return get_client_policys(nif, ramo, company_id)

@tool
def get_policy_document_tool(policy_id: str, company_id: str) -> dict:
    """
    Obtiene el documento de una póliza y devuelve su información estructurada.
    
    Internamente: descarga el PDF del ERP y lo procesa con OCR para extraer
    todos los datos relevantes de la póliza.
    
    Args:
        policy_id: Número de la póliza
        company_id: ID de la compañía (se obtiene automáticamente del contexto)
    
    Returns:
        dict con la información extraída de la póliza (titular, coberturas, fechas, etc.)
        o error si no se pudo obtener/procesar el documento
    """
    # 1. Fetch document from ERP (only needs policy number)
    logger.info(f"[GET_POLICY_DOC] Fetching document for policy {policy_id}")
    doc_result = get_policy_document_from_erp(policy_id, company_id)
    
    if not doc_result.get("success"):
        logger.error(f"[GET_POLICY_DOC] Failed to fetch document: {doc_result.get('error')}")
        return {
            "success": False,
            "error": doc_result.get("error", "No se pudo obtener el documento de la póliza")
        }
    
    # 2. Extract document data (base64)
    documents = doc_result.get("documents", [])
    if not documents:
        return {
            "success": False,
            "error": "No se encontró documento para esta póliza"
        }
    
    # Get the first document (ERP returns: description, filename, data)
    doc = documents[0] if isinstance(documents, list) else documents
    b64_data = doc.get("data")
    mime_type = "application/pdf"  # ERP returns PDF documents
    
    if not b64_data:
        return {
            "success": False,
            "error": "El documento no contiene datos válidos"
        }
    
    # 3. Process with OCR service
    logger.info(f"[GET_POLICY_DOC] Processing document with OCR")
    ocr_result = extract_policy_data(mime_type, b64_data)
    
    if ocr_result.get("status") == "failed":
        logger.error(f"[GET_POLICY_DOC] OCR failed: {ocr_result.get('error')}")
        return {
            "success": False,
            "error": ocr_result.get("error", "No se pudo procesar el documento")
        }
    
    # 4. Return structured data
    logger.info(f"[GET_POLICY_DOC] Successfully extracted policy data")
    return {
        "success": True,
        "policy_id": policy_id,
        "filename": doc.get("filename"),
        "description": doc.get("description"),
        "data": ocr_result.get("data", {})
    }

# ============================================================================
# CLAIM TOOLS
# ============================================================================

@tool
def get_claims_tool(nif: str, company_id: str) -> dict:
    """
    Obtiene todos los siniestros de un cliente por NIF, incluyendo su estado.
    
    Args:
        nif: NIF/DNI del cliente
        company_id: ID de la compañía (se obtiene automáticamente del contexto)
    
    Returns:
        dict con lista de siniestros: id_claim, riesgo (risk), date (opening_date), status
    """
    return get_claims_from_erp(nif=nif, company_id=company_id)
