"""Pre-processing helpers for the orchestrator: attachments, NIF extraction, welcome flow."""
import re
import logging

from core.db import SessionManager
from core.memory_schema import append_turn, update_global
from services.zoa_client import (
    send_whatsapp_response,
    search_contact_by_phone,
    extract_nif_from_contact_search,
)

logger = logging.getLogger(__name__)
session_manager = SessionManager()


def extract_attachments(payload: dict) -> list:
    """Extract media attachments from the incoming payload."""
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


def extract_nif_from_text(text: str) -> str:
    """Extract NIF/DNI/NIE/CIF from free text using regex."""
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


def handle_nif_and_welcome(
    memory: dict,
    mensaje: str,
    wa_id: str,
    company_id: str,
    channel: str = "whatsapp"
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
    print(f"\n[NIF_THINK] wa_id={wa_id} current_nif={nif_value} lookup_failed={nif_lookup_failed} message='{mensaje}'")
    if not nif_value and not nif_lookup_failed:
        # 1.1: Try to extract from current message
        nif_from_message = extract_nif_from_text(mensaje)
        if nif_from_message:
            print(f"[NIF_THINK] Extracted from message: {nif_from_message}")
            nif_value = nif_from_message
        
        # 1.2: Try CRM/ZOA lookup if still no NIF
        if not nif_value and wa_id and company_id:
            print(f"[NIF_THINK] Searching CRM for {wa_id}...")
            try:
                contact_response = search_contact_by_phone(wa_id, company_id)
                nif_value = extract_nif_from_contact_search(contact_response)
                print(f"[NIF_THINK] CRM result NIF: {nif_value}")
            except Exception as e:
                print(f"[NIF_THINK] CRM Error: {e}")
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
        
        # Send welcome message via WhatsApp (only for whatsapp channel)
        if company_id and channel == "whatsapp":
            send_whatsapp_response(
                text=welcome_message,
                company_id=company_id,
                wa_id=wa_id
            )
        
        return memory, nif_value, False, welcome_message  # Don't continue, return early
    
    # STEP 3: If we still don't have NIF after welcome, ask for it
    if not nif_value:
        # Try one more time to extract from current message
        nif_from_message = extract_nif_from_text(mensaje)
        
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
            
            # Send request via WhatsApp (only for whatsapp channel)
            if company_id and channel == "whatsapp":
                send_whatsapp_response(
                    text=nif_request_message,
                    company_id=company_id,
                    wa_id=wa_id
                )
            
            return memory, nif_value, False, nif_request_message  # Don't continue, return early
    
    # STEP 4: We have NIF, continue with normal flow
    logger.info(f"[NIF_HANDLER] NIF available: {nif_value} - proceeding to agents")
    return memory, nif_value, True, None
