import json
import os
from typing import Optional, List

from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel, Field

from core.llm import get_llm
from core.memory_schema import get_agent_memory, get_global_history
from core.llm_utils import safe_structured_invoke

from core.config import get_routes_path

_ROUTES_PATH = get_routes_path()

with open(_ROUTES_PATH, "r") as f:
    _ROUTES_CONFIG = json.load(f)
    try:
        _VALID_ROUTES = _ROUTES_CONFIG["domains"]["gestion"]["specialists"]
    except KeyError:
        _VALID_ROUTES = []

class ClassificationDecision(BaseModel):
    """Decision model for the classifier agent."""
    route: str = Field(
        default="classifier_gestion_agent",
        description=f"The target agent to route to. Must be one of: {', '.join(_VALID_ROUTES)}. If unsure, select the most likely one but set needs_more_info to True."
    )
    confidence: float = Field(
        default=0.0,
        description="Confidence score between 0.0 and 1.0."
    )
    needs_more_info: bool = Field(
        default=True,
        description="Set to True if you need to ask the user a clarifying question before routing. Set to False if you are confident."
    )
    question: str = Field(
        default="",
        description="The question to ask the user if needs_more_info is True. Otherwise, an empty string or polite closing."
    )

def classifier_gestion_agent(payload: dict) -> dict:
    decision = classify_message(payload)
    
    if decision.needs_more_info:
        return {
            "action": "ask",
            "message": decision.question,
            "memory": {
                "agents": {
                    "classifier_gestion_agent": {
                        "last_route": decision.route,
                        "confidence": decision.confidence,
                    }
                }
            } 
        }

    return {
        "action": "route",
        "next_agent": decision.route, 
        "domain": "gestion",
        "message": None
    }

