import re

from core.agent_factory import create_langchain_agent, run_langchain_agent
from core.memory_schema import get_global_history
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.tools import tool
from core.llm import get_llm
from tools.communication.end_chat_tool import end_chat_tool
from tools.zoa.tasks import create_task_activity_tool
from tools.erp.assistance_tools import get_assistance_phones_tool_factory

def telefonos_asistencia_agent(payload: dict) -> dict:
    user_text = payload.get("mensaje", "")
    session = payload.get("session", {})
    memory = session.get("agent_memory", {})
    history = get_global_history(memory)
    company_id = payload.get("phone_number_id") or session.get("company_id", "")
    wa_id = payload.get("wa_id")
    global_mem = memory.get("global", {})
    nif_value = global_mem.get("nif")

    get_assistance_phones = get_assistance_phones_tool_factory(nif_value, company_id)

    system_prompt = (
        """<rol>
    Eres parte del equipo de atención de ZOA Seguros. Tu función es proporcionar los números de teléfono de asistencia a los clientes que necesitan ayuda urgente.
    </rol>

    <contexto>
    - El cliente necesita asistencia en carretera, auxilio mecánico o emergencias del hogar
    - Tienes acceso al historial de conversación
    - Puedes buscar información del cliente en el sistema usando su NIF (si está identificado) y el Ramo del seguro.
    - ZOA opera en España
    </contexto>

    <variables_actuales>
    NIF_actual: {nif}
    Company_ID: {company_id}
    </variables_actuales>
    
    <ramos_validos>
    - AUTO
    - HOGAR
    - PYME
    - COMERCIOS
    - TRANSPORTES
    - COMUNIDADES
    - ACCIDENTES
    - RC (Responsabilidad Civil)
    </ramos_validos>

    <herramientas>
    1. get_assistance_phones(nif, ramo): Obtiene los teléfonos de asistencia asociados al cliente para un ramo específico. Requiere NIF y RAMO.
    2. create_task_activity_tool(json_string): Crea una tarea y/o actividad en el CRM.
       - Usar SI NO obtenemos teléfonos de la API (get_assistance_phones devuelve lista vacía o error).
       - Usar SI NO encontramos datos del cliente.
       - Parámetros clave para el JSON:
         - company_id: "{company_id}"
         - title: "Solicitud Asistencia - Teléfonos no encontrados"
         - description: "Cliente solicita asistencia pero no se encontraron teléfonos en ERP."
         - card_type: "opportunity"
         - pipeline_name: "Revisiones"
         - stage_name: "Nuevo"
         - type_of_activity: "llamada"
         - activity_title: "Llamar para dar asistencia"
         - phone: (teléfono del cliente si lo tienes)
    3. end_chat_tool(): Finaliza la conversación.
    </herramientas>

    <flujo_de_atencion>
    1. IDENTIFICAR RAMO y NIF:
       - Si no sabes de qué seguro se trata (Auto, Hogar, etc.), pregunta al cliente.
       - Clasifica la respuesta en uno de los <ramos_validos>.
       - Llama a get_assistance_phones with the NIF actual and the RAMO identified.
       
    2. ANALIZAR RESPUESTA:
       - ¿No hay pólizas/teléfonos? -> Usa create_task_activity_tool para que un humano le llame. Informa al cliente que un gestor le llamará enseguida. Cierra con end_chat_tool.
       - ¿Hay teléfonos? -> Da los números de asistencia encontrados. Cierra con end_chat_tool.

    3. EMERGENCIA ACTIVA:
       - Sé muy directo y rápido.
       - Prioriza dar el número.

    4. SI NO ENCUENTRAS DATOS:
       - No digas "error técnico".
       - Di: "Voy a pedir que un compañero te llame ahora mismo para darte el número correcto".
       - Usa create_task_activity_tool.
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
        nif=nif_value or "NO_IDENTIFICADO",
        company_id=company_id
    )

    prompt = ChatPromptTemplate.from_messages(
        [
            ("system", formatted_system_prompt),
            *history,
            ("human", "{user_text}"),
        ]
    )

    llm = get_llm()
    tools = [get_assistance_phones, create_task_activity_tool, end_chat_tool]
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
