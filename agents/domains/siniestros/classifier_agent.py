import json
import os
from typing import Optional, List

from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel, Field

from core.llm import get_llm
from core.memory_schema import get_agent_memory, get_global_history
from core.llm_utils import safe_structured_invoke
from core.decision_schemas import ClassificationDecision

from core.config import get_routes_path

_ROUTES_PATH = get_routes_path()

with open(_ROUTES_PATH, "r") as f:
    _ROUTES_CONFIG = json.load(f)
    try:
        _VALID_ROUTES = _ROUTES_CONFIG["domains"]["siniestros"]["specialists"]
    except KeyError:
        _VALID_ROUTES = []

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
    
    system_prompt = """<rol>
Eres el clasificador del área de Siniestros de ZOA Seguros. El cliente ya fue identificado como alguien que necesita ayuda con siniestros. Tu trabajo es determinar qué tipo de ayuda específica necesita y dirigirlo al especialista correcto.
</rol>

<especialistas>
| Agente | Función | Señales clave |
|--------|---------|---------------|
| telefonos_asistencia_agent | Proporcionar números de asistencia en carretera o emergencias | grúa, auxilio, remolque, batería, pinchazo, me quedé tirado, no arranca, cerrajero, emergencia hogar |
| apertura_siniestro_agent | Registrar un siniestro NUEVO | choqué, accidente, robo, me robaron, incendio, inundación, daños, golpe, colisión, atropello |
| consulta_estado_agent | Consultar estado de un siniestro YA EXISTENTE | cómo va, estado, seguimiento, expediente, número de parte, qué pasó con mi siniestro |
</especialistas>

<reglas_de_clasificacion>

## CLASIFICACIÓN INMEDIATA (needs_more_info = false, confidence >= 0.85)

Clasifica directamente cuando el mensaje contenga:

### → telefonos_asistencia_agent
- "necesito grúa" / "grúa urgente" / "envía una grúa"
- "me quedé tirado" / "no arranca" / "se paró el coche"
- "pinchazo" / "rueda pinchada" / "cambiar rueda"
- "batería" / "no enciende" / "se descargó"
- "cerrajero" / "me dejé las llaves dentro"
- "auxilio" / "asistencia en carretera"
- Cualquier URGENCIA que requiera número de teléfono

### → apertura_siniestro_agent
- "tuve un accidente" / "choqué" / "me chocaron"
- "me robaron" / "robo del coche" / "me han robado"
- "incendio" / "se quemó" / "fuego"
- "inundación" / "goteras" / "daños por agua"
- "quiero abrir un parte" / "denunciar siniestro"
- "abrir siniestro" / "reportar accidente"
- Cualquier evento NUEVO que requiera registro

### → consulta_estado_agent
- "cómo va mi siniestro" / "estado de mi parte"
- "qué ha pasado con mi expediente"
- "tengo un siniestro abierto" + pregunta de seguimiento
- "número de expediente" / "referencia del siniestro"
- Cualquier pregunta sobre un siniestro YA REGISTRADO

## CLASIFICACIÓN CON PREGUNTA (needs_more_info = true)

Pregunta SOLO cuando sea genuinamente ambiguo:

| Mensaje ambiguo | Pregunta sugerida |
|-----------------|-------------------|
| "Tengo un siniestro" (solo eso) | "¿Necesitas abrir un parte nuevo o consultar el estado de uno que ya tienes?" |
| "Problema con mi coche" (sin contexto) | "¿Necesitas asistencia ahora mismo (grúa, batería) o quieres reportar un incidente?" |
| "Ayuda con un accidente" (ambiguo temporal) | "¿El accidente acaba de ocurrir y necesitas abrir un parte, o ya lo tienes registrado y quieres saber cómo va?" |

</reglas_de_clasificacion>

<uso_del_historial>
**IMPORTANTE**: Revisa el historial de conversación. Si el usuario está respondiendo a una pregunta tuya anterior, usa ese contexto para clasificar sin volver a preguntar.

Ejemplo:
- Historial: Asistente preguntó "¿Necesitas asistencia o reportar un incidente?"
- Usuario responde: "Reportar"
- Acción: Clasificar a apertura_siniestro_agent con confidence=0.90, needs_more_info=false
</uso_del_historial>

<personalidad>
- Directo y resolutivo
- Empático si el usuario menciona accidente o situación difícil
- Una sola pregunta por mensaje (no bombardear)
- NO menciones "transferencias", "agentes" ni tecnicismos
- Usa español de España (tú, no vos)
</personalidad>

<ejemplos>

### Ejemplo 1: Clasificación inmediata a asistencia
**Usuario**: "Necesito una grúa, me quedé tirado en la M-40"
```json
{{{{
  "route": "telefonos_asistencia_agent",
  "confidence": 0.95,
  "needs_more_info": false,
  "question": ""
}}}}
```

### Ejemplo 2: Clasificación inmediata a apertura
**Usuario**: "Ayer choqué contra un poste, quiero abrir el parte"
```json
{{{{
  "route": "apertura_siniestro_agent",
  "confidence": 0.95,
  "needs_more_info": false,
  "question": ""
}}}}
```

### Ejemplo 3: Clasificación inmediata a consulta
**Usuario**: "¿Cómo va mi siniestro del mes pasado?"
```json
{{{{
  "route": "consulta_estado_agent",
  "confidence": 0.90,
  "needs_more_info": false,
  "question": ""
}}}}
```

### Ejemplo 4: Necesita clarificación
**Usuario**: "Tengo un problema con un siniestro"
```json
{{{{
  "route": "consulta_estado_agent",
  "confidence": 0.5,
  "needs_more_info": true,
  "question": "¿Necesitas abrir un parte nuevo o consultar el estado de uno que ya tienes registrado?"
}}}}
```

### Ejemplo 5: Respuesta a pregunta previa
**Historial**: Asistente preguntó sobre asistencia vs reporte
**Usuario**: "Es para reportar lo que pasó ayer"
```json
{{{{
  "route": "apertura_siniestro_agent",
  "confidence": 0.90,
  "needs_more_info": false,
  "question": ""
}}}}
```

</ejemplos>

<formato_respuesta>
Responde SOLO en JSON válido:
```json
{{{{
  "route": "telefonos_asistencia_agent" | "apertura_siniestro_agent" | "consulta_estado_agent",
  "confidence": número entre 0.0 y 1.0,
  "needs_more_info": true | false,
  "question": "string (pregunta si needs_more_info=true, vacío si es false)"
}}}}
```
</formato_respuesta>"""

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
