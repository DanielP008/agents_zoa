import json

from langchain.agents import AgentExecutor, create_tool_calling_agent
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.tools import tool

from agents.llm import get_llm
from tools.zoa_client import create_claim as zoa_create_claim
from tools.state_store import get_state, set_state


@tool
def create_claim_tool(data: str) -> dict:
    """Registra un siniestro en ZOA con los datos proporcionados (JSON string)."""
    try:
        payload = json.loads(data)
        return zoa_create_claim(payload)
    except:
        return {"error": "Invalid JSON format"}


def handle(payload: dict) -> dict:
    user_text = payload.get("text", "")
    user_id = payload.get("from", "unknown")
    session_id = payload.get("session_id", user_id)
    
    # Simple state handling
    state = get_state(session_id)
    history = state.get("apertura_history", [])

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
    agent = create_tool_calling_agent(llm, tools, prompt)
    executor = AgentExecutor(agent=agent, tools=tools, verbose=False)

    result = executor.invoke({"user_text": user_text})
    output_text = result.get("output", "")

    # Update state
    history.append(("human", user_text))
    history.append(("ai", output_text))
    set_state(session_id, {**state, "apertura_history": history[-10:]}) # keep last 10

    return {
        "agent": "apertura_siniestro_agent",
        "message": output_text,
    }
