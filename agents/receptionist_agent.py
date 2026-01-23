import json
import os

from langchain.agents.tool_calling_agent.base import create_tool_calling_agent
from langchain.agents.agent import AgentExecutor

from langchain_core.prompts import ChatPromptTemplate
from langchain_core.tools import tool

from agents.llm import get_llm

import pathlib

# Robust path resolution for Docker /app env
# Assuming structure: /app/agents/receptionist_agent.py
# contracts is at: /app/contracts/routes.json
_CURRENT_DIR = pathlib.Path(__file__).parent.resolve() # /app/agents
_ROOT_DIR = _CURRENT_DIR.parent # /app
_ROUTES_PATH = _ROOT_DIR / "contracts" / "routes.json"

with open(_ROUTES_PATH, "r") as f:
    _ROUTES_CONFIG = json.load(f)
    _VALID_DOMAINS = set(_ROUTES_CONFIG["domains"])


def handle(payload: dict) -> dict:
    # Adapt classify_domain to return action format
    decision = classify_domain(payload)
    domain = decision.get("domain")
    
    if domain in _ROUTES_CONFIG["domains"]:
        domain_config = _ROUTES_CONFIG["domains"][domain]
        classifier_agent = domain_config.get("classifier")
        
        if classifier_agent:
            return {
                "action": "route",
                "next_agent": classifier_agent,
                "domain": domain,
                "message": f"Entendido, te paso con el area de {domain}."
            }
        else:
            return {
                "action": "ask", # Keep user here
                "message": f"El area de {domain} no esta disponible aun. Algo mas?"
            }

    return {
        "action": "ask",
        "message": "Hola, soy ZOA. Puedo ayudarte con Siniestros, Gestion o Ventas. Que necesitas?"
    }

def classify_domain(payload: dict) -> dict:
    user_text = payload.get("mensaje", "")
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
