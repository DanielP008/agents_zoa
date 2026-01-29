# Siniestros Agents

The Siniestros (Claims) domain handles all interactions related to accidents, assistance, and claim management.

## Classifier
`agents/domains/siniestros/classifier_agent.py`
- **Role**: Analyzes user intent to route to the correct specialist.
- **Routes to**:
  - `telefonos_asistencia_agent`: Emergency assistance, tow truck, etc.
  - `apertura_siniestro_agent`: Reporting new claims (accidents, theft, etc.).
  - `consulta_estado_agent`: Status updates on existing claims.

## Specialists

### `telefonos_asistencia_agent.py`
- **Role**: Provides emergency contact numbers for assistance.
- **Key Logic**: 
  - Identifies client by NIF and Ramo (Auto, Hogar, etc.).
  - Queries ERP for active policy phones.
  - If phones are not found or client is unidentified, creates a high-priority task for a human agent to call back.
- **Tools**: 
  - `get_assistance_phones(nif, ramo)`
  - `create_task_activity_tool` (fallback for manual assistance)

### `apertura_siniestro_agent.py`
- **Role**: Collects information to open a new claim.
- **Key Logic**: 
  - Conducts a structured interview to gather specific details based on policy type (Auto, Hogar, etc.).
  - Requests photos when applicable.
  - Creates a comprehensive task with all collected data for the back-office team to process.
- **Tools**: 
  - `create_claim_tool` (automated registration)
  - `create_task_activity_tool` (manual processing task)

### `consulta_estado_agent.py`
- **Role**: Provides status updates on existing claims.
- **Key Logic**: 
  - Distinguishes between generic questions (theory/process) and specific claim inquiries.
  - Generic questions are answered by the expert knowledge base.
  - Specific inquiries look up policy/claim status in the ERP.
  - Complex or sensitive specific queries create a task for a human manager.
- **Tools**: 
  - `lookup_policy`
  - `process_document` (OCR for documents/photos)
  - `ask_expert_knowledge`
  - `create_task_activity_tool` (escalation)
