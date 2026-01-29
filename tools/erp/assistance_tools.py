from langchain_core.tools import tool
from services.erp_client import get_assistance_phones_from_erp

def get_assistance_phones_tool_factory(nif_value: str, company_id: str):
    @tool
    def get_assistance_phones(nif: str, ramo: str) -> dict:
        """Obtiene las pólizas activas del cliente para un ramo específico (AUTO, HOGAR, etc.) con sus teléfonos de asistencia."""
        final_nif = nif_value or "00000000T"
        # Mapeamos 'ramo' si es necesario o lo pasamos directo. Asumimos que el agente extrae uno de los valores válidos.
        return get_assistance_phones_from_erp(nif=final_nif, ramo=ramo, company_id=company_id)
    return get_assistance_phones
