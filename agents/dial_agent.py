"""Dial agent — identifies caller intent and transfers to the right PBX extension."""

import json
import logging
from infra.agent_runner import create_langchain_agent, run_langchain_agent
from infra.llm import get_llm
from core.memory import get_global_history
from tools.communication.transfer_call_tool import transfer_call_tool

from agents.dial_agent_prompts import get_prompt

logger = logging.getLogger(__name__)

AGENT_NAME = "dial_agent"

EXTENSIONS_CONFIG = {
    "ecuestres": {
        "extension": "201",
        "keywords": ["caballo", "yegua", "potro", "jinete", "cuadra", "hípica", "ecuestre"],
    },
    "albatera": {
        "extension": "202",
        "keywords": ["Albatera", "oficina de Albatera"],
    },
    "valencia_carlet": {
        "extension": "203",
        "keywords": ["Valencia", "Carlet", "oficina Valencia"],
    },
    "default": {
        "extension": "202",
        "keywords": [],
    },
}

_DEPT_LABELS = {
    "ecuestres": "Ecuestres — caballos , hípica , jinetes",
    "albatera": "Oficina Albatera — seguros generales",
    "valencia_carlet": "Oficina Valencia / Carlet — seguros generales",
    "default": "Por defecto — cualquier consulta no identificada",
}

def _build_extensions_prompt() -> str:
    """Build a human-readable extensions map for the prompt."""
    lines = []
    for dept, cfg in EXTENSIONS_CONFIG.items():
        label = _DEPT_LABELS.get(dept, dept.upper())
        lines.append(f"- {label}: extensión {cfg['extension']}")
    return "\n".join(lines)


def dial_agent(payload: dict) -> dict:
    session = payload.get("session", {})
    memory = session.get("agent_memory", {})
    history = get_global_history(memory)
    user_text = payload.get("mensaje", "")

    extensions_map = _build_extensions_prompt()
    system_prompt = get_prompt(extensions_map=extensions_map)

    llm = get_llm()
    tools = [transfer_call_tool]

    agent = create_langchain_agent(llm, tools, system_prompt)
    result = run_langchain_agent(agent, user_text, history, agent_name=AGENT_NAME)

    output_text = result.get("output", "")
    action = result.get("action", "ask")
    tool_calls = result.get("tool_calls")

    if "__TRANSFER_CALL__:" in output_text:
        extension = output_text.split("__TRANSFER_CALL__:")[1].strip()
        clean_msg = output_text.split("__TRANSFER_CALL__:")[0].strip()
        if not clean_msg:
            clean_msg = "Perfecto . . . un compañero te atenderá en seguida . . . Un momento por favor."
        return {
            "action": "transfer_call",
            "extension": extension,
            "message": clean_msg,
            "tool_calls": tool_calls,
        }

    return {
        "action": action,
        "message": output_text,
        "tool_calls": tool_calls,
    }
