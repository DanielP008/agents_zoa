import json
import re

from langchain_core.prompts import ChatPromptTemplate

from core.llm import get_llm
from core.memory_schema import get_global_history
from core.llm_utils import safe_structured_invoke
from core.config import get_routes_path
from core.decision_schemas import ReceptionistDecision
from agents.receptionist_agent_prompts import get_prompt

_ROUTES_PATH = get_routes_path()

with open(_ROUTES_PATH, "r") as f:
    _ROUTES_CONFIG = json.load(f)
    _VALID_DOMAINS = set(
        k for k, v in _ROUTES_CONFIG["domains"].items()
        if v.get("enabled", True)
    )

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

    active_domains_map = {
        k: v.get("receptionist_label", k.capitalize())
        for k, v in _ROUTES_CONFIG["domains"].items()
        if v.get("classifier") and v.get("enabled", True)
    }
    available_domains_str = ", ".join(active_domains_map.values())

    greeting_instruction = ""
    if is_first_interaction:
        greeting_instruction = "Esta es la PRIMERA interacción. Preséntate brevemente como Sofía de ZOA Seguros y pregunta en qué puedes ayudar."
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

    # Get prompt based on channel
    channel = payload.get("channel", "whatsapp")
    system_prompt = get_prompt(channel)

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
    except Exception:
        structured_llm = llm.with_structured_output(ReceptionistDecision)

    chain = prompt | structured_llm

    decision = safe_structured_invoke(
        chain,
        {
            "user_text": user_text,
            "available_domains": available_domains_str,
            "greeting_instruction": greeting_instruction,
            "consultation_context": consultation_context,
            "nif_status": nif_status,
        },
        fallback_factory=lambda: ReceptionistDecision(
            domain=None,
            message="Disculpa, tuve un problema técnico. ¿Podrías repetir tu consulta?",
            confidence=0.0
        ),
        error_context="receptionist_decision"
    )

    # --- NIF extraction ---
    extracted_nif = ""
    if decision.nif:
        extracted_nif = decision.nif.strip().upper()
    if not extracted_nif:
        extracted_nif = _extract_nif_from_text(user_text)

    if extracted_nif and not nif_value:
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
        message = f"Disculpa, no entendí bien. ¿Tu consulta es sobre {available_domains_str}?"

    final_patch = memory_patch or {}
    if "global" not in final_patch:
        final_patch["global"] = {}
    # Only clear if the user actually sent something that looks like an intent
    if len(user_text) > 2:
        final_patch["global"]["consultation_completed"] = False

    result = {"action": "ask", "message": message, "memory": final_patch}
    return result
