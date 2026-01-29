"""ERP tools for consulta estado (claims list and claim status)."""

from langchain_core.tools import tool
from services.erp_client import get_claims_from_erp, get_status_claim_from_erp


@tool
def get_claims_tool(company_id: str, nif: str, ramo: str, phone: str = "") -> dict:
    """Obtiene todos los siniestros de un cliente por NIF y ramo (línea).
    Ramo puede ser: Auto, Hogar, PYME/Comercio, Responsabilidad Civil, Comunidades vecinos, etc.
    Devuelve lista con id_claim, riesgo (matrícula/dirección/nombre) y fecha para identificar a cuál se refiere el cliente."""
    return get_claims_from_erp(nif=nif, line=ramo, company_id=company_id, phone=phone or None)


@tool
def get_status_claims_tool(company_id: str, id_claim: str) -> dict:
    """Obtiene el estado de un siniestro concreto por su id_claim.
    Usar después de get_claims_tool cuando ya sepas qué siniestro consulta el cliente."""
    return get_status_claim_from_erp(id_claim=id_claim, company_id=company_id)
