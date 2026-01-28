"""Centralized LangChain agent creation and execution."""
import logging
from typing import Any, Dict, List, Optional

from langchain.agents.agent import AgentExecutor
from langchain.agents.tool_calling_agent.base import create_tool_calling_agent
from langchain_core.language_models import BaseLanguageModel
from langchain_core.prompts import BasePromptTemplate, ChatPromptTemplate, MessagesPlaceholder
from langchain_core.tools import BaseTool

logger = logging.getLogger(__name__)


def create_langchain_agent(
    llm: BaseLanguageModel,
    tools: List[BaseTool],
    prompt: BasePromptTemplate,
    user_input_key: str = "user_text",
    verbose: bool = False,
    **executor_kwargs
) -> AgentExecutor:
    """Create a LangChain tool-calling agent."""
    prompt_variables = prompt.input_variables
    if "agent_scratchpad" not in prompt_variables:
        if isinstance(prompt, ChatPromptTemplate):
            messages = list(prompt.messages)
            messages.append(MessagesPlaceholder(variable_name="agent_scratchpad"))
            prompt = ChatPromptTemplate.from_messages(messages)
        else:
            logger.warning("Prompt does not have agent_scratchpad and is not ChatPromptTemplate. LangChain may fail.")
    
    agent = create_tool_calling_agent(llm, tools, prompt)
    return AgentExecutor(
        agent=agent,
        tools=tools,
        verbose=verbose,
        **executor_kwargs
    )


def run_langchain_agent(
    agent_executor: AgentExecutor,
    user_text: str,
    user_input_key: str = "user_text",
    **invoke_kwargs
) -> Dict[str, Any]:
    """Execute a LangChain agent with standardized input handling."""
    invoke_data = {user_input_key: user_text}
    invoke_data.update(invoke_kwargs)

    result = agent_executor.invoke(invoke_data)

    intermediate_steps = result.get("intermediate_steps", [])
    
    for step in intermediate_steps:
        try:
            if isinstance(step, tuple) and len(step) >= 2:
                agent_action, tool_result = step[0], step[1]
                
                tool_name = None
                
                if hasattr(agent_action, 'tool'):
                    tool_name = agent_action.tool
                
                if not tool_name and hasattr(agent_action, 'tool_input'):
                    tool_input = agent_action.tool_input
                    if isinstance(tool_input, dict) and 'tool' in tool_input:
                        tool_name = tool_input['tool']
                
                if not tool_name:
                    action_str = str(agent_action)
                    if 'end_chat_tool' in action_str.lower():
                        tool_name = 'end_chat_tool'
                
                if not tool_name and isinstance(tool_result, dict):
                    if 'action' in tool_result and tool_result.get('action') == 'end_chat':
                        tool_name = 'end_chat_tool'
                
                if tool_name == 'end_chat_tool':
                    message = tool_result.get("message", "Conversación finalizada.") if isinstance(tool_result, dict) else "Conversación finalizada."
                    logger.info(f"end_chat_tool detected! Returning action='end_chat' with message: {message}")
                    return {
                        "output": message,
                        "action": "end_chat",
                        "tool_used": "end_chat_tool"
                    }
        except Exception as e:
            logger.warning(f"Error checking intermediate step for end_chat_tool: {e}")
            continue

    return result