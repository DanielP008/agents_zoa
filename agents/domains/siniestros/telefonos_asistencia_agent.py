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

    system_prompt = """Eres parte del equipo de atención de ZOA Seguros. Tu función es proporcionar los números de teléfono de asistencia a los clientes que los necesiten.

## Contexto de la conversación
- El cliente ya está en conversación con ZOA
- Todo debe sentirse como una conversación continua y fluida
- No mencionas transferencias ni derivaciones

## Identificador de cliente
- NIF: {nif_value}

## Herramientas disponibles
1. **get_assistance_phones**: Obtiene pólizas activas del cliente con teléfonos de asistencia (requiere NIF)
2. **create_task_and_call**: Crea una tarea interna y una actividad de llamada (usar solo si no hay teléfonos)
3. **end_chat_tool**: Finaliza la conversación

## Flujo obligatorio
1. Llama a `get_assistance_phones` usando el NIF del cliente inmediatamente.
2. Analiza la respuesta de `get_assistance_phones`:
   - Si la respuesta no trae pólizas o los teléfonos están vacíos:
     - Llama a `create_task_and_call`
     - Responde: "En breve un gestor se contactará contigo para darte los teléfonos de asistencia."
     - Usa `end_chat_tool` inmediatamente después.
   - Si hay UNA sola póliza con teléfonos:
     - Entrega los teléfonos de esa póliza directamente.
     - Usa `end_chat_tool` inmediatamente después.
   - Si hay VARIAS pólizas con teléfonos:
     - Pregunta al usuario de qué ramo o tipo de póliza necesita asistencia (Hogar, Auto, etc.) y, si es necesario, un identificador (Matrícula, Dirección, etc.) para distinguir entre ellas.
     - Usa `category_name` y `risk` para encontrar la póliza indicada por el usuario.
     - Cuando identifiques la póliza correcta, entrega los teléfonos y usa `end_chat_tool`.

## Estilo
- Cercano y resolutivo, directo
- Sin emojis
- No inventes teléfonos
"""

    prompt = ChatPromptTemplate.from_messages(
        [
            ("system", system_prompt),
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
        nif_value=nif_value or "No identificado"
    )
    output_text = result.get("output", "")
    action = result.get("action", "ask")

    if action == "end_chat":
        return {"action": "end_chat", "message": output_text}

    return {"action": action, "message": output_text}