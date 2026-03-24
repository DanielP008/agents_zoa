"""Consulta estado de siniestros agent for LangChain 1.x."""
import logging
from datetime import datetime
from infra.agent_runner import (
    create_langchain_agent, run_langchain_agent,
    task_tool_already_called, _TASK_DONE_SUFFIX,
    auto_create_task_if_needed, force_redirect_if_task_done,
)
from core.memory import get_global_history
from langchain.tools import tool

from infra.llm import get_llm
from agents.domains.common.generic_knowledge_agent import generic_knowledge_agent
from tools.communication.end_chat_tool import end_chat_tool
from tools.communication.redirect_to_receptionist_tool import redirect_to_receptionist_tool
from tools.zoa.tasks_tool import create_task_activity_tool
from tools.erp.erp_tool import get_claims_tool
from agents.domains.siniestros.consulta_estado_agent_prompts import get_prompt

logger = logging.getLogger(__name__)

AGENT_NAME = "consulta_estado_agent"

def consulta_estado_agent(payload: dict) -> dict:
    user_text = payload.get("mensaje", "")
    session = payload.get("session", {})
    memory = session.get("agent_memory", {})
    global_mem = memory.get("global", {})
    nif = global_mem.get("nif")
    history = get_global_history(memory)
    company_id = payload.get("company_id")
    wa_id = payload.get("wa_id")

    @tool
    def ask_expert_knowledge(query: str) -> str:
        """Consulta al agente experto en seguros para responder dudas GENÉRICAS.
        Usar cuando la pregunta es sobre coberturas generales, procedimientos estándar o dudas teóricas,
        y NO sobre un expediente específico."""
        sub_payload = {
            "mensaje": query,
            "session": session
        }
        result = generic_knowledge_agent(sub_payload)
        return result.get("message", "No pude obtener respuesta del experto.")

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
        company_id=company_id,
        wa_id=wa_id or ''
    )

    task_done = task_tool_already_called(memory, AGENT_NAME)
    if task_done:
        system_prompt += _TASK_DONE_SUFFIX
        logger.info("[CONSULTA_ESTADO_AGENT] Task already created — restricting tools")

    llm = get_llm()

    tools = [
        get_claims_tool,
        end_chat_tool,
        redirect_to_receptionist_tool,
        ask_expert_knowledge,
    ]
    if not task_done:
        tools.insert(3, create_task_activity_tool)
    
    agent = create_langchain_agent(llm, tools, system_prompt)
    result = run_langchain_agent(agent, user_text, history, agent_name="consulta_estado_agent")
    
    output_text = result.get("output", "")
    action = result.get("action", "ask")
    tool_calls = result.get("tool_calls")

    if not task_done:
        updated_tool_calls = auto_create_task_if_needed(
            tool_calls, output_text,
            company_id=company_id, nif_value=nif or "NO_IDENTIFICADO", wa_id=wa_id or "",
            title="Consulta Estado Siniestro",
            description=f"Cliente consulta estado de siniestro. NIF: {nif or 'NO_IDENTIFICADO'}.",
            activity_title="Llamar para informar estado siniestro",
            agent_label="CONSULTA_ESTADO_AGENT",
        )
        if updated_tool_calls:
            result["tool_calls"] = updated_tool_calls
            tool_calls = updated_tool_calls

    if task_done:
        forced = force_redirect_if_task_done(output_text, action, tool_calls)
        if forced:
            logger.info("[CONSULTA_ESTADO_AGENT] Task done & LLM didn't redirect — forcing redirect")
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

    return {
        "action": action,
        "message": output_text,
        "tool_calls": tool_calls
    }
