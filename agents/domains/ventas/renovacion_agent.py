"""Renovación agent - gestiona renovaciones de pólizas vía WhatsApp."""

import logging
from datetime import datetime
from infra.agent_runner import (
    create_langchain_agent, run_langchain_agent,
    task_tool_already_called, _TASK_DONE_SUFFIX,
    auto_create_task_if_needed, force_redirect_if_task_done,
)
from core.memory import get_global_history
from infra.llm import get_llm

from tools.zoa.tasks_tool import create_task_activity_tool
from tools.communication.end_chat_tool import end_chat_tool
from tools.communication.redirect_to_receptionist_tool import redirect_to_receptionist_tool
from tools.sales.retarificacion_tool import (
    consulta_vehiculo_tool,
    get_town_by_cp_tool,
    consultar_catastro_tool,
    create_retarificacion_project_tool,
    finalizar_proyecto_hogar_tool,
    get_last_project_ids,
)

from agents.domains.ventas.renovacion_agent_prompts import get_prompt

logger = logging.getLogger(__name__)

AGENT_NAME = "renovacion_agent"


def renovacion_agent(payload: dict) -> dict:
    user_text = payload.get("mensaje", "")
    session = payload.get("session", {})
    memory = session.get("agent_memory", {})
    history = get_global_history(memory)

    company_id = payload.get("phone_number_id") or session.get("company_id", "")
    wa_id = payload.get("wa_id")
    if "global" not in memory:
        memory["global"] = {}
    global_mem = memory["global"]
    nif_value = global_mem.get("nif") or "NO_IDENTIFICADO"

    now = datetime.now()
    current_date = now.strftime("%d/%m/%Y")
    current_time = now.strftime("%H:%M")
    current_year = now.year

    # Extract IDs from memory for the prompt if they exist
    proyecto_id = memory.get("global", {}).get("proyecto_id", "NO_DISPONIBLE")
    id_pasarela = memory.get("global", {}).get("id_pasarela", "NO_DISPONIBLE")

    channel = payload.get("channel", "whatsapp")
    is_aichat = payload.get("is_aichat", False)

    # Define closing instructions based on channel
    if is_aichat:
        closing_instructions = """
   - Si el cliente responde que **SÍ** le interesa alguna opción (o pregunta cómo contratar):
     1. **NO** ejecutes ninguna herramienta de creación de tareas (PROHIBIDO en AiChat).
     2. Responde directamente: "Perfecto, puedes proceder con la contratación usando estos datos. ¿Necesitas ayuda con algo más?"
   
   - Si el cliente responde que **NO** (o dice "gracias", "adiós"):
     1. Despídete amablemente.
     2. Ejecuta `end_chat_tool`.
"""
    else:
        closing_instructions = """
   - Si el cliente responde que **SÍ** le interesa alguna opción (o pregunta cómo contratar):
     1. Ejecuta `create_task_activity_tool` con:
        - title: "Interesado en oferta renovación"
        - description: "Cliente interesado en oferta presentada. Llamar para cerrar."
        - activity_title: "Llamar para cerrar venta"
     2. Responde al cliente: "Perfecto, he registrado tu interés. Un gestor revisará tu solicitud y te contactará muy pronto para finalizar la contratación. ¿Necesitas algo más?"
   
   - Si el cliente responde que **NO** (o dice "gracias", "adiós"):
     1. Despídete amablemente.
     2. Ejecuta `end_chat_tool`.
"""

    system_prompt = get_prompt(channel).format(
        current_date=current_date,
        current_time=current_time,
        current_year=current_year,
        company_id=company_id,
        nif_value=nif_value,
        wa_id=wa_id or "NO_DISPONIBLE",
        proyecto_id=proyecto_id,
        id_pasarela=id_pasarela,
        closing_instructions=closing_instructions,
    )

    task_done = task_tool_already_called(memory, AGENT_NAME)
    if task_done:
        system_prompt += _TASK_DONE_SUFFIX
        logger.info("[RENOVACION_AGENT] Task already created — restricting tools")

    llm = get_llm()
    tools = [
        consulta_vehiculo_tool,
        get_town_by_cp_tool,
        consultar_catastro_tool,
        create_retarificacion_project_tool,
        finalizar_proyecto_hogar_tool,
        end_chat_tool,
        redirect_to_receptionist_tool,
    ]
    if not task_done:
        tools.insert(4, create_task_activity_tool)

    agent = create_langchain_agent(llm, tools, system_prompt)
    logger.info(f"[RENOVACION_AGENT] Before agent run - memory proyecto_id={global_mem.get('proyecto_id')}, id_pasarela={global_mem.get('id_pasarela')}")
    result = run_langchain_agent(agent, user_text, history, agent_name="renovacion_agent")
    logger.info(f"[RENOVACION_AGENT] After agent run - checking for new project IDs")

    _memory_patch = {}
    new_pid, new_pas = get_last_project_ids()
    logger.info(f"[RENOVACION_AGENT] get_last_project_ids returned: pid={new_pid}, pas={new_pas}")
    if new_pid and new_pas:
        logger.info(f"[RENOVACION_AGENT] Persisting project IDs: proyecto_id={new_pid}, id_pasarela={new_pas}")
        global_mem["proyecto_id"] = str(new_pid)
        global_mem["id_pasarela"] = int(new_pas)
        memory["global"] = global_mem
        _memory_patch = {"global": {"proyecto_id": str(new_pid), "id_pasarela": int(new_pas)}}
    else:
        logger.info(f"[RENOVACION_AGENT] No new IDs from tool. Current memory IDs: proyecto_id={global_mem.get('proyecto_id')}, id_pasarela={global_mem.get('id_pasarela')}")

    output_text = result.get("output", "")
    action = result.get("action", "ask")
    tool_calls = result.get("tool_calls")

    if not task_done:
        updated_tool_calls = auto_create_task_if_needed(
            tool_calls, output_text,
            company_id=company_id, nif_value=nif_value, wa_id=wa_id or "",
            title="Renovación de Póliza",
            description=f"Cliente consulta renovación de póliza. NIF: {nif_value}.",
            activity_title="Llamar para gestionar renovación",
            agent_label="RENOVACION_AGENT",
        )
        if updated_tool_calls:
            result["tool_calls"] = updated_tool_calls
            tool_calls = updated_tool_calls

    if task_done:
        forced = force_redirect_if_task_done(output_text, action, tool_calls)
        if forced:
            logger.info("[RENOVACION_AGENT] Task done & LLM didn't redirect — forcing redirect")
            return forced

    # Check if redirect to receptionist was triggered
    if "__REDIRECT_TO_RECEPTIONIST__" in output_text:
        clean_message = output_text.replace("__REDIRECT_TO_RECEPTIONIST__", "").strip()
        return {
            "action": "route",
            "next_agent": "receptionist_agent",
            "domain": None,
            "message": clean_message,
            "tool_calls": tool_calls,
            "memory": _memory_patch,
        }

    if action == "end_chat":
        return {
            "action": "end_chat",
            "message": output_text,
            "tool_calls": tool_calls,
            "memory": _memory_patch,
        }

    return {
        "action": action,
        "message": output_text,
        "tool_calls": tool_calls,
        "memory": _memory_patch,
    }
