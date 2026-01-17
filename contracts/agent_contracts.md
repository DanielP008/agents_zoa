# Agent Contracts

## Message Flow
User -> Handler -> Router -> Classifier (if no active session) -> Specific Agent -> Router -> Handler -> User

## 1. Classifier
**Responsibility**: Determine user intent and collect initial information.  
**Input**:
```json
{
  "user_id": "string (phone number)",
  "user_text": "string",
  "session_id": "string (optional)",
  "last_route": "string (from state)",
  "last_question": "string (from state)"
}
```
**Output (JSON)**:
```json
{
  "route": "telefonos_asistencia | apertura_siniestro | consulta_estado | classifier",
  "confidence": 0.0-1.0,
  "needs_more_info": boolean,
  "question": "string (optional, if needs_more_info=true)"
}
```
**Tools**:
- `whatsapp_send`: to ask clarification questions directly.

## 2. Router
**Responsibility**: Deterministic dispatch based on classifier output or session state.  
**Logic**:
- If `needs_more_info`: Return question payload.
- If `route` is valid: Call `call_{agent_name}(payload)`.
- Fallback: Return error/help message.

## 3. Specific Agents
**Common Contract**:
- **Input**: Inbound message payload (`text`, `from`, `metadata`).
- **Output**: JSON dict with agent-specific keys (e.g. `claim_id`, `policy_data`, `message`).

### Agent: Telefonos de Asistencia
- **Goal**: Provide assistance numbers based on policy type.
- **Output**:
  ```json
  {
    "agent": "telefonos_asistencia",
    "message": "string (response text)",
    "debug": "object"
  }
  ```

### Agent: Apertura Siniestro
- **Goal**: Create a claim in ZOA ERP.
- **Tools**: `create_claim(payload)`
- **Output**:
  ```json
  {
    "agent": "apertura_siniestro",
    "message": "string (confirmation + next steps)",
    "claim": { "id": "string", "status": "string" }
  }
  ```

### Agent: Consulta Estado
- **Goal**: Check policy status or process documents via OCR.
- **Tools**: `fetch_policy(id)`, `extract_text(doc)`
- **Output**:
  ```json
  {
    "agent": "consulta_estado",
    "message": "string",
    "policy": "object",
    "ocr": "object (optional)"
  }
  ```

## 4. Aggregator (Deprecated)
*Merged into Router/Handler logic for single-turn simplicity.*
