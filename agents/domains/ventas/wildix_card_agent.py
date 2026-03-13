"""Wildix Card Agent — background processor for insurance tarification cards.

Receives concatenated call transcriptions from zoa_buffer, classifies them,
extracts insurance-relevant data, and creates/updates AI Chat cards via flow-zoa.

OPTIMIZED: Uses a single direct LLM call + JSON parsing instead of a full
LangChain agent loop (which required 2 LLM round-trips for tool calls).
Uses the fast LLM for speed.
"""

import json
import logging
import re
from datetime import datetime

from infra.llm import get_llm_fast
from infra.timing import Timer, set_current_agent
from tools.sales.card_tools import (
    create_card_tool,
    update_card_tool_direct,
    get_card_state,
    reset_card_state,
    set_call_context,
)
from agents.domains.ventas.wildix_card_agent_prompts import get_wildix_card_prompt

logger = logging.getLogger(__name__)

AGENT_NAME = "wildix_card_agent"

# Noise patterns — fragments that contain no insurance-relevant data
_NOISE_PATTERNS = re.compile(
    r"^("
    r"(hola|buenos d[ií]as|buenas tardes|buenas noches|adiós|adi[oó]s|hasta luego|vale|ok|sí|no|un momento|espera|de acuerdo|perfecto|claro|entendido|gracias|muchas gracias)"
    r"[.!?,\s]*"
    r")+$",
    re.IGNORECASE,
)


def _is_noise(text: str) -> bool:
    """Return True if the text is pure conversational filler with no data."""
    cleaned = text.strip()
    if not cleaned or len(cleaned) < 3:
        return True
    return bool(_NOISE_PATTERNS.match(cleaned))


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


def _clean_llm_response(raw: str) -> str:
    """Strip markdown fences and leading/trailing whitespace from LLM output."""
    text = raw.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        # Remove first line (```json or ```)
        lines = lines[1:]
        # Remove last line if it's ```
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    # Also handle inline ```json prefix
    if text.startswith("json"):
        text = text[4:].strip()
    return text


