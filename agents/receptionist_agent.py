import json
import os

from langchain.agents.tool_calling_agent.base import create_tool_calling_agent
from langchain.agents.agent import AgentExecutor

import re

from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel, Field

from core.llm import get_llm
from core.memory_schema import get_global_history
from core.llm_utils import safe_structured_invoke

from core.config import get_routes_path

_ROUTES_PATH = get_routes_path()

with open(_ROUTES_PATH, "r") as f:
    _ROUTES_CONFIG = json.load(f)
    _VALID_DOMAINS = set(_ROUTES_CONFIG["domains"])


def _extract_nif_from_text(text: str) -> str:
    if not text:
        return ""
    patterns = [
        r"\b\d{8}[A-Za-z]\b",
        r"\b[XYZ]\d{7}[A-Za-z]\b",
        r"\b[A-Za-z]\d{7}[A-Za-z0-9]\b",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return match.group(0).upper()
    return ""


def _build_nif_memory_patch(nif: str) -> dict:
    return {"global": {"nif": nif, "nif_lookup_failed": False}}


class ReceptionistDecision(BaseModel):
    domain: str | None = Field(
        default=None,
        description="El dominio detectado (siniestros, gestion, ventas) si está claro, o null si no."
    )
    message: str | None = Field(
        default=None,
        description="Respuesta natural al usuario si no se detecta dominio o se requiere más información."
    )
    confidence: float | None = Field(
        default=0.0,
        description="Nivel de confianza de la clasificación (0.0 a 1.0).",
        ge=0.0,
        le=1.0
    )

def receptionist_agent(payload: dict) -> dict:
    session = payload.get("session", {})
    memory = session.get("agent_memory", {})
    user_text = payload.get("mensaje", "")
    wa_id = payload.get("wa_id")
    company_id = payload.get("phone_number_id", "default")
    global_mem = memory.get("global", {})
    nif_value = global_mem.get("nif")
    memory_patch = None
    print(f"[RECEPTIONIST] NIF check - memory nif: {nif_value}")
    
    consultation_completed = global_mem.get("consultation_completed", False)
    
    closure_phrases = [
        "no", "no gracias", "nada más", "nada mas", "gracias", "thank you", 
        "listo", "perfecto", "ok", "vale", "chau", "adiós", "adios", "bye",
        "eso es todo", "ya está", "ya esta", "suficiente", "solucionado"
    ]
    user_text_lower = user_text.lower().strip()
    is_closure = any(phrase in user_text_lower for phrase in closure_phrases)
    
    if consultation_completed and is_closure and len(user_text_lower) < 30:
        from core.db import SessionManager
        session_manager = SessionManager()
        session_manager.delete_session(wa_id, company_id)
        
        print(f"\n[RECEPTIONIST AUTO-RESET] Session deleted for wa_id: {wa_id}")
        print(f"[RECEPTIONIST AUTO-RESET] Closure phrase detected: '{user_text}'")
        
        return {
            "action": "finish",
            "message": "¡Perfecto! Fue un placer ayudarte. Si necesitas algo más en el futuro, aquí estaré. ¡Que tengas un excelente día! 😊"
        }

    
    if session.get("domain"):
        existing_domain = session.get("domain")
        if existing_domain in _ROUTES_CONFIG["domains"]:
            domain_config = _ROUTES_CONFIG["domains"][existing_domain]
            if domain_config.get("classifier"):
                return {
                    "action": "route",
                    "next_agent": domain_config.get("classifier"),
                    "domain": existing_domain,
                    "message": None
                }

    history = get_global_history(memory)
    
    has_assistant_messages = any(role == "ai" for role, _ in history)
    is_first_interaction = not has_assistant_messages

    if not nif_value:
        detected_nif = _extract_nif_from_text(user_text)
        if detected_nif:
            print(f"[RECEPTIONIST] NIF extracted from user text: {detected_nif}")
            nif_value = detected_nif
            memory_patch = _build_nif_memory_patch(detected_nif)
        elif not is_first_interaction:
            print(f"[RECEPTIONIST] NIF missing and not first interaction, asking user for NIF")
            return {
                "action": "ask",
                "message": "Para continuar, necesito tu NIF, DNI, NIE o CIF. ¿Podés indicármelo?"
            }
        else:
            print(f"[RECEPTIONIST] NIF missing but first interaction, continuing with greeting")
    else:
        print(f"[RECEPTIONIST] NIF already in memory: {nif_value}")
    
    if payload.get("ask_nif") and not nif_value:
        return {
            "action": "ask",
            "message": "Para continuar, necesito tu NIF, DNI, NIE o CIF. ¿Podés indicármelo?"
        }

    active_domains_map = {
        k: v.get("receptionist_label", k.capitalize())
        for k, v in _ROUTES_CONFIG["domains"].items()
        if v.get("classifier")
    }
    available_domains_str = ", ".join(active_domains_map.values())

    greeting_instruction = ""
    if is_first_interaction:
        greeting_instruction = "Esta es la PRIMERA interacción. DEBES presentarte brevemente como Sofía, recepcionista virtual de ZOA Seguros."
    else:
        greeting_instruction = "Esta NO es la primera interacción. NO te vuelvas a presentar. Ve directo al grano o pide la información que falta."
    
    consultation_context = ""
    if consultation_completed:
        consultation_context = "\n\n**IMPORTANTE**: La consulta anterior del usuario fue completada exitosamente. Si el usuario tiene una NUEVA consulta diferente, clasifícala normalmente. Si el usuario agradece o despide, responde amablemente y confirma que finalizas la atención."

    system_prompt = """Eres Sofia, la recepcionista virtual de ZOA Seguros. Eres profesional, amable y natural.

Tus áreas de atención son: {available_domains}

Tu tarea es analizar el mensaje del usuario y decidir:
1. Si la consulta corresponde claramente a una de las áreas disponibles -> Identifica el `domain`.
2. Si la consulta es ambigua, falta información o no corresponde a ninguna área -> Genera una respuesta natural (`message`) pidiendo aclaración.

## Guía de Clasificación

### SINIESTROS (domain: "siniestros")
- **Denunciar accidentes**: choques, robos, daños al vehículo.
- **Asistencia en carretera**: números de grúa, auxilio mecánico, batería, quedarse sin combustible.
- **Consultar siniestros**: estado de un siniestro ya iniciado, seguimiento de trámites.

### GESTION (domain: "gestion")
- **Solicitar devoluciones**: reembolsos, recibos pagados de más.
- **Consultar póliza**: ver coberturas, datos del contrato, información del vehículo, vencimientos.
- **Modificar póliza**: cambiar datos bancarios, beneficiarios, domicilio, teléfono, email.

### VENTAS (domain: "ventas")
- **Contratar seguro nuevo**: cotizaciones, comparar coberturas (Terceros, Terceros Completo, Todo Riesgo).
- **Mejorar tu seguro actual**: agregar coberturas, upgrades, productos complementarios (hogar, vida).

## Instrucciones de Respuesta
- Si clasificas un dominio con confianza: devuelve el `domain` y `confidence` alto. `message` puede ser null.
- Si NO clasificas: `domain` debe ser null. `message` debe ser tu respuesta al usuario.
- **IMPORTANTE**: {greeting_instruction}
- **Cuando el usuario saluda o pide ayuda general**: Preséntate y menciona de forma descriptiva las funcionalidades principales que ofreces:
  - Asistencia en siniestros (denuncias, números de emergencia, seguimiento)
  - Gestión de pólizas (devoluciones, consultas, modificaciones)
  - Contratación y mejora de seguros (cotizaciones, nuevas pólizas, upgrades)
  
  Hazlo de manera conversacional y natural, sin listar mecánicamente. Invita al usuario a contarte qué necesita.
{consultation_context}

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
    
    try:
        structured_llm = llm.with_structured_output(ReceptionistDecision, method="json_mode")
    except:
        structured_llm = llm.with_structured_output(ReceptionistDecision)
    
    chain = prompt | structured_llm

    print(f"\n[RECEPTIONIST DEBUG] user_text: {user_text}")
    print(f"[RECEPTIONIST DEBUG] available_domains: {available_domains_str}")
    print(f"[RECEPTIONIST DEBUG] greeting_instruction: {greeting_instruction}")
    print(f"[RECEPTIONIST DEBUG] consultation_completed: {consultation_completed}")
    
    decision = safe_structured_invoke(
        chain,
        {
            "user_text": user_text,
            "available_domains": available_domains_str,
            "greeting_instruction": greeting_instruction,
            "consultation_context": consultation_context,
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
    confidence = decision.confidence if decision.confidence is not None else 0.0
    
    if domain and domain in active_domains_map:
        domain_config = _ROUTES_CONFIG["domains"][domain]
        classifier_agent = domain_config.get("classifier")
        
        if classifier_agent:
            response = {
                "action": "route",
                "next_agent": classifier_agent,
                "domain": domain,
                "message": None
            }
            if memory_patch:
                response["memory"] = memory_patch
            return response
    
    if not message:
        message = f"Disculpa, no entendí bien. ¿Tu consulta es sobre {available_domains_str}?"

    response = {
        "action": "ask",
        "message": message
    }
    if memory_patch:
        response["memory"] = memory_patch
    return response
