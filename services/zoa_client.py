"""ZOA client with backward-compatible function wrappers."""

import threading
import re
import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List, Union

from langsmith import traceable
from services.interfaces.zoa_interfaces import (
    ContactsInterface,
    ConversationsInterface,
    CardActionsInterface,
    AiChatInterface,
)

logger = logging.getLogger(__name__)


def extract_nif_from_contact_search(response: Dict[str, Any]) -> str:
    """Extract NIF from a ZOA contact search response."""
    if not isinstance(response, dict):
        return ""
    data = response.get("data")
    if isinstance(data, list) and data:
        return (data[0] or {}).get("nif", "") or ""
    if isinstance(data, dict):
        return data.get("nif", "") or ""
    return response.get("nif", "") or ""

def download_media(wamid: str, company_id: str) -> Dict[str, Any]:
    """Download media via ZOA (action=conversations, option=search) using wamid."""
    interface = ConversationsInterface()
    result, _ = interface.execute(
        company_id=company_id,
        option="search",
        request_data={"wamid": wamid},
    )
    return result

def send_whatsapp_response_sync(
    text: str,
    company_id: str,
    wa_id: str = None,
) -> dict:
    """Send a WhatsApp message through ZOA (Synchronous)."""
    conversation_id = f"{company_id}_{wa_id}"
    
    interface = ConversationsInterface()
    result, _ = interface.execute(
        company_id=company_id,
        option="send",
        request_data={
            "type": "text",
            "text": text,
            "conversation_id": conversation_id
        }
    )
    return result

def send_whatsapp_response(
    text: str,
    company_id: str,
    wa_id: str = None,
) -> dict:
    """
    Send a WhatsApp message through ZOA in a background thread (fire-and-forget).
    
    This prevents the agent from blocking while waiting for the message to be sent.
    """
    def _task():
        try:
            send_whatsapp_response_sync(text, company_id, wa_id)
        except Exception as e:
            logger.error(f"[ZOA_CLIENT] Failed to send async WhatsApp message: {e}")

    thread = threading.Thread(target=_task, daemon=True)
    thread.start()
    
    # Return a dummy success response immediately
    return {"success": True, "message": "Message queued in background"}

def send_aichat_response(
    text: str,
    company_id: str,
    user_id: str = None,
) -> dict:
    """Send an AiChat message through ZOA."""
    logger.info(f"[ZOA_CLIENT] Sending AiChat response. User: {user_id}, Company: {company_id}, Text: {text[:50]}...")
    interface = AiChatInterface()
    result, _ = interface.execute(
        company_id=company_id,
        option="send",
        request_data={
            "user_id": user_id,
            "body_type": "text",
            "body": {"data": text},
        }
    )
    return result

def create_aichat_card(
    company_id: str,
    user_id: str,
    call_id: str,
    body_type: str,
    data: Dict[str, Any],
    complete: bool = False,
) -> Dict[str, Any]:
    """Create a tarification card (auto_sheet / home_sheet) via ZOA AI Chat."""
    logger.info(f"[ZOA_CLIENT] Creating card: body_type={body_type}, call_id={call_id}, complete={complete}")
    interface = AiChatInterface()
    result, status = interface.execute(
        company_id=company_id,
        option="create",
        request_data={
            "user_id": user_id,
            "body_type": body_type,
            "call_id": call_id,
            "complete": str(complete).lower(),
            "data": data,
        },
    )
    if status != 200:
        logger.error(f"[ZOA_CLIENT] Card create failed ({status}): {result}")
    return result


def update_aichat_card(
    company_id: str,
    user_id: str,
    call_id: str,
    body_type: str,
    data: Dict[str, Any],
    complete: bool = False,
) -> Dict[str, Any]:
    """Update an existing tarification card via ZOA AI Chat."""
    logger.info(f"[ZOA_CLIENT] Updating card: body_type={body_type}, call_id={call_id}, complete={complete}")
    interface = AiChatInterface()
    result, status = interface.execute(
        company_id=company_id,
        option="update",
        request_data={
            "user_id": user_id,
            "body_type": body_type,
            "call_id": call_id,
            "complete": str(complete).lower(),
            "data": data,
        },
    )
    if status != 200:
        logger.error(f"[ZOA_CLIENT] Card update failed ({status}): {result}")
    return result


def search_contact_by_phone(
    phone: str,
    company_id: str,
) -> Dict[str, Any]:
    """Search a contact in ZOA by phone."""
    interface = ContactsInterface()
    result, _ = interface.execute(
        company_id=company_id,
        option="search",
        request_data={"phone": phone}
    )
    return result

def fetch_policy(policy_number: str) -> Dict[str, Any]:
    """Fetch policy information from ZOA."""
    # TODO: Implement with real ZOA interface when available
    if policy_number == "not_found":
        return {"error": "Policy not found"}
    return {
        "policy_number": policy_number,
        "status": "active",
        "holder": "Usuario de Prueba",
        "type": "auto",
        "coverage": "Todo Riesgo",
        "valid_until": "2026-12-31"
    }

