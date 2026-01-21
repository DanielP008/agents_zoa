import json

from langchain.agents import create_tool_calling_agent
from langchain.agents.agent import AgentExecutor
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.tools import tool

from agents.llm import get_llm
from tools.zoa_client import fetch_policy
from tools.ocr_client import extract_text


@tool
def lookup_policy(policy_number: str) -> dict:
    """Busca informacion de una poliza por su numero."""
    return fetch_policy(policy_number)

@tool
def process_document(doc_type: str) -> dict:
    """Procesa un documento (OCR) para extraer texto. Simulado."""
    # En la realidad, aqui pasariamos la URL o el binario del documento
    return extract_text({"type": doc_type})


def handle(payload: dict) -> dict:
    user_text = payload.get("text", "")
    session = payload.get("session", {})
    history = session.get("agent_memory", {}).get("consulta_history", [])

    system_prompt = (
        "Eres el agente de Consulta de Estado de ZOA. "
        "Ayudas a clientes a ver el estado de su poliza o siniestro. "
        "Pide el numero de poliza si es necesario y usa 'lookup_policy'. "
        "Si envian un documento, usa 'process_document'. "
    )

    prompt = ChatPromptTemplate.from_messages(
        [
            ("system", system_prompt),
            *history,
            ("human", "{user_text}"),
        ]
    )

    llm = get_llm()
    tools = [lookup_policy, process_document]
    agent = create_tool_calling_agent(llm, tools, prompt)
    executor = AgentExecutor(agent=agent, tools=tools, verbose=False)

    result = executor.invoke({"user_text": user_text})
    output_text = result.get("output", "")

    # Update state
    history.append(("human", user_text))
    history.append(("ai", output_text))

    return {
        "action": "ask",
        "message": output_text,
        "memory": {"consulta_history": history[-6:]}
    }
