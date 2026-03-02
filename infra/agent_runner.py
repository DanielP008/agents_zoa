"""Centralized LangChain 1.x agent creation and execution."""

import contextvars
import logging
import re
from typing import Any, Dict, List, Optional

from langchain.agents import create_agent, AgentState
from langchain_core.callbacks import BaseCallbackHandler
from langchain.messages import HumanMessage, AIMessage, SystemMessage, ToolMessage
from langchain.tools import BaseTool

from infra.timing import Timer, set_current_agent

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# "Please wait" message — sent once per request on first qualifying tool call
# ---------------------------------------------------------------------------
_WAIT_MESSAGE = (
    "Vale, voy a revisar tu ficha de cliente. "
    "Por favor espera unos segundos y te contesto enseguida."
)
_EXCLUDED_TOOLS = frozenset({
    "end_chat_tool",
    "redirect_to_receptionist_tool",
    "send_whatsapp_tool",
})

# Context vars — set by the orchestrator before invoking the agent chain
_wa_id: contextvars.ContextVar[str] = contextvars.ContextVar("_wa_id", default="")
_phone_number_id: contextvars.ContextVar[str] = contextvars.ContextVar("_phone_number_id", default="")
_wa_channel: contextvars.ContextVar[str] = contextvars.ContextVar("_wa_channel", default="")
_wait_msg_sent: contextvars.ContextVar[bool] = contextvars.ContextVar("_wait_msg_sent", default=False)
_client_name: contextvars.ContextVar[str] = contextvars.ContextVar("_client_name", default="")


def set_wa_context(wa_id: str, phone_number_id: str, channel: str, client_name: str = "") -> None:
    """Set WhatsApp context for the current request (called by orchestrator)."""
    _wa_id.set(wa_id or "")
    _phone_number_id.set(phone_number_id or "")
    _wa_channel.set(channel or "")
    _wait_msg_sent.set(False)
    _client_name.set(client_name or "")


def get_client_name() -> str:
    """Return the OCR-extracted client name for the current request."""
    return _client_name.get()


class _WaitMessageCallback(BaseCallbackHandler):
    """Sends a 'please wait' WhatsApp message on the first qualifying tool call."""

    def on_tool_start(self, serialized: Dict[str, Any], input_str: str, **kwargs) -> None:
        tool_name = serialized.get("name", "")
        if tool_name in _EXCLUDED_TOOLS:
            return
        if _wait_msg_sent.get(False):
            return

        wa_id = _wa_id.get("")
        phone_id = _phone_number_id.get("")
        channel = _wa_channel.get("")

        if not wa_id or not phone_id or channel != "whatsapp":
            return

        _wait_msg_sent.set(True)
        try:
            from services.zoa_client import send_whatsapp_response
            send_whatsapp_response(text=_WAIT_MESSAGE, company_id=phone_id, wa_id=wa_id)
            logger.info(f"[AGENT_RUNNER] Wait message sent to {wa_id}")
        except Exception:
            logger.exception("[AGENT_RUNNER] Failed to send wait message")


def task_tool_already_called(memory: dict, agent_name: str) -> bool:
    """Return True if create_task_activity_tool was already invoked by *agent_name*
    in the CURRENT activation (i.e. since the last turn handled by a different agent).

    When the user returns to the same agent after visiting others, we treat it as
    a fresh consultation so a new task can be created for the new request.
    """
    for turn in reversed(memory.get("conversation_history", [])):
        if turn.get("agent") != agent_name:
            return False
        for tc in (turn.get("tool_calls") or []):
            if tc.get("name") == "create_task_activity_tool":
                return True
    return False


_TASK_DONE_SUFFIX = (
    "\n\n[SISTEMA] La tarea YA FUE CREADA anteriormente. "
    "NO crees otra tarea. Solo tienes dos opciones:\n"
    "- Si el cliente quiere algo más → usa redirect_to_receptionist_tool\n"
    "- Si el cliente no necesita nada más → usa end_chat_tool"
)


_CALLBACK_HINTS = (
    "no he encontrado", "no encontré", "no hay teléfonos", "no se encontraron",
    "compañero te llame", "pedir que", "gestor se ponga en contacto",
    "registrar tu consulta", "registrar tu solicitud", "voy a registrar",
    "te llame mañana", "te llamará", "pondrá en contacto",
    "gestor revisará", "ya está anotado", "siniestro registrado",
    "he registrado", "un compañero", "contacto contigo",
)


