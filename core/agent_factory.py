"""Centralized LangChain 1.x agent creation and execution."""
import logging
from typing import Any, Dict, List, Optional, Union

from langchain.agents import create_agent, AgentState
from langchain.tools import BaseTool
from langchain.messages import HumanMessage, AIMessage, SystemMessage

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
    
    return agent


def run_langchain_agent(
    agent,
    user_text: str,
    history: Optional[List] = None,
    **invoke_kwargs
) -> Dict[str, Any]:
    """
    Execute a LangChain 1.x agent with standardized input handling.
    
    Args:
        agent: The LangChain agent to execute
        user_text: User's input text
        history: Optional conversation history as list of message tuples
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
    
    # Invoke agent
    try:
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
        
        # Check if any tool returned end_chat action
        if isinstance(result, dict):
            for msg in result.get("messages", []):
                if hasattr(msg, 'tool_calls'):
                    for tool_call in (msg.tool_calls or []):
                        if tool_call.get("name") == "end_chat_tool":
                            action = "end_chat"
                            break
                # Check tool messages for end_chat
                if hasattr(msg, 'content'):
                    msg_text = _extract_text_from_content(msg.content)
                    if '"action": "end_chat"' in msg_text:
                        action = "end_chat"
        
        # Final check: if output contains the exact end_chat message patterns
        if isinstance(output, str) and "Fue un placer ayudarte" in output and "excelente día" in output:
            logger.info(f"[AGENT_FACTORY] Detected end_chat by message pattern")
            action = "end_chat"
        
        if action == "end_chat":
            logger.info(f"[AGENT_FACTORY] ✓ end_chat detected!")
        
        return {
            "output": output,
            "action": action
        }
        
    except Exception as e:
        logger.error(f"[AGENT_FACTORY] Error invoking agent: {e}")
        raise
