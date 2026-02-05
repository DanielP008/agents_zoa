import json
from datetime import datetime
from core.agent_factory import create_langchain_agent, run_langchain_agent
from core.memory_schema import get_global_history

from core.llm import get_llm
from tools.zoa.tasks import create_task_activity_tool
from tools.communication.end_chat_tool import end_chat_tool
from agents.domains.siniestros.apertura_siniestro_agent_prompts import get_prompt
def apertura_siniestro_agent(payload: dict) -> dict:
    user_text = payload.get("mensaje", "")
    session = payload.get("session", {})
    memory = session.get("agent_memory", {})
    history = get_global_history(memory)
    
    company_id = payload.get("phone_number_id") or session.get("company_id", "")
    wa_id = payload.get("wa_id")
    global_mem = memory.get("global", {})
    nif_value = global_mem.get("nif") or "NO_IDENTIFICADO"
    
    # DEBUG: Print memory and history before agent execution
    print("\n" + "="*60)
    print("🔍 DEBUG APERTURA_SINIESTRO_AGENT")
    print("="*60)
    print(f"📨 User text: {user_text}")
    print(f"\n📦 Memory completa:")
    print(json.dumps(memory, indent=2, default=str, ensure_ascii=False))
    print(f"\n📜 History (lo que ve el agente):")
    for i, msg in enumerate(history):
        # Handle both tuple format (role, content) and object format
        if isinstance(msg, tuple):
            role, content = msg[0], msg[1] if len(msg) > 1 else ""
            content_str = str(content)
            print(f"  [{i}] {role}: {content_str[:200]}..." if len(content_str) > 200 else f"  [{i}] {role}: {content_str}")
        else:
            content_str = str(getattr(msg, 'content', msg))
            msg_type = getattr(msg, 'type', 'unknown')
            print(f"  [{i}] {msg_type}: {content_str[:200]}..." if len(content_str) > 200 else f"  [{i}] {msg_type}: {content_str}")
    print("="*60 + "\n")
    
    # Get current date/time for context
    now = datetime.now()
    current_date = now.strftime("%d/%m/%Y")
    current_time = now.strftime("%H:%M")
    current_year = now.year

    # Get prompt based on channel and format with variables
    channel = payload.get("channel", "whatsapp")
    system_prompt = get_prompt(channel).format(
        current_date=current_date,
        current_time=current_time,
        current_year=current_year,
        company_id=company_id,
        nif_value=nif_value,
        wa_id=wa_id or 'NO_DISPONIBLE'
    )

    llm = get_llm()
    tools = [create_task_activity_tool, end_chat_tool]
    
    agent = create_langchain_agent(llm, tools, system_prompt)
    result = run_langchain_agent(agent, user_text, history)
    
    # DEBUG: Print result
    print("\n" + "="*60)
    print("🔍 DEBUG RESULT APERTURA_SINIESTRO_AGENT")
    print("="*60)
    print(f"📤 Result: {json.dumps(result, indent=2, default=str, ensure_ascii=False)}")
    print("="*60 + "\n")
    
    output_text = result.get("output", "")
    action = result.get("action", "ask")
    tool_calls = result.get("tool_calls")

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
