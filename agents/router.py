from agents.receptionist_agent import classify_domain
from agents.domains.siniestros.classifier_agent import classify_message as classify_siniestros
from agents.domains.siniestros.apertura_siniestro_agent import handle as call_apertura_siniestro
from agents.domains.siniestros.consulta_estado_agent import handle as call_consulta_estado
from agents.domains.siniestros.telefonos_asistencia_agent import handle as call_telefonos_asistencia


def _route_siniestros(payload: dict) -> dict:
    decision = classify_siniestros(payload)
    if decision.get("needs_more_info"):
        return {
            "type": "question",
            "route": decision.get("route"),
            "message": decision.get("question"),
        }

    route = decision.get("route")
    if route == "apertura_siniestro_agent":
        return call_apertura_siniestro(payload)
    if route == "consulta_estado_agent":
        return call_consulta_estado(payload)
    if route == "telefonos_asistencia_agent":
        return call_telefonos_asistencia(payload)
        
    return {
        "type": "fallback",
        "message": "No entendi tu solicitud de siniestros."
    }


def route_message(payload: dict) -> dict:
    # Level 1: Receptionist
    domain_decision = classify_domain(payload)
    domain = domain_decision.get("domain")

    if domain == "siniestros":
        return _route_siniestros(payload)
    
    if domain in ["gestion", "ventas"]:
        return {
            "type": "fallback", 
            "message": f"El area de {domain} aun no esta disponible."
        }

    return {
        "type": "fallback",
        "message": (
            "Hola, soy ZOA. Puedo ayudarte con Siniestros, Gestion o Ventas. "
            "Que necesitas?"
        ),
    }
