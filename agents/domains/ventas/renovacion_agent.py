"""Renovación agent - gestiona renovaciones de pólizas vía WhatsApp."""

import logging
from datetime import datetime
from core.agent_factory import create_langchain_agent, run_langchain_agent
from core.memory_schema import get_global_history
from core.llm import get_llm
from services.ocr_service import extract_document_data

from tools.zoa.tasks_tool import create_task_activity_tool
from tools.communication.end_chat_tool import end_chat_tool
from tools.communication.redirect_to_receptionist_tool import redirect_to_receptionist_tool
from tools.sales.retarificacion_tool import retarificacion_tool

from agents.domains.ventas.renovacion_agent_prompts import get_prompt

logger = logging.getLogger(__name__)


def _process_pending_attachments(memory: dict) -> tuple[list[dict], list[int]]:
    """Pre-process any unprocessed attachments via OCR.
    
    Returns:
        tuple: (ocr_results list, indices of processed attachments)
    """
    global_mem = memory.get("global", {})
    attachments = global_mem.get("attachments", [])
    processed_indices = global_mem.get("processed_attachment_indices", [])

    ocr_results = []
    newly_processed = []

    for i, att in enumerate(attachments):
        if i in processed_indices:
            continue

        mime_type = att.get("mime_type", "application/octet-stream")
        b64_data = att.get("data")
        filename = att.get("filename", f"documento_{i+1}")

        if not b64_data:
            logger.warning(f"[RENOVACION] Attachment {i} has no data, skipping")
            newly_processed.append(i)
            continue

        logger.info(f"[RENOVACION] Processing attachment {i}: {filename} ({mime_type})")
        result = extract_document_data(mime_type, b64_data)

        if result.get("status") == "success":
            ocr_results.append({
                "filename": filename,
                "mime_type": mime_type,
                "data": result.get("data", {}),
            })
            logger.info(f"[RENOVACION] OCR success for {filename}")
        else:
            ocr_results.append({
                "filename": filename,
                "mime_type": mime_type,
                "error": result.get("error", "OCR failed"),
            })
            logger.error(f"[RENOVACION] OCR failed for {filename}: {result.get('error')}")

        newly_processed.append(i)

    return ocr_results, processed_indices + newly_processed


def renovacion_agent(payload: dict) -> dict:
    user_text = payload.get("mensaje", "")
    session = payload.get("session", {})
    memory = session.get("agent_memory", {})
    history = get_global_history(memory)

    company_id = payload.get("phone_number_id") or session.get("company_id", "")
    wa_id = payload.get("wa_id")
    global_mem = memory.get("global", {})
    nif_value = global_mem.get("nif") or "NO_IDENTIFICADO"

    now = datetime.now()
    current_date = now.strftime("%d/%m/%Y")
    current_time = now.strftime("%H:%M")
    current_year = now.year

    # Pre-process any pending attachments via OCR (before LLM call)
    ocr_results, updated_indices = _process_pending_attachments(memory)

    if ocr_results:
        # Save processed indices back to memory so we don't re-process
        global_mem["processed_attachment_indices"] = updated_indices
        memory["global"] = global_mem
        session["agent_memory"] = memory

        # Inject OCR results into user message so the LLM can see them
        ocr_context = "\n\n[DOCUMENTOS PROCESADOS AUTOMÁTICAMENTE]:\n"
        for r in ocr_results:
            if "error" in r:
                ocr_context += f"\n📄 {r['filename']} ({r['mime_type']}): ERROR - {r['error']}\n"
            else:
                import json
                ocr_context += f"\n📄 {r['filename']} ({r['mime_type']}):\n{json.dumps(r['data'], indent=2, ensure_ascii=False)}\n"
        user_text = user_text + ocr_context

    channel = payload.get("channel", "whatsapp")
    system_prompt = get_prompt(channel).format(
        current_date=current_date,
        current_time=current_time,
        current_year=current_year,
        company_id=company_id,
        nif_value=nif_value,
        wa_id=wa_id or "NO_DISPONIBLE",
    )

    llm = get_llm()
    tools = [
        retarificacion_tool,
        create_task_activity_tool,
        end_chat_tool,
        redirect_to_receptionist_tool,
    ]

    agent = create_langchain_agent(llm, tools, system_prompt)
    result = run_langchain_agent(agent, user_text, history, agent_name="renovacion_agent")

    output_text = result.get("output", "")
    action = result.get("action", "ask")
    tool_calls = result.get("tool_calls")

    # Check if redirect to receptionist was triggered
    if "__REDIRECT_TO_RECEPTIONIST__" in output_text:
        clean_message = output_text.replace("__REDIRECT_TO_RECEPTIONIST__", "").strip()
        return {
            "action": "route",
            "next_agent": "receptionist_agent",
            "domain": None,
            "message": clean_message,
            "tool_calls": tool_calls,
        }

    if action == "end_chat":
        return {
            "action": "end_chat",
            "message": output_text,
            "tool_calls": tool_calls,
        }

    return {
        "action": action,
        "message": output_text,
        "tool_calls": tool_calls,
    }
