"""Centralized LangChain 1.x agent creation and execution."""

import contextvars
import logging
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


def set_wa_context(wa_id: str, phone_number_id: str, channel: str) -> None:
    """Set WhatsApp context for the current request (called by orchestrator)."""
    _wa_id.set(wa_id or "")
    _phone_number_id.set(phone_number_id or "")
    _wa_channel.set(channel or "")
    _wait_msg_sent.set(False)


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

        if tool_calls_executed:
            logger.info(f"[AGENT_RUNNER] Tool calls executed: {[tc['name'] for tc in tool_calls_executed]}")

        # Fallback pattern detection
        if isinstance(output, str) and "Fue un placer ayudarte" in output and "excelente día" in output:
            logger.info("[AGENT_RUNNER] Detected end_chat by message pattern")
            action = "end_chat"

        if action == "end_chat":
            logger.info("[AGENT_RUNNER] end_chat detected!")

        # --- Empty response guard: retry once, then fallback ---
        if not output or not output.strip():
            if not tool_calls_executed:
                logger.warning(
                    f"[AGENT_RUNNER] Empty response from {agent_name}, retrying once..."
                )
                try:
                    with Timer("agent", f"{agent_name}_retry", model=model_name_str):
                        retry_result = agent.invoke({"messages": messages}, **invoke_kwargs)
                    retry_output = ""
                    if isinstance(retry_result, dict):
                        retry_msgs = retry_result.get("messages", [])
                        if retry_msgs:
                            last_msg = retry_msgs[-1]
                            if hasattr(last_msg, 'content'):
                                retry_output = _extract_text_from_content(last_msg.content)
                            elif isinstance(last_msg, dict):
                                retry_output = _extract_text_from_content(last_msg.get("content", ""))
                    elif hasattr(retry_result, 'content'):
                        retry_output = _extract_text_from_content(retry_result.content)

                    if retry_output and retry_output.strip():
                        logger.info(f"[AGENT_RUNNER] Retry succeeded for {agent_name}")
                        output = retry_output
                    else:
                        logger.warning(f"[AGENT_RUNNER] Retry also empty for {agent_name}, using fallback")
                        output = _EMPTY_RESPONSE_FALLBACK
                except Exception as retry_err:
                    logger.error(f"[AGENT_RUNNER] Retry failed for {agent_name}: {retry_err}")
                    output = _EMPTY_RESPONSE_FALLBACK

        return {
            "output": output,
            "action": action,
            "tool_calls": tool_calls_executed if tool_calls_executed else None,
        }

    except Exception as e:
        logger.error(f"[AGENT_RUNNER] Error invoking agent: {e}")
        raise
