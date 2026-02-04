import os
import re
import logging
from core.db import SessionManager

logger = logging.getLogger(__name__)
from core.memory_schema import (
    append_turn,
    apply_memory_patch,
    ensure_memory_shape,
    update_global,
)
from core.routing.main_router import route_request
from services.zoa_client import (
    send_whatsapp_response,
    search_contact_by_phone,
    extract_nif_from_contact_search,
)
from core.routing.allowlist import build_agent_allowlist, load_routes_config

session_manager = SessionManager()

_ROUTES_CONFIG = load_routes_config()
_AGENT_ALLOWLIST = build_agent_allowlist(_ROUTES_CONFIG)

def process_message(payload: dict) -> dict:
    
    wa_id = payload.get("wa_id")
    mensaje = payload.get("mensaje")
    phone_number_id = payload.get("phone_number_id")
    
    company_id = phone_number_id or "default"
    # Add company_id to payload for agents and tools
    payload["company_id"] = company_id

    session = session_manager.get_session(wa_id, company_id)
    target_agent = session.get("target_agent", "receptionist_agent")
    memory = ensure_memory_shape(session.get("agent_memory", {}))

    # Handle attachments
    attachments = _extract_attachments(payload)
    if attachments:
        global_mem = memory.get("global", {})
        existing = global_mem.get("attachments", [])
        if not isinstance(existing, list):
            existing = []
        memory = update_global(memory, attachments=existing + attachments)
        session["agent_memory"] = memory

        if not mensaje:
            mensaje = "[imagen adjunta]"
            payload["mensaje"] = mensaje

    # Handle NIF lookup and welcome message
    memory, nif_value, should_continue, generated_message = _handle_nif_and_welcome(
        memory, 
        mensaje, 
        wa_id, 
        company_id
    )
    
    session["agent_memory"] = memory
    
    # If _handle_nif_and_welcome returned should_continue=False, return early
    if not should_continue:
        return {
            "type": "text",
            "message": generated_message or memory.get("global", {}).get("last_message", ""),
            "agent": "orchestrator"
        }
    
    # Now proceed with normal agent flow
    memory = append_turn(
        memory,
        role="user",
        text=mensaje,
        agent=target_agent,
        domain=session.get("domain"),
        action="input",
    )
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

        if action == "end_chat":
            logger.info(f"[ORCHESTRATOR] end_chat action triggered. Cleaning up session for wa_id: {wa_id}")
            deleted = session_manager.delete_session(wa_id, company_id)
            
            if deleted:
                logger.info(f"[ORCHESTRATOR] Session successfully deleted for wa_id: {wa_id}")
            else:
                logger.warning(f"[ORCHESTRATOR] Failed to delete session for wa_id: {wa_id}")

            return {
                "type": "text",
                "message": agent_message,
                "agent": "receptionist_agent",
                "status": "completed",
                "session_deleted": deleted
            }

        if action == "route" and not agent_message:
            new_target = response.get("next_agent")
            new_domain = response.get("domain")
            if new_domain is None:
                new_domain = session.get("domain")
            
            if not new_target:
                return {"error": "Route action missing next_agent"}
            
            allowed_next = _AGENT_ALLOWLIST.get(target_agent, [])
            if new_target not in allowed_next:
                return {
                    "type": "text",
                    "message": "No pude derivarte en este momento. ¿Podés intentar de nuevo?",
                    "agent": target_agent
                }
            
            session["target_agent"] = new_target
            if new_domain:
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
            
            session_manager.set_target_agent(wa_id, new_target, new_domain, company_id)
            session_manager.update_agent_memory(wa_id, memory, company_id)
            
            target_agent = new_target
            continue
        
        break
    
    if chain_depth >= MAX_CHAIN_DEPTH:
        return {"error": "Max routing chain depth exceeded"}
    
    should_send_message = False
    if action in ["ask", "finish", "route"] and agent_message:
        should_send_message = True
        
    if should_send_message and phone_number_id:
        whatsapp_result = send_whatsapp_response(
            text=agent_message,
            company_id=phone_number_id,
            wa_id=wa_id
        )
        
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
            )
        memory = apply_memory_patch(memory, response.get("memory", {}))
        memory = update_global(
            memory,
            last_agent=target_agent,
            last_action=action,
            last_domain=session.get("domain"),
        )
        session_manager.update_agent_memory(wa_id, memory, company_id)
        result = {
            "type": "text",
            "message": agent_message,
            "agent": target_agent
        }
        return result
        
    if action == "route":
        new_target = response.get("next_agent")
        new_domain = response.get("domain")
        if new_domain is None:
            new_domain = session.get("domain")
        
        if not new_target:
            return {"error": "Route action missing next_agent"}
        allowed_next = _AGENT_ALLOWLIST.get(target_agent, [])
        if new_target not in allowed_next:
            return {
                "type": "text",
                "message": "No pude derivarte en este momento. ¿Podés intentar de nuevo?",
                "agent": target_agent
            }
        
        session_manager.set_target_agent(wa_id, new_target, new_domain, company_id)
        if agent_message:
            memory = append_turn(
                memory,
                role="assistant",
                text=agent_message,
                agent=target_agent,
                domain=new_domain,
                action=action,
            )
        memory = apply_memory_patch(memory, response.get("memory", {}))
        memory = update_global(
            memory,
            last_agent=target_agent,
            last_action=action,
            last_domain=new_domain,
        )
        session_manager.update_agent_memory(wa_id, memory, company_id)
        
        result = {
            "type": "transition", 
            "message": agent_message,
            "next_agent": new_target
        }
        return result
            
    if action == "finish":
        session_manager.set_target_agent(wa_id, "receptionist_agent", None, company_id)
        
        if agent_message:
            memory = append_turn(
                memory,
                role="assistant",
                text=agent_message,
                agent=target_agent,
                domain=session.get("domain"),
                action=action,
            )
        
        memory = update_global(
            memory,
            last_agent=target_agent,
            last_action=action,
            last_domain=session.get("domain"),
            consultation_completed=True,
        )
        session_manager.update_agent_memory(wa_id, memory, company_id)
        
        result = {
            "type": "text", 
            "message": agent_message, 
            "status": "completed"
        }
        return result

    return {"error": "Unknown action"}

