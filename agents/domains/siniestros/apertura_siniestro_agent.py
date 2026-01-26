import json

from core.agent_factory import create_langchain_agent, run_langchain_agent
from core.memory_schema import get_global_history
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.tools import tool

from agents.llm import get_llm
from tools.zoa_client import create_claim as zoa_create_claim


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
        "Responde siempre en español y confirma la accion al usuario."
    )

    prompt = ChatPromptTemplate.from_messages(
        [
            ("system", system_prompt),
            *history,
            ("human", "{user_text}"),
        ]
    )

    llm = get_llm()
    tools = [create_claim_tool]
    executor = create_langchain_agent(llm, tools, prompt)

    result = run_langchain_agent(executor, user_text)
    output_text = result.get("output", "")

    # Check if we are done (tool called?) -> Detect by checking output text
    action = "ask"
    if "registrado" in output_text.lower() or "claim_id" in output_text.lower():
        action = "finish"

    return {
        "action": action,
        "message": output_text
    }
