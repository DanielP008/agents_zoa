import json
import os
from typing import Dict, Any

from core.hooks import get_contracts_path
from agents.receptionist_agent import receptionist_agent
from agents.domains.siniestros.classifier_agent import classifier_siniestros_agent
from agents.domains.siniestros.apertura_siniestro_agent import apertura_siniestro_agent
from agents.domains.siniestros.consulta_estado_agent import consulta_estado_agent
from agents.domains.siniestros.telefonos_asistencia_agent import telefonos_asistencia_agent

# Load routes configuration
_ROUTES_PATH = get_contracts_path("routes.json")

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

    return {
        "action": "finish",
        "message": f"Error: Agent {target_agent} not found. Resetting."
    }
