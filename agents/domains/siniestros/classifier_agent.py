import json
import os
from typing import Optional, List

from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel, Field

from core.llm import get_llm_fast
from core.memory_schema import get_agent_memory, get_global_history
from core.llm_utils import safe_structured_invoke
from core.decision_schemas import ClassificationDecision
from core.config import get_routes_path
from core.routing.allowlist import get_active_specialists
from agents.domains.siniestros.classifier_agent_prompts import get_prompt

_ROUTES_PATH = get_routes_path()

with open(_ROUTES_PATH, "r") as f:
    _ROUTES_CONFIG = json.load(f)

_ACTIVE_SPECIALISTS = get_active_specialists("siniestros", _ROUTES_CONFIG)

# Fallback confirmation questions per route (never mention agents/transfers)
_CONFIRMATIONS = {
    "telefonos_asistencia_agent": "Para confirmar, lo que necesitas son teléfonos de asistencia, ¿cierto?",
    "apertura_siniestro_agent": "Para confirmar, necesitas registrar un siniestro nuevo, ¿correcto?",
    "consulta_estado_agent": "Para confirmar, quieres saber el estado de un siniestro que ya tienes abierto, ¿verdad?",
}

def _sanitize_question(question: str | None) -> str | None:
    """Strip routing-related phrases from LLM-generated questions."""
    if not question:
        return None
    blocked = ["contacto", "especialista", "redirijo", "paso con", "transfiero", "derivar", "transferi"]
    if any(phrase in question.lower() for phrase in blocked):
        return None
    return question

def classifier_siniestros_agent(payload: dict) -> dict:
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
                        "classifier_siniestros_agent": {
                            "last_route": decision.route,
                            "confidence": decision.confidence,
                        }
                    }
                } 
            }

    # Always confirm before routing — never silently passthrough.
    # Use the LLM-generated question if clean, otherwise use fallback.
    confirmation = _sanitize_question(decision.question) or _CONFIRMATIONS.get(
        decision.route, "Para confirmar, ¿es esto lo que necesitas?"
    )
    return {
        "action": "route",
        "next_agent": decision.route, 
        "domain": "siniestros",
        "message": confirmation
    }

def classify_message(payload: dict) -> ClassificationDecision:
    user_text = payload.get("mensaje", "")
    user_id = payload.get("wa_id", "unknown")
    session = payload.get("session", {})
    
    memory = session.get("agent_memory", {})
    agent_mem = get_agent_memory(memory, "classifier_siniestros_agent")
    last_route = agent_mem.get("last_route", "unknown")
    history = get_global_history(memory)
    
    # Get prompt based on channel, filtered to active specialists
    channel = payload.get("channel", "whatsapp")
    system_prompt = get_prompt(channel, _ACTIVE_SPECIALISTS)

    prompt = ChatPromptTemplate.from_messages(
        [
            ("system", system_prompt),
            *history,
            ("human", "Contexto adicional: ultimo_route_provisional={last_route}\n\nMensaje del Usuario: {user_text}"),
        ]
    )

    llm = get_llm_fast()
    
    try:
        structured_llm = llm.with_structured_output(ClassificationDecision, method="json_mode")
    except:
        structured_llm = llm.with_structured_output(ClassificationDecision)
    
    chain = prompt | structured_llm

    result = safe_structured_invoke(
        chain,
        {
            "last_route": last_route,
            "user_text": user_text,
        },
        fallback_factory=lambda: ClassificationDecision(
            route="classifier_siniestros_agent",
            confidence=0.0,
            needs_more_info=True,
            question="Disculpa, no entendí bien. ¿Podrías decirme si necesitas asistencia, denunciar un siniestro o consultar un trámite?"
        ),
        error_context="classifier_siniestros_decision"
    )
    
    return result
