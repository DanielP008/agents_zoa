from langchain_core.tools import tool
from services.erp_client import get_assistance_phones_from_erp

@tool
def get_assistance_phones(nif: str, ramo: str, company_id: str) -> dict:
    """
    Obtiene las pólizas activas del cliente para un ramo específico (AUTO, HOGAR, etc.) con sus teléfonos de asistencia.
    
    Args:
        nif: NIF/DNI del cliente
        ramo: Tipo de seguro (AUTO, HOGAR, PYME, COMERCIOS, TRANSPORTES, COMUNIDADES, ACCIDENTES, RC)
        company_id: ID de la compañía para el ERP
    
    Returns:
        dict con las pólizas y teléfonos de asistencia del cliente
    """
    return get_assistance_phones_from_erp(nif=nif, ramo=ramo, company_id=company_id)