def wildix_card_agent(payload: dict) -> dict:
    """Process a buffered call transcription and manage the tarification card.

    OPTIMIZED: Single LLM call + direct tool invocation instead of
    LangChain agent loop (eliminates one full LLM round-trip).

    Args:
        payload: dict with keys: company_id, user_id, call_id, message,
                 session (dict with agent_memory), new_text (optional delta)

    Returns:
        dict with estado, ramo, action, memory_patch
    """
    message = payload.get("message", "").strip()
    new_text = payload.get("new_text", "").strip()
    company_id = payload.get("company_id", "")
    user_id = payload.get("user_id", "")
    call_id = payload.get("call_id", "")

    session = payload.get("session", {})
    memory = session.get("agent_memory", {})
    if "global" not in memory:
        memory["global"] = {}
    global_mem = memory["global"]

    logger.info(
        f"[{AGENT_NAME}] Processing message ({len(message)} chars, "
        f"delta={len(new_text)} chars) for call={call_id}"
    )

    if not message:
        return {"action": "processed", "estado": "irrelevant", "ramo": None}

    # FAST PATH: If we have delta text and it's pure noise, skip LLM entirely
    if new_text and _is_noise(new_text):
        logger.info(f"[{AGENT_NAME}] Delta is noise, skipping LLM: '{new_text[:80]}'")
        return {
            "action": "processed",
            "estado": "noise_skip",
            "ramo": global_mem.get("ramo_activo"),
            "memory_patch": {},
            "tool_calls": None,
        }

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

    # Use FAST LLM (GPT-4o-mini / Gemini Flash) — extraction doesn't need a heavy model
    llm = get_llm_fast()

    set_current_agent(AGENT_NAME)

    # DELTA MODE: Prefer processing only the new text to save tokens and latency
    # If new_text is available, use it. Otherwise fall back to full message.
    target_text = new_text if new_text else message
    logger.info(f"[{AGENT_NAME}] Delta Mode: Processing '{target_text[:100]}...' (Is Delta: {bool(new_text)})")

    # SINGLE LLM call — no agent loop, no tool-calling round-trip
    model_name = getattr(llm, "model_name", "") or getattr(llm, "model", "") or ""
    with Timer("agent", AGENT_NAME, model=model_name):
        try:
            llm_response = llm.invoke([
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": target_text},
            ])
            raw_output = llm_response.content if hasattr(llm_response, "content") else str(llm_response)
        except Exception as e:
            logger.error(f"[{AGENT_NAME}] LLM invocation failed: {e}")
            raise

    logger.info(f"[{AGENT_NAME}] LLM output ({len(raw_output)} chars): {raw_output[:300]}")

    # Parse structured JSON response
    cleaned = _clean_llm_response(raw_output)
    try:
        parsed = json.loads(cleaned)
    except (json.JSONDecodeError, TypeError) as e:
        logger.warning(f"[{AGENT_NAME}] Failed to parse LLM JSON: {e}. Raw: {cleaned[:200]}")
        return {
            "action": "processed",
            "estado": "parse_error",
            "ramo": global_mem.get("ramo_activo"),
            "memory_patch": {},
            "tool_calls": None,
        }

    estado = parsed.get("estado", "irrelevant")
    ramo = parsed.get("ramo")
    tool_action = parsed.get("tool_action")
    tool_payload = parsed.get("tool_payload", {})

    logger.info(
        f"[{AGENT_NAME}] Parsed: estado={estado}, ramo={ramo}, "
        f"tool_action={tool_action}"
    )

    # Execute tool directly (no second LLM call needed)
    tool_calls = None

    # SAFETY CHECK: If card already exists, force update or block create
    if tool_action == "create" and global_mem.get("card_created"):
        logger.warning(f"[{AGENT_NAME}] LLM requested CREATE but card already exists. Switching to UPDATE.")
        tool_action = "update"
        # Ensure body_type matches existing ramo if possible
        if not tool_payload.get("body_type"):
             current_ramo = global_mem.get("ramo_activo")
             if current_ramo:
                 tool_payload["body_type"] = "auto_sheet" if current_ramo == "AUTO" else "home_sheet"

    if tool_action == "create" and tool_payload:
        body_type = tool_payload.get("body_type")
        data = tool_payload.get("data", {})
        complete = tool_payload.get("complete", False)

        with Timer("tool", "create_card_direct", parent=AGENT_NAME):
            result = create_card_tool(
                body_type=body_type,
                data=data,
                complete=complete,
            )

        tool_calls = [{"name": "create_card_tool", "args": tool_payload}]
        logger.info(f"[{AGENT_NAME}] Card created: {result}")

    elif tool_action == "update" and tool_payload:
        # Ensure body_type is present in tool_payload for update
        body_type = tool_payload.get("body_type")
        if not body_type:
            # Fallback to current ramo if LLM forgot to include body_type
            current_ramo = global_mem.get("ramo_activo")
            if current_ramo:
                body_type = "auto_sheet" if current_ramo == "AUTO" else "home_sheet"
        
        # MERGE STRATEGY: Combine existing data with new data
        # The LLM might return only the fields that changed (delta), so we must merge.
        new_data = tool_payload.get("data", {})
        existing_data = global_mem.get("card_data", {})
        
        # Deep merge for nested dictionaries (tomador, vehiculo, etc.)
        merged_data = existing_data.copy()
        for category, fields in new_data.items():
            if isinstance(fields, dict):
                if category not in merged_data:
                    merged_data[category] = {}
                # Update only the fields present in new_data
                merged_data[category].update(fields)
            else:
                # Direct value update
                merged_data[category] = fields
                
        complete = tool_payload.get("complete", False)

        if body_type:
            with Timer("tool", "update_card_direct", parent=AGENT_NAME):
                result = update_card_tool_direct(
                    body_type=body_type,
                    data=merged_data,  # Send the FULL merged object
                    complete=complete,
                )
            tool_calls = [{"name": "update_card_tool", "args": tool_payload}]
            logger.info(f"[{AGENT_NAME}] Card updated: {result}")
        else:
            logger.error(f"[{AGENT_NAME}] Cannot update card: missing body_type and no ramo_activo in memory")

    # Build memory patch — ALWAYS persist card_data after a tool call
    # so the next flush cycle has the full merged state
    new_state = get_card_state()
    memory_patch = {}

    # Determine the authoritative values for ramo/created:
    # Prefer new_state (set by create_card_tool), fall back to existing memory
    effective_ramo = new_state.get("ramo_activo") or global_mem.get("ramo_activo")
    effective_created = new_state.get("card_created") or global_mem.get("card_created", False)
    # For card_data: if a tool was called, use merged_data; otherwise keep existing
    effective_data = global_mem.get("card_data", {})
    if tool_action == "update" and tool_payload:
        effective_data = merged_data  # The deep-merged object we sent to the API
    elif tool_action == "create" and new_state.get("card_data"):
        effective_data = new_state["card_data"]

    if effective_ramo or effective_created or tool_calls:
        global_mem["ramo_activo"] = effective_ramo
        global_mem["card_created"] = effective_created
        global_mem["card_data"] = effective_data
        memory_patch = {
            "global": {
                "ramo_activo": effective_ramo,
                "card_created": effective_created,
                "card_data": effective_data,
            }
        }
        logger.info(
            f"[{AGENT_NAME}] Memory updated: "
            f"ramo={effective_ramo}, created={effective_created}, "
            f"data_keys={list(effective_data.keys())}"
        )

    # Use ramo from parsed response or from memory
    final_ramo = ramo or global_mem.get("ramo_activo")

    logger.info(f"[{AGENT_NAME}] Done: estado={estado}, ramo={final_ramo}")

    return {
        "action": "processed",
        "estado": estado,
        "ramo": final_ramo,
        "memory_patch": memory_patch,
        "tool_calls": tool_calls,
    }
