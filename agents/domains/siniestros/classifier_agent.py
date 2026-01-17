import json
import os

from langchain.agents import AgentExecutor, create_tool_calling_agent
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.tools import tool

from agents.llm import get_llm
from tools.state_store import get_state, set_state
from tools.whatsapp_client import send_whatsapp_message

_BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
_ROUTES_PATH = os.path.join(_BASE_DIR, "contracts", "routes.json")

with open(_ROUTES_PATH, "r") as f:
    _ROUTES_CONFIG = json.load(f)
    _VALID_ROUTES = set(_ROUTES_CONFIG["siniestros_agents"])
    _DEFAULT_ROUTE = "classifier_siniestros_agent"

@tool
def whatsapp_send(to: str, text: str) -> dict:
    """Send a WhatsApp message (mock)."""
    return send_whatsapp_message(to=to, text=text)


def classify_message(payload: dict) -> dict:
    user_text = payload.get("text", "")
    user_id = payload.get("from", "unknown")
    session_id = payload.get("session_id", user_id)
    state = get_state(session_id)

    system_prompt = (
        "Eres el clasificador de SINIESTROS de ZOA. "
        "Tus agentes disponibles son: telefonos_asistencia_agent, apertura_siniestro_agent, consulta_estado_agent. "
        "Si falta informacion, hace UNA pregunta al usuario enviandola "
        "por la tool whatsapp_send. Luego responde SOLO un JSON con: "
        "{route, confidence, needs_more_info, question}. "
        "Contexto previo: ultimo_route={last_route}, ultima_pregunta={last_question}."
    )

    prompt = ChatPromptTemplate.from_messages(
        [
            ("system", system_prompt),
            ("human", "Cliente ({user_id}): {user_text}"),
        ]
    )

    llm = get_llm()
    tools = [whatsapp_send]
    agent = create_tool_calling_agent(llm, tools, prompt)
    executor = AgentExecutor(agent=agent, tools=tools, verbose=False)

    result = executor.invoke(
        {
            "user_id": user_id,
            "user_text": user_text,
            "last_route": state.get("last_route", "unknown"),
            "last_question": state.get("last_question", ""),
        }
    )
    output = result.get("output", "")
    try:
        decision = json.loads(output)
        route = decision.get("route")
        if route not in _VALID_ROUTES:
            route = _DEFAULT_ROUTE
            decision["route"] = route

        set_state(
            session_id,
            {
                "last_route": route,
                "last_question": decision.get("question", ""),
            },
        )
        return decision
    except json.JSONDecodeError:
        return {
            "route": "classifier",
            "confidence": 0.1,
            "needs_more_info": True,
            "question": (
                "Para ayudarte, podrias decirme si es asistencia, siniestro "
                "o consulta de poliza?"
            ),
        }
