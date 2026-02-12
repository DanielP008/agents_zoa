from __future__ import annotations

import logging
from copy import deepcopy
from datetime import datetime
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

_DEFAULT_MEMORY: Dict[str, Any] = {
    "global": {
        "language": "es",
        "summary": "",
        "last_agent": None,
        "last_action": None,
        "last_domain": None,
        "preferences": {},
    },
    "conversation_history": [],
    "domains": {},
    "agents": {},
    "metadata": {
        "version": 1,
        "updated_at": None,
    },
}

def _utc_now() -> str:
    return datetime.utcnow().replace(microsecond=0).isoformat() + "Z"

def get_default_memory() -> Dict[str, Any]:
    return deepcopy(_DEFAULT_MEMORY)

def ensure_memory_shape(memory: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    if not isinstance(memory, dict):
        memory = {}
    base = get_default_memory()
    for key, value in memory.items():
        if isinstance(base.get(key), dict) and isinstance(value, dict):
            base[key].update(value)
        else:
            base[key] = value
    return base

def update_global(memory: Dict[str, Any], **kwargs: Any) -> Dict[str, Any]:
    memory = ensure_memory_shape(memory)
    memory["global"].update({k: v for k, v in kwargs.items()})
    memory["metadata"]["updated_at"] = _utc_now()
    return memory

def append_turn(
    memory: Dict[str, Any],
    *,
    role: str,
    text: str,
    agent: Optional[str],
    domain: Optional[str],
    action: Optional[str],
    tool_calls: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    memory = ensure_memory_shape(memory)
    turn = {
        "role": role,
        "text": text,
        "timestamp": _utc_now(),
        "agent": agent,
        "domain": domain,
        "action": action,
    }
    if tool_calls:
        turn["tool_calls"] = tool_calls
    memory["conversation_history"].append(turn)
    memory["metadata"]["updated_at"] = _utc_now()
    return memory

def apply_memory_patch(memory: Dict[str, Any], patch: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    memory = ensure_memory_shape(memory)
    if not patch:
        return memory
    patch = ensure_memory_shape(patch)
    for key in ("global", "domains", "agents", "metadata"):
        if isinstance(patch.get(key), dict):
            memory[key].update(patch[key])
    if isinstance(patch.get("conversation_history"), list):
        memory["conversation_history"].extend(patch["conversation_history"])
    memory["metadata"]["updated_at"] = _utc_now()
    return memory

# ---------------------------------------------------------------------------
# History compression settings
# ---------------------------------------------------------------------------
# When conversation_history exceeds RECENT_WINDOW messages, older turns are
# compressed into a compact summary (user answers kept intact, assistant
# messages truncated) and only the most recent RECENT_WINDOW messages are
# sent in full.  This keeps token count stable regardless of conversation
# length while preserving all factual data the client provided.
RECENT_WINDOW = 6          # last 3 exchanges sent in full
ASSISTANT_TRUNCATE = 100   # max chars for assistant msgs in summary


def _build_context_summary(old_turns: List[Dict[str, Any]]) -> str:
    """Build a compact summary of older conversation turns.

    Preserves full user messages (they contain the actual data) and truncates
    assistant messages (mostly questions / filler).
    """
    lines: List[str] = []
    for turn in old_turns:
        text = turn.get("text", "").strip()
        if not text:
            continue
        if turn.get("role") == "user":
            lines.append(f"- Cliente: {text}")
        else:
            truncated = text[:ASSISTANT_TRUNCATE]
            if len(text) > ASSISTANT_TRUNCATE:
                truncated += "..."
            lines.append(f"- Agente: {truncated}")
    return "\n".join(lines)


def get_global_history(memory: Dict[str, Any]) -> List[tuple]:
    """Get conversation history formatted for LangChain.

    When the history is longer than RECENT_WINDOW messages the function
    compresses older turns into a lightweight context block and only sends the
    most recent messages in full.  This reduces input tokens dramatically on
    long conversations (10+ turns) without losing any client-provided data.
    """
    memory = ensure_memory_shape(memory)
    raw_history = memory.get("conversation_history", [])

    # ── Short conversations: return everything as-is ──────────────────────
    if len(raw_history) <= RECENT_WINDOW:
        # Keep persistent data available in memory without noisy stdout prints.
        global_data = memory.get("global", {})
        if global_data.get("nif") or global_data.get("wa_id") or global_data.get("company_id"):
            logger.debug(
                "[MEMORY] Datos obligatorios disponibles (conversación corta): "
                f"nif={bool(global_data.get('nif'))}, "
                f"wa_id={bool(global_data.get('wa_id'))}, "
                f"company_id={bool(global_data.get('company_id'))}"
            )
            
        return [
            (("human" if h.get("role") == "user" else "ai"), h.get("text", ""))
            for h in raw_history
        ]

    # ── Long conversations: compress old turns + recent window ────────────
    old_turns = raw_history[:-RECENT_WINDOW]
    recent_turns = raw_history[-RECENT_WINDOW:]

    context_summary = _build_context_summary(old_turns)

    # Add persistent global data to summary so it's never lost
    global_data = memory.get("global", {})
    persistent_info = []
    if global_data.get("nif"):
        persistent_info.append(f"- NIF/NIE: {global_data['nif']}")
    
    # Use wa_id from payload if available, or from global memory
    wa_id = global_data.get("wa_id")
    if wa_id:
        persistent_info.append(f"- Teléfono (wa_id): {wa_id}")

    # Add company_id to persistent info
    company_id = global_data.get("company_id")
    if company_id:
        persistent_info.append(f"- Company ID: {company_id}")
    
    if persistent_info:
        context_summary = "[DATOS OBLIGATORIOS DEL CLIENTE]\n" + "\n".join(persistent_info) + "\n\n" + context_summary

    # Keep summary evolution in structured logs (avoid noisy stdout prints).
    logger.debug("[MEMORY] Evolución del resumen: %s", context_summary or "Sin historial antiguo todavía.")

    old_chars = sum(len(t.get("text", "")) for t in old_turns)
    summary_chars = len(context_summary)
    logger.info(
        f"[MEMORY] History compressed: {len(raw_history)} turns → "
        f"summary({len(old_turns)}) + recent({len(recent_turns)}). "
        f"Old text: ~{old_chars} chars → summary: ~{summary_chars} chars "
        f"({100 - round(summary_chars / max(old_chars, 1) * 100)}% reduction)"
    )

    formatted: List[tuple] = []

    if context_summary:
        formatted.append((
            "human",
            "[CONTEXTO DE TURNOS ANTERIORES]\n"
            + context_summary
            + "\n[FIN CONTEXTO ANTERIORES]"
        ))
        formatted.append((
            "ai",
            "Entendido, tengo presentes todos los datos anteriores del cliente."
        ))

    for turn in recent_turns:
        role = "human" if turn.get("role") == "user" else "ai"
        formatted.append((role, turn.get("text", "")))

    return formatted

def get_agent_memory(memory: Dict[str, Any], agent_name: str, default: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Get agent-specific memory namespace."""
    memory = ensure_memory_shape(memory)
    return memory.get("agents", {}).get(agent_name, default or {})

def set_agent_memory(memory: Dict[str, Any], agent_name: str, agent_data: Dict[str, Any]) -> Dict[str, Any]:
    """Set agent-specific memory namespace."""
    memory = ensure_memory_shape(memory)
    if "agents" not in memory:
        memory["agents"] = {}
    memory["agents"][agent_name] = agent_data
    memory["metadata"]["updated_at"] = _utc_now()
    return memory

def get_domain_memory(memory: Dict[str, Any], domain_name: str, default: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Get domain-specific memory namespace."""
    memory = ensure_memory_shape(memory)
    return memory.get("domains", {}).get(domain_name, default or {})

def set_domain_memory(memory: Dict[str, Any], domain_name: str, domain_data: Dict[str, Any]) -> Dict[str, Any]:
    """Set domain-specific memory namespace."""
    memory = ensure_memory_shape(memory)
    if "domains" not in memory:
        memory["domains"] = {}
    memory["domains"][domain_name] = domain_data
    memory["metadata"]["updated_at"] = _utc_now()
    return memory

def get_global_memory(memory: Dict[str, Any]) -> Dict[str, Any]:
    """Get global memory namespace."""
    memory = ensure_memory_shape(memory)
    return memory["global"]

def update_global_memory(memory: Dict[str, Any], **updates) -> Dict[str, Any]:
    """Update global memory namespace."""
    memory = ensure_memory_shape(memory)
    memory["global"].update(updates)
    memory["metadata"]["updated_at"] = _utc_now()
    return memory
