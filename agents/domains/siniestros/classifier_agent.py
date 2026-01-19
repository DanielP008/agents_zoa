import json
import os

from langchain.agents import AgentExecutor, create_tool_calling_agent
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.tools import tool

from agents.llm import get_llm
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


def handle(payload: dict) -> dict:
    # Llama a classify_message y adapta la respuesta al formato action
    decision = classify_message(payload)
    
    if decision.get("needs_more_info"):
        return {
            "action": "ask",
            "message": decision.get("question"),
            "memory": {"last_route": decision.get("route")} 
        }

    return {
        "action": "route",
        "next_agent": decision.get("route"), # e.g. apertura_siniestro_agent
        "domain": "siniestros",
        "message": "Entendido."
    }

def classify_message(payload: dict) -> dict:
    user_text = payload.get("text", "")
    user_id = payload.get("from", "unknown")
    session = payload.get("session", {})
    
    # Check if we are already in a domain loop
    # In new architecture, router handles this, but we can peek at memory
    memory = session.get("agent_memory", {})
    last_route = memory.get("last_route", "unknown")
    last_question = memory.get("last_question", "")

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
            "last_route": last_route,
            "last_question": last_question,
        }
    )
    output = result.get("output", "")
    try:
        decision = json.loads(output)
        route = decision.get("route")
        if route not in _VALID_ROUTES:
            route = _DEFAULT_ROUTE
            decision["route"] = route

        # New Architecture: We return the decision to be handled by handle() wrapper
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
