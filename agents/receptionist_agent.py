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


def receptionist_agent(payload: dict) -> dict:
    
    session = payload.get("session", {})
    memory = session.get("agent_memory", {})
    conversation_history = memory.get("conversation_history", [])
    is_first_message = len(conversation_history) == 0
    
    # Classify the domain
    decision = classify_domain(payload)
    domain = decision.get("domain")
    confidence = decision.get("confidence", 0.0)
    
    
    if domain in _ROUTES_CONFIG["domains"]:
        domain_config = _ROUTES_CONFIG["domains"][domain]
        classifier_agent = domain_config.get("classifier")
        
        if classifier_agent:
            return {
                "action": "route",
                "next_agent": classifier_agent,
                "domain": domain,
                "message": None  # No message = passthrough, next agent responds immediately
            }
        else:
            return {
                "action": "ask",
                "message": f"El area de {domain} no esta disponible aun. ¿En que mas puedo ayudarte?"
            }

    # Could not classify - ask for clarification
    available_domains_str = ", ".join(
        [
            _ROUTES_CONFIG["domains"][d].get("receptionist_label", d.capitalize())
            for d in _VALID_DOMAINS
        ]
    )
    
    if is_first_message:
        return {
            "action": "ask",
            "message": f"Hola, soy Sofia, tu asistente virtual. Puedo ayudarte con {available_domains_str}. ¿Que necesitas?"
        }
    else:
        return {
            "action": "ask",
            "message": f"Disculpa, no estoy segura de haber entendido. ¿Tu consulta es sobre {available_domains_str}?"
        }

class DomainClassification(BaseModel):
    domain: str = Field(
        description="Nombre del dominio o 'ask' si falta info."
    )
    confidence: float = Field(
        description="Confianza entre 0.0 y 1.0.",
        ge=0.0,
        le=1.0
    )

def classify_domain(payload: dict) -> dict:
    user_text = payload.get("mensaje", "")
    session = payload.get("session", {})
    
    
    # Check if we are already in a domain loop - handled by orchestrator now
    # But we can respect active domain if passed?
    if session.get("domain"):
        existing_domain = session.get("domain")
        return {
            "domain": existing_domain,
            "confidence": 1.0,
            "reason": "active_session"
        }

    
    # Dynamic list of available domains from routes.json
    available_domains = ", ".join(_VALID_DOMAINS)
    
    # Get conversation history for context
    memory = session.get("agent_memory", {})
    history = get_agent_history(memory, "receptionist_agent")
    
    parser = PydanticOutputParser(pydantic_object=DomainClassification)

    system_prompt = """Eres el Recepcionista de ZOA Seguros. Tu objetivo es derivar al cliente a una de las áreas disponibles.

Áreas disponibles: {available_domains}

## Guía de clasificación

### SINIESTROS (domain: "siniestros")
Deriva a siniestros cuando el usuario mencione:
- Accidentes de tráfico, choques, colisiones
- Robos o hurtos del vehículo
- Daños al vehículo (cristales, golpes, vandalismo)
- **Asistencia en carretera**: grúa, ruedas pinchadas, batería descargada, quedarse tirado, avería
- Consultas sobre siniestros existentes o en proceso
- Documentación de siniestros

### GESTION (domain: "gestion")
Deriva a gestión cuando el usuario mencione:
- Devoluciones o reembolsos
- Pagos, recibos, facturas
- Modificar datos de la póliza
- Consultar coberturas o estado de póliza
- Cambio de beneficiarios
- Domiciliación bancaria

### VENTAS (domain: "ventas")
Deriva a ventas cuando el usuario mencione:
- Contratar una póliza nueva
- Cotizar un seguro
- Información sobre productos o coberturas disponibles

## INSTRUCCIONES
1. Analiza el mensaje del usuario y el historial de conversación.
2. Clasifica en una de las áreas disponibles ({available_domains}).
3. Si el área no está disponible, usa la más cercana.
4. Si el mensaje es ambiguo o muy corto (ej: "hola", "info"), usa domain='ask'.
5. **IMPORTANTE**: Si el usuario menciona problemas con el coche, avería, quedarse tirado, ruedas, grúa → es SINIESTROS.

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
            "available_domains": available_domains,
        },
        error_context="receptionist_domain_classification"
    )

    if not result or isinstance(result, dict) and result.get("error"):
        return {"domain": "receptionist_agent", "confidence": 0.0}

    # Parse the response
    parsed_data = parse_llm_json_response(result, ["domain", "confidence"])
    if not parsed_data or "domain" not in parsed_data:
        return {"domain": "receptionist_agent", "confidence": 0.0}

    domain = parsed_data.get("domain", "receptionist_agent")
    confidence = parsed_data.get("confidence", 0.0)

    if domain not in _VALID_DOMAINS:
        domain = "receptionist_agent" # fallback

    return {"domain": domain, "confidence": confidence}
