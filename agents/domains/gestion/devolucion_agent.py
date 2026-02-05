"""Devolucion agent for LangChain 1.x."""
from core.agent_factory import create_langchain_agent, run_langchain_agent
from core.memory_schema import get_global_history
from core.llm import get_llm
from tools.communication.end_chat_tool import end_chat_tool
from tools.zoa.tasks import create_task_activity_tool
from tools.erp.erp_tools import (
    get_client_policys_tool,
    get_policy_document_tool,
)
from agents.domains.gestion.devolucion_agent_prompts import get_prompt

def devolucion_agent(payload: dict) -> dict:
   user_text = payload.get("mensaje", "")
   session = payload.get("session", {})
   memory = session.get("agent_memory", {})
   history = get_global_history(memory)
   
   company_id = payload.get("phone_number_id") or session.get("company_id", "")
   global_mem = memory.get("global", {})
   nif_value = global_mem.get("nif") or ""
   wa_id = payload.get("wa_id") or ""

   # Get prompt based on channel and format with variables
   channel = payload.get("channel", "whatsapp")
   system_prompt = get_prompt(channel).format(
      nif_value=nif_value,
      company_id=company_id,
      wa_id=wa_id
   )

   llm = get_llm()
   tools = [create_task_activity_tool, end_chat_tool, get_client_policys_tool, get_policy_document_tool]
   
   agent = create_langchain_agent(llm, tools, system_prompt)
   result = run_langchain_agent(agent, user_text, history)
   
   output_text = result.get("output", "")
   action = result.get("action", "ask")

   return {
      "action": action,
      "message": output_text
   }
