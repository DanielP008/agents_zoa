import json
import os
from typing import Optional, List

from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel, Field

from agents.llm import get_llm
from core.memory_schema import get_agent_memory, get_global_history
from core.llm_utils import safe_structured_invoke

from core.hooks import get_routes_path

_ROUTES_PATH = get_routes_path()

with open(_ROUTES_PATH, "r") as f:
    _ROUTES_CONFIG = json.load(f)
    try:
        _VALID_ROUTES = _ROUTES_CONFIG["domains"]["gestion"]["specialists"]
    except KeyError:
        _VALID_ROUTES = []

class ClassificationDecision(BaseModel):
    """Decision model for the classifier agent."""
    route: str = Field(
        default="classifier_gestion_agent",
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

def classifier_gestion_agent(payload: dict) -> dict:
    decision = classify_message(payload)
    
    if decision.needs_more_info:
        return {
            "action": "ask",
            "message": decision.question,
            "memory": {
                "agents": {
                    "classifier_gestion_agent": {
                        "last_route": decision.route,
                        "confidence": decision.confidence,
                    }
                }
            } 
        }

    return {
        "action": "route",
        "next_agent": decision.route, 
        "domain": "gestion",
        "message": None
    }

def classify_message(payload: dict) -> ClassificationDecision:
    user_text = payload.get("mensaje", "")
    user_id = payload.get("wa_id", "unknown")
    session = payload.get("session", {})
    
    memory = session.get("agent_memory", {})
    agent_mem = get_agent_memory(memory, "classifier_gestion_agent")
    last_route = agent_mem.get("last_route", "unknown")
    history = get_global_history(memory)
    
    system_prompt = (
        """<rol>
Eres el clasificador del área de Gestión de ZOA Seguros. Tu trabajo es entender exactamente qué necesita el cliente y dirigirlo al especialista correcto.
</rol>

<contexto>
El cliente ya fue identificado como alguien que necesita gestionar algo de su póliza. Ahora debes determinar qué tipo de gestión específica necesita.
</contexto>

<especialistas_disponibles>
1. devolucion_agent: Para solicitar devoluciones de dinero, reembolsos, o recibos cobrados de más.

2. consultar_poliza_agent: Para consultar información de la póliza (coberturas, datos del contrato, vencimientos, información del vehículo/inmueble).

3. modificar_poliza_agent: Para modificar datos de la póliza (cuenta bancaria, beneficiarios, domicilio, teléfono, email, matrícula).
</especialistas_disponibles>

<instrucciones>
1. Analiza el mensaje del cliente y el historial de conversación.

2. SEÑALES CLARAS:
   - "devolución", "reembolso", "me cobraron de más", "quiero que me devuelvan" → devolucion_agent
   - "qué cubre mi póliza", "cuándo vence", "ver mi contrato", "datos de mi seguro" → consultar_poliza_agent
   - "cambiar cuenta", "actualizar domicilio", "modificar beneficiario", "cambiar matrícula" → modificar_poliza_agent

3. SEÑALES AMBIGUAS:
   - "Mi póliza" solo → NO asumas. Pregunta: "¿Quieres consultar los datos de tu póliza o necesitas modificar algo?"
   - "Tengo una duda sobre mi seguro" → Pregunta qué duda específica tiene

4. USA EL HISTORIAL: Si el cliente responde a una pregunta tuya anterior, usa ese contexto para decidir.

5. Sé directo y amable. Una sola pregunta por mensaje.
</instrucciones>

<personalidad>
- Profesional y eficiente
- No usas frases robóticas
- No mencionas transferencias ni agentes
</personalidad>

<formato_respuesta>
Responde SOLO en JSON válido:
{{
  "route": "devolucion_agent" | "consultar_poliza_agent" | "modificar_poliza_agent",
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

    print(f"\n[CLASSIFIER GESTION DEBUG] user_text: {user_text}")
    print(f"[CLASSIFIER GESTION DEBUG] last_route: {last_route}")
    
    result = safe_structured_invoke(
        chain,
        {
            "last_route": last_route,
            "user_text": user_text,
        },
        fallback_factory=lambda: ClassificationDecision(
            route="classifier_gestion_agent",
            confidence=0.0,
            needs_more_info=True,
            question="Disculpa, no entendí bien. ¿Necesitas solicitar una devolución, consultar tu póliza o modificar algún dato?"
        ),
        error_context="classifier_gestion_decision"
    )
    
    print(f"[CLASSIFIER GESTION DEBUG] result: {result}")
    print(f"[CLASSIFIER GESTION DEBUG] result.route: {result.route}")
    print(f"[CLASSIFIER GESTION DEBUG] result.needs_more_info: {result.needs_more_info}")
    print(f"[CLASSIFIER GESTION DEBUG] result.question: {result.question}")
    
    return result
