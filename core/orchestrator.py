import json
import logging
import threading
from core.db import SessionManager
from core.timing import start_trace, dump_trace

logger = logging.getLogger(__name__)
from core.memory_schema import (
    append_turn,
    apply_memory_patch,
    ensure_memory_shape,
    update_global,
)
from core.routing.main_router import route_request
from services.zoa_client import send_whatsapp_response
from services.ocr_service import extract_document_data
from core.routing.allowlist import build_agent_allowlist, load_routes_config
from core.preprocessors import extract_attachments, try_silent_nif_lookup

session_manager = SessionManager()

_ROUTES_CONFIG = load_routes_config()
_AGENT_ALLOWLIST = build_agent_allowlist(_ROUTES_CONFIG)


def _process_attachments_ocr(memory: dict) -> tuple[dict, str]:
    """Run OCR on all unprocessed attachments and return extracted text.

    Returns:
        (updated_memory, ocr_context_text)
    """
    global_mem = memory.get("global", {})
    attachments = global_mem.get("attachments", [])
    if not attachments:
        return memory, ""

    processed = set(global_mem.get("processed_attachment_indices", []))
    ocr_texts = []

    for i, att in enumerate(attachments):
        if i in processed:
            continue
        if not isinstance(att, dict):
            continue
        b64_data = att.get("data")
        if not b64_data:
            continue

        mime_type = att.get("mime_type", "application/octet-stream")
        filename = att.get("filename", f"adjunto_{i+1}")

        logger.info(f"[ORCHESTRATOR_OCR] Processing attachment {i}: {filename} ({mime_type})")
        result = extract_document_data(mime_type, b64_data)

        if result.get("status") == "success":
            extracted = result.get("data", {})
            ocr_texts.append(
                f"[Contenido extraído de '{filename}' ({mime_type})]:\n"
                f"{json.dumps(extracted, ensure_ascii=False, indent=2)}"
            )
            att["ocr_status"] = "success"
            logger.info(f"[ORCHESTRATOR_OCR] OCR success for {filename}")
        else:
            raw = result.get("raw_output")
            if raw:
                ocr_texts.append(
                    f"[Contenido extraído de '{filename}' ({mime_type})]:\n{raw}"
                )
                att["ocr_status"] = "raw"
            else:
                att["ocr_status"] = "failed"
                att["ocr_error"] = result.get("error", "OCR failed")
                logger.error(f"[ORCHESTRATOR_OCR] OCR failed for {filename}: {result.get('error')}")

        # Prune base64 after processing
        att.pop("data", None)
        att["data_pruned"] = True
        processed.add(i)

    if processed:
        global_mem["processed_attachment_indices"] = sorted(processed)
        global_mem["attachments"] = attachments
        memory["global"] = global_mem

    return memory, "\n\n".join(ocr_texts)

