import json
from langchain_core.prompts import ChatPromptTemplate
from infra.llm import get_llm
from core.memory import get_global_history
from infra.llm_utils import safe_structured_invoke
from infra.decision_schemas import ReceptionistDecision
from agents.aichat_receptionist_prompts import get_prompt

def aichat_receptionist_agent(payload: dict) -> dict:
    """Receptionist agent specialized for AiChat channel."""
    session = payload.get("session", {})
    memory = session.get("agent_memory", {})
    user_text = payload.get("mensaje", "")
    
    history = get_global_history(memory)
    has_assistant_messages = any(role == "ai" for role, _ in history)
    
    system_prompt = get_prompt()
    
    prompt = ChatPromptTemplate.from_messages([
        ("system", system_prompt),
        *history,
        ("human", "Mensaje del cliente: {user_text}"),
    ])
    
    llm = get_llm()
    try:
        structured_llm = llm.with_structured_output(ReceptionistDecision, method="json_mode")
    except Exception:
        structured_llm = llm.with_structured_output(ReceptionistDecision)
        
    chain = prompt | structured_llm
    
    decision = safe_structured_invoke(
        chain,
        {"user_text": user_text},
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