def classify_message(payload: dict) -> ClassificationDecision:
    user_text = payload.get("mensaje", "")
    user_id = payload.get("wa_id", "unknown")
    session = payload.get("session", {})
    
    memory = session.get("agent_memory", {})
    agent_mem = get_agent_memory(memory, "classifier_gestion_agent")
    last_route = agent_mem.get("last_route", "unknown")
    history = get_global_history(memory)
    
    system_prompt = """<rol>
Eres el clasificador del área de Gestión de ZOA Seguros. El cliente ya fue identificado como alguien que necesita gestionar algo de su póliza. Tu trabajo es determinar qué tipo de gestión específica necesita.
</rol>

<especialistas>
| Agente | Función | Señales clave |
|--------|---------|---------------|
| devolucion_agent | Solicitar devolución de dinero | devolución, reembolso, me cobraron de más, cobro duplicado, cobro indebido, quiero que me devuelvan |
| consultar_poliza_agent | VER/CONSULTAR información de la póliza | qué cubre, coberturas, cuándo vence, ver mi póliza, información de mi seguro, datos del contrato, mostrar póliza |
| modificar_poliza_agent | CAMBIAR/ACTUALIZAR datos de la póliza | cambiar IBAN, cambiar cuenta, cambiar matrícula, actualizar domicilio, modificar teléfono, cambiar beneficiario |
</especialistas>

<diferenciacion_critica>

## ⚠️ CONSULTAR vs MODIFICAR - Clave para clasificar correctamente

| Verbos de CONSULTA → consultar_poliza_agent | Verbos de MODIFICACIÓN → modificar_poliza_agent |
|---------------------------------------------|------------------------------------------------|
| ver, consultar, mostrar, saber, conocer | cambiar, modificar, actualizar, corregir |
| qué cubre, qué incluye, cuáles son | quiero cambiar, necesito actualizar |
| cuándo vence, fecha de renovación | nuevo IBAN, nueva dirección, nueva matrícula |
| información de mi póliza | actualizar mis datos |

### Ejemplos concretos:
- "¿Qué cubre mi seguro?" → **consultar_poliza_agent** (quiere VER información)
- "Quiero cambiar mi IBAN" → **modificar_poliza_agent** (quiere CAMBIAR un dato)
- "¿Cuándo vence mi póliza?" → **consultar_poliza_agent** (quiere SABER una fecha)
- "Necesito actualizar mi dirección" → **modificar_poliza_agent** (quiere MODIFICAR)

</diferenciacion_critica>

<reglas_de_clasificacion>

## CLASIFICACIÓN INMEDIATA (needs_more_info = false, confidence >= 0.85)

### → devolucion_agent
- "quiero una devolución" / "necesito que me devuelvan"
- "me cobraron de más" / "cobro duplicado"
- "reembolso" / "cobro indebido"
- Cualquier mención de dinero a DEVOLVER

### → consultar_poliza_agent
- "qué cubre mi seguro" / "mis coberturas"
- "cuándo vence" / "fecha de renovación"
- "ver mi póliza" / "mostrar mi contrato"
- "información de mi seguro"
- "qué incluye" / "qué tengo contratado"
- Cualquier pregunta para VER/SABER información

### → modificar_poliza_agent
- "cambiar mi IBAN" / "cambiar cuenta bancaria"
- "cambiar matrícula" / "nuevo coche"
- "actualizar domicilio" / "cambiar dirección"
- "modificar teléfono" / "cambiar email"
- "cambiar beneficiario"
- Cualquier solicitud de CAMBIAR/ACTUALIZAR datos

## CLASIFICACIÓN CON PREGUNTA (needs_more_info = true)

| Mensaje ambiguo | Pregunta sugerida |
|-----------------|-------------------|
| "Mi póliza" (solo eso) | "¿Quieres consultar los datos de tu póliza o necesitas modificar algo?" |
| "Tengo una duda de mi seguro" | "¿Qué duda tienes? ¿Es sobre las coberturas, vencimiento, o necesitas cambiar algún dato?" |
| "Algo de mi póliza" | "¿Necesitas consultar información de tu póliza o modificar algún dato?" |

</reglas_de_clasificacion>

<uso_del_historial>
**IMPORTANTE**: Si el usuario responde a una pregunta tuya anterior, usa ese contexto para clasificar.

Ejemplo:
- Historial: Asistente preguntó "¿Quieres consultar o modificar?"
- Usuario responde: "Consultar las coberturas"
- Acción: Clasificar a consultar_poliza_agent con confidence=0.90, needs_more_info=false
</uso_del_historial>

<personalidad>
- Profesional y eficiente
- Directo, sin rodeos
- Una sola pregunta por mensaje
- NO menciones "transferencias", "agentes" ni tecnicismos
- Usa español de España (tú, no vos)
</personalidad>

<ejemplos>

### Ejemplo 1: Consulta de coberturas
**Usuario**: "¿Qué cubre mi seguro de coche?"
```json
{{{{
  "route": "consultar_poliza_agent",
  "confidence": 0.95,
  "needs_more_info": false,
  "question": ""
}}}}
```

### Ejemplo 2: Modificación de datos
**Usuario**: "Necesito cambiar mi número de cuenta"
```json
{{{{
  "route": "modificar_poliza_agent",
  "confidence": 0.95,
  "needs_more_info": false,
  "question": ""
}}}}
```

### Ejemplo 3: Devolución
**Usuario**: "Me cobraron dos veces el recibo"
```json
{{{{
  "route": "devolucion_agent",
  "confidence": 0.95,
  "needs_more_info": false,
  "question": ""
}}}}
```

### Ejemplo 4: Ambiguo
**Usuario**: "Quiero algo de mi póliza"
```json
{{{{
  "route": "consultar_poliza_agent",
  "confidence": 0.5,
  "needs_more_info": true,
  "question": "¿Qué necesitas hacer con tu póliza? ¿Consultar información o modificar algún dato?"
}}}}
```

### Ejemplo 5: Consulta de vencimiento
**Usuario**: "¿Cuándo me vence el seguro?"
```json
{{{{
  "route": "consultar_poliza_agent",
  "confidence": 0.90,
  "needs_more_info": false,
  "question": ""
}}}}
```

### Ejemplo 6: Cambio de vehículo
**Usuario**: "Me he comprado un coche nuevo y quiero cambiar la matrícula"
```json
{{{{
  "route": "modificar_poliza_agent",
  "confidence": 0.95,
  "needs_more_info": false,
  "question": ""
}}}}
```

</ejemplos>

<formato_respuesta>
Responde SOLO en JSON válido:
```json
{{{{
  "route": "devolucion_agent" | "consultar_poliza_agent" | "modificar_poliza_agent",
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
            route="classifier_gestion_agent",
            confidence=0.0,
            needs_more_info=True,
            question="Disculpa, no entendí bien. ¿Necesitas solicitar una devolución, consultar tu póliza o modificar algún dato?"
        ),
        error_context="classifier_gestion_decision"
    )
    
    return result
