import os
import requests
import json
from typing import Optional, Dict, Any

def send_whatsapp_response(
    text: str, 
    company_id: str,    # phone_number_id 
    wa_id: str = None,  # reciever's name
) -> dict:
    """
    Sends a WhatsApp message by calling the external ZOA Cloud Function.
    
    The ZOA Cloud Function main() expects:
    {
        "action": "conversations",
        "option": "send",
        "company_id": "...",  # Required by Cloud Function validation
        ...
    }
    
    ZoaConversation.send() expects (for text messages):
    {
        "phone_number_id": "...",  # Preferred, or company_id as fallback
        "type": "text",
        "text": "...",
        "phone": "..."  # Used when conversation_id is not present
    }
    """
    
    # URL of the ZOA Cloud Function (Main Router)
    zoa_endpoint = os.environ.get("ZOA_ENDPOINT_URL", "https://flow-zoa-673887944015.europe-southwest1.run.app")
    if not zoa_endpoint:
        return {"error": "ZOA_ENDPOINT_URL not configured"}

    # Construct the payload for the ZOA Cloud Function

    conversation_id = f"{company_id}_{wa_id}"
    
    payload = {
        "action": "conversations",
        "option": "send",
        "company_id": company_id,  # Required by Cloud Function main()
        "type": "text",
        "text": text,
        "conversation_id": conversation_id
    }
    

    try:
        headers = {
            "Content-Type": "application/json"
        }
        
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

def create_claim(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Creates a claim in the ZOA system.
    """
    return {
        "status": "success",
        "claim_id": "CLM-" + str(os.urandom(4).hex()),
        "message": "Siniestro registrado correctamente"
    }

def fetch_policy(policy_number: str) -> Dict[str, Any]:
    """
    Fetches policy information from ZOA.
    """
    
    # Mock response
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
