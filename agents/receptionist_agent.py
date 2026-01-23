import json
import os

from langchain.agents.tool_calling_agent.base import create_tool_calling_agent
from langchain.agents.agent import AgentExecutor

from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import PydanticOutputParser
from pydantic import BaseModel, Field
from langchain_core.tools import tool

from agents.llm import get_llm

import pathlib

# Robust path resolution for Docker /app env
# Assuming structure: /app/agents/receptionist_agent.py
# contracts is at: /app/contracts/routes.json
_CURRENT_DIR = pathlib.Path(__file__).parent.resolve() # /app/agents
_ROOT_DIR = _CURRENT_DIR.parent # /app
_ROUTES_PATH = _ROOT_DIR / "contracts" / "routes.json"

with open(_ROUTES_PATH, "r") as f:
    _ROUTES_CONFIG = json.load(f)
    _VALID_DOMAINS = set(_ROUTES_CONFIG["domains"])


def handle(payload: dict) -> dict:
    print("\n[RECEPTIONIST] 👋 Receptionist agent handling request")
    print(f"[RECEPTIONIST] Message: {payload.get('mensaje', '')[:80]}...")
    
    session = payload.get("session", {})
    memory = session.get("agent_memory", {})
    conversation_history = memory.get("conversation_history", [])
    is_first_message = len(conversation_history) == 0
    
    # Classify the domain
    print("[RECEPTIONIST] 🔍 Classifying domain...")
    decision = classify_domain(payload)
    domain = decision.get("domain")
    confidence = decision.get("confidence", 0.0)
    
    print(f"[RECEPTIONIST] ✓ Classification result: domain={domain}, confidence={confidence}")
    
    if domain in _ROUTES_CONFIG["domains"]:
        domain_config = _ROUTES_CONFIG["domains"][domain]
        classifier_agent = domain_config.get("classifier")
        
        if classifier_agent:
            print(f"[RECEPTIONIST] 🔀 Routing to {classifier_agent} (passthrough)")
            return {
                "action": "route",
                "next_agent": classifier_agent,
                "domain": domain,
                "message": None  # No message = passthrough, next agent responds immediately
            }
        else:
            print(f"[RECEPTIONIST] ⚠️  Domain {domain} has no classifier configured")
            return {
                "action": "ask",
                "message": f"El area de {domain} no esta disponible aun. ¿En que mas puedo ayudarte?"
            }

    # Could not classify - ask for clarification
    print("[RECEPTIONIST] 💬 Asking user for clarification")
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
    
    print(f"[RECEPTIONIST] 📝 Classifying domain for: '{user_text[:60]}...'")
    
    # Check if we are already in a domain loop - handled by orchestrator now
    # But we can respect active domain if passed?
    if session.get("domain"):
        existing_domain = session.get("domain")
        print(f"[RECEPTIONIST] ✓ Using existing domain from session: {existing_domain}")
        return {
            "domain": existing_domain,
            "confidence": 1.0,
            "reason": "active_session"
        }

    print("[RECEPTIONIST] 🤖 Calling LLM for domain classification...")
    
    # Dynamic list of available domains from routes.json
    available_domains = ", ".join(_VALID_DOMAINS)
    
    # Get conversation history for context
    memory = session.get("agent_memory", {})
    conversation_history = memory.get("conversation_history", [])
    
    # Build context from last few turns
    history_context = ""
    if conversation_history:
        recent_turns = conversation_history[-6:]  # Last 3 exchanges
        history_lines = []
        for turn in recent_turns:
            role = "Usuario" if turn.get("role") == "user" else "Asistente"
            history_lines.append(f"{role}: {turn.get('text', '')}")
        history_context = "\n".join(history_lines)
    
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
1. Analiza el mensaje del usuario.
2. Clasifica en una de las áreas disponibles ({available_domains}).
3. Si el área no está disponible, usa la más cercana.
4. Si el mensaje es ambiguo o muy corto (ej: "hola", "info"), usa domain='ask'.
5. **IMPORTANTE**: Si el usuario menciona problemas con el coche, avería, quedarse tirado, ruedas, grúa → es SINIESTROS.

{format_instructions}"""

    # Build the human message with context
    if history_context:
        human_message = """Historial de conversación:
{history_context}

Mensaje actual del cliente: {user_text}"""
    else:
        human_message = "Mensaje del cliente: {user_text}"

    prompt = ChatPromptTemplate.from_messages(
        [
            ("system", system_prompt),
            ("human", human_message),
        ]
    )

    llm = get_llm()
    chain = prompt | llm
    
    try:
        result = chain.invoke(
            {
                "user_text": user_text,
                "history_context": history_context,
                "format_instructions": parser.get_format_instructions(),
                "available_domains": available_domains,
            }
        )
        output = result.content
        print(f"[RECEPTIONIST] 📥 LLM raw response: {output}")
        
        # Clean markdown if present
        cleaned_output = output.strip()
        if cleaned_output.startswith("```"):
            cleaned_output = cleaned_output.split("```")[1]
            if cleaned_output.startswith("json"):
                cleaned_output = cleaned_output[4:]
            cleaned_output = cleaned_output.strip()
            
        parsed = parser.parse(cleaned_output)
        domain = parsed.domain
        confidence = parsed.confidence
        
        if domain not in _VALID_DOMAINS:
            print(f"[RECEPTIONIST] ⚠️  Invalid domain '{domain}', falling back to receptionist")
            domain = "receptionist_agent" # fallback
            
        print(f"[RECEPTIONIST] ✓ Parsed decision: domain={domain}, confidence={confidence}")
        return {"domain": domain, "confidence": confidence}
    except json.JSONDecodeError as e:
        print(f"[RECEPTIONIST] ❌ Failed to parse LLM JSON: {e}")
        print(f"[RECEPTIONIST]   Raw output: {output if 'output' in locals() else 'N/A'}")
        return {"domain": "receptionist_agent", "confidence": 0.0}
    except Exception as e:
        print(f"[RECEPTIONIST] ❌ Error during classification: {e}")
        import traceback
        print(f"[RECEPTIONIST] Traceback: {traceback.format_exc()}")
        return {"domain": "receptionist_agent", "confidence": 0.0}
