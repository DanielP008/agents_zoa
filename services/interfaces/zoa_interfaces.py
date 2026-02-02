"""ZOA API interfaces following internal ZOA interface pattern."""

import os
import requests
import json
import logging
from typing import Optional, Dict, Any, Tuple

logger = logging.getLogger(__name__)


def _get_zoa_headers() -> Dict[str, str]:
    """Return headers for ZOA API requests."""
    api_key = os.environ.get("ZOA_API_KEY", "")
    return {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "apiKey": api_key
    }


def _make_zoa_request(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Helper to send requests to ZOA Cloud Function."""
    zoa_endpoint = os.environ.get(
        "ZOA_ENDPOINT_URL",
        "https://prod-flow-zoa-673887944015.europe-southwest1.run.app"
    )
    zoa_endpoint = zoa_endpoint.strip('"').strip("'")
    
    if not zoa_endpoint:
        return {"error": "ZOA_ENDPOINT_URL not configured"}

    try:
        headers = _get_zoa_headers()
        logger.debug(f"ZOA request: {payload}")
        response = requests.post(zoa_endpoint, headers=headers, data=json.dumps(payload), timeout=10)
        
        try:
            result = response.json()
            logger.debug(f"ZOA response: {result}")
            return result
        except json.JSONDecodeError:
            return {"status": response.status_code, "text": response.text}
    except requests.exceptions.Timeout:
        return {"error": "Request timeout"}
    except requests.exceptions.ConnectionError as e:
        return {"error": f"Connection failed: {str(e)}"}
    except Exception as e:
        return {"error": str(e)}


# =============================================================================
# ZOA Interface Classes
# =============================================================================

class ZoaBaseInterface:
    """Base class for ZOA API interactions following internal interface."""
    
    def __init__(self):
        self.action_name: Optional[str] = None

    def execute(
        self, 
        company_id: str, 
        option: str, 
        request_data: Optional[Dict[str, Any]] = None
    ) -> Tuple[Dict[str, Any], int]:
        """
        Execute a specific action ensuring required parameters exist.
        
        Args:
            company_id: Company ID (required)
            option: Operation to execute (search, create, update, send, assign, status, assign_status)
            request_data: Additional data for the request
            
        Returns:
            Tuple of (response_dict, status_code)
        """
        if request_data is None:
            request_data = {}

        # 1. Validate required fields
        if not company_id:
            return {"error": "El campo 'company_id' es obligatorio."}, 400
        
        if not option:
            return {"error": "El campo 'option' es obligatorio."}, 400

        if not self.action_name:
            return {"error": "Error interno: 'action' no definido en la clase."}, 500

        # 2. Enrich request data with required fields
        request_data['company_id'] = company_id
        request_data['option'] = option
        request_data['action'] = self.action_name

        # 3. Execute request
        try:
            result = _make_zoa_request(request_data)
            status = 200 if "error" not in result else 400
            return result, status
        except Exception as e:
            return {"error": f"Error interno ejecutando '{self.action_name}/{option}': {str(e)}"}, 500


class ContactsInterface(ZoaBaseInterface):
    """Interface for contacts operations."""
    def __init__(self):
        super().__init__()
        self.action_name = "contacts"


class UsersInterface(ZoaBaseInterface):
    """Interface for users operations."""
    def __init__(self):
        super().__init__()
        self.action_name = "users"


class CardsInterface(ZoaBaseInterface):
    """Interface for cards operations."""
    def __init__(self):
        super().__init__()
        self.action_name = "cards"


class CardActionsInterface(ZoaBaseInterface):
    """Interface for card+activity operations."""
    def __init__(self):
        super().__init__()
        self.action_name = "cardact"


class ActivitiesInterface(ZoaBaseInterface):
    """Interface for activities operations."""
    def __init__(self):
        super().__init__()
        self.action_name = "activities"


class DepartmentsInterface(ZoaBaseInterface):
    """Interface for departments operations."""
    def __init__(self):
        super().__init__()
        self.action_name = "departments"


class TagsInterface(ZoaBaseInterface):
    """Interface for tags operations."""
    def __init__(self):
        super().__init__()
        self.action_name = "tags"


class ReadAllInterface(ZoaBaseInterface):
    """Interface for readall operations."""
    def __init__(self):
        super().__init__()
        self.action_name = "readall"


class EmailInterface(ZoaBaseInterface):
    """Interface for email operations."""
    def __init__(self):
        super().__init__()
        self.action_name = "email_module"


class ConversationsInterface(ZoaBaseInterface):
    """Interface for conversations operations."""
    def __init__(self):
        super().__init__()
        self.action_name = "conversations"


class NotesInterface(ZoaBaseInterface):
    """Interface for notes operations."""
    def __init__(self):
        super().__init__()
        self.action_name = "notes"


class SchedulerInterface(ZoaBaseInterface):
    """Interface for scheduler operations."""
    def __init__(self):
        super().__init__()
        self.action_name = "scheduler"
