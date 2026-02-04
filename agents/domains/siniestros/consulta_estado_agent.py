"""Consulta estado de siniestros agent for LangChain 1.x."""
from core.agent_factory import create_langchain_agent, run_langchain_agent
from core.memory_schema import get_global_history
from langchain.tools import tool

from core.llm import get_llm
from agents.domains.common.generic_knowledge_agent import generic_knowledge_agent
from tools.communication.end_chat_tool import end_chat_tool
from tools.zoa.tasks import create_task_activity_tool
from tools.erp.erp_tools import get_claims_tool
from tools.document_ai.ocr_tools import process_document


def consulta_estado_agent(payload: dict) -> dict:
    user_text = payload.get("mensaje", "")
    session = payload.get("session", {})
    memory = session.get("agent_memory", {})
    global_mem = memory.get("global", {})
    nif = global_mem.get("nif")
    history = get_global_history(memory)
    company_id = payload.get("company_id")
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

    system_prompt = f"""<rol>
Eres parte del equipo de siniestros de ZOA Seguros. Tu función es informar a los clientes sobre el estado de sus siniestros ya abiertos.
</rol>

<contexto>
- El cliente quiere saber cómo va un siniestro que ya tiene abierto
- Puedes consultar el estado en el sistema
- También puedes procesar documentos que el cliente envíe (fotos de póliza, DNI, etc.)
- ZOA opera en España
</contexto>

<variables_actuales>
NIF_actual: {nif or 'NO_IDENTIFICADO'}
Company_ID: {company_id}
</variables_actuales>

<herramientas>
1. get_claims_tool(nif, company_id): Obtiene TODOS los siniestros del cliente con su estado.
   - Devuelve lista con: id_claim, riesgo (risk), date (opening_date), status.
   - IMPORTANTE: Siempre usa company_id="{company_id}"
2. process_document(data): Procesa un documento enviado por el cliente (PDF/Imagen) para extraer información en formato JSON. Requiere un JSON string con 'mime_type' y 'b64_data'.
3. create_task_activity_tool(json_string): Crea una tarea para que un gestor atienda una consulta específica.
   - USAR cuando la consulta es muy específica (datos personales sensibles, importes exactos) y no puedes responder automáticamente.
   - JSON debe incluir:
     - company_id: "{company_id}"
     - title: "Consulta Estado Siniestro"
     - description: "El cliente consulta estado de siniestro y requiere atención humana: [resumen de la consulta]"
     - card_type: "opportunity"
     - pipeline_name: "Revisiones"
     - stage_name: "Nuevo"
     - type_of_activity: "llamada"
     - activity_title: "Responder consulta estado"
     - wa_id: "{wa_id or ''}"
4. ask_expert_knowledge(query): Responde dudas genéricas o teóricas sobre seguros.
5. end_chat_tool(): Finaliza la conversación cuando el cliente tenga la información que necesitaba.
</herramientas>

<flujo_de_atencion>
1. CLASIFICAR CONSULTA:
   - ¿Es GENÉRICA (teoría, coberturas generales)? -> Usa ask_expert_knowledge.
   - ¿Es ESPECÍFICA (sobre SU caso)? -> Sigue al paso 2.

2. IDENTIFICAR el siniestro:
   - Si tienes NIF_actual, usa get_claims_tool para listar todos sus siniestros.
   - Si envía foto, usa process_document para extraer información.
   - Si tienes identificador (Matrícula, Dirección, Nombre), úsalo para filtrar resultados.

3. CONSULTAR en el sistema:
   - Usa get_claims_tool(nif, company_id="{company_id}") para obtener los siniestros del cliente con su estado.

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

    llm = get_llm()

    tools = [
        get_claims_tool,
        process_document,
        end_chat_tool,
        create_task_activity_tool,
        ask_expert_knowledge,
    ]
    
    agent = create_langchain_agent(llm, tools, system_prompt)
    result = run_langchain_agent(agent, user_text, history)
    
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
