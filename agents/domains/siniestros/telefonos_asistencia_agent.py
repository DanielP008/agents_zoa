"""Telefonos asistencia agent for LangChain 1.x."""
import logging

from core.agent_factory import create_langchain_agent, run_langchain_agent
from core.memory_schema import get_global_history
from core.llm import get_llm_fast
from tools.communication.end_chat_tool import end_chat_tool
from tools.communication.redirect_to_receptionist_tool import redirect_to_receptionist_tool
from tools.communication.send_whatsapp_tool import send_whatsapp_tool
from tools.zoa.tasks import create_task_activity_tool
from tools.erp.erp_tools import get_assistance_phones
from agents.domains.siniestros.telefonos_asistencia_agent_prompts import get_prompt

logger = logging.getLogger(__name__)

def telefonos_asistencia_agent(payload: dict) -> dict:
   user_text = payload.get("mensaje", "")
   session = payload.get("session", {})
   memory = session.get("agent_memory", {})
   history = get_global_history(memory)
   company_id = payload.get("company_id") or session.get("company_id", "")
   wa_id = payload.get("wa_id") or ""
   global_mem = memory.get("global", {})
   nif_value = global_mem.get("nif") or "NO_IDENTIFICADO"

   # Get prompt based on channel and format with variables
   channel = payload.get("channel", "whatsapp")
   system_prompt = get_prompt(channel).format(
       nif_value=nif_value,
       company_id=company_id,
       wa_id=wa_id
   )

   llm = get_llm_fast()
   tools = [get_assistance_phones, create_task_activity_tool, end_chat_tool, redirect_to_receptionist_tool]
   
   # Add WhatsApp tool for phone calls so the agent can send numbers via message
   if channel in ("call", "wildix_voice"):
       tools.append(send_whatsapp_tool)
   
   agent = create_langchain_agent(llm, tools, system_prompt)
   result = run_langchain_agent(agent, user_text, history, agent_name="telefonos_asistencia_agent")
   
   output_text = result.get("output", "")
   action = result.get("action", "ask")
   tool_calls = result.get("tool_calls")

   logger.info(f"[TELEFONOS_AGENT] Result: action={action}, output={output_text[:100]}...")

   # Check if redirect to receptionist was triggered
   if "__REDIRECT_TO_RECEPTIONIST__" in output_text:
      return {"action": "route", "next_agent": "receptionist_agent", "message": "", "tool_calls": tool_calls}

   if action == "end_chat":
      logger.info(f"[TELEFONOS_AGENT] Returning end_chat action")
      return {"action": "end_chat", "message": output_text, "tool_calls": tool_calls}

   return {"action": action, "message": output_text, "tool_calls": tool_calls}