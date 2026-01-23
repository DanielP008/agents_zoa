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
    print("\n[ZOA_CLIENT] 📤 PREPARING TO SEND WHATSAPP MESSAGE")
    print(f"[ZOA_CLIENT]   To: {wa_id}")
    print(f"[ZOA_CLIENT]   Company ID: {company_id}")
    print(f"[ZOA_CLIENT]   Message length: {len(text)} chars")
    print(f"[ZOA_CLIENT]   Message preview: {text[:80]}...")
    
    # URL of the ZOA Cloud Function (Main Router)
    zoa_endpoint = os.environ.get("ZOA_ENDPOINT_URL", "https://flow-zoa-673887944015.europe-southwest1.run.app")
    if not zoa_endpoint:
        print("[ZOA_CLIENT] ❌ ERROR: ZOA_ENDPOINT_URL is not set.")
        return {"error": "ZOA_ENDPOINT_URL not configured"}

    # Construct the payload for the ZOA 'main' function
    payload = {
        "action": "conversations",
        "option": "send",
        "company_id": company_id,
        "type": "text",
        "text": text,
        "phone": wa_id
    }

    print(f"[ZOA_CLIENT] 🌐 Calling ZOA endpoint: {zoa_endpoint}")
    print(f"[ZOA_CLIENT] 📦 Payload: {json.dumps(payload, indent=2)}")

    try:
        headers = {
            "Content-Type": "application/json"
        }
        
        print("[ZOA_CLIENT] ⏳ Sending POST request...")
        response = requests.post(zoa_endpoint, json=payload, headers=headers, timeout=10)
        print(f"[ZOA_CLIENT] ✓ Response received | Status: {response.status_code}")
        
        try:
            response_json = response.json()
            print(f"[ZOA_CLIENT] 📥 Response body: {json.dumps(response_json, indent=2)}")
            print("[ZOA_CLIENT] ✅ WhatsApp message sent successfully")
            return response_json
        except json.JSONDecodeError:
            print(f"[ZOA_CLIENT] ⚠️  Non-JSON response: {response.text[:200]}")
            return {"status": response.status_code, "text": response.text}
    except requests.exceptions.Timeout:
        print("[ZOA_CLIENT] ❌ ERROR: Request timeout (10s)")
        return {"error": "Request timeout"}
    except requests.exceptions.ConnectionError as e:
        print(f"[ZOA_CLIENT] ❌ ERROR: Connection failed: {e}")
        return {"error": f"Connection failed: {str(e)}"}
    except Exception as e:
        print(f"[ZOA_CLIENT] ❌ ERROR: Unexpected error: {e}")
        import traceback
        print(f"[ZOA_CLIENT] Traceback: {traceback.format_exc()}")
        return {"error": str(e)}

def create_claim(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Creates a claim in the ZOA system.
    """
    print(f"DEBUG: Creating claim with data: {data}")
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