def _extract_attachments(payload: dict) -> list:
    attachments = []
    media = payload.get("media")
    if isinstance(media, dict):
        media = [media]
    if isinstance(media, list):
        for item in media:
            if not isinstance(item, dict):
                continue
            data = item.get("data") or item.get("base64")
            if not data:
                continue
            attachments.append(
                {
                    "mime_type": item.get("mime_type") or item.get("type") or "application/octet-stream",
                    "data": data,
                    "filename": item.get("filename"),
                    "source": "media",
                }
            )
    image_b64 = payload.get("image_base64")
    if image_b64:
        attachments.append(
            {
                "mime_type": payload.get("image_mime_type") or "image/jpeg",
                "data": image_b64,
                "filename": payload.get("image_filename"),
                "source": "image_base64",
            }
        )
    return attachments

def _extract_nif_from_text(text: str) -> str:
    """Extract NIF/DNI/NIE/CIF from text."""
    if not text:
        return ""
    patterns = [
        r"\b\d{8}[A-Za-z]\b",
        r"\b[XYZ]\d{7}[A-Za-z]\b",
        r"\b[A-Za-z]\d{7}[A-Za-z0-9]\b",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return match.group(0).upper()
    return ""

def _handle_nif_and_welcome(
    memory: dict,
    mensaje: str,
    wa_id: str,
    company_id: str
) -> tuple[dict, str, bool, str | None]:
    """
    Handle NIF lookup and welcome message logic.
    
    Returns:
        tuple: (updated_memory, nif_value, should_continue, generated_message)
               should_continue=False means orchestrator needs to return early with a message
    """
    global_mem = memory.get("global", {})
    nif_value = global_mem.get("nif")
    nif_lookup_failed = global_mem.get("nif_lookup_failed", False)
    orchestrator_welcomed = global_mem.get("orchestrator_welcomed", False)
    
    logger.info(f"[NIF_HANDLER] wa_id: {wa_id}, nif: {nif_value}, welcomed: {orchestrator_welcomed}")
    
    # STEP 1: Try to get NIF if we don't have it yet
    if not nif_value and not nif_lookup_failed:
        # 1.1: Try to extract from current message
        nif_from_message = _extract_nif_from_text(mensaje)
        if nif_from_message:
            logger.info(f"[NIF_HANDLER] NIF extracted from message: {nif_from_message}")
            nif_value = nif_from_message
        
        # 1.2: Try CRM/ZOA lookup if still no NIF
        if not nif_value and wa_id and company_id:
            logger.info(f"[NIF_HANDLER] Attempting ZOA CRM lookup for wa_id={wa_id}, company_id={company_id}")
            try:
                contact_response = search_contact_by_phone(wa_id, company_id)
                logger.info(f"[NIF_HANDLER] Raw contact response: {contact_response}")
                nif_value = extract_nif_from_contact_search(contact_response)
                logger.info(f"[NIF_HANDLER] Extracted NIF from contact: {nif_value}")
            except Exception as e:
                logger.error(f"[NIF_HANDLER] Error during contact lookup: {e}", exc_info=True)
            
        # 1.3: Save NIF or mark lookup as failed
        if nif_value:
            logger.info(f"[NIF_HANDLER] NIF found: {nif_value}")
            memory = update_global(memory, nif=nif_value, nif_lookup_failed=False)
            session_manager.update_agent_memory(wa_id, memory, company_id)
        else:
            logger.info(f"[NIF_HANDLER] No NIF found, marking lookup as failed")
            memory = update_global(memory, nif_lookup_failed=True)
            session_manager.update_agent_memory(wa_id, memory, company_id)
    
    # STEP 2: Send welcome message if first interaction
    if not orchestrator_welcomed:
        logger.info(f"[NIF_HANDLER] First interaction - preparing welcome message")
        
        # Build welcome message based on whether we have NIF
        if nif_value:
            welcome_message = (
                "¡Hola! Soy Sofía, la recepcionista virtual de ZOA Seguros. "
                "Estoy aquí para ayudarte con lo que necesites: puedo asistirte si has tenido un siniestro o necesitas una grúa, "
                "ayudarte con la gestión de tu póliza y devoluciones, o asesorarte si buscas contratar un nuevo seguro o mejorar tu cobertura actual. "
                "¿En qué puedo ayudarte hoy?"
            )
        else:
            welcome_message = (
                "¡Hola! Soy Sofía, la recepcionista virtual de ZOA Seguros. "
                "Para poder ayudarte, necesito tu NIF, DNI, NIE o CIF. ¿Podrías proporcionármelo?"
            )
        
        memory = update_global(memory, orchestrator_welcomed=True)
        memory = append_turn(
            memory,
            role="assistant",
            text=welcome_message,
            agent="orchestrator",
            domain=None,
            action="welcome",
        )
        session_manager.update_agent_memory(wa_id, memory, company_id)
        
        # Send welcome message via WhatsApp
        if company_id:
            send_whatsapp_response(
                text=welcome_message,
                company_id=company_id,
                wa_id=wa_id
            )
        
        return memory, nif_value, False, welcome_message  # Don't continue, return early
    
    # STEP 3: If we still don't have NIF after welcome, ask for it
    if not nif_value:
        # Try one more time to extract from current message
        nif_from_message = _extract_nif_from_text(mensaje)
        
        if nif_from_message:
            nif_value = nif_from_message
            memory = update_global(memory, nif=nif_value, nif_lookup_failed=False)
            session_manager.update_agent_memory(wa_id, memory, company_id)
            logger.info(f"[NIF_HANDLER] NIF captured from user message: {nif_value}")
            return memory, nif_value, True, None  # Continue with normal flow
        else:
            # Still no NIF - ask for it
            logger.info(f"[NIF_HANDLER] No NIF available - requesting from user")
            nif_request_message = "Necesito tu NIF, DNI, NIE o CIF para continuar. ¿Podrías proporcionármelo?"
            
            memory = append_turn(
                memory,
                role="user",
                text=mensaje,
                agent="orchestrator",
                domain=None,
                action="input",
            )
            memory = append_turn(
                memory,
                role="assistant",
                text=nif_request_message,
                agent="orchestrator",
                domain=None,
                action="ask_nif",
            )
            session_manager.update_agent_memory(wa_id, memory, company_id)
            
            # Send request via WhatsApp
            if company_id:
                send_whatsapp_response(
                    text=nif_request_message,
                    company_id=company_id,
                    wa_id=wa_id
                )
            
            return memory, nif_value, False, nif_request_message  # Don't continue, return early
    
    # STEP 4: We have NIF, continue with normal flow
    logger.info(f"[NIF_HANDLER] NIF available: {nif_value} - proceeding to agents")
    return memory, nif_value, True, None