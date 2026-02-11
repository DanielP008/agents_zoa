"""Modificar poliza agent for LangChain 1.x."""
from core.agent_factory import create_langchain_agent, run_langchain_agent
from core.memory_schema import get_global_history
from core.llm import get_llm
from tools.zoa.tasks_tool import create_task_activity_tool
from tools.communication.end_chat_tool import end_chat_tool
from tools.communication.redirect_to_receptionist_tool import redirect_to_receptionist_tool
from tools.erp.erp_tool import (get_client_policys_tool, get_policy_document_tool)
from agents.domains.gestion.modificar_poliza_agent_prompts import get_prompt

def modificar_poliza_agent(payload: dict) -> dict:
    user_text = payload.get("mensaje", "")
    session = payload.get("session", {})
    memory = session.get("agent_memory", {})
    history = get_global_history(memory)
    
    company_id = payload.get("phone_number_id") or session.get("company_id", "")
    global_mem = memory.get("global", {})
    nif_value = global_mem.get("nif") or "NO_IDENTIFICADO"
    wa_id = payload.get("wa_id") or ""

    # Get prompt based on channel and format with variables
    channel = payload.get("channel", "whatsapp")
    system_prompt = get_prompt(channel).format(
        nif_value=nif_value,
        company_id=company_id,
        wa_id=wa_id
    )

    llm = get_llm()
    tools = [create_task_activity_tool, end_chat_tool, redirect_to_receptionist_tool, get_client_policys_tool, get_policy_document_tool]
    
    agent = create_langchain_agent(llm, tools, system_prompt)
    result = run_langchain_agent(agent, user_text, history, agent_name="modificar_poliza_agent")
    
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

    if "actualizada" in output_text.lower() or "modificada" in output_text.lower():
        action = "finish"

    return {
        "action": action,
        "message": output_text,
        "tool_calls": tool_calls
    }
