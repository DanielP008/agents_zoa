import os
import requests
import json
from typing import Optional, Dict, Any

def _get_zoa_headers() -> Dict[str, str]:
    """Return headers for ZOA API requests."""
    api_key = os.environ.get("ZOA_API_KEY", "")
    return {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "apiKey": api_key
    }

def send_whatsapp_response(
    text: str,
    company_id: str,
    wa_id: str = None,
) -> dict:
    """Send a WhatsApp message through the ZOA Cloud Function."""
    zoa_endpoint = os.environ.get("ZOA_ENDPOINT_URL", "https://flow-zoa-673887944015.europe-southwest1.run.app")
    if not zoa_endpoint:
        return {"error": "ZOA_ENDPOINT_URL not configured"}

    conversation_id = f"{company_id}_{wa_id}"
    
    payload = {
        "action": "conversations",
        "option": "send",
        "company_id": company_id,
        "type": "text",
        "text": text,
        "conversation_id": conversation_id
    }
    

    try:
        headers = _get_zoa_headers()
        
        response = requests.post(zoa_endpoint, json=payload, headers=headers, timeout=10)
        
        try:
            response_json = response.json()
            return response_json
        except json.JSONDecodeError:
            return {"status": response.status_code, "text": response.text}
    except requests.exceptions.Timeout:
        return {"error": "Request timeout"}
    except requests.exceptions.ConnectionError as e:
        return {"error": f"Connection failed: {str(e)}"}
    except Exception as e:
        return {"error": str(e)}

def search_contact_by_phone(
    phone: str,
    company_id: str,
) -> Dict[str, Any]:
    """Search a contact in ZOA by phone."""
    zoa_endpoint = os.environ.get(
        "ZOA_ENDPOINT_URL",
        "https://flow-zoa-673887944015.europe-southwest1.run.app"
    )
    if not zoa_endpoint:
        return {"error": "ZOA_ENDPOINT_URL not configured"}

    payload = {
        "action": "contacts",
        "option": "search",
        "company_id": company_id,
        "phone": phone,
    }

    try:
        headers = _get_zoa_headers()
        response = requests.post(zoa_endpoint, json=payload, headers=headers, timeout=10)
        try:
            print(f"[ZOA_CLIENT] ZOA API raw response: {response.json()}")
            return response.json()
        except json.JSONDecodeError:
            return {"status": response.status_code, "text": response.text}
    except requests.exceptions.Timeout:
        return {"error": "Request timeout"}
    except requests.exceptions.ConnectionError as e:
        return {"error": f"Connection failed: {str(e)}"}
    except Exception as e:
        return {"error": str(e)}

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
    zoa_endpoint = os.environ.get(
        "ZOA_ENDPOINT_URL",
        "https://flow-zoa-673887944015.europe-southwest1.run.app"
    )
    if not zoa_endpoint:
        return {"error": "ZOA_ENDPOINT_URL not configured"}
    
    payload = {
        "action": "claims",
        "option": "create",
        **data
    }
    
    try:
        headers = _get_zoa_headers()
        response = requests.post(zoa_endpoint, json=payload, headers=headers, timeout=10)
        try:
            return response.json()
        except json.JSONDecodeError:
            return {"status": response.status_code, "text": response.text}
    except requests.exceptions.Timeout:
        return {"error": "Request timeout"}
    except requests.exceptions.ConnectionError as e:
        return {"error": f"Connection failed: {str(e)}"}
    except Exception as e:
        return {"error": str(e)}

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

def create_task_with_activity(
    task_description: str,
    client_nif: str,
    company_id: str,
    wa_id: Optional[str] = None,
    priority: str = "normal",
    activity_type: str = "call",
    attachments: Optional[list] = None,
    context: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Create a task with an activity in ZOA."""
    zoa_endpoint = os.environ.get(
        "ZOA_ENDPOINT_URL",
        "https://flow-zoa-673887944015.europe-southwest1.run.app"
    )
    if not zoa_endpoint:
        return {"error": "ZOA_ENDPOINT_URL not configured"}
    
    payload = {
        "action": "tasks",
        "option": "create_with_activity",
        "company_id": company_id,
        "task_description": task_description,
        "client_nif": client_nif,
        "priority": priority,
        "activity_type": activity_type,
    }
    
    if wa_id:
        payload["wa_id"] = wa_id
    if attachments:
        payload["attachments"] = attachments
    if context:
        payload["context"] = context
    
    try:
        headers = _get_zoa_headers()
        response = requests.post(zoa_endpoint, json=payload, headers=headers, timeout=10)
        try:
            return response.json()
        except json.JSONDecodeError:
            return {"status": response.status_code, "text": response.text}
    except requests.exceptions.Timeout:
        return {"error": "Request timeout"}
    except requests.exceptions.ConnectionError as e:
        return {"error": f"Connection failed: {str(e)}"}
    except Exception as e:
        return {"error": str(e)}