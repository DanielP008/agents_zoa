import json
import os
from pathlib import Path
from typing import Dict, Any

from agents.receptionist_agent import receptionist_agent

# Siniestros Domain
from agents.domains.siniestros.classifier_agent import classifier_siniestros_agent
from agents.domains.siniestros.apertura_siniestro_agent import apertura_siniestro_agent
from agents.domains.siniestros.consulta_estado_agent import consulta_estado_agent
from agents.domains.siniestros.telefonos_asistencia_agent import telefonos_asistencia_agent

# Gestion Domain
from agents.domains.gestion.classifier_agent import classifier_gestion_agent
from agents.domains.gestion.devolucion_agent import devolucion_agent
from agents.domains.gestion.consultar_poliza_agent import consultar_poliza_agent
from agents.domains.gestion.modificar_poliza_agent import modificar_poliza_agent

# Ventas Domain
from agents.domains.ventas.classifier_agent import classifier_ventas_agent
from agents.domains.ventas.nueva_poliza_agent import nueva_poliza_agent
from agents.domains.ventas.venta_cruzada_agent import venta_cruzada_agent

# Load routes configuration from the same directory
_ROUTES_PATH = Path(__file__).parent / "routes.json"

# Ensure the file exists before reading
if os.path.exists(_ROUTES_PATH):
    with open(_ROUTES_PATH, "r") as f:
        ROUTES_CONFIG = json.load(f)
else:
    ROUTES_CONFIG = {}

def get_accessible_agents() -> Dict[str, Any]:
    """Returns the tree/list of accessible agents."""
    return ROUTES_CONFIG

def route_request(target_agent: str, payload: dict) -> dict:
    """
    Central dispatcher.
    Calls the specific python function based on agent name.
    """

    if target_agent == "receptionist_agent":
        result = receptionist_agent(payload)
        return result
    
    # Siniestros Domain
    if target_agent == "classifier_siniestros_agent":
        result = classifier_siniestros_agent(payload)
        return result
    if target_agent == "apertura_siniestro_agent":
        result = apertura_siniestro_agent(payload)
        return result
    if target_agent == "consulta_estado_agent":
        result = consulta_estado_agent(payload)
        return result
    if target_agent == "telefonos_asistencia_agent":
        result = telefonos_asistencia_agent(payload)
        return result
    
    # Gestion Domain
    if target_agent == "classifier_gestion_agent":
        result = classifier_gestion_agent(payload)
        return result
    if target_agent == "devolucion_agent":
        result = devolucion_agent(payload)
        return result
    if target_agent == "consultar_poliza_agent":
        result = consultar_poliza_agent(payload)
        return result
    if target_agent == "modificar_poliza_agent":
        result = modificar_poliza_agent(payload)
        return result
    
    # Ventas Domain
    if target_agent == "classifier_ventas_agent":
        result = classifier_ventas_agent(payload)
        return result
    if target_agent == "nueva_poliza_agent":
        result = nueva_poliza_agent(payload)
        return result
    if target_agent == "venta_cruzada_agent":
        result = venta_cruzada_agent(payload)
        return result

    return {
        "action": "finish",
        "message": f"Error: Agent {target_agent} not found. Resetting."
    }
