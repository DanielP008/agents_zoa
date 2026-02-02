from langchain_core.tools import tool
from services.erp_client import get_client_policys, get_policy_document_from_erp
from tools.document_ai.ocr_tools import document_to_json

@tool
def get_client_policys_tool(nif: str, ramo: str, company_id: str) -> dict:
    """
    Devuelve las pólizas del cliente para un ramo específico.
    
    Args:
        nif: NIF/DNI del cliente
        ramo: Tipo de seguro (AUTO, HOGAR, etc.)
        company_id: ID de la compañía para el ERP
    
    Returns:
        dict con las pólizas del cliente
    """
    return get_client_policys(nif, ramo, company_id=company_id)

@tool
def get_policy_document_tool(nif: str, policy_id: str, company_id: str) -> dict:
    """
    Devuelve el documento PDF de una póliza específica.
    
    Args:
        nif: NIF/DNI del cliente
        policy_id: ID de la póliza
        company_id: ID de la compañía para el ERP
    
    Returns:
        dict con el PDF de la póliza en base64
    """
    return get_policy_document_from_erp(nif, policy_id, company_id=company_id)

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
