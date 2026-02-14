"""Venta cruzada agent for LangChain 1.x."""
from infra.agent_runner import create_langchain_agent, run_langchain_agent
from core.memory import get_global_history

from infra.llm import get_llm
from tools.communication.end_chat_tool import end_chat_tool
from tools.communication.redirect_to_receptionist_tool import redirect_to_receptionist_tool
from tools.sales.cross_sell_tool import get_customer_policies_tool, create_cross_sell_offer_tool
from agents.domains.ventas.venta_cruzada_agent_prompts import get_prompt

def venta_cruzada_agent(payload: dict) -> dict:
    user_text = payload.get("mensaje", "")
    session = payload.get("session", {})
    memory = session.get("agent_memory", {})
    history = get_global_history(memory)

    # Get prompt based on channel
    channel = payload.get("channel", "whatsapp")
    system_prompt = get_prompt(channel)

    llm = get_llm()
    tools = [get_customer_policies_tool, create_cross_sell_offer_tool, end_chat_tool, redirect_to_receptionist_tool]
    
    agent = create_langchain_agent(llm, tools, system_prompt)
    result = run_langchain_agent(agent, user_text, history, agent_name="venta_cruzada_agent")
    
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

    return {
        "action": action,
        "message": output_text,
        "tool_calls": tool_calls
    }
