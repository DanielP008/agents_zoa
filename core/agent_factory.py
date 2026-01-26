"""
Centralized LangChain agent creation and execution.
Reduces boilerplate and ensures consistent configuration.
"""
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
    """
    Create a LangChain tool-calling agent with consistent configuration.
    Automatically adds agent_scratchpad if missing from prompt.

    Args:
        llm: The language model to use
        tools: List of tools available to the agent
        prompt: The prompt template for the agent
        user_input_key: Key for user input in prompt (default: "user_text")
        verbose: Whether to enable verbose logging
        **executor_kwargs: Additional arguments for AgentExecutor

    Returns:
        Configured AgentExecutor instance
    """
    # Ensure prompt has agent_scratchpad (required by create_tool_calling_agent)
    prompt_variables = prompt.input_variables
    if "agent_scratchpad" not in prompt_variables:
        # If it's a ChatPromptTemplate, add MessagesPlaceholder for agent_scratchpad
        if isinstance(prompt, ChatPromptTemplate):
            messages = list(prompt.messages)
            messages.append(MessagesPlaceholder(variable_name="agent_scratchpad"))
            prompt = ChatPromptTemplate.from_messages(messages)
        else:
            # For other prompt types, log warning and let LangChain handle it
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
    """
    Execute a LangChain agent with standardized input handling.

    Args:
        agent_executor: The configured AgentExecutor
        user_text: The user's input text
        user_input_key: Key for user input in invoke dict
        **invoke_kwargs: Additional arguments for invoke

    Returns:
        Agent execution result
    """
    invoke_data = {user_input_key: user_text}
    invoke_data.update(invoke_kwargs)

    return agent_executor.invoke(invoke_data)