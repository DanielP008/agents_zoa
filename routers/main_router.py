from agents.receptionist_agent import handle as receptionist_handle
from agents.domains.siniestros.classifier_agent import handle as siniestros_classifier_handle
from agents.domains.siniestros.apertura_siniestro_agent import handle as apertura_handle
from agents.domains.siniestros.consulta_estado_agent import handle as consulta_handle
from agents.domains.siniestros.telefonos_asistencia_agent import handle as asistencia_handle

def route_request(target_agent: str, payload: dict) -> dict:
    """
    Central dispatcher.
    Calls the specific python function based on agent name.
    """
    if target_agent == "receptionist_agent":
        return receptionist_handle(payload)
    
    # Siniestros Domain
    if target_agent == "classifier_siniestros_agent":
        return siniestros_classifier_handle(payload)
    if target_agent == "apertura_siniestro_agent":
        return apertura_handle(payload)
    if target_agent == "consulta_estado_agent":
        return consulta_handle(payload)
    if target_agent == "telefonos_asistencia_agent":
        return asistencia_handle(payload)

    return {
        "action": "finish",
        "message": f"Error: Agent {target_agent} not found. Resetting."
    }
