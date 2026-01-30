from core.agent_factory import create_langchain_agent, run_langchain_agent
from core.memory_schema import get_global_history
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.tools import tool

from core.llm import get_llm
from agents.domains.common.generic_knowledge_agent import generic_knowledge_agent
from tools.communication.end_chat_tool import end_chat_tool
from tools.zoa.tasks import create_task_activity_tool
from tools.erp.claim_tools import get_claims_tool, get_status_claims_tool
from tools.document_ai.ocr_tools import process_document


def consulta_estado_agent(payload: dict) -> dict:
    user_text = payload.get("mensaje", "")
    session = payload.get("session", {})
    memory = session.get("agent_memory", {})
    history = get_global_history(memory)
    company_id = session.get("company_id", "default_company")
    wa_id = payload.get("wa_id")

    @tool
    def ask_expert_knowledge(query: str) -> str:
        """Consulta al agente experto en seguros para responder dudas GENÉRICAS.
        Usar cuando la pregunta es sobre coberturas generales, procedimientos estándar o dudas teóricas,
        y NO sobre un expediente específico."""
        sub_payload = {
            "mensaje": query,
            "session": session
        }
        result = generic_knowledge_agent(sub_payload)
        return result.get("message", "No pude obtener respuesta del experto.")

    system_prompt = (
        """<rol>
    Eres parte del equipo de siniestros de ZOA Seguros. Tu función es informar a los clientes sobre el estado de sus siniestros ya abiertos.
    </rol>

    <contexto>
    - El cliente quiere saber cómo va un siniestro que ya tiene abierto
    - Puedes consultar el estado en el sistema
    - También puedes procesar documentos que el cliente envíe (fotos de póliza, DNI, etc.)
    - ZOA opera en España
    </contexto>

    <variables_actuales>
    Company_ID: {company_id}
    </variables_actuales>

    <herramientas>
    1. get_claims_tool(company_id, nif, ramo, phone): Obtiene los siniestros del cliente para un ramo (Auto, Hogar, etc.). Devuelve lista con id_claim, riesgo y fecha.
    2. get_status_claims_tool(company_id, id_claim): Obtiene el estado de un siniestro concreto por id_claim.
    3. process_document(data): Procesa un documento enviado por el cliente (PDF/Imagen) para extraer información en formato JSON. Requiere un JSON string con 'mime_type' y 'b64_data'.
    4. create_task_activity_tool(json_string): Crea una tarea para que un gestor atienda una consulta específica.
       - USAR cuando la consulta es muy específica (datos personales sensibles, importes exactos) y no puedes responder automáticamente.
       - JSON debe incluir:
         - company_id: "{company_id}"
         - title: "Consulta Estado Siniestro"
         - description: "El cliente consulta estado de siniestro y requiere atención humana: [resumen de la consulta]"
         - card_type: "task"
         - pipeline_name: "Principal"
         - stage_name: "Nuevo"
         - type_of_activity: "llamada"
         - activity_title: "Responder consulta estado"
         - wa_id: "{wa_id}"
    5. ask_expert_knowledge(query): Responde dudas genéricas o teóricas sobre seguros.
    6. end_chat_tool(): Finaliza la conversación cuando el cliente tenga la información que necesitaba.
    </herramientas>

    <flujo_de_atencion>
    1. CLASIFICAR CONSULTA:
       - ¿Es GENÉRICA (teoría, coberturas generales)? -> Usa ask_expert_knowledge.
       - ¿Es ESPECÍFICA (sobre SU caso)? -> Sigue al paso 2.

    2. IDENTIFICAR el siniestro:
       - Pide el número de póliza o el número de expediente/siniestro.
       - Si envía foto, usa process_document.
       - Si tienes identificador (Matrícula, Dirección, Nombre), úsalo.

    3. CONSULTAR en el sistema:
       - Usa get_claims_tool(company_id, nif, ramo) para listar los siniestros del cliente; luego get_status_claims_tool(company_id, id_claim) para obtener el estado.

    4. INFORMAR de forma clara:
       - Estado actual, última actualización, próximos pasos.

    5. MANEJO DE EXCEPCIONES:
       - Si la consulta es MUY específica (datos personales sensibles, importes exactos de peritaje) y no tienes acceso:
         - Usa create_task_activity_tool para escalar al gestor.
         - Informa al cliente que le contactarán.

    6. PREGUNTAS GENERALES (FAQs):
       - ¿Cuánto tarda? -> 15-30 días aprox.
       - ¿Cuándo pagan? -> 5-10 días tras aprobación.
    </flujo_de_atencion>

    <personalidad>
    - Informativo y claro
    - Paciente
    - No usas frases robóticas
    - No usas emojis
    - Comprensivo si hay demoras
    </personalidad>

    <restricciones>
    - NUNCA inventes estados.
    - NUNCA menciones "transferencias", "derivaciones" o "agentes".
    - USA end_chat_tool cuando el cliente tenga la información y confirme que no necesita más.
    </restricciones>"""
    )

    formatted_system_prompt = system_prompt.format(
        company_id=company_id,
        wa_id=wa_id or ""
    )

    prompt = ChatPromptTemplate.from_messages(
        [
            ("system", formatted_system_prompt),
            *history,
            ("human", "{user_text}"),
        ]
    )

    llm = get_llm(model_name="gemini-3-flash-preview")

    tools = [
        get_claims_tool,
        get_status_claims_tool,
        process_document,
        end_chat_tool,
        create_task_activity_tool,
        ask_expert_knowledge,
    ]
    executor = create_langchain_agent(llm, tools, prompt)

    result = run_langchain_agent(executor, user_text)
    output_text = result.get("output", "")
    action = result.get("action", "ask")

    if action == "end_chat":
        return {
            "action": "end_chat",
            "message": output_text
        }

    return {
        "action": action,
        "message": output_text
    }
