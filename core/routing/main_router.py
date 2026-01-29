import json
import os
from pathlib import Path
from typing import Dict, Any

from agents.receptionist_agent import receptionist_agent

from agents.domains.siniestros.classifier_agent import classifier_siniestros_agent
from agents.domains.siniestros.apertura_siniestro_agent import apertura_siniestro_agent
from agents.domains.siniestros.consulta_estado_agent import consulta_estado_agent
from agents.domains.siniestros.telefonos_asistencia_agent import telefonos_asistencia_agent

from agents.domains.gestion.classifier_agent import classifier_gestion_agent
from agents.domains.gestion.devolucion_agent import devolucion_agent
from agents.domains.gestion.consultar_poliza_agent import consultar_poliza_agent
from agents.domains.gestion.modificar_poliza_agent import modificar_poliza_agent

# Ventas deshabilitado (enabled: false en routes.json). Descomentar para reactivar:
# from agents.domains.ventas.classifier_agent import classifier_ventas_agent
# from agents.domains.ventas.nueva_poliza_agent import nueva_poliza_agent
# from agents.domains.ventas.venta_cruzada_agent import venta_cruzada_agent

_ROUTES_PATH = Path(__file__).parent / "routes.json"

if os.path.exists(_ROUTES_PATH):
    with open(_ROUTES_PATH, "r") as f:
        ROUTES_CONFIG = json.load(f)
else:
    ROUTES_CONFIG = {}

def get_accessible_agents() -> Dict[str, Any]:
    """Return the accessible agents tree."""
    return ROUTES_CONFIG

def route_request(target_agent: str, payload: dict) -> dict:
    """Dispatch a request to the target agent."""

    if target_agent == "receptionist_agent":
        return receptionist_agent(payload)
    if target_agent == "classifier_siniestros_agent":
        return classifier_siniestros_agent(payload)
    if target_agent == "apertura_siniestro_agent":
        return apertura_siniestro_agent(payload)
    if target_agent == "consulta_estado_agent":
        return consulta_estado_agent(payload)
    if target_agent == "telefonos_asistencia_agent":
        return telefonos_asistencia_agent(payload)
    if target_agent == "classifier_gestion_agent":
        return classifier_gestion_agent(payload)
    if target_agent == "devolucion_agent":
        return devolucion_agent(payload)
    if target_agent == "consultar_poliza_agent":
        return consultar_poliza_agent(payload)
    if target_agent == "modificar_poliza_agent":
        return modificar_poliza_agent(payload)

    # Ventas deshabilitado. Descomentar imports arriba y este bloque para reactivar:
    # if target_agent == "classifier_ventas_agent":
    #     return classifier_ventas_agent(payload)
    # if target_agent == "nueva_poliza_agent":
    #     return nueva_poliza_agent(payload)
    # if target_agent == "venta_cruzada_agent":
    #     return venta_cruzada_agent(payload)

    return {
        "action": "finish",
        "message": f"Error: Agent {target_agent} not found. Resetting."
    }
