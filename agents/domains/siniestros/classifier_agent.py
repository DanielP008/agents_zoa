import json
import os
from typing import Optional, List

from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel, Field

from core.llm import get_llm
from core.memory_schema import get_agent_memory, get_global_history
from core.llm_utils import safe_structured_invoke

from core.config import get_routes_path

_ROUTES_PATH = get_routes_path()

with open(_ROUTES_PATH, "r") as f:
    _ROUTES_CONFIG = json.load(f)
    try:
        _VALID_ROUTES = _ROUTES_CONFIG["domains"]["siniestros"]["specialists"]
    except KeyError:
        _VALID_ROUTES = []

class ClassificationDecision(BaseModel):
    """Decision model for the classifier agent."""
    route: str = Field(
        default="classifier_siniestros_agent",
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

def classifier_siniestros_agent(payload: dict) -> dict:
    decision = classify_message(payload)
    
    if decision.needs_more_info:
        return {
            "action": "ask",
            "message": decision.question,
            "memory": {
                "agents": {
                    "classifier_siniestros_agent": {
                        "last_route": decision.route,
                        "confidence": decision.confidence,
                    }
                }
            } 
        }

    return {
        "action": "route",
        "next_agent": decision.route, 
        "domain": "siniestros",
        "message": None
    }

def classify_message(payload: dict) -> ClassificationDecision:
    user_text = payload.get("mensaje", "")
    user_id = payload.get("wa_id", "unknown")
    session = payload.get("session", {})
    
    memory = session.get("agent_memory", {})
    agent_mem = get_agent_memory(memory, "classifier_siniestros_agent")
    last_route = agent_mem.get("last_route", "unknown")
    history = get_global_history(memory)
    
    system_prompt = (
        """<rol>
Eres el clasificador del área de Siniestros de ZOA Seguros. Tu trabajo es entender exactamente qué necesita el cliente y dirigirlo al especialista correcto.
</rol>

<contexto>
El cliente ya fue identificado como alguien que necesita ayuda con siniestros. Ahora debes determinar qué tipo de ayuda específica necesita.
</contexto>

<especialistas_disponibles>
1. telefonos_asistencia_agent: Para solicitar números de asistencia en carretera (grúa, auxilio mecánico, asistencia en viaje) o emergencias del hogar.

2. apertura_siniestro_agent: Para denunciar un siniestro NUEVO (choque, robo, daños, incendio, inundación, etc.).

3. consulta_estado_agent: Para consultar el estado de un siniestro YA ABIERTO o hacer seguimiento de un trámite existente.
</especialistas_disponibles>

<instrucciones>
1. Analiza el mensaje del cliente y el historial de conversación.

2. SEÑALES CLARAS:
   - "grúa", "auxilio", "me quedé tirado", "batería", "pinchazo" → telefonos_asistencia_agent
   - "choqué", "me robaron", "tuve un accidente", "se inundó", "incendio" → apertura_siniestro_agent
   - "cómo va mi siniestro", "estado de mi reclamo", "número de expediente" → consulta_estado_agent

3. SEÑALES AMBIGUAS:
   - "Siniestro" solo → NO asumas. Pregunta: "¿Necesitas denunciar un siniestro nuevo o consultar el estado de uno que ya tienes abierto?"
   - "Tengo un problema con mi coche" → Pregunta: "¿Necesitas asistencia ahora mismo (grúa, auxilio) o quieres denunciar un incidente?"

4. USA EL HISTORIAL: Si el cliente responde a una pregunta tuya anterior, usa ese contexto para decidir.

5. Sé directo y amable en tus preguntas. Una sola pregunta por mensaje.
</instrucciones>

<personalidad>
- Resolutivo, vas al grano
- Empático si el cliente menciona un accidente o situación difícil
- No usas frases robóticas
- No mencionas transferencias ni agentes
</personalidad>

<formato_respuesta>
Responde SOLO en JSON válido:
{{
  "route": "telefonos_asistencia_agent" | "apertura_siniestro_agent" | "consulta_estado_agent",
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
