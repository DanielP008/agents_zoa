"""Agent dispatch: maps agent names to handler functions."""

import logging

from agents.receptionist_agent import receptionist_agent
from agents.aichat_receptionist_agent import aichat_receptionist_agent

from agents.domains.siniestros.classifier_agent import classifier_siniestros_agent
from agents.domains.siniestros.apertura_siniestro_agent import apertura_siniestro_agent
from agents.domains.siniestros.consulta_estado_agent import consulta_estado_agent
from agents.domains.siniestros.telefonos_asistencia_agent import telefonos_asistencia_agent

from agents.domains.gestion.classifier_agent import classifier_gestion_agent
from agents.domains.gestion.devolucion_agent import devolucion_agent
from agents.domains.gestion.consultar_poliza_agent import consultar_poliza_agent
from agents.domains.gestion.modificar_poliza_agent import modificar_poliza_agent

from agents.domains.ventas.classifier_agent import classifier_ventas_agent
from agents.domains.ventas.renovacion_agent import renovacion_agent
from agents.domains.ventas.nueva_poliza_agent import nueva_poliza_agent
from agents.domains.ventas.venta_cruzada_agent import venta_cruzada_agent

from agents.dial_agent import dial_agent

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Agent registry: name → handler callable
# ---------------------------------------------------------------------------
_AGENT_REGISTRY: dict[str, callable] = {
    "receptionist_agent": receptionist_agent,
    "aichat_receptionist_agent": aichat_receptionist_agent,
    # Claims
    "classifier_siniestros_agent": classifier_siniestros_agent,
    "apertura_siniestro_agent": apertura_siniestro_agent,
    "consulta_estado_agent": consulta_estado_agent,
    "telefonos_asistencia_agent": telefonos_asistencia_agent,
    # Management
    "classifier_gestion_agent": classifier_gestion_agent,
    "devolucion_agent": devolucion_agent,
    "consultar_poliza_agent": consultar_poliza_agent,
    "modificar_poliza_agent": modificar_poliza_agent,
    # Sales
    "classifier_ventas_agent": classifier_ventas_agent,
    "renovacion_agent": renovacion_agent,
    "nueva_poliza_agent": nueva_poliza_agent,
    "venta_cruzada_agent": venta_cruzada_agent,
    # Special
    "dial_agent": dial_agent,
}


def route_request(target_agent: str, payload: dict) -> dict:
    """Dispatch a request to the target agent."""
    handler = _AGENT_REGISTRY.get(target_agent)
    if handler is None:
        logger.error(f"[ROUTER] Agent not found: {target_agent}")
        return {
            "action": "finish",
            "message": f"Error: Agent {target_agent} not found. Resetting.",
        }
    return handler(payload)
