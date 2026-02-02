"""All ERP tools consolidated in one file."""
from langchain.tools import tool
from services.erp_client import (
    get_assistance_phones_from_erp,
    get_client_policys,
    get_policy_document_from_erp,
    get_claims_from_erp,
)
from tools.document_ai.ocr_tools import document_to_json


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
        dict con las pólizas y teléfonos de asistencia del cliente
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
        dict con las pólizas del cliente
    """
    return get_client_policys(nif, ramo, company_id)


@tool
def get_policy_document_tool(nif: str, policy_id: str, company_id: str) -> dict:
    """
    Devuelve el documento PDF de una póliza específica.
    
    Args:
        nif: NIF/DNI del cliente
        policy_id: ID de la póliza
        company_id: ID de la compañía (se obtiene automáticamente del contexto)
    
    Returns:
        dict con el PDF de la póliza en base64
    """
    return get_policy_document_from_erp(nif, policy_id, company_id)


@tool
def ocr_policy_document_tool(mime_type: str, data: str) -> dict:
    """
    Convierte un documento PDF en base64 a información estructurada JSON usando OCR.
    
    Args:
        mime_type: Tipo MIME del documento (ej: 'application/pdf')
        data: Documento en base64
    
    Returns:
        dict con la información extraída del documento
    """
    return document_to_json(mime_type, data)


# ============================================================================
# CLAIM TOOLS
# ============================================================================

@tool
def get_claims_tool(nif: str, ramo: str, company_id: str, phone: str = "") -> dict:
    """
    Obtiene todos los siniestros de un cliente por NIF y ramo (línea), incluyendo su estado.
    
    Args:
        nif: NIF/DNI del cliente
        ramo: Tipo de seguro (Auto, Hogar, PYME/Comercio, RC, Comunidades, etc.)
        company_id: ID de la compañía (se obtiene automáticamente del contexto)
        phone: Teléfono del cliente (opcional)
    
    Returns:
        dict con lista de siniestros: id_claim, riesgo, fecha y status
    """
    return get_claims_from_erp(nif=nif, line=ramo, company_id=company_id, phone=phone or None)
