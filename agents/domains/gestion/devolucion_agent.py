import json

from core.agent_factory import create_langchain_agent, run_langchain_agent
from core.memory_schema import get_global_history
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.tools import tool

from agents.llm import get_llm
from tools.end_chat_tool import end_chat_tool


@tool
def create_refund_request_tool(data: str) -> dict:
    """Registra una solicitud de devolución en ZOA con los datos proporcionados (JSON string)."""
    try:
        payload = json.loads(data)
        return {"success": True, "refund_id": "REF-12345", "message": "Solicitud de devolución registrada"}
    except:
        return {"error": "Invalid JSON format"}


def devolucion_agent(payload: dict) -> dict:
    user_text = payload.get("mensaje", "")
    session = payload.get("session", {})
    memory = session.get("agent_memory", {})
    history = get_global_history(memory)

    system_prompt = (
        "Eres el agente de Devoluciones de ZOA. "
        "Tu objetivo es ayudar al cliente a solicitar una devolución de dinero. "
        "Necesitas recolectar: número de póliza, monto a devolver, motivo de la devolución, y datos bancarios (CBU/CVU). "
        "Pregunta uno por uno si faltan datos. "
        "Cuando tengas toda la información, usa la tool 'create_refund_request_tool' para registrar la solicitud. "
        "Responde siempre en español, sé amable y profesional. "
        "Confirma la acción al usuario y proporciona un número de seguimiento. "
        "\n\nIMPORTANTE: Usa 'end_chat_tool' cuando la solicitud de devolución esté completamente registrada y el usuario no necesite nada más. "
        "NO uses 'end_chat_tool' si el usuario hace preguntas adicionales o necesita otro tipo de ayuda."
    )

    prompt = ChatPromptTemplate.from_messages(
        [
            ("system", system_prompt),
            *history,
            ("human", "{user_text}"),
        ]
    )

    llm = get_llm()
    tools = [create_refund_request_tool, end_chat_tool]
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
