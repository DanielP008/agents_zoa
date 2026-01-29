import re

from core.agent_factory import create_langchain_agent, run_langchain_agent
from core.memory_schema import get_global_history
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.tools import tool
from agents.llm import get_llm
from tools.end_chat_tool import end_chat_tool
from tools.ERP_client import get_assistance_phones_from_erp
from tools.zoa_client import create_task_with_activity

def telefonos_asistencia_agent(payload: dict) -> dict:
    user_text = payload.get("mensaje", "")
    session = payload.get("session", {})
    memory = session.get("agent_memory", {})
    history = get_global_history(memory)
    company_id = payload.get("phone_number_id") or session.get("company_id", "")
    wa_id = payload.get("wa_id")
    global_mem = memory.get("global", {})
    nif_value = global_mem.get("nif")

    @tool
    def get_assistance_phones(nif: str) -> dict:
        """Obtiene las pólizas activas del cliente con sus teléfonos de asistencia."""
        final_nif = nif_value or "00000000T"
        return get_assistance_phones_from_erp(nif=final_nif, company_id=company_id)

    @tool
    def create_task_and_call(task_description: str, client_nif: str) -> dict:
        """Crea una tarea interna con una actividad de llamada en ZOA (todo en una sola llamada)."""
        return create_task_with_activity(
            task_description=task_description,
            client_nif=client_nif,
            company_id=company_id,
            wa_id=wa_id,
            activity_type="call"
        )

    system_prompt = (
        """<rol>
Eres parte del equipo de atención de ZOA Seguros. Tu función es proporcionar los números de teléfono de asistencia a los clientes que necesitan ayuda urgente.
</rol>

<contexto>
- El cliente necesita asistencia en carretera, auxilio mecánico o emergencias del hogar
- Tienes acceso al historial de conversación
- Puedes buscar información del cliente en el sistema usando su NIF (si está identificado)
- ZOA opera en España
</contexto>

<variables_actuales>
NIF_actual: {nif}
</variables_actuales>

<herramientas>
1. get_assistance_phones(nif): Obtiene los teléfonos de asistencia asociados al cliente.
2. create_task_and_call(task_description, client_nif): Crea tarea y llamada si no encontramos teléfonos.
3. end_chat_tool(): Finaliza la conversación.
</herramientas>

<flujo_de_atencion>
1. IDENTIFICAR AL CLIENTE Y PÓLIZAS:
   - Llama a get_assistance_phones inmediatamente con el NIF actual.
   
2. ANALIZAR RESPUESTA:
   - ¿No hay pólizas/teléfonos? -> Usa create_task_and_call. Informa al cliente que un gestor le llamará enseguida. Cierra con end_chat_tool.
   - ¿Hay UNA póliza? -> Da los teléfonos de esa póliza. Cierra con end_chat_tool.
   - ¿Hay VARIAS pólizas? -> Pregunta al cliente cuál necesita (Auto, Hogar...). Cuando identifiques la correcta, da los números y cierra.

3. EMERGENCIA ACTIVA:
   - Sé muy directo y rápido.
   - Prioriza dar el número.

4. SI NO ENCUENTRAS DATOS:
   - No digas "error técnico".
   - Di: "Voy a pedir que un compañero te llame ahora mismo para darte el número correcto".
   - Usa create_task_and_call.
</flujo_de_atencion>

<personalidad>
- Cercano y resolutivo
- Directo al grano
- No usas emojis
- No usas frases robóticas
</personalidad>

<restricciones>
- Solo proporcionas teléfonos de asistencia.
- NUNCA inventes números.
- NUNCA menciones "transferencias" o "agentes".
- USA end_chat_tool cuando el cliente tenga el número o se haya creado la tarea de llamada.
</restricciones>"""
    )
    
    formatted_system_prompt = system_prompt.format(
        nif=nif_value or "NO_IDENTIFICADO"
    )

    prompt = ChatPromptTemplate.from_messages(
        [
            ("system", formatted_system_prompt),
            *history,
            ("human", "{user_text}"),
        ]
    )

    llm = get_llm()
    tools = [get_assistance_phones, create_task_and_call, end_chat_tool]
    executor = create_langchain_agent(llm, tools, prompt)

    result = run_langchain_agent(
        executor,
        user_text,
    )
    output_text = result.get("output", "")
    action = result.get("action", "ask")

    if action == "end_chat":
        return {"action": "end_chat", "message": output_text}

    return {"action": action, "message": output_text}
