import json
import os
from typing import Optional, List

from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
from pydantic import BaseModel, Field

from infra.llm import get_llm_fast
from core.memory import get_agent_memory, get_global_history
from infra.llm_utils import safe_structured_invoke
from infra.decision_schemas import ClassificationDecision
from infra.config import get_routes_path
from core.routing.allowlist import get_active_specialists
from agents.domains.ventas.classifier_agent_prompts import get_prompt

_ROUTES_PATH = get_routes_path()

with open(_ROUTES_PATH, "r") as f:
    _ROUTES_CONFIG = json.load(f)

_ACTIVE_SPECIALISTS = get_active_specialists("ventas", _ROUTES_CONFIG)

# Fallback confirmation questions per route (never mention agents/transfers)
_CONFIRMATIONS = {
    "nueva_poliza_agent": "Para confirmar, quieres contratar una póliza nueva, ¿correcto?",
    "venta_cruzada_agent": "Para confirmar, te interesa mejorar o ampliar un seguro que ya tienes, ¿verdad?",
    "renovacion_agent": "Para confirmar, quieres que te busquemos las mejores opciones para renovar tu póliza, ¿verdad?",
}

def _sanitize_question(question: str | None) -> str | None:
    """Strip routing-related phrases from LLM-generated questions."""
    if not question:
        return None
    blocked = ["contacto", "especialista", "redirijo", "paso con", "transfiero", "derivar", "transferi"]
    if any(phrase in question.lower() for phrase in blocked):
        return None
    return question

def classifier_ventas_agent(payload: dict) -> dict:
    decision = classify_message(payload)
    
    if decision.action == "end_chat":
        return {
            "action": "end_chat",
            "message": decision.question or "¡Perfecto! Fue un placer ayudarte. Si necesitas algo más, aquí estaré. ¡Que tengas un excelente día! 😊"
        }

    # If the classifier needs more info, ask the user
    if decision.needs_more_info:
        clean_q = _sanitize_question(decision.question)
        if clean_q:
            return {
                "action": "ask",
                "message": clean_q,
                "memory": {
                    "agents": {
                        "classifier_ventas_agent": {
                            "last_route": decision.route,
                            "confidence": decision.confidence,
                        }
                    }
                } 
            }

    # Always confirm before routing — never silently passthrough.
    confirmation = _sanitize_question(decision.question) or _CONFIRMATIONS.get(
        decision.route, "Para confirmar, ¿es esto lo que necesitas?"
    )
    return {
        "action": "route",
        "next_agent": decision.route, 
        "domain": "ventas",
        "message": confirmation
    }

def classify_message(payload: dict) -> ClassificationDecision:
    user_text = payload.get("mensaje", "")
    user_id = payload.get("wa_id", "unknown")
    session = payload.get("session", {})
    
    memory = session.get("agent_memory", {})
    agent_mem = get_agent_memory(memory, "classifier_ventas_agent")
    last_route = agent_mem.get("last_route", "unknown")
    history = get_global_history(memory)
    
    # Get prompt based on channel, filtered to active specialists
    channel = payload.get("channel", "whatsapp")
    system_prompt = get_prompt(channel, _ACTIVE_SPECIALISTS)

    messages = [SystemMessage(content=system_prompt)]
    for role, text in history:
        if role == "human":
            messages.append(HumanMessage(content=text))
        else:
            messages.append(AIMessage(content=text))
    messages.append(HumanMessage(
        content=f"Contexto adicional: ultimo_route_provisional={last_route}\n\nMensaje del Usuario: {user_text}"
    ))

    llm = get_llm_fast()
    
    try:
        structured_llm = llm.with_structured_output(ClassificationDecision, method="json_mode")
    except:
        structured_llm = llm.with_structured_output(ClassificationDecision)

    result = safe_structured_invoke(
        structured_llm,
        messages,
        fallback_factory=lambda: ClassificationDecision(
            route="classifier_ventas_agent",
            confidence=0.0,
            needs_more_info=True,
            question="Disculpa, no entendí bien. ¿Buscas contratar una póliza nueva o mejorar un seguro que ya tienes?"
        ),
        error_context="classifier_ventas_decision"
    )
    
    return result
