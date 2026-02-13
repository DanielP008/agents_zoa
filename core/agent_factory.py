"""Centralized LangChain 1.x agent creation and execution."""
import logging
from typing import Any, Dict, List, Optional, Union

from langchain.agents import create_agent, AgentState
from langchain.tools import BaseTool
from langchain.messages import HumanMessage, AIMessage, SystemMessage, ToolMessage
from core.timing import Timer, set_current_agent

logger = logging.getLogger(__name__)
def _extract_text_from_content(content: Any) -> str:
    """
    Extract text from LangChain 1.x content which can be:
    - A simple string
    - A list of content blocks (new format with 'type' and 'text' keys)
    """
    if isinstance(content, str):
        return content
    
    if isinstance(content, list):
        # New LangChain 1.x content blocks format
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
    """
    Create a LangChain 1.x agent.
    
    Args:
        llm: Language model (ChatGoogleGenerativeAI instance or model string)
        tools: List of tools available to the agent
        system_prompt: System prompt string for the agent
        **agent_kwargs: Additional arguments for create_agent
    
    Returns:
        A LangChain agent instance
    """
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
def run_langchain_agent(
    agent,
    user_text: str,
    history: Optional[List] = None,
    agent_name: str = "unknown_agent",
    **invoke_kwargs
) -> Dict[str, Any]:
    """
    Execute a LangChain 1.x agent with standardized input handling.
    
    Args:
        agent: The LangChain agent to execute
        user_text: User's input text
        history: Optional conversation history as list of message tuples
        agent_name: Name of the agent (for timing/profiling)
        **invoke_kwargs: Additional arguments for invoke
    
    Returns:
        Dict with 'output' and 'action' keys
    """
    # Build messages from history
    messages = []
    
    if history:
        for msg_type, content in history:
            if msg_type == "human":
                messages.append({"role": "user", "content": content})
            elif msg_type == "ai":
                messages.append({"role": "assistant", "content": content})
    
    # Add current user message
    messages.append({"role": "user", "content": user_text})
    
    # Set current agent for tool-level timing parent tracking
    set_current_agent(agent_name)
    
    # Invoke agent with timing
    try:
        model_name_str = getattr(agent, "_llm_model_name", "")
             
        with Timer("agent", agent_name, model=model_name_str):
            result = agent.invoke({"messages": messages}, **invoke_kwargs)
        
        logger.info(f"[AGENT_FACTORY] Agent result type: {type(result)}")
        
        # Extract output from result
        output = ""
        if isinstance(result, dict):
            # New format: result contains messages
            result_messages = result.get("messages", [])
            if result_messages:
                last_message = result_messages[-1]
                if hasattr(last_message, 'content'):
                    # Handle both string and content blocks format
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
        
        logger.info(f"[AGENT_FACTORY] Agent output: {output[:100]}...")
        
        # Check for end_chat pattern in the result
        action = "ask"
        tool_calls_executed = []  # Track all tool calls made during this turn
        
        # Check if any tool returned end_chat or redirect action
        if isinstance(result, dict):
            # Prefer the ToolMessage content if end_chat_tool or redirect_to_receptionist_tool was called.
            end_chat_tool_message_text: Optional[str] = None
            redirect_tool_message_text: Optional[str] = None
            ai_message_text: Optional[str] = None
            
            for i, msg in enumerate(result.get("messages", [])):
                # Check for AIMessage that calls the tool
                if hasattr(msg, 'tool_calls'):
                    for tool_call in (msg.tool_calls or []):
                        # Track all tool calls
                        tool_calls_executed.append({
                            "name": tool_call.get("name"),
                            "args": tool_call.get("args", {})
                        })
                        
                        tool_name = tool_call.get("name")
                        if tool_name == "end_chat_tool":
                            action = "end_chat"
                        elif tool_name == "redirect_to_receptionist_tool":
                            # We keep action as "ask" but ensure the flag is in output
                            pass

                        # Capture the text content of this AIMessage if it exists
                        if hasattr(msg, 'content') and msg.content:
                            ai_message_text = _extract_text_from_content(msg.content)
                
                # ToolMessage path
                if isinstance(msg, ToolMessage):
                    tool_name = getattr(msg, "name", None)
                    if tool_name == "end_chat_tool":
                        end_chat_tool_message_text = _extract_text_from_content(msg.content)
                        action = "end_chat"
                    elif tool_name == "redirect_to_receptionist_tool":
                        redirect_tool_message_text = _extract_text_from_content(msg.content)
                        # We don't change action to route here yet, 
                        # let the agent handle it via the __REDIRECT_TO_RECEPTIONIST__ flag
                        continue

                # Check tool messages for end_chat pattern manually
                if hasattr(msg, 'content'):
                    msg_text = _extract_text_from_content(msg.content)
                    if '"action": "end_chat"' in msg_text:
                        action = "end_chat"

            # DECISION LOGIC FOR OUTPUT:
            if action == "end_chat":
                parts = []
                if ai_message_text and ai_message_text.strip():
                    parts.append(ai_message_text.strip())
                if end_chat_tool_message_text and end_chat_tool_message_text.strip():
                    parts.append(end_chat_tool_message_text.strip())
                
                if parts:
                    output = "\n\n".join(parts)
                    logger.info(f"[AGENT_FACTORY] Combined output for end_chat: {output[:50]}...")
            
            elif redirect_tool_message_text:
                # Ensure the redirect flag is preserved even if the AI added more text
                if redirect_tool_message_text not in output:
                    output = f"{output}\n\n{redirect_tool_message_text}".strip()
                    logger.info(f"[AGENT_FACTORY] Appended redirect flag to output")
        
        # Log tool calls if any
        if tool_calls_executed:
            logger.info(f"[AGENT_FACTORY] Tool calls executed: {[tc['name'] for tc in tool_calls_executed]}")
        
        # Final check: if output contains the exact end_chat message patterns
        if isinstance(output, str) and "Fue un placer ayudarte" in output and "excelente día" in output:
            logger.info(f"[AGENT_FACTORY] Detected end_chat by message pattern")
            action = "end_chat"
        
        if action == "end_chat":
            logger.info(f"[AGENT_FACTORY] ✓ end_chat detected!")
        
        return {
            "output": output,
            "action": action,
            "tool_calls": tool_calls_executed if tool_calls_executed else None
        }
        
    except Exception as e:
        logger.error(f"[AGENT_FACTORY] Error invoking agent: {e}")
        raise
