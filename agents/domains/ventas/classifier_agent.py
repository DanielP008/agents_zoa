import json
import os
from typing import Optional, List

from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel, Field

from agents.llm import get_llm
from core.memory_schema import get_agent_memory, get_global_history
from core.llm_utils import safe_structured_invoke

# Configuration loading to avoid circular imports with main_router
from core.hooks import get_routes_path

_ROUTES_PATH = get_routes_path()

with open(_ROUTES_PATH, "r") as f:
    _ROUTES_CONFIG = json.load(f)
    # Parse new structure
    try:
        _VALID_ROUTES = _ROUTES_CONFIG["domains"]["ventas"]["specialists"]
    except KeyError:
        _VALID_ROUTES = []

class ClassificationDecision(BaseModel):
    """Decision model for the classifier agent."""
    route: str = Field(
        default="classifier_ventas_agent",
        description=f"The target agent to route to. Must be one of: {', '.join(_VALID_ROUTES)}. If unsure, select the most likely one but set needs_more_info to True."
    )
    confidence: float = Field(
        default=0.0,
        description="Confidence score between 0.0 and 1.0."
    )
    needs_more_info: bool = Field(
        default=True,
        description="Set to True if you need to ask the user a clarifying question before routing. Set to False if you are confident."
    )
    question: str = Field(
        default="",
        description="The question to ask the user if needs_more_info is True. Otherwise, an empty string or polite closing."
    )

def classifier_ventas_agent(payload: dict) -> dict:
    decision = classify_message(payload)
    
    if decision.needs_more_info:
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
        "message": None  # Passthrough: el agente especializado responderá directamente
    }

def classify_message(payload: dict) -> ClassificationDecision:
    user_text = payload.get("mensaje", "")
    user_id = payload.get("wa_id", "unknown")
    session = payload.get("session", {})
    
    memory = session.get("agent_memory", {})
    agent_mem = get_agent_memory(memory, "classifier_ventas_agent")
    last_route = agent_mem.get("last_route", "unknown")
    history = get_global_history(memory)
    
    # Construct the prompt
    system_prompt = (
        "Eres el Agente Clasificador de Ventas de ZOA. "
        "Tu objetivo es entender EXACTAMENTE qué necesita el usuario y derivarlo al agente correcto.\n\n"
        f"Los agentes disponibles son:\n"
        f"- nueva_poliza_agent: Para cotizar y contratar una nueva póliza de seguro.\n"
        f"- venta_cruzada_agent: Para ofrecer productos adicionales a clientes que YA tienen póliza (upgrades, coberturas extras, otros seguros).\n\n"
        "Instrucciones:\n"
        "1. Analiza el mensaje del usuario y el historial de conversación.\n"
        "2. Si la intención no es clara o faltan detalles clave para decidir entre los agentes, DEBES preguntar (needs_more_info=True).\n"
        "3. Si el usuario ya es cliente y busca mejorar/ampliar su seguro actual, va a venta_cruzada_agent.\n"
        "4. Si el usuario es nuevo o busca una póliza completamente nueva, va a nueva_poliza_agent.\n"
        "5. Sé amable y directo en tus preguntas.\n"
        "6. Si estás seguro, establece needs_more_info=False y route al agente correcto.\n"
        "7. Contexto previo: El usuario puede estar respondiendo a una pregunta anterior. Usa el historial para entender el contexto completo.\n\n"
        "## Formato de respuesta\n"
        "DEBES responder en formato JSON válido con esta estructura exacta:\n"
        "{{\n"
        '  "route": "nombre_del_agente",\n'
        '  "confidence": número entre 0.0 y 1.0,\n'
        '  "needs_more_info": true o false,\n'
        '  "question": "string o cadena vacía"\n'
        "}}"
    )

    prompt = ChatPromptTemplate.from_messages(
        [
            ("system", system_prompt),
            *history,
            ("human", "Contexto adicional: ultimo_route_provisional={last_route}\n\nMensaje del Usuario: {user_text}"),
        ]
    )

    llm = get_llm()
    
    # Use json_mode for more reliable structured output with Gemini
    try:
        structured_llm = llm.with_structured_output(ClassificationDecision, method="json_mode")
    except:
        structured_llm = llm.with_structured_output(ClassificationDecision)
    
    chain = prompt | structured_llm

    print(f"\n[CLASSIFIER VENTAS DEBUG] user_text: {user_text}")
    print(f"[CLASSIFIER VENTAS DEBUG] last_route: {last_route}")
    
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
    
    print(f"[CLASSIFIER VENTAS DEBUG] result: {result}")
    print(f"[CLASSIFIER VENTAS DEBUG] result.route: {result.route}")
    print(f"[CLASSIFIER VENTAS DEBUG] result.needs_more_info: {result.needs_more_info}")
    print(f"[CLASSIFIER VENTAS DEBUG] result.question: {result.question}")
    
    return result
