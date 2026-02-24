import json
import logging
import re

from langchain_core.messages import HumanMessage, AIMessage, SystemMessage

from infra.llm import get_llm
from core.memory import get_global_history
from infra.llm_utils import safe_structured_invoke
from infra.config import get_routes_path
from infra.decision_schemas import ReceptionistDecision
from core.routing.allowlist import get_active_specialists
from agents.receptionist_agent_prompts import get_prompt

logger = logging.getLogger(__name__)

_ROUTES_PATH = get_routes_path()

with open(_ROUTES_PATH, "r") as f:
    _ROUTES_CONFIG = json.load(f)
    _VALID_DOMAINS = set(
        k for k, v in _ROUTES_CONFIG["domains"].items()
        if v.get("enabled", True)
    )

# Build active domains and specialist mapping for prompt assembly
_ACTIVE_DOMAINS = [
    k for k, v in _ROUTES_CONFIG["domains"].items()
    if v.get("enabled", True) and v.get("classifier")
]
_ACTIVE_SPECIALISTS_BY_DOMAIN = {
    domain: get_active_specialists(domain, _ROUTES_CONFIG)
    for domain in _ACTIVE_DOMAINS
}

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

def receptionist_agent(payload: dict) -> dict:
    session = payload.get("session", {})
    memory = session.get("agent_memory", {})
    user_text = payload.get("mensaje", "")
    wa_id = payload.get("wa_id")
    company_id = payload.get("phone_number_id", "default")
    global_mem = memory.get("global", {})
    nif_value = global_mem.get("nif")
    memory_patch = None

    consultation_completed = global_mem.get("consultation_completed", False)

    closure_phrases = [
        "no", "no gracias", "nada más", "nada mas", "gracias", "thank you",
        "listo", "perfecto", "ok", "vale", "chau", "adiós", "adios", "bye",
        "eso es todo", "ya está", "ya esta", "suficiente", "solucionado"
    ]
    user_text_lower = user_text.lower().strip()
    is_closure = any(phrase in user_text_lower for phrase in closure_phrases)

    if consultation_completed and is_closure and len(user_text_lower) < 30:
        return {
            "action": "end_chat",
            "message": "¡Perfecto! Fue un placer ayudarte. Si necesitas algo más en el futuro, aquí estaré. ¡Que tengas un excelente día! 😊"
        }

    # Domain shortcut: only if we already have NIF
    if session.get("domain") and nif_value:
        existing_domain = session.get("domain")
        if existing_domain in _ROUTES_CONFIG["domains"] and _ROUTES_CONFIG["domains"][existing_domain].get("enabled", True):
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

    # Convert history tuples to Message objects to prevent template injection
    history_messages = []
    for role, text in history:
        if role == "human":
            history_messages.append(HumanMessage(content=text))
        elif role == "ai":
            history_messages.append(AIMessage(content=text))
        else:
            history_messages.append(HumanMessage(content=text))

    active_domains_map = {
        k: v.get("receptionist_label", k.capitalize())
        for k, v in _ROUTES_CONFIG["domains"].items()
        if v.get("classifier") and v.get("enabled", True)
    }
    available_domains_str = ", ".join(active_domains_map.values())

    greeting_instruction = ""
    if is_first_interaction:
        greeting_instruction = (
            "Esta es la PRIMERA interacción. "
            "SI el usuario solo dice 'hola' o similar, preséntate brevemente como Sofía de ZOA Seguros y pregunta en qué puedes ayudar. "
            "PERO SI el usuario ya dice lo que quiere (ej: 'quiero renovar', 'tuve un accidente'), NO saludes ni preguntes '¿en qué ayudo?'. "
            "Ve DIRECTAMENTE a pedir el NIF si falta o a clasificar si ya tienes todo."
        )
    else:
        greeting_instruction = "Esta NO es la primera interacción. NO te vuelvas a presentar. Ve directo al grano."

    consultation_context = ""
    if consultation_completed:
        consultation_context = "\n\n**IMPORTANTE**: La consulta anterior del usuario fue completada exitosamente. Si el usuario tiene una NUEVA consulta diferente, clasifícala normalmente. Si el usuario agradece o despide, responde amablemente y confirma que finalizas la atención."

    # Build NIF status for the prompt
    if nif_value:
        nif_status = f"El NIF del cliente ya está disponible: {nif_value}. No necesitas pedirlo."
    else:
        nif_status = "El NIF del cliente NO está disponible. Necesitarás pedirlo antes de poder redirigir a un especialista."

    # Get prompt based on channel, filtered to active domains/specialists
    channel = payload.get("channel", "whatsapp")
    system_prompt_template = get_prompt(channel, _ACTIVE_DOMAINS, _ACTIVE_SPECIALISTS_BY_DOMAIN)

    # Format the system prompt manually so history messages (which may
    # contain JSON with curly braces from OCR) are never parsed as templates.
    formatted_system = system_prompt_template.format(
        available_domains=available_domains_str,
        greeting_instruction=greeting_instruction,
        consultation_context=consultation_context,
        nif_status=nif_status,
    )

    messages = [SystemMessage(content=formatted_system)]
    messages.extend(history_messages)
    messages.append(HumanMessage(content=f"Mensaje del cliente: {user_text}"))

    llm = get_llm()

    try:
        structured_llm = llm.with_structured_output(ReceptionistDecision, method="json_mode")
    except Exception:
        structured_llm = llm.with_structured_output(ReceptionistDecision)

    decision = safe_structured_invoke(
        structured_llm,
        messages,
        fallback_factory=lambda: ReceptionistDecision(
            domain=None,
            message="Disculpa, tuve un problema técnico. ¿Podrías repetir tu consulta?",
            confidence=0.0
        ),
        error_context="receptionist_decision"
    )

    # --- NIF extraction ---
    extracted_nif = ""
    # If the decision contains a NIF, use it
    if decision.nif:
        extracted_nif = decision.nif.strip().upper()
    
    # If not, try to extract it from the user text
    if not extracted_nif:
        extracted_nif = _extract_nif_from_text(user_text)

    # If NIF was found (either in decision or extracted from text)
    if extracted_nif:
        # If we didn't have a NIF before, or if the new NIF is different, update it
        if not nif_value or nif_value != extracted_nif:
            nif_value = extracted_nif
            memory_patch = _build_nif_memory_patch(nif_value)
    
    # --- Routing logic ---
    domain = decision.domain
    message = decision.message
    confidence = decision.confidence if decision.confidence is not None else 0.0

    if domain and domain in active_domains_map:
        if nif_value:
            # Both domain and NIF available -> route
            domain_config = _ROUTES_CONFIG["domains"][domain]
            classifier_agent = domain_config.get("classifier")
            if classifier_agent:
                # Merge patches to clear consultation_completed
                final_patch = memory_patch or {}
                if "global" not in final_patch:
                    final_patch["global"] = {}
                final_patch["global"]["consultation_completed"] = False

                result = {
                    "action": "route",
                    "next_agent": classifier_agent,
                    "domain": domain,
                    "message": None,
                    "memory": final_patch
                }
                return result
        else:
            # Domain detected but no NIF -> ask for NIF (don't route yet)
            if not message:
                message = "Para poder gestionar tu consulta, necesito tu NIF, DNI o NIE. ¿Podrías proporcionármelo?"
            
            final_patch = memory_patch or {}
            if "global" not in final_patch:
                final_patch["global"] = {}
            final_patch["global"]["consultation_completed"] = False
            
            result = {"action": "ask", "message": message, "memory": final_patch}
            return result

    # No domain detected (or unknown domain) -> ask for clarification
    if not message:
        # If NIF was just provided but no domain, acknowledge it
        if memory_patch and "nif" in memory_patch.get("global", {}):
            message = "Gracias, he recibido tu documento. ¿En qué puedo ayudarte hoy? ¿Necesitas abrir un siniestro, consultar una póliza o algo más?"
        else:
            message = f"Disculpa, no entendí bien. ¿Tu consulta es sobre {available_domains_str}?"

    final_patch = memory_patch or {}
    if "global" not in final_patch:
        final_patch["global"] = {}
    # Only clear if the user actually sent something that looks like an intent
    if len(user_text) > 2:
        final_patch["global"]["consultation_completed"] = False

    result = {"action": "ask", "message": message, "memory": final_patch}
    return result
