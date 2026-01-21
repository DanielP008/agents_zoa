import os
import requests
import json
from typing import Optional, Dict, Any

def send_whatsapp_response(
    text: str, 
    company_id: str, 
    conversation_id: str = None, 
    to: str = None
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
    zoa_endpoint = os.environ.get("ZOA_ENDPOINT_URL")
    if not zoa_endpoint:
        print("ERROR: ZOA_ENDPOINT_URL is not set.")
        return {"error": "ZOA_ENDPOINT_URL not configured"}

    # Construct the payload for the ZOA 'main' function
    payload = {
        "action": "conversations",
        "option": "send",
        "company_id": company_id,
        "type": "text",
        "text": text
    }
    
    if conversation_id:
        payload["conversation_id"] = conversation_id
    elif to:
        payload["to"] = to
    else:
        return {"error": "Missing conversation_id or 'to' number"}

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
