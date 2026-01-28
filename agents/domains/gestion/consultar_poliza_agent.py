import json

from core.agent_factory import create_langchain_agent, run_langchain_agent
from core.memory_schema import get_global_history
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.tools import tool

from agents.llm import get_llm
from tools.end_chat_tool import end_chat_tool


@tool
def get_policy_info_tool(policy_number: str) -> dict:
    """Obtiene información de una póliza desde ZOA dado su número."""
    try:
        return {
            "success": True,
            "policy_number": policy_number,
            "holder": "Juan Pérez",
            "coverage": "Todo Riesgo",
            "vehicle": "Ford Focus 2020",
            "expiration": "2026-12-31",
            "premium": "$15,000/mes"
        }
    except Exception as e:
        return {"error": str(e)}


def consultar_poliza_agent(payload: dict) -> dict:
    user_text = payload.get("mensaje", "")
    session = payload.get("session", {})
    memory = session.get("agent_memory", {})
    history = get_global_history(memory)

    system_prompt = (
        "Eres el agente de Consulta de Póliza de ZOA. "
        "Tu objetivo es ayudar al cliente a obtener información sobre su póliza. "
        "Necesitas el número de póliza para realizar la consulta. "
        "Una vez que tengas el número, usa la tool 'get_policy_info_tool' para obtener los datos. "
        "Presenta la información de manera clara y organizada. "
        "Si el cliente pregunta por algo específico (coberturas, vencimiento, datos del vehículo), enfócate en eso. "
        "Responde siempre en español, sé amable y profesional. "
        "\n\nIMPORTANTE: Usa 'end_chat_tool' cuando hayas proporcionado toda la información solicitada sobre la póliza y el usuario no necesite nada más. "
        "NO uses 'end_chat_tool' si el usuario hace preguntas adicionales o necesita consultar otros aspectos."
    )

    prompt = ChatPromptTemplate.from_messages(
        [
            ("system", system_prompt),
            *history,
            ("human", "{user_text}"),
        ]
    )

    llm = get_llm()
    tools = [get_policy_info_tool, end_chat_tool]
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
