"""Action handlers for the orchestrator: ask, route, finish, end_chat."""

import logging

from core.memory import (
    append_turn,
    apply_memory_patch,
    update_global,
)
from infra.timing import dump_trace

logger = logging.getLogger(__name__)

_DEFAULT_AGENT = "receptionist_agent"
_ROUTE_BLOCKED_MSG = "No pude derivarte en este momento. ¿Podés intentar de nuevo?"


def validate_route_target(target_agent: str, next_agent: str | None,
                          allowlist: dict) -> str | None:
    """Validate a route target against the allowlist.

    Returns error message string if invalid, None if valid.
    """
    if not next_agent:
        return "Route action missing next_agent"
    allowed = allowlist.get(target_agent, [])
    if next_agent not in allowed:
        return _ROUTE_BLOCKED_MSG
    return None


def resolve_domain(response: dict, session: dict) -> str | None:
    """Pick domain from agent response, falling back to session."""
    if "domain" in response:
        return response.get("domain")
    return session.get("domain")


def record_assistant_turn(memory: dict, *, message: str | None, agent: str,
                          domain: str | None, action: str,
                          tool_calls: list | None) -> dict:
    """Append an assistant turn to memory if a message exists."""
    if message:
        memory = append_turn(
            memory,
            role="assistant",
            text=message,
            agent=agent,
            domain=domain,
            action=action,
            tool_calls=tool_calls,
        )
    return memory


def persist_session(session: dict, session_id: str, *, target_agent: str,
                    domain: str | None, memory: dict,
                    session_manager) -> None:
    """Write session state to DB in a single call."""
    session["target_agent"] = target_agent
    session["domain"] = domain
    session["agent_memory"] = memory
    session_manager.save_session(session_id, session)


# ---------------------------------------------------------------------------
# Action handlers
# ---------------------------------------------------------------------------

def handle_end_chat(wa_id: str, company_id: str, agent_message: str | None,
                    channel: str, session_manager, 
                    is_aichat: bool = False) -> dict:
    """Handle the end_chat action: delete session and return."""
    logger.info(f"[ORCHESTRATOR] end_chat triggered for wa_id={wa_id}")
    
    # 1. Get current session to preserve identifiers if needed (though delete_session is absolute)
    # 2. Delete the session from PostgreSQL
    deleted = session_manager.delete_session(wa_id, company_id)
    
    if deleted:
        logger.info(f"[ORCHESTRATOR] Session deleted for wa_id={wa_id}")
    else:
        logger.warning(f"[ORCHESTRATOR] Failed to delete session for wa_id={wa_id}")

    dump_trace(channel)
    
    default_receptionist = "aichat_receptionist_agent" if is_aichat else _DEFAULT_AGENT
    return {
        "type": "text",
        "message": agent_message,
        "agent": default_receptionist,
        "status": "completed",
        "session_deleted": deleted,
    }


def _handle_session_reset(wa_id: str, company_id: str, is_aichat: bool = False):
    """Reset user session and return a clean start message."""
    deleted = session_manager.delete_session(wa_id, company_id)
    
    # Choose the correct receptionist based on channel
    receptionist = "aichat_receptionist_agent" if is_aichat else _DEFAULT_AGENT
    
    # Default greeting
    if is_aichat:
        message = (
            "Hola, soy Sofía, tu asistente virtual de ZOA Seguros para corredores. "
            "He borrado todos los datos anteriores (incluyendo NIF y documentos).\n\n"
            "Puedo ayudarte con:\n\n"
            "• Teléfonos de asistencia para tu cliente\n\n"
            "• Retarificación y renovación de pólizas\n\n"
            "¿Con cuál de estas opciones necesitas ayuda hoy?"
        )
    else:
        message = "Hola, soy Sofía. ¿En qué puedo ayudarte hoy?"

    return {
        "status": "ok",
        "message": message,
        "agent": receptionist,
        "session_deleted": deleted
    }


def handle_ask(response: dict, session: dict, session_id: str, memory: dict,
               target_agent: str, channel: str, session_manager,
               is_aichat: bool = False) -> dict:
    """Handle the ask action: persist and return message."""
    agent_message = response.get("message")
    memory = record_assistant_turn(
        memory, message=agent_message, agent=target_agent,
        domain=session.get("domain"), action="ask",
        tool_calls=response.get("tool_calls"),
    )
    memory = apply_memory_patch(memory, response.get("memory", {}))
    memory = update_global(
        memory,
        last_agent=target_agent,
        last_action="ask",
        last_domain=session.get("domain"),
    )
    persist_session(session, session_id, target_agent=target_agent,
                    domain=session.get("domain"), memory=memory,
                    session_manager=session_manager)
    dump_trace(channel)
    return {"type": "text", "message": agent_message, "agent": target_agent}


_RECEPTIONIST_AGENTS = frozenset({"receptionist_agent", "aichat_receptionist_agent"})
_RECEPTIONIST_GREETING = "Dime, ¿Qué otra consulta tienes?"


def handle_route(response: dict, session: dict, session_id: str, memory: dict,
                 target_agent: str, channel: str, session_manager,
                 allowlist: dict, is_aichat: bool = False) -> dict:
    """Handle the route action (with user-facing message)."""
    new_target = response.get("next_agent")
    new_domain = resolve_domain(response, session)

    error = validate_route_target(target_agent, new_target, allowlist)
    if error:
        dump_trace(channel)
        if error == _ROUTE_BLOCKED_MSG:
            return {"type": "text", "message": error, "agent": target_agent}
        return {"error": error}

    agent_message = response.get("message")

    # When routing back to the receptionist, replace the specialist's farewell
    # with a clean greeting — the specialist already communicated everything.
    if new_target in _RECEPTIONIST_AGENTS:
        if agent_message and agent_message.strip():
            agent_message = agent_message
        else:
            agent_message = _RECEPTIONIST_GREETING

    memory = record_assistant_turn(
        memory, message=agent_message, agent=target_agent,
        domain=new_domain, action="route",
        tool_calls=response.get("tool_calls"),
    )
    memory = apply_memory_patch(memory, response.get("memory", {}))
    memory = update_global(
        memory,
        last_agent=target_agent,
        last_action="route",
        last_domain=new_domain,
    )
    persist_session(session, session_id, target_agent=new_target,
                    domain=new_domain, memory=memory,
                    session_manager=session_manager)
    dump_trace(channel)
    return {"type": "transition", "message": agent_message, "next_agent": new_target}


def handle_finish(response: dict, session: dict, session_id: str, memory: dict,
                  target_agent: str, channel: str, session_manager,
                  is_aichat: bool = False) -> dict:
    """Handle the finish action: reset to receptionist."""
    agent_message = response.get("message")
    memory = record_assistant_turn(
        memory, message=agent_message, agent=target_agent,
        domain=session.get("domain"), action="finish",
        tool_calls=response.get("tool_calls"),
    )
    memory = update_global(
        memory,
        last_agent=target_agent,
        last_action="finish",
        last_domain=session.get("domain"),
        consultation_completed=True,
    )
    
    default_receptionist = "aichat_receptionist_agent" if is_aichat else _DEFAULT_AGENT
    persist_session(session, session_id, target_agent=default_receptionist,
                    domain=None, memory=memory,
                    session_manager=session_manager)
    dump_trace(channel)
    return {"type": "text", "message": agent_message, "status": "completed"}
