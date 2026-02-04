"""ZOA client with backward-compatible function wrappers."""

from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List, Union

from services.interfaces.zoa_interfaces import (
    ContactsInterface,
    ConversationsInterface,
    CardActionsInterface,
)


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


def send_whatsapp_response(
    text: str,
    company_id: str,
    wa_id: str = None,
) -> dict:
    """Send a WhatsApp message through ZOA."""
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


def create_task_activity(
    company_id: str,
    title: str,
    description: Optional[str] = None,
    card_type: str = "opportunity",
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
    pipeline_name: Optional[str] = None,
    stage_name: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Create a card and optionally an activity in ZOA (action='cardact').
    
    To link to a contact, provide at least one of: phone, email, nif, mobile.
    For 'llamada' activities, date and start_time are auto-set to now+5min if not provided.
    """
    # Auto-calculate date and start_time for 'llamada' activities (now + 1 day)
    if type_of_activity == "llamada":
        scheduled_time = datetime.now() + timedelta(days=1)
        if date is None:
            date = scheduled_time.strftime("%Y-%m-%d")
        if start_time is None:
            start_time = scheduled_time.strftime("%H:%M")
    
    # Build request data with required fields and defaults
    request_data = {
        "title": title,
        #"card_type": card_type,        # TODO: Add card_type back when ZOA supports it
        "amount": amount,
        "duration": duration,
        "repeat": repeat,
        "end_type": end_type,
        "type": activity_type,
    }
    
    # Optional fields mapping
    optional_fields = {
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
        "pipeline_name": pipeline_name,
        #"stage_name": stage_name, # switch to Nuevo
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
