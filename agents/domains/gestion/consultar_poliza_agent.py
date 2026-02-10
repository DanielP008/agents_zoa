import json
from typing import Any, Dict

from langchain.tools import tool

from core.llm import get_llm
from agents.domains.common.generic_knowledge_agent import generic_knowledge_agent
from core.agent_factory import create_langchain_agent, run_langchain_agent
from core.memory_schema import get_global_history
from tools.zoa.tasks import create_task_activity_tool
from tools.communication.end_chat_tool import end_chat_tool
from tools.communication.redirect_to_receptionist_tool import redirect_to_receptionist_tool
from tools.erp.erp_tools import (
    get_client_policys_tool,
    get_policy_document_tool,
)
from agents.domains.gestion.consultar_poliza_agent_prompts import get_prompt

RAMO_OPTIONS = [
    "hogar",
    "auto",
    "pyme/comercio",
    "responsabilidad civil",
    "comunidades vecinos",
]

def _get_state(memory: Dict[str, Any]) -> Dict[str, Any]:
    return (
        memory.get("domains", {})
        .get("gestion", {})
        .get("consultar_poliza", {})
        or {}
    )

def _state_patch(memory: Dict[str, Any], updates: Dict[str, Any]) -> Dict[str, Any]:
    domain_data = memory.get("domains", {}).get("gestion", {}) or {}
    current = domain_data.get("consultar_poliza", {}) or {}
    new_state = {**current, **updates}
    return {"domains": {"gestion": {**domain_data, "consultar_poliza": new_state}}}

def consultar_poliza_agent(payload: dict) -> dict:
    user_text = (payload.get("mensaje") or "").strip()
    session = payload.get("session", {})
    memory = session.get("agent_memory", {})
    global_mem = memory.get("global", {})
    nif = global_mem.get("nif")
    company_id = payload.get("company_id")
    wa_id = payload.get("wa_id")
    history = get_global_history(memory)

    state = _get_state(memory)
    ramo = state.get("ramo")
    ocr_text = state.get("ocr_text")
    policy_id = state.get("policy_id")
    policies = state.get("policies")

    @tool
    def ask_expert_knowledge(query: str) -> str:
        """Consulta al agente experto en seguros para responder dudas GENÉRICAS.
        Usar cuando la pregunta es sobre conceptos, coberturas generales o dudas que no requieren datos del cliente."""
        sub_payload = {
            "mensaje": query,
            "session": session
        }
        result = generic_knowledge_agent(sub_payload)
        return result.get("message", "No pude obtener respuesta del experto.")

    # Get prompt based on channel and format with variables
    channel = payload.get("channel", "whatsapp")
    system_prompt = get_prompt(channel).format(
        nif=nif or 'NO_IDENTIFICADO',
        ramo=ramo or 'No especificado',
        company_id=company_id,
        wa_id=wa_id or ''
    )

    llm = get_llm()
    tools = [
        get_client_policys_tool, 
        get_policy_document_tool, 
        ask_expert_knowledge, 
        create_task_activity_tool,
        end_chat_tool,
        redirect_to_receptionist_tool
    ]
    
    agent = create_langchain_agent(llm, tools, system_prompt)
    result = run_langchain_agent(agent, user_text, history, agent_name="consultar_poliza_agent")
    
    output_text = result.get("output", "")
    action = result.get("action", "ask")
    tool_calls = result.get("tool_calls")
    
    # Check if redirect to receptionist was triggered
    if "__REDIRECT_TO_RECEPTIONIST__" in output_text:
        clean_message = output_text.replace("__REDIRECT_TO_RECEPTIONIST__", "").strip()
        return {
            "action": "route",
            "next_agent": "receptionist_agent",
            "domain": None,
            "message": clean_message,
            "tool_calls": tool_calls
        }
    
    if action == "end_chat":
        return {
            "action": "end_chat",
            "message": output_text,
            "tool_calls": tool_calls
        }
    
    # State update logic
    memory_patch = _state_patch(
        memory,
        {
            "ramo": ramo or state.get("ramo"),
            "policies": policies,
            "policy_id": policy_id,
            "ocr_text": ocr_text,
        },
    )

    return {
        "action": action,
        "message": output_text,
        "memory": memory_patch,
        "tool_calls": tool_calls
    }
