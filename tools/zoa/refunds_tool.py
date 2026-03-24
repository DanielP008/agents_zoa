import json
from langchain.tools import tool
from services.zoa_client import create_task_activity

@tool
def create_refund_request_tool(data: str) -> dict:
    """Registers a refund request by creating a task for the manager (JSON string).
    Expected fields: company_id, nif, policy_number, reason, amount, iban, phone (optional)."""
    try:
        payload = json.loads(data)
        
        # Extract fields
        company_id = payload.get("company_id")
        nif = payload.get("nif")
        policy_number = payload.get("policy_number", "Not specified")
        reason = payload.get("reason", "Not specified")
        amount = payload.get("amount", "Not specified")
        iban = payload.get("iban", "Not specified")
        phone = payload.get("phone")
        wa_id = payload.get("wa_id")
        
        if not company_id:
            return {"error": "company_id is required"}
        
        # Build description for the manager
        description = f"""Refund request:
- Policy: {policy_number}
- Reason: {reason}
- Amount: {amount}
- Destination IBAN: {iban}
- NIF: {nif or 'Not provided'}

The client requests a refund. Verify data and process."""
        
        # Create task + activity
        task_data = {
            "company_id": company_id,
            "title": f"Refund - Policy {policy_number}",
            "description": description,
            "card_type": "task",
            "type_of_activity": "call",
            "activity_title": "Manage refund",
            "activity_description": f"Contact the client to manage refund of {amount}",
        }
        
        if nif:
            task_data["nif"] = nif
        if phone:
            task_data["phone"] = phone
        if wa_id:
            task_data["mobile"] = wa_id
        
        result = create_task_activity(**task_data)
        
        # If successful, return friendly message
        if result.get("success") or result.get("status") == "success":
            return {
                "success": True,
                "message": "Refund request registered. A manager will contact you to process it."
            }
        else:
            return result
            
    except json.JSONDecodeError:
        return {"error": "Invalid JSON format"}
    except Exception as e:
        return {"error": str(e)}
