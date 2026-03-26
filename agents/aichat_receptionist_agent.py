import json
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
from infra.llm import get_llm
from core.memory import get_global_history
from infra.llm_utils import safe_structured_invoke
from core.schemas import ReceptionistDecision
from agents.aichat_receptionist_prompts import get_prompt

from infra.config import get_routes_path
from core.routing.allowlist import get_active_specialists

def aichat_receptionist_agent(payload: dict) -> dict:
    """Receptionist agent specialized for AiChat channel."""
    # Reload config to be dynamic
    routes_path = get_routes_path()
    with open(routes_path, "r") as f:
        routes_config = json.load(f)
    
    active_domains = [
        k for k, v in routes_config["domains"].items()
        if v.get("enabled", True) and v.get("classifier")
    ]
    active_specialists_by_domain = {
        domain: get_active_specialists(domain, routes_config)
        for domain in active_domains
    }

    session = payload.get("session", {})
    memory = session.get("agent_memory", {})
    user_text = payload.get("mensaje", "")
    
    history = get_global_history(memory)
    has_assistant_messages = any(role == "ai" for role, _ in history)
    
    system_prompt = get_prompt()
    
    messages = [SystemMessage(content=system_prompt)]
    for role, text in history:
        if role == "human":
            messages.append(HumanMessage(content=text))
        else:
            messages.append(AIMessage(content=text))
    messages.append(HumanMessage(content=f"Mensaje del cliente: {user_text}"))
    
    llm = get_llm()
    try:
        structured_llm = llm.with_structured_output(ReceptionistDecision, method="json_mode")
    except Exception:
        structured_llm = llm.with_structured_output(ReceptionistDecision)
    
    decision = safe_structured_invoke(
        structured_llm,
        messages,
        fallback_factory=lambda: ReceptionistDecision(
            domain=None,
            message="Disculpa, tuve un problema técnico. ¿Podrías repetir tu consulta?",
            confidence=0.0
        ),
        error_context="aichat_receptionist_decision"
    )
    
    domain = decision.domain
    message = decision.message
    
    if domain == "siniestros":
        return {
            "action": "route",
            "next_agent": "telefonos_asistencia_agent",
            "domain": "siniestros",
            "message": None
        }
    elif domain == "ventas":
        return {
            "action": "route",
            "next_agent": "renovacion_agent",
            "domain": "ventas",
            "message": None
        }
        
    # Default: ask for clarification
    if not message:
        message = "Hola, soy Sofía de ZOA Seguros. ¿Necesitas los teléfonos de asistencia o información sobre tu renovación?"
        
    return {"action": "ask", "message": message}
