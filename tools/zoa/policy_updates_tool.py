import json
from langchain.tools import tool
from services.zoa_client import create_task_activity

@tool
def update_policy_tool(data: str) -> dict:
    """Updates policy data by creating a task for the manager (JSON string).
    Expected fields: company_id, nif, policy_number, changes (dict), phone (optional)."""
    try:
        payload = json.loads(data)
        
        # Extract fields
        company_id = payload.get("company_id")
        nif = payload.get("nif")
        policy_number = payload.get("policy_number", "Not specified")
        changes = payload.get("changes", {})
        phone = payload.get("phone")
        wa_id = payload.get("wa_id")
        
        if not company_id:
            return {"error": "company_id is required"}
        if not changes:
            return {"error": "changes is required"}
        
        # Build description of changes
        changes_str = "\n".join([f"- {key}: {value}" for key, value in changes.items()])
        
        description = f"""Policy modification request:
- Policy: {policy_number}
- NIF: {nif or 'Not provided'}

Requested changes:
{changes_str}

The client requests these changes. Verify data and update policy."""
        
        # Create task + activity
        task_data = {
            "company_id": company_id,
            "title": f"Modify Policy {policy_number}",
            "description": description,
            "card_type": "task",
            "type_of_activity": "call",
            "activity_title": "Manage modification",
            "activity_description": f"Contact the client to confirm and apply changes in policy {policy_number}",
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
                "policy_number": policy_number,
                "updated_fields": list(changes.keys()),
                "message": "Modification request registered. A manager will verify the changes and confirm with you."
            }
        else:
            return result
            
    except json.JSONDecodeError:
        return {"error": "Invalid JSON format"}
    except Exception as e:
        return {"error": str(e)}
