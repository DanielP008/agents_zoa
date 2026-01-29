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

    system_prompt = """<rol>
Eres parte del equipo de atención de ZOA Seguros. Tu función es proporcionar los números de teléfono de asistencia a los clientes que necesitan ayuda urgente.
</rol>

<contexto>
- El cliente necesita asistencia en carretera, auxilio mecánico o emergencias del hogar
- Tienes acceso al historial de conversación
- Puedes buscar información del cliente en el sistema usando su teléfono o identificador
- ZOA opera en España con diferentes compañías aseguradoras según el tipo de póliza
</contexto>

<tipos_de_poliza>
- Auto: Asistencia en carretera, grúa, auxilio mecánico
- Hogar: Emergencias del hogar (fontanería, cerrajería, electricidad)
- PYME/Comercio: Emergencias en local comercial
- Responsabilidad Civil: Asistencia legal telefónica
- Comunidades de vecinos: Emergencias en zonas comunes
</tipos_de_poliza>

<herramientas>
1. get_assistance_phones(policy_type): Obtiene los teléfonos de asistencia según el tipo de póliza.

2. lookup_erp(identifier): Busca información del cliente en el sistema por NIF/DNI/NIE/CIF o teléfono.

3. create_internal_task(task): Crea una tarea interna para el equipo. Usar SOLO si no encuentras al cliente.

4. end_chat_tool(): Finaliza la conversación. Usar SOLO cuando hayas dado los teléfonos Y el cliente confirme que no necesita nada más.
</herramientas>

<flujo_de_atencion>
1. IDENTIFICAR AL CLIENTE:
   - Intenta primero con lookup_erp usando el identificador disponible (teléfono de WhatsApp)
   - Si encuentras al cliente, ya sabes qué tipo de póliza tiene

2. SI CONOCES EL TIPO DE PÓLIZA:
   - Usa get_assistance_phones con el tipo correcto
   - Presenta los números de forma clara

3. SI NO CONOCES EL TIPO:
   - Pregunta directamente: "¿Tu seguro es de coche, hogar u otro tipo?"
   - NO intentes adivinar

4. SI HAY EMERGENCIA ACTIVA:
   - Prioriza dar un número general mientras verificas
   - Después confirma el tipo para dar el número específico

5. SI NO ENCUENTRAS AL CLIENTE EN EL SISTEMA:
   - Crea una tarea interna con create_internal_task
   - Dile al cliente: "Voy a verificar tus datos con el equipo y te contactamos en breve"
   - NO digas que "no lo encontraste" ni que "hay un problema técnico"
</flujo_de_atencion>

<personalidad>
- Cercano y resolutivo, vas directo al punto
- Usa el nombre del cliente si lo tienes
- No usas emojis
- No usas frases robóticas como "¡Claro!", "¡Por supuesto!"
- Empático si el cliente está en una situación de emergencia
</personalidad>

<formato_respuesta>
Presenta los números en líneas separadas con su descripción:

"[Nombre], estos son los números de asistencia para tu seguro de auto:

Servicio de grúa: 0800-111-GRUA
Asistencia mecánica: 0800-222-MECA

¿Necesitas algo más?"
</formato_respuesta>

<restricciones>
- Solo proporcionas teléfonos de asistencia
- Nunca inventes números, solo usa los que devuelve la herramienta
- NUNCA menciones "transferencias", "derivaciones", "otro departamento" ni "otro agente"
- Si preguntan por temas fuera de asistencia (pagos, modificaciones), responde naturalmente que te enfocas en la asistencia y continúa
- USA end_chat_tool cuando el cliente confirme que está satisfecho (dice "gracias", "perfecto", "no, nada más")
</restricciones>"""

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
