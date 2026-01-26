import json
import os

from langchain.agents.tool_calling_agent.base import create_tool_calling_agent
from langchain.agents.agent import AgentExecutor

from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel, Field

from agents.llm import get_llm
from core.memory_schema import get_global_history
from core.llm_utils import safe_structured_invoke

from core.hooks import get_routes_path

_ROUTES_PATH = get_routes_path()

with open(_ROUTES_PATH, "r") as f:
    _ROUTES_CONFIG = json.load(f)
    _VALID_DOMAINS = set(_ROUTES_CONFIG["domains"])


class ReceptionistDecision(BaseModel):
    domain: str | None = Field(
        default=None,
        description="El dominio detectado (siniestros, gestion, ventas) si está claro, o null si no."
    )
    message: str | None = Field(
        default=None,
        description="Respuesta natural al usuario si no se detecta dominio o se requiere más información."
    )
    confidence: float = Field(
        default=0.0,
        description="Nivel de confianza de la clasificación (0.0 a 1.0).",
        ge=0.0,
        le=1.0
    )

def receptionist_agent(payload: dict) -> dict:
    session = payload.get("session", {})
    memory = session.get("agent_memory", {})
    user_text = payload.get("mensaje", "")
    
    # 1. Check active session domain (shortcut)
    if session.get("domain"):
        existing_domain = session.get("domain")
        # Validate it still exists/is active
        if existing_domain in _ROUTES_CONFIG["domains"]:
            domain_config = _ROUTES_CONFIG["domains"][existing_domain]
            if domain_config.get("classifier"):
                return {
                    "action": "route",
                    "next_agent": domain_config.get("classifier"),
                    "domain": existing_domain,
                    "message": None
                }

    # 2. Prepare Context for LLM
    # Use global conversation history formatted for LangChain
    history = get_global_history(memory)
    
    # Check if this is the first interaction (ignoring the current input which is not in history yet)
    is_first_interaction = len(history) == 0
    
    # Filter only domains with active classifiers
    active_domains_map = {
        k: v.get("receptionist_label", k.capitalize())
        for k, v in _ROUTES_CONFIG["domains"].items()
        if v.get("classifier")
    }
    available_domains_str = ", ".join(active_domains_map.values())

    # Dynamic greeting instruction based on history state
    greeting_instruction = ""
    if is_first_interaction:
        greeting_instruction = "Esta es la PRIMERA interacción. DEBES presentarte brevemente como Sofía, recepcionista virtual de ZOA Seguros."
    else:
        greeting_instruction = "Esta NO es la primera interacción. NO te vuelvas a presentar. Ve directo al grano o pide la información que falta."

    system_prompt = """Eres Sofia, la recepcionista virtual de ZOA Seguros. Eres profesional, amable y natural.

Tus áreas de atención son: {available_domains}

Tu tarea es analizar el mensaje del usuario y decidir:
1. Si la consulta corresponde claramente a una de las áreas disponibles -> Identifica el `domain`.
2. Si la consulta es ambigua, falta información o no corresponde a ninguna área -> Genera una respuesta natural (`message`) pidiendo aclaración.

## Guía de Clasificación

### SINIESTROS (domain: "siniestros")
- Accidentes, choques, robos, daños.
- **Asistencia en carretera**: grúa, batería, avería, quedarse tirado.
- Consultas de siniestros existentes.

### GESTION (domain: "gestion")
- Recibos, pagos, devoluciones.
- Modificar póliza, datos bancarios, beneficiarios.
- Consultar coberturas.

### VENTAS (domain: "ventas")
- Contratar nueva póliza.
- Cotizaciones.
- Información comercial.

## Instrucciones de Respuesta
- Si clasificas un dominio con confianza: devuelve el `domain` y `confidence` alto. `message` puede ser null.
- Si NO clasificas: `domain` debe ser null. `message` debe ser tu respuesta al usuario.
- Tu respuesta debe ser natural y profesional. No listes todas las opciones a menos que sea necesario para guiar al usuario.
- **IMPORTANTE**: {greeting_instruction}

## Formato de respuesta
DEBES responder en formato JSON válido con esta estructura exacta:
{{{{
  "domain": "string o null",
  "message": "string o null", 
  "confidence": número entre 0.0 y 1.0
}}}}"""

    prompt = ChatPromptTemplate.from_messages(
        [
            ("system", system_prompt),
            *history,
            ("human", "Mensaje del cliente: {user_text}"),
        ]
    )

    llm = get_llm()
    
    # Use json_mode for more reliable structured output with Gemini
    # This is a known workaround for with_structured_output reliability issues
    try:
        structured_llm = llm.with_structured_output(ReceptionistDecision, method="json_mode")
    except:
        # Fallback to default method if json_mode is not available
        structured_llm = llm.with_structured_output(ReceptionistDecision)
    
    chain = prompt | structured_llm

    print(f"\n[RECEPTIONIST DEBUG] user_text: {user_text}")
    print(f"[RECEPTIONIST DEBUG] available_domains: {available_domains_str}")
    print(f"[RECEPTIONIST DEBUG] greeting_instruction: {greeting_instruction}")
    
    decision = safe_structured_invoke(
        chain,
        {
            "user_text": user_text,
            "available_domains": available_domains_str,
            "greeting_instruction": greeting_instruction,
        },
        fallback_factory=lambda: ReceptionistDecision(
            domain=None,
            message="Disculpa, tuve un problema técnico. ¿Podrías repetir tu consulta?",
            confidence=0.0
        ),
        error_context="receptionist_decision"
    )
    
    print(f"[RECEPTIONIST DEBUG] decision: {decision}")
    print(f"[RECEPTIONIST DEBUG] decision.domain: {decision.domain}")
    print(f"[RECEPTIONIST DEBUG] decision.message: {decision.message}")
    print(f"[RECEPTIONIST DEBUG] decision.confidence: {decision.confidence}")

    domain = decision.domain
    message = decision.message
    
    # 4. Execute Decision
    
    # Case A: Valid Domain Identified
    if domain and domain in active_domains_map:
        domain_config = _ROUTES_CONFIG["domains"][domain]
        classifier_agent = domain_config.get("classifier")
        
        if classifier_agent:
            return {
                "action": "route",
                "next_agent": classifier_agent,
                "domain": domain,
                "message": None # Passthrough
            }
    
    # Case B: No domain or Invalid domain -> Ask with generated message
    if not message:
        # Fallback message if LLM routed but failed valid check (rare) or returned null message
        message = f"Disculpa, no entendí bien. ¿Tu consulta es sobre {available_domains_str}?"

    return {
        "action": "ask",
        "message": message
    }