def auto_create_task_if_needed(
    tool_calls,
    output_text: str,
    *,
    company_id: str,
    nif_value: str,
    wa_id: str,
    title: str,
    description: str,
    activity_title: str = "Llamar al cliente",
    activity_description: str = "",
    agent_label: str = "AGENT",
    client_name: str = "",
):
    """Create a CRM task if the agent promises a callback but didn't call create_task_activity_tool.

    Returns the updated tool_calls list if a task was created, or None if nothing was done.
    The caller MUST update result["tool_calls"] with the return value when not None.
    """
    tc_names = {tc["name"] for tc in (tool_calls or [])}
    if "create_task_activity_tool" in tc_names:
        return None

    output_lower = output_text.lower()
    if not any(hint in output_lower for hint in _CALLBACK_HINTS):
        return None

    resolved_name = client_name or _client_name.get()
    task_payload = {
        "company_id": company_id,
        "title": title,
        "description": description,
        "card_type": "task",
        "pipeline_name": "Cotizaciones",
        "type_of_activity": "llamada",
        "activity_title": activity_title,
        "phone": wa_id,
    }
    if resolved_name:
        task_payload["name"] = resolved_name
    if activity_description:
        task_payload["activity_description"] = activity_description

    try:
        from services.zoa_client import create_task_activity
        result = create_task_activity(**task_payload)
        logger.info(f"[{agent_label}] Auto-created task (LLM missed it): {result}")
        if tool_calls is None:
            tool_calls = []
        tool_calls.append({"name": "create_task_activity_tool", "args": task_payload})
        return tool_calls
    except Exception as e:
        logger.error(f"[{agent_label}] Auto-create task failed: {e}")
        return tool_calls


def force_redirect_if_task_done(output_text: str, action: str, tool_calls) -> dict | None:
    """When task_done=True but the LLM didn't redirect/end, force a redirect.

    Returns a response dict to return immediately, or None if no override needed.
    """
    if action in ("end_chat",):
        return None
    if "__REDIRECT_TO_RECEPTIONIST__" in (output_text or ""):
        return None

    tc_names = {tc["name"] for tc in (tool_calls or [])}
    if "redirect_to_receptionist_tool" in tc_names or "end_chat_tool" in tc_names:
        return None

    return {
        "action": "route",
        "next_agent": "receptionist_agent",
        "domain": None,
        "message": output_text,
        "tool_calls": tool_calls,
    }


def _extract_text_from_content(content: Any) -> str:
    """Extract text from LangChain 1.x content (string or content blocks list)."""
    if isinstance(content, str):
        return content

    if isinstance(content, list):
        text_parts = []
        for block in content:
            if isinstance(block, dict):
                if block.get("type") == "text":
                    text_parts.append(block.get("text", ""))
                elif "text" in block:
                    text_parts.append(block["text"])
            elif isinstance(block, str):
                text_parts.append(block)
        return " ".join(text_parts).strip()

    return str(content) if content else ""


def create_langchain_agent(
    llm: Any,
    tools: List[BaseTool],
    system_prompt: str,
    **agent_kwargs
):
    """Create a LangChain 1.x agent."""
    if hasattr(llm, 'model'):
        model = llm
    else:
        model = llm

    agent = create_agent(
        model=model,
        tools=tools,
        system_prompt=system_prompt,
        **agent_kwargs
    )

    # Store model name for timing/profiling
    agent._llm_model_name = getattr(llm, "model_name", "") or getattr(llm, "model", "") or ""

    return agent


_EMPTY_RESPONSE_FALLBACK = (
    "Disculpa, tuve un problema procesando tu mensaje. ¿Podrías repetirlo?"
)
_MAX_EMPTY_RETRIES = 2


