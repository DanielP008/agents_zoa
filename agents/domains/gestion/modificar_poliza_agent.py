import json

from core.agent_factory import create_langchain_agent, run_langchain_agent
from core.memory_schema import get_global_history
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.tools import tool

from agents.llm import get_llm
from tools.end_chat_tool import end_chat_tool


@tool
def update_policy_tool(data: str) -> dict:
    """Actualiza datos de una póliza en ZOA con los cambios proporcionados (JSON string)."""
    try:
        payload = json.loads(data)
        return {
            "success": True,
            "policy_number": payload.get("policy_number"),
            "updated_fields": list(payload.get("changes", {}).keys()),
            "message": "Póliza actualizada correctamente"
        }
    except:
        return {"error": "Invalid JSON format"}


def modificar_poliza_agent(payload: dict) -> dict:
    user_text = payload.get("mensaje", "")
    session = payload.get("session", {})
    memory = session.get("agent_memory", {})
    history = get_global_history(memory)

    system_prompt = (
        "Eres el agente de Modificación de Póliza de ZOA. "
        "Tu objetivo es ayudar al cliente a modificar datos de su póliza. "
        "Puedes modificar: datos bancarios (CBU/CVU), beneficiarios, domicilio, teléfono, email, etc. "
        "Necesitas: número de póliza y los datos que se desean modificar. "
        "Pregunta uno por uno qué desea cambiar y cuáles son los nuevos valores. "
        "Cuando tengas toda la información, usa la tool 'update_policy_tool' para registrar los cambios. "
        "Responde siempre en español, sé amable y profesional. "
        "Confirma los cambios realizados al usuario."
    )

    prompt = ChatPromptTemplate.from_messages(
        [
            ("system", system_prompt),
            *history,
            ("human", "{user_text}"),
        ]
    )

    llm = get_llm()
    tools = [update_policy_tool, end_chat_tool]
    executor = create_langchain_agent(llm, tools, prompt)

    result = run_langchain_agent(executor, user_text)
    output_text = result.get("output", "")
    action = result.get("action", "ask")

    if action == "end_chat":
        return {
            "action": "end_chat",
            "message": output_text
        }

    if "actualizada" in output_text.lower() or "modificada" in output_text.lower():
        action = "finish"

    return {
        "action": action,
        "message": output_text
    }
