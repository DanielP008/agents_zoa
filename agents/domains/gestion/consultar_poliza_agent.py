"""Consultar poliza agent for LangChain 1.x."""
import json
import logging
from datetime import datetime
from typing import Any, Dict

from langchain.tools import tool

from infra.llm import get_llm
from agents.domains.common.generic_knowledge_agent import generic_knowledge_agent
from infra.agent_runner import create_langchain_agent, run_langchain_agent
from core.agent_safeguards import task_tool_already_called, _TASK_DONE_SUFFIX, auto_create_task_if_needed, force_redirect_if_task_done
from core.memory import get_global_history
from tools.zoa.tasks_tool import create_task_activity_tool
from tools.communication.end_chat_tool import end_chat_tool
from tools.communication.redirect_to_receptionist_tool import redirect_to_receptionist_tool
from tools.erp.erp_tool import (
    get_client_policys_tool,
    get_policy_document_tool,
)
from agents.domains.gestion.consultar_poliza_agent_prompts import get_prompt

logger = logging.getLogger(__name__)

AGENT_NAME = "consultar_poliza_agent"

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
    company_id = payload.get("phone_number_id") or session.get("company_id") or "default"
    wa_id = payload.get("wa_id")
    history = get_global_history(memory)

    state = _get_state(memory)
    ramo = state.get("ramo")
    ocr_text = state.get("ocr_text")
    policy_id = state.get("policy_id")
    policies = state.get("policies")

    @tool
    def ask_expert_knowledge(query: str) -> str:
        """Consults the insurance expert agent to answer GENERIC questions.
        Use when the question is about concepts, general coverage, or doubts that do not require client data."""
        sub_payload = {
            "mensaje": query,
            "session": session
        }
        return generic_knowledge_agent(sub_payload).get("message", "Could not get response from expert.")

    now = datetime.now()
    current_date = now.strftime("%d/%m/%Y")
    current_time = now.strftime("%H:%M")
    current_year = now.year

    channel = payload.get("channel", "whatsapp")
    system_prompt = get_prompt(channel).format(
        current_date=current_date,
        current_time=current_time,
        current_year=current_year,
        nif=nif or 'NO_IDENTIFICADO',
        ramo=ramo or 'No especificado',
        company_id=company_id,
        wa_id=wa_id or 'NO_DISPONIBLE'
    )

    task_done = task_tool_already_called(memory, AGENT_NAME)
    if task_done:
        system_prompt += _TASK_DONE_SUFFIX
        logger.info("[CONSULTAR_POLIZA_AGENT] Task already created — restricting tools")

    llm = get_llm()
    tools = [
        get_client_policys_tool, 
        get_policy_document_tool, 
        ask_expert_knowledge, 
        end_chat_tool,
        redirect_to_receptionist_tool
    ]
    if not task_done:
        tools.insert(3, create_task_activity_tool)
    
    agent = create_langchain_agent(llm, tools, system_prompt)
    result = run_langchain_agent(agent, user_text, history, agent_name="consultar_poliza_agent")
    
    output_text = result.get("output", "")
    action = result.get("action", "ask")
    tool_calls = result.get("tool_calls")

    if not task_done:
        updated_tool_calls = auto_create_task_if_needed(
            tool_calls, output_text,
            company_id=company_id, nif_value=nif or "NO_IDENTIFICADO", wa_id=wa_id or "NO_DISPONIBLE",
            title="Consulta de Póliza",
            description=f"Cliente consulta sobre su póliza. NIF: {nif or 'NO_IDENTIFICADO'}.",
            activity_title="Llamar para informar sobre póliza",
            activity_description=f"El cliente ha tenido un problema técnico al consultar su póliza de {ramo or 'seguros'}. Contactar para ayudarle.",
            agent_label="CONSULTAR_POLIZA_AGENT",
        )
        if updated_tool_calls:
            if not result.get("tool_calls"):
                result["tool_calls"] = []
            result["tool_calls"] = updated_tool_calls
            tool_calls = updated_tool_calls

    if task_done:
        forced = force_redirect_if_task_done(output_text, action, tool_calls)
        if forced:
            logger.info("[CONSULTAR_POLIZA_AGENT] Task done & LLM didn't redirect — forcing redirect")
            return forced

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
