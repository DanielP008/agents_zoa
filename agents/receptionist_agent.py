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
    print("\n[RECEPTIONIST] 👋 Receptionist agent handling request")
    print(f"[RECEPTIONIST] Message: {payload.get('mensaje', '')[:80]}...")
    
    # Adapt classify_domain to return action format
    print("[RECEPTIONIST] 🔍 Classifying domain...")
    decision = classify_domain(payload)
    domain = decision.get("domain")
    confidence = decision.get("confidence", 0.0)
    
    print(f"[RECEPTIONIST] ✓ Classification result: domain={domain}, confidence={confidence}")
    
    if domain in _ROUTES_CONFIG["domains"]:
        domain_config = _ROUTES_CONFIG["domains"][domain]
        classifier_agent = domain_config.get("classifier")
        
        if classifier_agent:
            print(f"[RECEPTIONIST] 🔀 Routing to {classifier_agent}")
            return {
                "action": "route",
                "next_agent": classifier_agent,
                "domain": domain,
                "message": f"Entendido, te paso con el area de {domain}."
            }
        else:
            print(f"[RECEPTIONIST] ⚠️  Domain {domain} has no classifier configured")
            return {
                "action": "ask", # Keep user here
                "message": f"El area de {domain} no esta disponible aun. Algo mas?"
            }

    print("[RECEPTIONIST] 💬 Asking user for clarification")
    return {
        "action": "ask",
        "message": "Hola, soy ZOA. Puedo ayudarte con Siniestros, Gestion o Ventas. Que necesitas?"
    }

def classify_domain(payload: dict) -> dict:
    user_text = payload.get("mensaje", "")
    session = payload.get("session", {})
    
    print(f"[RECEPTIONIST] 📝 Classifying domain for: '{user_text[:60]}...'")
    
    # Check if we are already in a domain loop - handled by orchestrator now
    # But we can respect active domain if passed?
    if session.get("domain"):
        existing_domain = session.get("domain")
        print(f"[RECEPTIONIST] ✓ Using existing domain from session: {existing_domain}")
        return {
            "domain": existing_domain,
            "confidence": 1.0,
            "reason": "active_session"
        }

    print("[RECEPTIONIST] 🤖 Calling LLM for domain classification...")
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
    
    try:
        result = chain.invoke({"user_text": user_text})
        output = result.content
        print(f"[RECEPTIONIST] 📥 LLM raw response: {output}")
        
        # Clean markdown if present
        cleaned_output = output.strip()
        if cleaned_output.startswith("```"):
            cleaned_output = cleaned_output.split("```")[1]
            if cleaned_output.startswith("json"):
                cleaned_output = cleaned_output[4:]
            cleaned_output = cleaned_output.strip()
            
        decision = json.loads(cleaned_output)
        domain = decision.get("domain")
        confidence = decision.get("confidence", 0.5)
        
        if domain not in _VALID_DOMAINS:
            print(f"[RECEPTIONIST] ⚠️  Invalid domain '{domain}', falling back to receptionist")
            domain = "receptionist_agent" # fallback
            
        print(f"[RECEPTIONIST] ✓ Parsed decision: domain={domain}, confidence={confidence}")
        return {"domain": domain, "confidence": confidence}
    except json.JSONDecodeError as e:
        print(f"[RECEPTIONIST] ❌ Failed to parse LLM JSON: {e}")
        print(f"[RECEPTIONIST]   Raw output: {output if 'output' in locals() else 'N/A'}")
        return {"domain": "receptionist_agent", "confidence": 0.0}
    except Exception as e:
        print(f"[RECEPTIONIST] ❌ Error during classification: {e}")
        import traceback
        print(f"[RECEPTIONIST] Traceback: {traceback.format_exc()}")
        return {"domain": "receptionist_agent", "confidence": 0.0}
