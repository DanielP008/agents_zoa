from infra.agent_runner import create_langchain_agent, run_langchain_agent
from infra.llm import get_llm_fast
from tools.communication.end_chat_tool import end_chat_tool
from agents.domains.common.generic_knowledge_agent_prompts import get_prompt

def generic_knowledge_agent(payload: dict) -> dict:
    """
    Expert agent in general insurance knowledge.
    Can be instantiated by other agents to answer generic questions.
    """
    user_text = payload.get("mensaje", "")
    session = payload.get("session", {})
    
    # Get prompt based on channel
    channel = payload.get("channel", "whatsapp")
    system_prompt = get_prompt(channel)

    llm = get_llm_fast()
    tools = [end_chat_tool]
    
    agent = create_langchain_agent(llm, tools, system_prompt)
    result = run_langchain_agent(agent, user_text, agent_name="generic_knowledge_agent")
    
    output_text = result.get("output", "")
    action = result.get("action", "answer")

    if action == "end_chat":
        return {
            "action": "end_chat",
            "message": output_text
        }

    return {
        "action": "answer",
        "message": output_text
    }
