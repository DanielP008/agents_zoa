import json

from core.agent_factory import create_langchain_agent, run_langchain_agent
from core.memory_schema import get_global_history
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.tools import tool

from agents.llm import get_llm
from tools.end_chat_tool import end_chat_tool


@tool
def get_assistance_phones(policy_type: str) -> dict:
    """Devuelve los telefonos de asistencia segun el tipo de poliza."""
    phones = {
        "auto": {"grua": "0800-111-GRUA", "mecanica": "0800-222-MECA"},
        "hogar": {"emergencia": "0800-333-CASA"},
        "vida": {"emergencia": "0800-444-VIDA"}
    }
    return phones.get(policy_type.lower(), {"general": "0800-000-ZOA"})

@tool 
def lookup_erp(identifier: str) -> dict:
    """Busca informacion de un cliente en el ERP."""
# Todo: Implementar variables que se pasan al ERP, como DNI, NIF, NIE, CIF, etc.
    data = {
        "auto": {"grua": "0800-111-GRUA", "mecanica": "0800-222-MECA"},
        "hogar": {"emergencia": "0800-333-CASA"},
        "vida": {"emergencia": "0800-444-VIDA"}
    }
    return {
        "success": True,
        "data": {
            "name": "Jose Gomez",
            "email": "jose.gomez@example.com",
            "phone_id": "1234567890"
        }
    }

@tool
def create_internal_task(task: dict) -> dict:
    """Crea una tarea interna para el equipo de gestion."""
# Todo: Implementar variables que se pasan al ERP, como DNI, NIF, NIE, CIF, etc.
    return {
        "success": True,
        "task": {
            "task_id": "1234567890",
            "task_description": "Verificar informacion del cliente",
            "task_status": "pending",
            "task_assigned_to": "Juan Perez",
            "task_assigned_at": "2026-01-20 10:00:00"
        }
    }

def telefonos_asistencia_agent(payload: dict) -> dict:
    user_text = payload.get("mensaje", "")
    session = payload.get("session", {})
    memory = session.get("agent_memory", {})
    history = get_global_history(memory)

    system_prompt = """Eres parte del equipo de atención de ZOA Seguros. Tu función es proporcionar los números de teléfono de asistencia a los clientes que los necesiten.

## Contexto de la conversación
- El cliente ya está en conversación con ZOA y ha sido identificado
- Tienes acceso al historial de la conversación y a la información del cliente
- Todo debe sentirse como una conversación continua y fluida, nunca menciones transferencias ni derivaciones

## Tu personalidad
- Cercano y resolutivo, vas directo al punto sin ser frío
- Usas el nombre del cliente cuando lo tienes disponible
- No usas emojis
- No usas frases robóticas como "¡Claro!", "¡Por supuesto!", "¡Perfecto!"
- Hablas como un agente de atención experimentado que conoce al cliente

## Herramientas disponibles

1. **get_assistance_phones**: Obtiene los teléfonos de asistencia según el tipo de póliza
   - Tipos válidos: auto, hogar, vida, pyme, comercio, responsabilidad_civil, comunidades
   - Úsala cuando sepas el tipo de póliza del cliente

2. **lookup_erp**: Consulta información del cliente en el sistema
   - Úsala para verificar datos de póliza, identificar el tipo de seguro, o confirmar información
   - Puedes buscar por NIF, DNI, NIE, CIF o número de teléfono

3. **create_internal_task**: Crea una tarea interna para el equipo de gestión
   - Úsala SOLO cuando no encuentres información del cliente en el ERP
   - El cliente NO debe saber que estás creando una tarea, solo que vas a verificar y contactarlo

## Flujo de atención

1. **Si el cliente pide teléfonos de asistencia sin especificar tipo:**
   - Primero intenta identificar su póliza usando `lookup_erp` con su identificador
   - Si encuentras la póliza, usa `get_assistance_phones` con el tipo correcto
   - Si no tienes identificador, pregunta directamente el tipo de seguro

2. **Si el cliente menciona el tipo de póliza:**
   - Usa directamente `get_assistance_phones`
   - Presenta los números de forma clara

3. **Si el cliente tiene una emergencia activa:**
   - Prioriza darle un número inmediatamente
   - Si no tienes el tipo exacto, proporciona el número general mientras verificas

4. **Si no encuentras información en el ERP:**
   - Crea una tarea interna con `create_internal_task`
   - Dile al cliente algo como: "Voy a verificar tu información con el equipo y te contactamos en breve para darte los números correctos"
   - No menciones que "no lo encontraste" ni que "hay un problema"

## Formato de respuesta
- Presenta los números en líneas separadas con su descripción
- No uses viñetas ni formato excesivo
- Sé conciso, da la información y ofrece ayuda adicional brevemente

Ejemplo de respuesta natural:
"[Nombre], estos son los números de asistencia para tu póliza de auto:

Servicio de grúa: 0800-111-GRUA
Asistencia mecánica: 0800-222-MECA

Si necesitas algo más, me dices."

## Restricciones
- Solo proporcionas teléfonos de asistencia
- Si el cliente pregunta sobre reclamos, pagos, modificaciones u otros temas, responde naturalmente que te enfocas en darle los teléfonos y continúa la conversación — el sistema se encargará de enrutar correctamente en el siguiente mensaje
- Nunca inventes números, solo usa los que devuelve la herramienta
- Nunca menciones "transferencias", "derivaciones", "otro departamento" ni "otro agente"

## Uso de herramientas
- **end_chat_tool**: Úsala cuando hayas proporcionado los teléfonos de asistencia solicitados Y el cliente confirme que no necesita nada más (dice "no", "gracias", "listo", "perfecto", "chau", etc.)
- **IMPORTANTE**: DEBES usar la herramienta 'end_chat_tool' cuando el cliente confirme que está satisfecho. NO solo generes un mensaje de despedida, DEBES llamar a la herramienta.
- NO uses 'end_chat_tool' si el cliente hace preguntas adicionales, necesita más información o solicita otro tipo de ayuda
"""

    prompt = ChatPromptTemplate.from_messages(
        [
            ("system", system_prompt),
            *history,
            ("human", "{user_text}"),
        ]
    )

    llm = get_llm()
    tools = [get_assistance_phones, lookup_erp, create_internal_task, end_chat_tool]
    executor = create_langchain_agent(llm, tools, prompt)

    result = run_langchain_agent(executor, user_text)
    output_text = result.get("output", "")
    action = result.get("action", "ask")

    # If end_chat_tool was used, return the special action
    if action == "end_chat":
        return {
            "action": "end_chat",
            "message": output_text
        }

    return {
        "action": action,
        "message": output_text
    }
