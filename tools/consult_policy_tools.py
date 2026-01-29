from langchain_core.tools import tool
from services.erp_client import get_client_policys, get_policy_document_from_erp
from tools.ocr_tools import document_to_json

def get_client_policys_tool_factory(company_id: str):
    @tool
    def get_client_policys_tool(nif: str, ramo: str) -> dict:
        """Devuelve las pólizas del cliente para un ramo."""
        return get_client_policys(nif, ramo, company_id=company_id)
    return get_client_policys_tool

def get_policy_document_tool_factory(company_id: str):
    @tool
    def get_policy_document_tool(nif: str, policy_id: str) -> dict:
        """Devuelve el PDF de póliza para un ID."""
        return get_policy_document_from_erp(nif, policy_id, company_id=company_id)
    return get_policy_document_tool

@tool
def ocr_policy_document_tool(mime_type: str, data: str) -> dict:
    """Convierte un PDF base64 en información estructurada JSON."""
    return document_to_json(mime_type, data)
