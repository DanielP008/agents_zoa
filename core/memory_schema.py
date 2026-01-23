from __future__ import annotations

from copy import deepcopy
from datetime import datetime
from typing import Any, Dict, Optional


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
) -> Dict[str, Any]:
    memory = ensure_memory_shape(memory)
    memory["conversation_history"].append(
        {
            "role": role,
            "text": text,
            "timestamp": _utc_now(),
            "agent": agent,
            "domain": domain,
            "action": action,
        }
    )
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
