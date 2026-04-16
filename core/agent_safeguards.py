"""Business safety nets for agent execution: auto-task creation, force redirects."""

import logging

from langsmith import traceable

from core.request_context import get_client_name

logger = logging.getLogger(__name__)

_TASK_DONE_SUFFIX = (
    "\n\n[SISTEMA] La tarea YA FUE CREADA anteriormente. "
    "NO crees otra tarea. Solo tienes dos opciones:\n"
    "- Si el cliente quiere algo más → usa redirect_to_receptionist_tool\n"
    "- Si el cliente no necesita nada más → usa end_chat_tool"
)


_CALLBACK_HINTS = (
    "no he encontrado", "no encontré", "no hay teléfonos", "no se encontraron",
    "compañero te llame", "pedir que", "gestor se ponga en contacto",
    "registrar tu consulta", "registrar tu solicitud", "voy a registrar",
    "te llame mañana", "te llamará", "pondrá en contacto",
    "gestor revisará", "ya está anotado", "siniestro registrado",
    "he registrado", "un compañero", "contacto contigo",
    "problema técnico", "error al conectar", "gestor se ocupará",
    "gestor lo mirará", "gestor lo revisará", "paso nota",
    "no he encontrado", "no aparecen", "no encuentro",
    "gestor se ocupe", "gestor se ponga", "gestor lo revise",
)


def task_tool_already_called(memory: dict, agent_name: str) -> bool:
    """Return True if create_task_activity_tool was already invoked by *agent_name*
    in the CURRENT activation (i.e. since the last turn handled by a different agent).

    When the user returns to the same agent after visiting others, we treat it as
    a fresh consultation so a new task can be created for the new request.
    """
    for turn in reversed(memory.get("conversation_history", [])):
        if turn.get("agent") != agent_name:
            return False
        for tc in (turn.get("tool_calls") or []):
            if tc.get("name") == "create_task_activity_tool":
                return True
    return False


@traceable(name="Auto-Create Task (Fail-safe)", run_type="tool")
def auto_create_task_if_needed(
    tool_calls,
    output_text: str,
    *,
    company_id: str,
    nif_value: str,
    wa_id: str,
    title: str,
    description: str,
    activity_title: str = "Llamar al cliente",
    activity_description: str = "",
    agent_label: str = "AGENT",
    client_name: str = "",
):
    """Create a CRM task if the agent promises a callback but didn't call create_task_activity_tool.

    Returns the updated tool_calls list if a task was created, or None if nothing was done.
    The caller MUST update result["tool_calls"] with the return value when not None.
    """
    tc_names = {tc["name"] for tc in (tool_calls or [])}
    if "create_task_activity_tool" in tc_names:
        return None

    output_lower = output_text.lower()
    if not any(hint in output_lower for hint in _CALLBACK_HINTS):
        return None

    resolved_name = client_name or get_client_name()
    task_payload = {
        "company_id": company_id,
        "title": title,
        "description": description,
        "card_type": "task",
        "pipeline_name": "Cotizaciones",
        "type_of_activity": "llamada",
        "activity_title": activity_title,
        "phone": wa_id,
    }
    if resolved_name:
        task_payload["name"] = resolved_name.upper()
    if nif_value and nif_value != "NO_IDENTIFICADO":
        task_payload["nif"] = nif_value
    if activity_description:
        task_payload["activity_description"] = activity_description

    try:
        from services.zoa_client import create_task_activity
        result = create_task_activity(**task_payload)
        logger.info(f"[{agent_label}] Auto-created task (LLM missed it): {result}")
        if tool_calls is None:
            tool_calls = []
        tool_calls.append({"name": "create_task_activity_tool", "args": task_payload})
        return tool_calls
    except Exception as e:
        logger.error(f"[{agent_label}] Auto-create task failed: {e}")
        return tool_calls


def force_redirect_if_task_done(output_text: str, action: str, tool_calls) -> dict | None:
    """When task_done=True but the LLM didn't redirect/end, force a redirect.

    Returns a response dict to return immediately, or None if no override needed.
    """
    if action in ("end_chat",):
        return None
    if "__REDIRECT_TO_RECEPTIONIST__" in (output_text or ""):
        return None

    tc_names = {tc["name"] for tc in (tool_calls or [])}
    if "redirect_to_receptionist_tool" in tc_names or "end_chat_tool" in tc_names:
        return None

    return {
        "action": "route",
        "next_agent": "receptionist_agent",
        "domain": None,
        "message": output_text,
        "tool_calls": tool_calls,
    }
