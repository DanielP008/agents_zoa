# ZOA Client

`tools/zoa_client.py` provides the main integration with the ZOA API (CRM/Task Management).

## Capabilities

### Contact Management
- `search_contact_by_phone(phone, company_id)`: Finds a contact and returns their details (including NIF).
- `extract_nif_from_contact_search(response)`: Helper to safely extract NIF from search results.

### Communication
- `send_whatsapp_response(text, company_id, wa_id)`: Sends a WhatsApp message to the user via ZOA.

### Claims
- `create_claim(data)`: Registers a new claim in the system.

### Tasks & Activities
- `create_task_with_activity(...)`: Creates a task and an associated activity (e.g., call, meeting) in the CRM.
- `create_task_activity(...)`: Low-level function to create cards/activities with support for all fields.
- `create_task_activity_tool`: LangChain tool wrapper for `create_task_activity`. Used by agents to create tasks for manual intervention (e.g., when NIF is missing or complex requests).

## Configuration
- `ZOA_ENDPOINT_URL`: URL of the ZOA Cloud Function.
- `ZOA_API_KEY`: API Key for authentication.
