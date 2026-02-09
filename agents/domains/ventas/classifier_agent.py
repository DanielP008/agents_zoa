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
from agents.domains.ventas.classifier_agent_prompts import get_prompt

_ROUTES_PATH = get_routes_path()

with open(_ROUTES_PATH, "r") as f:
    _ROUTES_CONFIG = json.load(f)
    try:
        _VALID_ROUTES = _ROUTES_CONFIG["domains"]["ventas"]["specialists"]
    except KeyError:
        _VALID_ROUTES = []

def classifier_ventas_agent(payload: dict) -> dict:
    decision = classify_message(payload)
    
    if decision.action == "end_chat":
        return {
            "action": "end_chat",
            "message": decision.question or "¡Perfecto! Fue un placer ayudarte. Si necesitas algo más, aquí estaré. ¡Que tengas un excelente día! 😊"
        }

    # Safeguard: only ask if there's actually a question to ask
    if decision.needs_more_info and decision.question:
        # If the LLM says it needs more info but provides a message that looks like routing,
        # it's likely a model hallucination in the decision object.
        routing_phrases = ["contacto", "especialista", "redirijo", "paso con", "transfiero"]
        if any(phrase in decision.question.lower() for phrase in routing_phrases) and decision.route:
            return {
                "action": "route",
                "next_agent": decision.route, 
                "domain": "ventas",
                "message": decision.question
            }

        return {
            "action": "ask",
            "message": decision.question,
            "memory": {
                "agents": {
                    "classifier_ventas_agent": {
                        "last_route": decision.route,
                        "confidence": decision.confidence,
                    }
                }
            } 
        }

    return {
        "action": "route",
        "next_agent": decision.route, 
        "domain": "ventas",
        "message": None
    }

def classify_message(payload: dict) -> ClassificationDecision:
    user_text = payload.get("mensaje", "")
    user_id = payload.get("wa_id", "unknown")
    session = payload.get("session", {})
    
    memory = session.get("agent_memory", {})
    agent_mem = get_agent_memory(memory, "classifier_ventas_agent")
    last_route = agent_mem.get("last_route", "unknown")
    history = get_global_history(memory)
    
    # Get prompt based on channel
    channel = payload.get("channel", "whatsapp")
    system_prompt = get_prompt(channel)

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
            route="classifier_ventas_agent",
            confidence=0.0,
            needs_more_info=True,
            question="Disculpa, no entendí bien. ¿Buscas contratar una póliza nueva o mejorar un seguro que ya tienes?"
        ),
        error_context="classifier_ventas_decision"
    )
    
    return result
