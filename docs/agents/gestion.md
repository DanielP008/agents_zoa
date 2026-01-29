# Gestión Agents

The Gestión (Management) domain handles administrative tasks, policy modifications, and refunds.

## Classifier
`agents/domains/gestion/classifier_agent.py`
- **Role**: Routes administrative requests to the appropriate handler.
- **Routes to**:
  - `devolucion_agent`: Refunds and billing issues.
  - `consultar_poliza_agent`: Information queries about policies.
  - `modificar_poliza_agent`: Changes to policy data.

## Specialists

### `devolucion_agent.py`
- **Role**: Processes refund requests and billing inquiries.
- **Key Logic**: 
  - Checks if NIF is identified.
  - **Identified**: Proceeds with structured refund request (IBAN, motive).
  - **Unidentified**: Collects basic info (DNI, Phone) and creates a task for manual verification/callback.
- **Tools**: 
  - `create_refund_request_tool` (standard flow)
  - `create_task_activity_tool` (unidentified/manual flow)

### `consultar_poliza_agent.py`
- **Role**: Provides information about active policies.
- **Key Logic**: 
  - Handles generic insurance questions via expert knowledge base.
  - For specific policy queries:
    - **Identified**: Retrieves policy details or documents from ERP.
    - **Unidentified**: Creates a task for a human agent to verify identity and assist.
- **Tools**: 
  - `get_client_policys_tool`
  - `get_policy_document_tool`
  - `ocr_policy_document_tool`
  - `ask_expert_knowledge`
  - `create_task_activity_tool` (unidentified flow)

### `modificar_poliza_agent.py`
- **Role**: Updates policy information.
- **Key Logic**: 
  - Validates if the requested change is allowed (e.g., IBAN, address, contact info).
  - **Identified & Allowed**: Updates directly in the system.
  - **Unidentified OR Complex/Not Allowed**: Creates a task for manual processing by a human manager.
- **Tools**: 
  - `update_policy_tool` (automated updates)
  - `create_task_activity_tool` (manual/complex updates)
