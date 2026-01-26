import json
import os

from langchain.agents.tool_calling_agent.base import create_tool_calling_agent
from langchain.agents.agent import AgentExecutor

from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import PydanticOutputParser
from pydantic import BaseModel, Field
from langchain_core.tools import tool

from agents.llm import get_llm
from core.llm_utils import safe_llm_invoke, parse_llm_json_response
from core.memory_schema import get_agent_history

from core.hooks import get_contracts_path

_ROUTES_PATH = get_contracts_path("routes.json")

with open(_ROUTES_PATH, "r") as f:
    _ROUTES_CONFIG = json.load(f)
    _VALID_DOMAINS = set(_ROUTES_CONFIG["domains"])


class ReceptionistDecision(BaseModel):
    domain: str | None = Field(
        description="El dominio detectado (siniestros, gestion, ventas) si está claro, o null si no."
    )
    message: str | None = Field(
        description="Respuesta natural al usuario si no se detecta dominio o se requiere más información."
    )
    confidence: float = Field(
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
    history = get_agent_history(memory, "receptionist_agent")
    
    # Filter only domains with active classifiers
    active_domains_map = {
        k: v.get("receptionist_label", k.capitalize())
        for k, v in _ROUTES_CONFIG["domains"].items()
        if v.get("classifier")
    }
    available_domains_str = ", ".join(active_domains_map.values())
    
    parser = PydanticOutputParser(pydantic_object=ReceptionistDecision)

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
- Si el usuario solo saluda, preséntate brevemente.

{format_instructions}"""

    prompt = ChatPromptTemplate.from_messages(
        [
            ("system", system_prompt),
            *history,
            ("human", "Mensaje del cliente: {user_text}"),
        ]
    )

    llm = get_llm()
    chain = prompt | llm

    result = safe_llm_invoke(
        chain.invoke,
        {
            "user_text": user_text,
            "format_instructions": parser.get_format_instructions(),
            "available_domains": available_domains_str,
        },
        error_context="receptionist_decision"
    )

    # 3. Process Result
    decision = None
    if result and not (isinstance(result, dict) and result.get("error")):
        parsed = parse_llm_json_response(result, ["domain", "message", "confidence"])
        if parsed:
            decision = parsed

    # Fallback if LLM fails
    if not decision:
        return {
            "action": "ask",
            "message": "Disculpa, tuve un problema técnico. ¿Podrías repetir tu consulta?"
        }

    domain = decision.get("domain")
    message = decision.get("message")
    
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