def process_message(payload: dict) -> dict:
    
    wa_id = payload.get("wa_id")
    mensaje = payload.get("mensaje")
    phone_number_id = payload.get("phone_number_id")
    
    company_id = phone_number_id or "default"
    channel = payload.get("channel", "whatsapp")
    
    # Start timing trace for this request
    session_id = f"{company_id}_{wa_id}"
    start_trace(session_id, channel)
    
    # Add company_id to payload for agents and tools
    payload["company_id"] = company_id

    session = session_manager.get_session(wa_id, company_id)
    target_agent = session.get("target_agent", "receptionist_agent")
    memory = ensure_memory_shape(session.get("agent_memory", {}))

    # Handle attachments: extract, OCR, and inject text into mensaje
    attachments = extract_attachments(payload)
    if attachments:
        global_mem = memory.get("global", {})
        existing = global_mem.get("attachments", [])
        if not isinstance(existing, list):
            existing = []
        memory = update_global(memory, attachments=existing + attachments)
        session["agent_memory"] = memory

    # Run OCR on any unprocessed attachments (images + PDFs)
    memory, ocr_text = _process_attachments_ocr(memory)
    if ocr_text:
        if mensaje:
            mensaje = f"{mensaje}\n\n{ocr_text}"
        else:
            mensaje = ocr_text
        payload["mensaje"] = mensaje
        session["agent_memory"] = memory
    elif attachments and not mensaje:
        mensaje = "[adjunto sin contenido extraíble]"
        payload["mensaje"] = mensaje

    # Silent CRM lookup for NIF (no user interaction)
    memory, nif_value = try_silent_nif_lookup(memory, wa_id, company_id)
    
    # Ensure wa_id and company_id are stored in global memory for persistence in summary
    if wa_id:
        memory = update_global(memory, wa_id=wa_id)
    if company_id:
        memory = update_global(memory, company_id=company_id)
        
    session["agent_memory"] = memory

    payload["session"] = session

    MAX_CHAIN_DEPTH = 5
    chain_depth = 0
    
    while chain_depth < MAX_CHAIN_DEPTH:
        chain_depth += 1
        
        payload["allowed_next_agents"] = _AGENT_ALLOWLIST.get(target_agent, [])
        response = route_request(target_agent, payload)
        
        action = response.get("action")
        agent_message = response.get("message")
        tool_calls = response.get("tool_calls")

        if action == "end_chat":
            logger.info(f"[ORCHESTRATOR] end_chat action triggered. Cleaning up session for wa_id: {wa_id}")
            deleted = session_manager.delete_session(wa_id, company_id)
            
            if deleted:
                logger.info(f"[ORCHESTRATOR] Session successfully deleted for wa_id: {wa_id}")
            else:
                logger.warning(f"[ORCHESTRATOR] Failed to delete session for wa_id: {wa_id}")

            dump_trace(channel)
            return {
                "type": "text",
                "message": agent_message,
                "agent": "receptionist_agent",
                "status": "completed",
                "session_deleted": deleted
            }

        if action == "route" and not agent_message:
            new_target = response.get("next_agent")
            new_domain = response.get("domain") if "domain" in response else session.get("domain")
            
            if not new_target:
                dump_trace(channel)
                return {"error": "Route action missing next_agent"}
            
            allowed_next = _AGENT_ALLOWLIST.get(target_agent, [])
            if new_target not in allowed_next:
                dump_trace(channel)
                return {
                    "type": "text",
                    "message": "No pude derivarte en este momento. ¿Podés intentar de nuevo?",
                    "agent": target_agent
                }
            
            session["target_agent"] = new_target
            session["domain"] = new_domain
            payload["session"] = session
            
            memory = apply_memory_patch(memory, response.get("memory", {}))
            memory = update_global(
                memory,
                last_agent=target_agent,
                last_action="passthrough",
                last_domain=new_domain,
            )
            session["agent_memory"] = memory
            target_agent = new_target
            continue
        
        break
    
    # Append user turn to memory AFTER routing chain resolved
    # (agents already include user_text in their own LLM context,
    #  appending before caused every message to appear twice)
    memory = append_turn(
        memory,
        role="user",
        text=mensaje,
        agent=target_agent,
        domain=session.get("domain"),
        action="input",
    )

    if chain_depth >= MAX_CHAIN_DEPTH:
        # Persist accumulated in-memory state before returning error
        session["agent_memory"] = memory
        session_manager.save_session(
            session_manager._get_composite_id(wa_id, company_id), session
        )
        dump_trace(channel)
        return {"error": "Max routing chain depth exceeded"}
    
    should_send_message = False
    if action in ["ask", "finish", "route"] and agent_message:
        should_send_message = True
    
    # Only send WhatsApp for whatsapp channel (wildix handles its own responses)
    # Fire-and-forget: the result is never used, so we avoid blocking ~230ms
    channel = payload.get("channel", "whatsapp")
    if should_send_message and phone_number_id and channel == "whatsapp":
        def _send_wa():
            try:
                send_whatsapp_response(
                    text=agent_message,
                    company_id=phone_number_id,
                    wa_id=wa_id,
                )
            except Exception:
                logger.exception("[ORCHESTRATOR] Fire-and-forget WhatsApp send failed")

        threading.Thread(target=_send_wa, daemon=True).start()

    elif should_send_message and not phone_number_id:
        pass

    if action == "ask":
        if agent_message:
            memory = append_turn(
                memory,
                role="assistant",
                text=agent_message,
                agent=target_agent,
                domain=session.get("domain"),
                action=action,
                tool_calls=tool_calls,
            )
        memory = apply_memory_patch(memory, response.get("memory", {}))
        memory = update_global(
            memory,
            last_agent=target_agent,
            last_action=action,
            last_domain=session.get("domain"),
        )
        # Persist all session changes in a single DB write (target_agent, domain, memory)
        session["target_agent"] = target_agent
        session["agent_memory"] = memory
        session_manager.save_session(session_id, session)
        dump_trace(channel)
        result = {
            "type": "text",
            "message": agent_message,
            "agent": target_agent
        }
        return result
        
    if action == "route":
        new_target = response.get("next_agent")
        new_domain = response.get("domain") if "domain" in response else session.get("domain")
        
        if not new_target:
            dump_trace(channel)
            return {"error": "Route action missing next_agent"}
        allowed_next = _AGENT_ALLOWLIST.get(target_agent, [])
        if new_target not in allowed_next:
            dump_trace(channel)
            return {
                "type": "text",
                "message": "No pude derivarte en este momento. ¿Podés intentar de nuevo?",
                "agent": target_agent
            }
        
        if agent_message:
            memory = append_turn(
                memory,
                role="assistant",
                text=agent_message,
                agent=target_agent,
                domain=new_domain,
                action=action,
                tool_calls=tool_calls,
            )
        memory = apply_memory_patch(memory, response.get("memory", {}))
        memory = update_global(
            memory,
            last_agent=target_agent,
            last_action=action,
            last_domain=new_domain,
        )
        # Persist all session changes in a single DB write
        session["target_agent"] = new_target
        session["domain"] = new_domain
        session["agent_memory"] = memory
        session_manager.save_session(session_id, session)
        
        dump_trace(channel)
        result = {
            "type": "transition", 
            "message": agent_message,
            "next_agent": new_target
        }
        return result
            
    if action == "finish":
        if agent_message:
            memory = append_turn(
                memory,
                role="assistant",
                text=agent_message,
                agent=target_agent,
                domain=session.get("domain"),
                action=action,
                tool_calls=tool_calls,
            )
        
        memory = update_global(
            memory,
            last_agent=target_agent,
            last_action=action,
            last_domain=session.get("domain"),
            consultation_completed=True,
        )
        # Persist all session changes in a single DB write (reset to receptionist)
        session["target_agent"] = "receptionist_agent"
        session["domain"] = None
        session["agent_memory"] = memory
        session_manager.save_session(session_id, session)
        
        dump_trace(channel)
        result = {
            "type": "text", 
            "message": agent_message, 
            "status": "completed"
        }
        return result

    dump_trace(channel)
    return {"error": "Unknown action"}