@traceable(name="ZOA CRM Create Activity", run_type="tool")
def create_task_activity(
    company_id: str,
    title: str,
    description: Optional[str] = None,
    card_type: Optional[str] = None,
    amount: float = 0.0,
    tags_name: Optional[Union[List[str], str]] = None,
    type_of_activity: Optional[str] = None,
    activity_title: Optional[str] = None,
    activity_description: Optional[str] = None,
    guests_names: Optional[Union[List[str], str]] = None,
    activity_type: str = "sales",
    date: Optional[str] = None,
    start_time: Optional[str] = None,
    duration: int = 30,
    repeat: bool = False,
    repetition_type: Optional[str] = None,
    repetitions_number: Optional[int] = None,
    end_type: str = "never",
    end_date: Optional[str] = None,
    phone: Optional[str] = None,
    email: Optional[str] = None,
    nif: Optional[str] = None,
    mobile: Optional[str] = None,
    name: Optional[str] = None,
    pipeline_name: Optional[str] = None,
    stage_name: Optional[str] = None,
    manager_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Create a card and optionally an activity in ZOA (action='cardact').
    
    To link to a contact, provide at least one of: phone, email, nif, mobile.
    For 'llamada' activities, date and start_time are auto-set to now+5min if not provided.
    """
    # tags_name must always include "<Dominio>-<Ramo>" (e.g. "Siniestros-Hogar")
    text_low = f"{title}\n{description or ''}".lower()
    if any(k in text_low for k in ("siniestro", "asistencia", "grua", "grúa", "carretera")):
        domain_tag = "Siniestros"
    elif any(k in text_low for k in ("póliza", "poliza", "devolución", "devolucion", "modificar", "modificación", "iban")):
        domain_tag = "Gestion"
    elif any(k in text_low for k in ("venta", "cotización", "cotizacion", "contratar", "presupuesto")):
        domain_tag = "Ventas"
    else:
        domain_tag = "General"

    ramo_text = f"{title}\n{description or ''}"
    ramo_match = re.search(
        r"(?i)\b(?:ramo|tipo de póliza|tipo de poliza)\s*:\s*([^\n\r,;]+)",
        ramo_text,
    )
    ramo_candidate = (ramo_match.group(1) if ramo_match else "").strip().strip("[]()").strip()
    ramo_search = ramo_candidate.lower() if ramo_candidate else text_low

    if "responsabilidad civil" in ramo_search or re.search(r"\brc\b", ramo_search):
        ramo_tag = "RC"
    elif "hogar" in ramo_search:
        ramo_tag = "Hogar"
    elif any(k in ramo_search for k in ("auto", "coche", "vehiculo", "vehículo")):
        ramo_tag = "Auto"
    elif "transport" in ramo_search:
        ramo_tag = "Transportes"
    elif "accident" in ramo_search:
        ramo_tag = "Accidentes"
    elif "comunidad" in ramo_search:
        ramo_tag = "Comunidades"
    elif "pyme" in ramo_search and "comerc" in ramo_search:
        ramo_tag = "Pyme/Comercio"
    elif "pyme" in ramo_search:
        ramo_tag = "Pyme"
    elif "comerc" in ramo_search:
        ramo_tag = "Comercios"
    else:
        ramo_tag = (ramo_candidate[:1].upper() + ramo_candidate[1:]) if ramo_candidate else "General"

    required_tag = f"{domain_tag}-{ramo_tag}"
    if isinstance(tags_name, list):
        if not any(str(t).strip().lower() == required_tag.lower() for t in tags_name):
            tags_name = [*tags_name, required_tag]
    elif isinstance(tags_name, str) and tags_name.strip():
        existing = [t.strip().lower() for t in tags_name.split(",") if t.strip()]
        if required_tag.lower() not in existing:
            tags_name = f"{tags_name},{required_tag}"
    else:
        tags_name = required_tag

    # Auto-calculate date and start_time for 'llamada' activities (now)
    if type_of_activity == "llamada":
        now = datetime.now()
        if date is None:
            date = now.strftime("%Y-%m-%d")
        if start_time is None:
            start_time = now.strftime("%H:%M")
    
    # Determine card_type based on domain if not explicitly provided
    if not card_type:
        domain_tag_lower = domain_tag.lower()
        if domain_tag_lower == "ventas":
            card_type = "opportunity"
        else:
            card_type = "task"

    # Determine pipeline_name based on card_type if not explicitly provided
    if not pipeline_name:
        card_type_lower = card_type.lower()
        if card_type_lower == "opportunity":
            if any(k in text_low for k in ("renovación", "renovacion", "renovar", "retarificación", "retarificacion")):
                pipeline_name = "Renovaciones"
            else:
                pipeline_name = "Cotizaciones"
        else:
            pipeline_name = "Cotizaciones"

    # Build request data with required fields and defaults
    request_data = {
        "title": title,
        "card_type": card_type,
        "amount": amount,
        "duration": duration,
        "repeat": repeat,
        "end_type": end_type,
        "type": activity_type,
    }

    # Optional fields mapping
    optional_fields = {
        "manager_id": manager_id,
        "description": description,
        "tags_name": tags_name,
        "type_of_activity": type_of_activity,
        "activity_title": activity_title,
        "activity_description": activity_description,
        "guests_names": guests_names,
        "date": date,
        "start_time": start_time,
        "repetition_type": repetition_type,
        "repetitions_number": repetitions_number,
        "end_date": end_date,
        "phone": phone,
        "email": email,
        "nif": nif,
        "mobile": mobile,
        "name": name,
        "pipeline_name": pipeline_name,
    }
    
    # Update with non-None optional fields
    request_data.update({k: v for k, v in optional_fields.items() if v is not None})
    
    interface = CardActionsInterface()
    result, _ = interface.execute(
        company_id=company_id,
        option="create",
        request_data=request_data
    )
    return result
