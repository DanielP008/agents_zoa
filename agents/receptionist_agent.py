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
from agents.receptionist_agent_prompts import get_prompt, DOMAIN_DATA

logger = logging.getLogger(__name__)

_ROUTES_PATH = get_routes_path()

def is_valid_nif(nif: str) -> bool:
    """Check if the provided NIF/DNI/NIE/CIF matches a valid Spanish format.
    
    Standard patterns:
    - DNI: 8 digits + 1 letter (e.g. 12345678A)
    - NIE: 1 letter (XYZ) + 7 digits + 1 letter (e.g. X1234567L)
    - CIF/Other: 1 letter + 7 digits + 1 letter/digit (e.g. B12345678)
    """
    if not nif:
        return False
    
    # Remove any spaces or dashes
    nif = nif.replace(" ", "").replace("-", "").upper()
    
    patterns = [
        r"^\d{8}[A-Z]$",        # DNI
        r"^[XYZ]\d{7}[A-Z]$",   # NIE
        r"^[A-Z]\d{7}[A-Z0-9]$" # CIF / Others
    ]
    
    for pattern in patterns:
        if re.match(pattern, nif):
            return True
    return False

def _extract_nif_from_text(text: str) -> str:
    if not text:
        return ""
    # We use the same patterns as is_valid_nif but with word boundaries for extraction
    patterns = [
        r"\b\d{8}[A-Z]\b",
        r"\b[XYZ]\d{7}[A-Z]\b",
        r"\b[A-Z]\d{7}[A-Z0-9]\b",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            val = match.group(0).upper()
            if is_valid_nif(val):
                return val
    return ""

def _build_nif_memory_patch(nif: str) -> dict:
    return {"global": {"nif": nif, "nif_lookup_failed": False}}

def receptionist_agent(payload: dict) -> dict:
    # Reload config to be dynamic
    with open(_ROUTES_PATH, "r") as f:
        routes_config = json.load(f)
    
    active_domains = [
        k for k, v in routes_config["domains"].items()
        if v.get("enabled", True) and v.get("classifier")
    ]
    active_specialists_by_domain = {
        domain: get_active_specialists(domain, routes_config)
        for domain in active_domains
    }

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
        if existing_domain in routes_config["domains"] and routes_config["domains"][existing_domain].get("enabled", True):
            domain_config = routes_config["domains"][existing_domain]
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

    active_domains_map = {}
    for k, v in routes_config["domains"].items():
        if not v.get("enabled", True) or not v.get("classifier"):
            continue
            
        active_specs = get_active_specialists(k, routes_config)
        if not active_specs:
            continue
            
        # Build description from specialist labels
        domain_data = DOMAIN_DATA.get(k, {})
        spec_services = domain_data.get("specialist_services", {})
        
        labels = []
        for spec in active_specs:
            if spec in spec_services:
                labels.append(spec_services[spec])
        
        if labels:
            desc = ", ".join(labels)
            label = v.get("receptionist_label", k.capitalize())
            active_domains_map[k] = f"{label} ({desc})"

    # Use double newline for clear separation in WhatsApp
    # We add a trailing newline to each item to force the LLM to respect it
    available_domains_str = "\n\n".join([f"• {label}" for label in active_domains_map.values()])

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
    system_prompt_template = get_prompt(channel, active_domains, active_specialists_by_domain)

    # Format the system prompt manually so history messages (which may
    # contain JSON with curly braces from OCR) are never parsed as templates.
    # We use a very explicit instruction in the available_domains placeholder
    formatted_system = system_prompt_template.format(
        available_domains="\n\n" + available_domains_str + "\n\n",
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

    # --- NIF extraction & validation ---
    extracted_nif = ""
    # If the decision contains a NIF, use it
    if decision.nif:
        extracted_nif = decision.nif.strip().replace(" ", "").replace("-", "").upper()
    
    # If not, try to extract it from the user text
    if not extracted_nif:
        extracted_nif = _extract_nif_from_text(user_text)

    # Validate the extracted NIF format
    if extracted_nif and not is_valid_nif(extracted_nif):
        logger.warning(f"[RECEPTIONIST] Invalid NIF format detected: {extracted_nif}. Ignoring it.")
        extracted_nif = ""
        # If the LLM thought it was valid but it wasn't, we override the message to ask again
        if channel == "call":
            decision.message = "Disculpa . . . No he podido leer bien tu DNI . . . ¿¿Podrías repetirlo completo incluyendo la letra??"
        else:
            decision.message = "Lo siento, el DNI/NIF que me has dado no parece tener un formato válido. ¿Podrías indicarlo completo incluyendo la letra?"
        decision.domain = None # Force to stay in receptionist until valid NIF is given
        decision.confidence = 0.0

    # If NIF was found and is valid
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
            domain_config = routes_config["domains"][domain]
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
            message = f"Gracias, he recibido tu documento. ¿En qué puedo ayudarte hoy?\n\n{available_domains_str}"
        else:
            message = f"Disculpa, no entendí bien. ¿Tu consulta es sobre alguna de estas áreas?\n\n{available_domains_str}"

    final_patch = memory_patch or {}
    if "global" not in final_patch:
        final_patch["global"] = {}
    # Only clear if the user actually sent something that looks like an intent
    if len(user_text) > 2:
        final_patch["global"]["consultation_completed"] = False

    result = {"action": "ask", "message": message, "memory": final_patch}
    return result
