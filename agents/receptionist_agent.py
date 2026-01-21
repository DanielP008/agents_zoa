import json
import os

from langchain.agents import AgentExecutor, create_tool_calling_agent
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.tools import tool

from agents.llm import get_llm

_BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_ROUTES_PATH = os.path.join(_BASE_DIR, "contracts", "routes.json")

with open(_ROUTES_PATH, "r") as f:
    _ROUTES_CONFIG = json.load(f)
    _VALID_DOMAINS = set(_ROUTES_CONFIG["domains"])


def handle(payload: dict) -> dict:
    # Adapt classify_domain to return action format
    decision = classify_domain(payload)
    domain = decision.get("domain")
    
    if domain == "siniestros":
        return {
            "action": "route",
            "next_agent": "classifier_siniestros_agent",
            "domain": "siniestros",
            "message": "Entendido, te paso con el area de siniestros."
        }
    
    if domain in ["gestion", "ventas"]:
        return {
            "action": "ask", # Keep user here
            "message": f"El area de {domain} no esta disponible. Algo mas?"
        }

    return {
        "action": "ask",
        "message": "Hola, soy ZOA. Puedo ayudarte con Siniestros, Gestion o Ventas. Que necesitas?"
    }

def classify_domain(payload: dict) -> dict:
    user_text = payload.get("text", "")
    session = payload.get("session", {})
    
    # Check if we are already in a domain loop - handled by orchestrator now
    # But we can respect active domain if passed?
    if session.get("domain"):
         return {
            "domain": session.get("domain"),
            "confidence": 1.0,
            "reason": "active_session"
        }

    system_prompt = (
        "Eres el Recepcionista de ZOA. Tu objetivo es derivar al cliente a una de estas areas: "
        "siniestros, gestion, ventas. "
        "Analiza el mensaje y responde SOLO un JSON con: {{domain, confidence}}."
    )

    prompt = ChatPromptTemplate.from_messages(
        [
            ("system", system_prompt),
            ("human", "Cliente: {user_text}"),
        ]
    )

    llm = get_llm()
    chain = prompt | llm
    
    result = chain.invoke({"user_text": user_text})
    output = result.content
    
    try:
        decision = json.loads(output)
        domain = decision.get("domain")
        if domain not in _VALID_DOMAINS:
            domain = "receptionist_agent" # fallback
            
        # If confidence is high, lock session to domain? 
        # For now we just route.
        return {"domain": domain, "confidence": decision.get("confidence", 0.5)}
    except:
        return {"domain": "receptionist_agent", "confidence": 0.0}
