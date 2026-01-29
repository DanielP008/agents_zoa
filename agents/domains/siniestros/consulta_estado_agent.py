import json
from functools import partial

from core.agent_factory import create_langchain_agent, run_langchain_agent
from core.memory_schema import get_global_history
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.tools import tool

from agents.llm import get_llm
from agents.domains.common.generic_knowledge_agent import generic_knowledge_agent
from tools.end_chat_tool import end_chat_tool
from tools.zoa_client import fetch_policy, create_task_with_activity
from tools.ocr_client import extract_text


@tool
def lookup_policy(policy_number: str) -> dict:
    """Busca informacion de una poliza por su numero."""
    return fetch_policy(policy_number)

@tool
def process_document(doc_type: str) -> dict:
    """Procesa un documento (OCR) para extraer texto. Simulado."""
    return extract_text({"type": doc_type})


def consulta_estado_agent(payload: dict) -> dict:
    user_text = payload.get("mensaje", "")
    session = payload.get("session", {})
    memory = session.get("agent_memory", {})
    history = get_global_history(memory)
    company_id = session.get("company_id", "default_company")

    @tool
    def notify_claims_manager(description: str, client_nif: str = "UNKNOWN") -> dict:
        """Crea una tarea y notifica al gestor de siniestros por Whatsapp.
        Usar cuando el cliente tiene una consulta especifica sobre su caso."""
        return create_task_with_activity(
            task_description=description,
            client_nif=client_nif,
            company_id=company_id,
            activity_type="whatsapp_notification"
        )

    @tool
    def ask_expert_knowledge(query: str) -> str:
        """Consulta al agente experto en seguros para responder dudas GENÉRICAS.
        Usar cuando la pregunta es sobre coberturas generales, procedimientos estándar o dudas teóricas,
        y NO sobre un expediente específico."""
        # Create a new payload for the sub-agent
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

<herramientas>
1. lookup_policy(policy_number): Busca información de una póliza y sus siniestros asociados por número de póliza.
2. process_document(doc_type): Procesa un documento enviado por el cliente para extraer información (OCR).
3. notify_claims_manager(description, client_nif): Notifica a un gestor humano si la consulta es muy específica y no puedes resolverla.
4. ask_expert_knowledge(query): Responde dudas genéricas o teóricas sobre seguros.
5. end_chat_tool(): Finaliza la conversación cuando el cliente tenga la información que necesitaba.
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
   - Usa lookup_policy para obtener el estado.

4. INFORMAR de forma clara:
   - Estado actual, última actualización, próximos pasos.

5. MANEJO DE EXCEPCIONES:
   - Si la consulta es MUY específica (datos personales sensibles, importes exactos de peritaje) y no tienes acceso:
     - Usa notify_claims_manager para escalar al gestor.
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

    prompt = ChatPromptTemplate.from_messages(
        [
            ("system", system_prompt),
            *history,
            ("human", "{user_text}"),
        ]
    )

    # Use specific model as requested in dev branch
    llm = get_llm(model_name="gemini-3-flash-preview")
    
    tools = [lookup_policy, process_document, end_chat_tool, notify_claims_manager, ask_expert_knowledge]
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
