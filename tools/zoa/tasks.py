import json
from langchain_core.tools import tool
from services.zoa_client import create_task_activity

@tool
def create_task_activity_tool(data: str) -> dict:
    """
    Creates a task/card and optionally an activity in ZOA.
    Input should be a JSON string with the following fields:
    - company_id: str (required)
    - title: str (required, title of the card)
    - description: str (optional)
    - card_type: str (optional, default "opportunity")
    - amount: float (optional)
    - tags_name: List[str] or str (optional, comma separated)
    - type_of_activity: str (optional, one of: "llamada", "reunion", "whatsapp", "email", "tarea". If present, creates activity)
    - activity_title: str (optional)
    - activity_description: str (optional)
    - guests_names: List[str] or str (optional)
    - activity_type: str (optional, default "sales")
    - date: str (optional, YYYY-MM-DD)
    - start_time: str (optional, HH:MM)
    - duration: int (optional, minutes)
    - repeat: bool (optional)
    - repetition_type: str (optional)
    - repetitions_number: int (optional)
    - end_type: str (optional)
    - end_date: str (optional)
    - phone: str (optional, to link contact)
    - email: str (optional, to link contact)
    - mobile: str (optional, to link contact)
    """
    VALID_ACTIVITY_TYPES = ["llamada", "reunion", "whatsapp", "email", "tarea"]
    
    try:
        payload = json.loads(data)
        
        # Validate required fields
        if "company_id" not in payload:
            return {"error": "company_id is required"}
        if "title" not in payload:
            return {"error": "title is required"}
        
        # Validate type_of_activity if provided
        type_of_activity = payload.get("type_of_activity")
        if type_of_activity and type_of_activity not in VALID_ACTIVITY_TYPES:
            return {
                "error": f"type_of_activity must be one of {VALID_ACTIVITY_TYPES}, got '{type_of_activity}'"
            }
            
        return create_task_activity(**payload)
    except json.JSONDecodeError:
        return {"error": "Invalid JSON format"}
    except Exception as e:
        return {"error": str(e)}
