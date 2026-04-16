import logging
from datetime import datetime
from infra.agent_runner import create_langchain_agent, run_langchain_agent
from core.agent_safeguards import task_tool_already_called, _TASK_DONE_SUFFIX, auto_create_task_if_needed, force_redirect_if_task_done
from core.memory import get_global_history

from infra.llm import get_llm
from tools.zoa.tasks_tool import create_task_activity_tool
from tools.communication.end_chat_tool import end_chat_tool
from tools.communication.redirect_to_receptionist_tool import redirect_to_receptionist_tool
from agents.domains.siniestros.apertura_siniestro_agent_prompts import get_prompt

logger = logging.getLogger(__name__)

AGENT_NAME = "apertura_siniestro_agent"


def apertura_siniestro_agent(payload: dict) -> dict:
    user_text = payload.get("mensaje", "")
    session = payload.get("session", {})
    memory = session.get("agent_memory", {})
    history = get_global_history(memory)
    
    company_id = payload.get("phone_number_id") or session.get("company_id", "")
    wa_id = payload.get("wa_id")
    global_mem = memory.get("global", {})
    nif_value = global_mem.get("nif") or "NO_IDENTIFICADO"
    
    now = datetime.now()
    current_date = now.strftime("%d/%m/%Y")
    current_time = now.strftime("%H:%M")
    current_year = now.year

    channel = payload.get("channel", "whatsapp")
    system_prompt = get_prompt(channel).format(
        current_date=current_date,
        current_time=current_time,
        current_year=current_year,
        company_id=company_id,
        nif_value=nif_value,
        wa_id=wa_id or 'NO_DISPONIBLE'
    )

    task_done = task_tool_already_called(memory, AGENT_NAME)
    if task_done:
        system_prompt += _TASK_DONE_SUFFIX
        logger.info("[APERTURA_AGENT] Task already created — restricting tools")

    llm = get_llm()
    tools = [end_chat_tool, redirect_to_receptionist_tool]
    if not task_done:
        tools.insert(0, create_task_activity_tool)
    
    agent = create_langchain_agent(llm, tools, system_prompt)
    result = run_langchain_agent(agent, user_text, history, agent_name="apertura_siniestro_agent")
    
    output_text = result.get("output", "")
    action = result.get("action", "ask")
    tool_calls = result.get("tool_calls")

    if not task_done:
        updated_tool_calls = auto_create_task_if_needed(
            tool_calls, output_text,
            company_id=company_id, nif_value=nif_value, wa_id=wa_id,
            title="Apertura Siniestro - Registro Automático",
            description=f"Apertura de siniestro reportada por el cliente. NIF: {nif_value}.",
            activity_title="Gestionar apertura siniestro",
            activity_description="Contactar cliente para finalizar apertura de siniestro.",
            agent_label="APERTURA_AGENT",
        )
        if updated_tool_calls:
            result["tool_calls"] = updated_tool_calls
            tool_calls = updated_tool_calls

    if task_done:
        forced = force_redirect_if_task_done(output_text, action, tool_calls)
        if forced:
            logger.info("[APERTURA_AGENT] Task done & LLM didn't redirect — forcing redirect")
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
