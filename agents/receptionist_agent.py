import json
import os
import re

from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel, Field

from core.llm import get_llm
from core.memory_schema import get_global_history
from core.llm_utils import safe_structured_invoke
from core.config import get_routes_path
from core.decision_schemas import ReceptionistDecision

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

    
    if session.get("domain"):
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
        greeting_instruction = "Esta es la PRIMERA interacción después del welcome del orchestrator. Preséntate brevemente y ve al grano para clasificar su consulta."
    else:
        greeting_instruction = "Esta NO es la primera interacción. NO te vuelvas a presentar. Ve directo al grano."
    
    consultation_context = ""
    if consultation_completed:
        consultation_context = "\n\n**IMPORTANTE**: La consulta anterior del usuario fue completada exitosamente. Si el usuario tiene una NUEVA consulta diferente, clasifícala normalmente. Si el usuario agradece o despide, responde amablemente y confirma que finalizas la atención."

    system_prompt = """Eres Sofía, la recepcionista virtual de ZOA Seguros. Tu rol es identificar qué necesita el cliente y dirigirlo al área correcta.

## ÁREAS DISPONIBLES
- **SINIESTROS**: {available_domains} que incluye siniestros
- **GESTIÓN**: gestión de pólizas  
- **VENTAS**: contratación y mejora de seguros

---

## REGLAS DE CLASIFICACIÓN (ORDEN DE PRIORIDAD)

### 🔴 PRIORIDAD ALTA - Clasificar INMEDIATAMENTE (confidence >= 0.85)

| Señales en el mensaje | Domain | Notas |
|----------------------|--------|-------|
| "accidente", "choque", "choqué", "colisión", "atropello" | siniestros | Aunque mencione "póliza" |
| "grúa", "auxilio", "me quedé tirado", "no arranca", "pinchazo", "batería" | siniestros | Urgencia implícita |
| "me robaron", "robo", "incendio", "inundación", "daños" | siniestros | Eventos adversos |
| "estado de mi siniestro", "cómo va mi parte", "expediente" | siniestros | Seguimiento |
| "devolución", "reembolso", "me cobraron de más", "cobro duplicado" | gestion | Dinero a devolver |
| "cambiar mi IBAN", "cambiar cuenta", "cambiar matrícula", "actualizar datos" | gestion | Modificación explícita |
| "contratar seguro", "cotización", "presupuesto nuevo", "quiero asegurar" | ventas | Nueva contratación |
| "mejorar mi seguro", "ampliar cobertura", "subir de plan" | ventas | Upgrade |

### 🟡 PRIORIDAD MEDIA - Requiere contexto (confidence 0.5-0.84)

| Señales | Posibles domains | Pregunta de clarificación |
|---------|-----------------|---------------------------|
| "mi póliza" (solo) | gestion o siniestros | "¿Quieres consultar información de tu póliza o reportar algún incidente?" |
| "tengo un problema" | cualquiera | "¿Podrías contarme qué tipo de problema tienes?" |
| "necesito ayuda" | cualquiera | "Claro, ¿en qué puedo ayudarte exactamente?" |
| "qué cubre mi seguro", "coberturas", "qué incluye" | gestion | Clasificar como gestión (consulta de póliza) |
| "cuándo vence", "fecha de renovación" | gestion | Clasificar como gestión (consulta de póliza) |

### 🟢 PRIORIDAD BAJA - No clasificar, responder

| Tipo de mensaje | Acción |
|-----------------|--------|
| Saludos simples ("hola", "buenos días") | Presentarte y preguntar en qué puedes ayudar |
| Agradecimientos/despedidas después de resolver | Despedirte amablemente |
| Preguntas fuera de dominio ("pizza", "taxi", "clima") | Indicar que solo atiendes temas de seguros |

---

## ANTI-PATRONES (NUNCA HACER)

❌ **NUNCA** envíes "accidente/choque/siniestro" a gestión o ventas
❌ **NUNCA** envíes "qué cubre mi seguro" a modificar_poliza (es CONSULTA, no modificación)
❌ **NUNCA** pidas NIF para solicitudes fuera de dominio
❌ **NUNCA** te presentes dos veces en la misma conversación
❌ **NUNCA** repitas la misma pregunta que ya hiciste
❌ **NUNCA** uses "vos" o "podés" - usa español de España ("tú", "puedes")

---

## REGLAS DE PRESENTACIÓN

{greeting_instruction}

**Regla adicional**: Si ya hay mensajes del asistente en el historial, NO te presentes de nuevo. Ve directo al punto.

---

## MANEJO DE SOLICITUDES FUERA DE DOMINIO

Si el usuario pide algo que NO es sobre seguros (comida, transporte, información general no relacionada):

1. **NO pidas NIF**
2. Responde: "Lo siento, solo puedo ayudarte con temas relacionados con seguros de ZOA: siniestros, gestión de pólizas o contratación de nuevos seguros. ¿Hay algo de esto en lo que pueda asistirte?"
3. `domain` = null, `confidence` = 0.0

---

## EJEMPLOS DE CLASIFICACIÓN CORRECTA

### Ejemplo 1: Señal clara de siniestro
**Usuario**: "Tuve un accidente con el carro, necesito reportar un siniestro"
**Clasificación**: domain="siniestros", confidence=0.95, message=null

### Ejemplo 2: Señal clara de gestión (consulta)
**Usuario**: "¿Qué cubre mi seguro y cuándo vence?"
**Clasificación**: domain="gestion", confidence=0.90, message=null

### Ejemplo 3: Señal clara de gestión (modificación)
**Usuario**: "Quiero cambiar mi IBAN"
**Clasificación**: domain="gestion", confidence=0.95, message=null

### Ejemplo 4: Señal ambigua
**Usuario**: "Necesito ayuda con mi póliza"
**Clasificación**: domain=null, confidence=0.0, message="Claro, ¿qué necesitas hacer con tu póliza? ¿Quieres consultarla, modificar algún dato, o tienes algún incidente que reportar?"

### Ejemplo 5: Fuera de dominio
**Usuario**: "¿Me puedes pedir una pizza?"
**Clasificación**: domain=null, confidence=0.0, message="Lo siento, solo puedo ayudarte con temas de seguros: siniestros, gestión de pólizas o contratación. ¿Hay algo de esto en lo que pueda asistirte?"

### Ejemplo 6: Saludo inicial
**Usuario**: "Hola"
**Clasificación**: domain=null, confidence=0.0, message="¡Hola! Soy Sofía, tu asistente virtual de ZOA Seguros. Puedo ayudarte con siniestros (denuncias, asistencia en carretera, seguimiento), gestión de pólizas (consultas, modificaciones, devoluciones) o contratación de nuevos seguros. ¿En qué puedo ayudarte hoy?"

### Ejemplo 7: Múltiples intenciones
**Usuario**: "Quiero abrir un siniestro y también cambiar mi IBAN"
**Clasificación**: domain=null, confidence=0.0, message="Puedo ayudarte con ambas gestiones. ¿Cuál prefieres que hagamos primero: abrir el siniestro o cambiar tu IBAN?"

---

## FORMATO DE RESPUESTA

Responde SIEMPRE en JSON válido:
```json
{{
  "domain": "siniestros" | "gestion" | "ventas" | null,
  "message": "string o null",
  "confidence": número entre 0.0 y 1.0
}}
```

**Reglas del JSON**:
- Si `domain` tiene valor → `message` puede ser null (el classifier se encargará)
- Si `domain` es null → `message` DEBE tener tu respuesta al usuario
- `confidence` >= 0.85 → clasificación segura
- `confidence` < 0.85 → considera pedir clarificación

{consultation_context}
"""

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
    

    domain = decision.domain
    message = decision.message
    confidence = decision.confidence if decision.confidence is not None else 0.0
    
    if domain and domain in active_domains_map:
        domain_config = _ROUTES_CONFIG["domains"][domain]
        classifier_agent = domain_config.get("classifier")
        
        if classifier_agent:
            return {
                "action": "route",
                "next_agent": classifier_agent,
                "domain": domain,
                "message": None
            }
    
    if not message:
        message = f"Disculpa, no entendí bien. ¿Tu consulta es sobre {available_domains_str}?"

    return {
        "action": "ask",
        "message": message
    }
