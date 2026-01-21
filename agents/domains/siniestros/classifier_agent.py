import json
import os
from typing import Optional, List

from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel, Field

from agents.llm import get_llm

# Configuration loading to avoid circular imports with main_router
import pathlib

# Robust path resolution
# Current: /app/agents/domains/siniestros/classifier_agent.py
# Root: /app
_CURRENT_DIR = pathlib.Path(__file__).parent.resolve()
_ROOT_DIR = _CURRENT_DIR.parent.parent.parent # up 3 levels: siniestros -> domains -> agents -> app
_ROUTES_PATH = _ROOT_DIR / "contracts" / "routes.json"

with open(_ROUTES_PATH, "r") as f:
    _ROUTES_CONFIG = json.load(f)
    # Parse new structure
    try:
        _VALID_ROUTES = _ROUTES_CONFIG["domains"]["siniestros"]["specialists"]
    except KeyError:
        _VALID_ROUTES = []

class ClassificationDecision(BaseModel):
    """Decision model for the classifier agent."""
    route: str = Field(
        description=f"The target agent to route to. Must be one of: {', '.join(_VALID_ROUTES)}. If unsure, select the most likely one but set needs_more_info to True."
    )
    confidence: float = Field(
        description="Confidence score between 0.0 and 1.0."
    )
    needs_more_info: bool = Field(
        description="Set to True if you need to ask the user a clarifying question before routing. Set to False if you are confident."
    )
    question: str = Field(
        description="The question to ask the user if needs_more_info is True. Otherwise, an empty string or polite closing.",
        default=""
    )

def handle(payload: dict) -> dict:
    """
    Handles the classification request.
    Returns an action dict:
    - action: "ask" -> stay on classifier, ask user.
    - action: "route" -> move to next agent.
    """
    decision = classify_message(payload)
    
    if decision.needs_more_info:
        return {
            "action": "ask",
            "message": decision.question,
            "memory": {
                "last_route": decision.route,
                "confidence": decision.confidence
            } 
        }

    return {
        "action": "route",
        "next_agent": decision.route, 
        "domain": "siniestros",
        "message": "Te derivo con el agente especializado."
    }

def classify_message(payload: dict) -> ClassificationDecision:
    user_text = payload.get("text", "")
    user_id = payload.get("from", "unknown")
    session = payload.get("session", {})
    
    memory = session.get("agent_memory", {})
    last_route = memory.get("last_route", "unknown")
    
    # Construct the prompt
    system_prompt = (
        "Eres el Agente Clasificador de Siniestros de ZOA. "
        "Tu objetivo es entender EXACTAMENTE qué necesita el usuario y derivarlo al agente correcto.\n\n"
        f"Los agentes disponibles son:\n"
        f"- telefonos_asistencia_agent: Para solicitar números de grúa, asistencia mecánica, o emergencias.\n"
        f"- apertura_siniestro_agent: Para denunciar un choque, robo, o accidente nuevo.\n"
        f"- consulta_estado_agent: Para consultar el estado de un siniestro YA iniciado o existente.\n\n"
        "Instrucciones:\n"
        "1. Analiza el mensaje del usuario y el historial.\n"
        "2. Si la intención no es clara o faltan detalles clave para decidir entre los agentes, DEBES preguntar (needs_more_info=True).\n"
        "3. NO asumas. Si el usuario dice 'siniestro', no sabes si quiere abrir uno o consultar uno existente. PREGUNTA.\n"
        "4. Sé amable y directo en tus preguntas.\n"
        "5. Si estás seguro, establece needs_more_info=False y route al agente correcto.\n"
        "6. Contexto previo: El usuario puede estar respondiendo a una pregunta anterior.\n"
    )

    prompt = ChatPromptTemplate.from_messages(
        [
            ("system", system_prompt),
            ("human", "Historial/Contexto: ultimo_route_provisional={last_route}\n\nMensaje del Usuario: {user_text}"),
        ]
    )

    llm = get_llm()
    structured_llm = llm.with_structured_output(ClassificationDecision)
    chain = prompt | structured_llm

    try:
        result = chain.invoke(
            {
                "last_route": last_route,
                "user_text": user_text,
            }
        )
        return result
    except Exception as e:
        # Fallback in case of LLM failure
        print(f"Error in classification: {e}")
        return ClassificationDecision(
            route="classifier_siniestros_agent", # provisional
            confidence=0.0,
            needs_more_info=True,
            question="Disculpa, no entendí bien. ¿Podrías decirme si necesitas asistencia, denunciar un siniestro o consultar un trámite?"
        )