def run_langchain_agent(
    agent,
    user_text: str,
    history: Optional[List] = None,
    agent_name: str = "unknown_agent",
    **invoke_kwargs
) -> Dict[str, Any]:
    """Execute a LangChain 1.x agent with standardized input handling.

    Returns:
        Dict with 'output', 'action', and 'tool_calls' keys.
    """
    # Build messages from history
    messages = []

    if history:
        for msg_type, content in history:
            if msg_type == "human":
                messages.append({"role": "user", "content": content})
            elif msg_type == "ai":
                messages.append({"role": "assistant", "content": content})

    messages.append({"role": "user", "content": user_text})

    # Set current agent for tool-level timing parent tracking
    set_current_agent(agent_name)

    try:
        model_name_str = getattr(agent, "_llm_model_name", "")

        # Inject wait-message callback if WhatsApp context is active
        config = invoke_kwargs.pop("config", {})
        callbacks = list(config.get("callbacks", []))
        if _wa_id.get("") and _phone_number_id.get("") and _wa_channel.get("") == "whatsapp":
            callbacks.append(_WaitMessageCallback())
        if callbacks:
            config["callbacks"] = callbacks
        if config:
            invoke_kwargs["config"] = config

        with Timer("agent", agent_name, model=model_name_str):
            result = agent.invoke({"messages": messages}, **invoke_kwargs)

        logger.info(f"[AGENT_RUNNER] Agent result type: {type(result)}")

        # Extract output from result
        output = ""
        if isinstance(result, dict):
            result_messages = result.get("messages", [])
            if result_messages:
                last_message = result_messages[-1]
                if hasattr(last_message, 'content'):
                    output = _extract_text_from_content(last_message.content)
                elif isinstance(last_message, dict):
                    raw_content = last_message.get("content", "")
                    output = _extract_text_from_content(raw_content)
            else:
                output = result.get("output", str(result))
        elif hasattr(result, 'content'):
            output = _extract_text_from_content(result.content)
        else:
            output = str(result)

        logger.info(f"[AGENT_RUNNER] Agent output: {output[:100]}...")

        # Detect action and collect tool calls
        action = "ask"
        tool_calls_executed = []

        if isinstance(result, dict):
            end_chat_tool_message_text: Optional[str] = None
            redirect_tool_message_text: Optional[str] = None
            ai_message_text: Optional[str] = None

            for msg in result.get("messages", []):
                if hasattr(msg, 'tool_calls'):
                    for tool_call in (msg.tool_calls or []):
                        tool_calls_executed.append({
                            "name": tool_call.get("name"),
                            "args": tool_call.get("args", {}),
                        })

                        tool_name = tool_call.get("name")
                        if tool_name == "end_chat_tool":
                            action = "end_chat"

                        if hasattr(msg, 'content') and msg.content:
                            ai_message_text = _extract_text_from_content(msg.content)

                if isinstance(msg, ToolMessage):
                    tool_name = getattr(msg, "name", None)
                    if tool_name == "end_chat_tool":
                        end_chat_tool_message_text = _extract_text_from_content(msg.content)
                        action = "end_chat"
                    elif tool_name == "redirect_to_receptionist_tool":
                        redirect_tool_message_text = _extract_text_from_content(msg.content)
                        continue
                    elif tool_name == "create_task_activity_tool":
                        # Skip adding the tool result to the final output text if it's a task creation
                        continue

                if hasattr(msg, 'content'):
                    msg_text = _extract_text_from_content(msg.content)
                    if '"action": "end_chat"' in msg_text:
                        action = "end_chat"

            # Assemble final output
            if action == "end_chat":
                parts = []
                if ai_message_text and ai_message_text.strip():
                    parts.append(ai_message_text.strip())
                if end_chat_tool_message_text and end_chat_tool_message_text.strip():
                    parts.append(end_chat_tool_message_text.strip())
                if parts:
                    output = "\n\n".join(parts)
                    logger.info(f"[AGENT_RUNNER] Combined output for end_chat: {output[:50]}...")

            elif redirect_tool_message_text:
                if redirect_tool_message_text not in output:
                    output = f"{output}\n\n{redirect_tool_message_text}".strip()
                    logger.info("[AGENT_RUNNER] Appended redirect flag to output")

        # Clean output from internal tool execution markers like [HERRAMIENTAS EJECUTADAS: ...]
        if isinstance(output, str):
            output = re.sub(r'\[HERRAMIENTAS EJECUTADAS:.*?\]', '', output).strip()

        # --- Empty response guard: retry once, then fallback ---
        if not output or not output.strip():
            logger.warning(
                f"[AGENT_RUNNER] Empty response from {agent_name}, retrying once..."
            )
            try:
                with Timer("agent", f"{agent_name}_retry", model=model_name_str):
                    retry_result = agent.invoke({"messages": messages}, **invoke_kwargs)
                
                retry_output = ""
                retry_action = "ask"
                retry_tool_calls = []

                if isinstance(retry_result, dict):
                    retry_msgs = retry_result.get("messages", [])
                    if retry_msgs:
                        last_msg = retry_msgs[-1]
                        retry_output = _extract_text_from_content(last_msg.content if hasattr(last_msg, 'content') else last_msg.get("content", ""))
                        
                        # Re-detect action and tool calls for retry
                        for msg in retry_msgs:
                            if hasattr(msg, 'tool_calls'):
                                for tc in (msg.tool_calls or []):
                                    retry_tool_calls.append({"name": tc.get("name"), "args": tc.get("args", {})})
                                    if tc.get("name") == "end_chat_tool": retry_action = "end_chat"
                elif hasattr(retry_result, 'content'):
                    retry_output = _extract_text_from_content(retry_result.content)

                if retry_output and retry_output.strip():
                    logger.info(f"[AGENT_RUNNER] Retry succeeded for {agent_name}")
                    output = retry_output
                    action = retry_action
                    if retry_tool_calls: tool_calls_executed = retry_tool_calls
                else:
                    logger.warning(f"[AGENT_RUNNER] Retry also empty for {agent_name}, using fallback")
                    output = _EMPTY_RESPONSE_FALLBACK
            except Exception as retry_err:
                logger.error(f"[AGENT_RUNNER] Retry failed for {agent_name}: {retry_err}")
                output = _EMPTY_RESPONSE_FALLBACK

        if tool_calls_executed:
            logger.info(f"[AGENT_RUNNER] Tool calls executed: {[tc['name'] for tc in tool_calls_executed]}")

        return {
            "output": output,
            "action": action,
            "tool_calls": tool_calls_executed if tool_calls_executed else None,
        }

    except Exception as e:
        logger.error(f"[AGENT_RUNNER] Error invoking agent: {e}")
        raise
