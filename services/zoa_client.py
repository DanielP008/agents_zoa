import os
import requests
import json
from typing import Optional, Dict, Any, List, Union
from langchain_core.tools import tool

def _get_zoa_headers() -> Dict[str, str]:
    """Return headers for ZOA API requests."""
    return {
        "Content-Type": "application/json",
    }

def _make_zoa_request(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Helper to send requests to ZOA Cloud Function."""
    zoa_endpoint = os.environ.get(
        "ZOA_ENDPOINT_URL",
        "https://prod-flow-zoa-673887944015.europe-southwest1.run.app"
    )

    # Strip quotes if present (some .env loaders include them)
    zoa_endpoint = zoa_endpoint.strip('"').strip("'")
    
    print(f"[ZOA_CLIENT] Using endpoint: {zoa_endpoint}")

    if not zoa_endpoint:
        return {"error": "ZOA_ENDPOINT_URL not configured"}

    try:
        headers = _get_zoa_headers()
        # Debug print can be removed in production
        # print(f"[ZOA_CLIENT] Sending payload: {payload}")
        
        response = requests.post(zoa_endpoint, headers=headers, data=json.dumps(payload), timeout=10)
        
        try:
            # print(f"[ZOA_CLIENT] Response: {response.text}")
            return response.json()
        except json.JSONDecodeError:
            return {"status": response.status_code, "text": response.text}
    except requests.exceptions.Timeout:
        return {"error": "Request timeout"}
    except requests.exceptions.ConnectionError as e:
        return {"error": f"Connection failed: {str(e)}"}
    except Exception as e:
        return {"error": str(e)}

def send_whatsapp_response(
    text: str,
    company_id: str,
    wa_id: str = None,
) -> dict:
    """Send a WhatsApp message through the ZOA Cloud Function."""
    conversation_id = f"{company_id}_{wa_id}"
    
    payload = {
        "action": "conversations",
        "option": "send",
        "company_id": company_id,
        "type": "text",
        "text": text,
        "conversation_id": conversation_id
    }
    
    return _make_zoa_request(payload)

def search_contact_by_phone(
    phone: str,
    company_id: str,
) -> Dict[str, Any]:
    """Search a contact in ZOA by phone."""
    payload = {
        "action": "contacts",
        "option": "search",
        "company_id": company_id,
        "phone": phone,
    }
    return _make_zoa_request(payload)

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

def create_claim(data: Dict[str, Any]) -> Dict[str, Any]:
    """Create a claim (siniestro) in ZOA."""
    payload = {
        "action": "claims",
        "option": "create",
        **data
    }
    return _make_zoa_request(payload)

def fetch_policy(policy_number: str) -> Dict[str, Any]:
    """Fetch policy information from ZOA."""
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
    """
    # Base payload with required fields and defaults
    payload = {
        "action": "cardact",
        "option": "create",
        "company_id": company_id,
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
        "stage_name": stage_name,
    }
    
    # Update payload with non-None optional fields
    payload.update({k: v for k, v in optional_fields.items() if v is not None})
    
    print("=" * 80)
    print("[ZOA_CLIENT] create_task_activity - PAYLOAD COMPLETO:")
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    print("=" * 80)
    
    result = _make_zoa_request(payload)
    
    print("[ZOA_CLIENT] create_task_activity - RESPUESTA DEL BACKEND:")
    print(json.dumps(result, indent=2, ensure_ascii=False))
    print("=" * 80)
    
    return result

