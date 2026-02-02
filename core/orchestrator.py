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
    
    # company_id for ZOA (CRM/Tasks) is the phone_number_id (e.g. 521783407682043)
    zoa_company_id = phone_number_id
    
    # company_id for ERP is {phone_number_id}_{wa_id}
    erp_company_id = f"{phone_number_id}_{wa_id}" if phone_number_id and wa_id else phone_number_id
    
    safe_session_company_id = phone_number_id or "default"
    session = session_manager.get_session(wa_id, safe_session_company_id)
    target_agent = session.get("target_agent", "receptionist_agent")
    memory = ensure_memory_shape(session.get("agent_memory", {}))

    # Add both IDs to the payload for use by agents and tools
    payload["zoa_company_id"] = zoa_company_id
    payload["erp_company_id"] = erp_company_id

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

    global_mem = memory.get("global", {})
    nif_value = global_mem.get("nif")
    nif_lookup_failed = global_mem.get("nif_lookup_failed", False)
    
    print(f"\n[NIF DEBUG] === INICIO FLUJO NIF ===")
    print(f"[NIF DEBUG] wa_id: {wa_id}")
    print(f"[NIF DEBUG] zoa_company_id: {zoa_company_id}")
    print(f"[NIF DEBUG] nif_value en memoria: {nif_value}")
    print(f"[NIF DEBUG] nif_lookup_failed: {nif_lookup_failed}")
    
    if not nif_value and not nif_lookup_failed and wa_id and zoa_company_id:
        print(f"[NIF DEBUG] Buscando contacto por teléfono...")
        contact_response = search_contact_by_phone(wa_id, zoa_company_id)
        print(f"[NIF DEBUG] Respuesta de search_contact_by_phone: {contact_response}")
        nif_value = extract_nif_from_contact_search(contact_response)
        print(f"[NIF DEBUG] NIF extraído: {nif_value}")
    else:
        print(f"[NIF DEBUG] No se busca contacto (ya tenemos NIF o lookup falló anteriormente)")
    
    if nif_value:
        print(f"[NIF DEBUG] Guardando NIF en memoria: {nif_value}")
        memory = update_global(memory, nif=nif_value, nif_lookup_failed=False)
        session["agent_memory"] = memory
        session_manager.update_agent_memory(wa_id, memory, safe_session_company_id)
    elif not nif_lookup_failed and wa_id and zoa_company_id:
        print(f"[NIF DEBUG] No se encontró NIF, marcando lookup como fallido")
        memory = update_global(memory, nif_lookup_failed=True)
        session["agent_memory"] = memory
        session_manager.update_agent_memory(wa_id, memory, safe_session_company_id)
    
    print(f"[NIF DEBUG] === FIN FLUJO NIF === nif_final: {nif_value}\n")
    
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
            logger.info(f"end_chat action triggered. Cleaning up session for wa_id: {wa_id}, company_id: {safe_session_company_id}")
            deleted = session_manager.delete_session(wa_id, safe_session_company_id)
            
            if deleted:
                logger.info(f"Session successfully deleted for wa_id: {wa_id}, company_id: {safe_session_company_id}")
            else:
                logger.warning(f"Failed to delete session for wa_id: {wa_id}, company_id: {safe_session_company_id} - Session may not exist")

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
            
            session_manager.set_target_agent(wa_id, new_target, new_domain, safe_session_company_id)
            session_manager.update_agent_memory(wa_id, memory, safe_session_company_id)
            
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
        session_manager.update_agent_memory(wa_id, memory, safe_session_company_id)
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
        
        session_manager.set_target_agent(wa_id, new_target, new_domain, safe_session_company_id)
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
        session_manager.update_agent_memory(wa_id, memory, safe_session_company_id)
        
        result = {
            "type": "transition", 
            "message": agent_message,
            "next_agent": new_target
        }
        return result
            
    if action == "finish":
        session_manager.set_target_agent(wa_id, "receptionist_agent", None, safe_session_company_id)
        
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
        session_manager.update_agent_memory(wa_id, memory, safe_session_company_id)
        
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