"""Wildix Card Agent — background processor for insurance tarification cards.

Receives concatenated call transcriptions from zoa_buffer, classifies them,
extracts insurance-relevant data, and creates/updates AI Chat cards via flow-zoa.
"""

import json
import logging
from datetime import datetime

from infra.agent_runner import create_langchain_agent, run_langchain_agent
from infra.llm import get_llm
from tools.sales.card_tools import (
    create_card_tool_wrapper,
    update_card_tool,
    get_card_state,
    reset_card_state,
    set_call_context,
)
from agents.domains.ventas.wildix_card_agent_prompts import get_wildix_card_prompt

logger = logging.getLogger(__name__)

AGENT_NAME = "wildix_card_agent"


def _build_card_state_text(memory_global: dict) -> str:
    """Build the card state string injected into the prompt."""
    ramo = memory_global.get("ramo_activo")
    created = memory_global.get("card_created", False)
    data = memory_global.get("card_data", {})

    if not ramo and not created:
        return "VACIO (no hay tarjeta creada todavía)"

    lines = [
        f"ramo_activo: {ramo}",
        f"card_created: {created}",
        f"card_data: {json.dumps(data, ensure_ascii=False)}",
    ]
    return "\n".join(lines)


def wildix_card_agent(payload: dict) -> dict:
    """Process a buffered call transcription and manage the tarification card.

    Args:
        payload: dict with keys: company_id, user_id, call_id, message,
                 session (dict with agent_memory)

    Returns:
        dict with estado, ramo, action, memory_patch
    """
    message = payload.get("message", "").strip()
    company_id = payload.get("company_id", "")
    user_id = payload.get("user_id", "")
    call_id = payload.get("call_id", "")

    session = payload.get("session", {})
    memory = session.get("agent_memory", {})
    if "global" not in memory:
        memory["global"] = {}
    global_mem = memory["global"]

    logger.info(
        f"[{AGENT_NAME}] Processing message ({len(message)} chars) for call={call_id}"
    )

    if not message:
        return {"action": "processed", "estado": "irrelevant", "ramo": None}

    card_state_text = _build_card_state_text(global_mem)
    current_date = datetime.now().strftime("%d/%m/%Y")

    prompt_template = get_wildix_card_prompt()
    system_prompt = prompt_template.format(
        current_date=current_date,
        company_id=company_id,
        user_id=user_id,
        call_id=call_id,
        card_state=card_state_text,
    )

    reset_card_state()
    set_call_context(company_id, user_id, call_id)

    llm = get_llm()
    
    # --- FAST PATH: Direct LLM Call (No Agent Loop) ---
    from langchain_core.messages import SystemMessage, HumanMessage
    
    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=message)
    ]
    
    try:
        # Force JSON output for speed and structure
        llm_response = llm.invoke(messages)
        content = llm_response.content
        
        # Clean up markdown code blocks if present
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0].strip()
        elif "```" in content:
            content = content.split("```")[1].split("```")[0].strip()
            
        parsed_result = json.loads(content)
        
        # Execute tool logic manually based on JSON response
        tool_action = parsed_result.get("tool_action") # "create", "update", or null
        tool_payload = parsed_result.get("tool_payload")
        
        tool_calls = []
        
        if tool_action == "create" and tool_payload:
            from tools.sales.card_tools import create_card_tool
            logger.info(f"[{AGENT_NAME}] Executing CREATE directly")
            create_card_tool(
                body_type=tool_payload.get("body_type"),
                data=tool_payload.get("data"),
                complete=tool_payload.get("complete", False)
            )
            tool_calls.append({"name": "create_card_tool", "args": tool_payload})
            
        elif tool_action == "update" and tool_payload:
            from tools.sales.card_tools import update_card_tool
            logger.info(f"[{AGENT_NAME}] Executing UPDATE directly")
            # The tool expects a JSON string wrapper because of the @tool decorator, 
            # but since we import the underlying function logic or wrapper, let's check card_tools.py
            # update_card_tool is a @tool wrapper that takes a string.
            # We should call the underlying logic if possible, or just call the wrapper with json string.
            update_card_tool(json.dumps(tool_payload)) 
            tool_calls.append({"name": "update_card_tool", "args": tool_payload})
            
        output_text = json.dumps(parsed_result)
        
    except Exception as e:
        logger.error(f"[{AGENT_NAME}] Fast path failed: {e}")
        output_text = "{}"
        tool_calls = []

    new_state = get_card_state()
    memory_patch = {}
    if new_state.get("ramo_activo"):
        global_mem["ramo_activo"] = new_state["ramo_activo"]
        global_mem["card_created"] = new_state["card_created"]
        global_mem["card_data"] = new_state["card_data"]
        memory_patch = {
            "global": {
                "ramo_activo": new_state["ramo_activo"],
                "card_created": new_state["card_created"],
                "card_data": new_state["card_data"],
            }
        }
        logger.info(f"[{AGENT_NAME}] Card state updated: ramo={new_state['ramo_activo']}, created={new_state['card_created']}")

    estado = "irrelevant"
    ramo = global_mem.get("ramo_activo")
    try:
        parsed = json.loads(output_text)
        estado = parsed.get("estado", "esperando")
        ramo = parsed.get("ramo", ramo)
    except (json.JSONDecodeError, TypeError):
        if tool_calls:
            tc_names = {tc["name"] for tc in tool_calls}
            if "create_card_tool_wrapper" in tc_names:
                estado = "creado"
            elif "update_card_tool" in tc_names:
                estado = "actualizado"

    logger.info(f"[{AGENT_NAME}] Done: estado={estado}, ramo={ramo}")

    return {
        "action": "processed",
        "estado": estado,
        "ramo": ramo,
        "memory_patch": memory_patch,
        "tool_calls": tool_calls,
    }
