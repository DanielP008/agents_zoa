import json

from langchain.agents import AgentExecutor, create_tool_calling_agent
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.tools import tool

from agents.llm import get_llm


@tool
def get_assistance_phones(policy_type: str) -> dict:
    """Devuelve los telefonos de asistencia segun el tipo de poliza."""
    phones = {
        "auto": {"grua": "0800-111-GRUA", "mecanica": "0800-222-MECA"},
        "hogar": {"emergencia": "0800-333-CASA"},
        "vida": {"emergencia": "0800-444-VIDA"}
    }
    return phones.get(policy_type.lower(), {"general": "0800-000-ZOA"})


def handle(payload: dict) -> dict:
    user_text = payload.get("text", "")
    session = payload.get("session", {})
    history = session.get("agent_memory", {}).get("asistencia_history", [])

    system_prompt = (
        "Eres el agente de Telefonos de Asistencia de ZOA. "
        "Pregunta el tipo de seguro (auto, hogar, vida) si no lo sabes. "
        "Usa la tool 'get_assistance_phones' para buscar el numero correcto. "
        "Responde amablemente con la informacion."
    )

    prompt = ChatPromptTemplate.from_messages(
        [
            ("system", system_prompt),
            *history,
            ("human", "{user_text}"),
        ]
    )

    llm = get_llm()
    tools = [get_assistance_phones]
    agent = create_tool_calling_agent(llm, tools, prompt)
    executor = AgentExecutor(agent=agent, tools=tools, verbose=False)

    result = executor.invoke({"user_text": user_text})
    output_text = result.get("output", "")

    # Update state
    history.append(("human", user_text))
    history.append(("ai", output_text))

    return {
        "action": "ask", # or finish if phones provided?
        "message": output_text,
        "memory": {"asistencia_history": history[-6:]}
    }
