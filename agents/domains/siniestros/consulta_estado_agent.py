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
        "Eres el agente de Consulta de Estado de ZOA. Tu objetivo es identificar al cliente y su tipo de consulta.\n"
        "Sigue ESTRICTAMENTE este flujo:\n"
        "1. Obtener identificador segun el tipo de seguro (pregunta al usuario si no lo tienes):\n"
        "   - Hogar -> Pedir 'Dirección del hogar'\n"
        "   - Auto -> Pedir 'Matrícula'\n"
        "   - PYME/Comercio -> Pedir 'Nombre comercio'\n"
        "   - Responsabilidad Civil -> Pedir 'Nombre empresa'\n"
        "   - Comunidades vecinos -> Pedir 'Dirección edificio'\n"
        "2. Identificar el tipo de consulta ('Cual es su consulta'):\n"
        "   - Si es una PREGUNTA ESPECÍFICA (sobre su expediente, estado real, datos personales): \n"
        "     Usa la herramienta 'notify_claims_manager' para avisar al gestor. Pide el NIF si es necesario para la herramienta, o usa 'UNKNOWN' si solo tienes el otro identificador.\n"
        "   - Si es una PREGUNTA GENÉRICA (coberturas generales, dudas de seguros, procedimientos): \n"
        "     NO respondas tú directamente. USA LA HERRAMIENTA 'ask_expert_knowledge' pasando la pregunta del usuario.\n\n"
        "No uses 'lookup_policy' a menos que sea estrictamente necesario para validar. Prioriza el flujo descrito."
    )

    prompt = ChatPromptTemplate.from_messages(
        [
            ("system", system_prompt),
            *history,
            ("human", "{user_text}"),
        ]
    )

    # Use specific model as requested
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
