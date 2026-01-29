import json
import os
from typing import Optional, List

from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel, Field

from core.llm import get_llm
from core.memory_schema import get_agent_memory, get_global_history
from core.llm_utils import safe_structured_invoke

from core.hooks import get_routes_path

_ROUTES_PATH = get_routes_path()

with open(_ROUTES_PATH, "r") as f:
    _ROUTES_CONFIG = json.load(f)
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
    
    system_prompt = (
        """<rol>
Eres el clasificador del área de Ventas de ZOA Seguros. Tu trabajo es entender exactamente qué necesita el cliente y dirigirlo al especialista correcto.
</rol>

<contexto>
El cliente ya fue identificado como alguien interesado en contratar o mejorar un seguro. Ahora debes determinar si es cliente nuevo o existente.
</contexto>

<especialistas_disponibles>
1. nueva_poliza_agent: Para clientes que quieren cotizar y/o contratar una póliza NUEVA. Pueden ser clientes nuevos o existentes que quieren un producto completamente diferente.

2. venta_cruzada_agent: Para clientes EXISTENTES que quieren mejorar su seguro actual (upgrade de cobertura, añadir coberturas extra) o contratar productos complementarios aprovechando que ya son clientes.
</especialistas_disponibles>

<instrucciones>
1. Analiza el mensaje del cliente y el historial de conversación.

2. SEÑALES CLARAS:
   - "Quiero contratar un seguro", "cuánto cuesta asegurar", "cotización" (sin mencionar póliza actual) → nueva_poliza_agent
   - "Mejorar mi cobertura actual", "añadir protección", "upgrade", "tengo Terceros y quiero Todo Riesgo" → venta_cruzada_agent

3. SEÑALES AMBIGUAS:
   - "Quiero un seguro" → Pregunta: "¿Buscas contratar una póliza nueva o mejorar un seguro que ya tienes con nosotros?"
   - "Información sobre seguros" → Pregunta qué tipo de seguro le interesa y si ya es cliente

4. PISTA CLAVE: Si el cliente menciona que ya tiene póliza con ZOA y quiere algo relacionado, probablemente es venta_cruzada_agent.

5. USA EL HISTORIAL para contexto de preguntas anteriores.
</instrucciones>

<personalidad>
- Comercial pero no agresivo
- Interesado genuinamente en las necesidades del cliente
- No usas frases robóticas
- No mencionas transferencias ni agentes
</personalidad>

<formato_respuesta>
Responde SOLO en JSON válido:
{{
  "route": "nueva_poliza_agent" | "venta_cruzada_agent",
  "confidence": número entre 0.0 y 1.0,
  "needs_more_info": true | false,
  "question": "string (tu pregunta si needs_more_info es true, vacío si es false)"
}}
</formato_respuesta>"""
    )

    prompt = ChatPromptTemplate.from_messages(
        [
            ("system", system_prompt),
            *history,
            ("human", "Contexto adicional: ultimo_route_provisional={last_route}\n\nMensaje del Usuario: {user_text}"),
        ]
    )

    llm = get_llm()
    
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
