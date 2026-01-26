import json

from core.agent_factory import create_langchain_agent, run_langchain_agent
from core.memory_schema import get_global_history
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.tools import tool

from agents.llm import get_llm
from tools.zoa_client import create_claim as zoa_create_claim
from tools.end_chat_tool import end_chat_tool


@tool
def create_claim_tool(data: str) -> dict:
    """Registra un siniestro en ZOA con los datos proporcionados (JSON string)."""
    try:
        payload = json.loads(data)
        return zoa_create_claim(payload)
    except:
        return {"error": "Invalid JSON format"}


def apertura_siniestro_agent(payload: dict) -> dict:
    user_text = payload.get("mensaje", "")
    session = payload.get("session", {})
    memory = session.get("agent_memory", {})
    history = get_global_history(memory)

    system_prompt = (
        "Eres el agente de Apertura de Siniestros de ZOA. "
        "Tu objetivo es recolectar: fecha, lugar, descripcion del evento y numero de poliza. "
        "Pregunta uno por uno si faltan datos. "
        "Cuando tengas todo, usa la tool 'create_claim_tool' para registrarlo. "
        "Responde siempre en español y confirma la accion al usuario. "
        "\n\nIMPORTANTE: "
        "- Usa 'end_chat_tool' cuando el siniestro esté completamente registrado y el usuario no necesite nada más. "
        "- NO uses 'end_chat_tool' si el usuario hace preguntas adicionales o necesita otro tipo de ayuda. "
        "- Sé inteligente: analiza si la conversación ha terminado realmente o si el usuario podría necesitar más asistencia."
    )

    prompt = ChatPromptTemplate.from_messages(
        [
            ("system", system_prompt),
            *history,
            ("human", "{user_text}"),
        ]
    )

    llm = get_llm()
    tools = [create_claim_tool, end_chat_tool]
    executor = create_langchain_agent(llm, tools, prompt)

    result = run_langchain_agent(executor, user_text)
    output_text = result.get("output", "")
    action = result.get("action", "ask")

    # If end_chat_tool was used, return the special action
    if action == "end_chat":
        return {
            "action": "end_chat",
            "message": output_text
        }

    return {
        "action": action,
        "message": output_text
    }
