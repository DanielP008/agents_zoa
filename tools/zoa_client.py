import os
import requests
import json
from typing import Optional, Dict, Any

def send_whatsapp_response(
    text: str, 
    company_id: str,  # phone_number_id 
    wa_id: str = None,  # waid
) -> dict:
    """
    Sends a WhatsApp message by calling the external ZOA Cloud Function.
    
    The ZOA Cloud Function expects:
    {
        "action": "conversations",
        "option": "send",
        "company_id": "...",
        "type": "text",
        "text": "...",
        "conversation_id": "..." (or "to")
    }
    """
    # URL of the ZOA Cloud Function (Main Router)
    zoa_endpoint = os.environ.get("ZOA_ENDPOINT_URL", "https://us-central1-zoasuite-5b94e.cloudfunctions.net/zoa_mcp")
    if not zoa_endpoint:
        print("ERROR: ZOA_ENDPOINT_URL is not set.")
        return {"error": "ZOA_ENDPOINT_URL not configured"}

    # Construct the payload for the ZOA 'main' function
    payload = {
        "action": "conversations",
        "option": "send",
        "company_id": company_id,
        "type": "text",
        "text": text,
        "phone":wa_id
    }

    try:
        # We don't need to send auth headers if the receiving Cloud Function 
        # hardcodes the token or handles it internally as per the snippet.
        # But we might need standard headers.
        headers = {
            "Content-Type": "application/json"
        }

        print(f"DEBUG: Calling ZOA Endpoint {zoa_endpoint}")
        response = requests.post(zoa_endpoint, json=payload, headers=headers, timeout=10)
        
        try:
            return response.json()
        except json.JSONDecodeError:
            return {"status": response.status_code, "text": response.text}

    except Exception as e:
        print(f"ERROR: Failed to call ZOA Endpoint: {e}")
        return {"error": str(e)}

def create_claim(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Creates a claim in the ZOA system.
    """
    # This is a placeholder. In a real scenario, this would POST to an endpoint.
    # For now, we'll just log it and return a success mock.
    print(f"DEBUG: Creating claim with data: {data}")
    
    # Example logic to call an external API could go here
    # zoa_endpoint = os.environ.get("ZOA_ENDPOINT_URL") ...
    
    return {
        "status": "success",
        "claim_id": "CLM-" + str(os.urandom(4).hex()),
        "message": "Siniestro registrado correctamente"
    }

def fetch_policy(policy_number: str) -> Dict[str, Any]:
    """
    Fetches policy information from ZOA.
    """
    print(f"DEBUG: Fetching policy {policy_number}")
    
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
