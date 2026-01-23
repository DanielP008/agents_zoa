# Agent Contracts

## Message Flow
User -> Handler -> Orchestrator -> Router -> Agent -> Orchestrator -> Handler -> User

## Session Flag (Postgres)
La transición de agentes se persiste en la tabla `sessions` usando los campos `target_agent` y `domain`.
El agente **no escribe directamente en Postgres**; en cambio retorna una acción `route` con `next_agent` y `domain`,
y el `Orchestrator` actualiza la sesión.

Ejemplo:
```json
{
  "action": "route",
  "next_agent": "classifier_agent",
  "domain": "siniestros",
  "message": "Te paso con el área de siniestros.",
  "memory": {}
}
```

## 1. Response Contract (All Agents)
Los agentes devuelven un dict con:
```json
{
  "action": "ask | route | finish",
  "message": "string",
  "next_agent": "string (solo si action=route)",
  "domain": "string | null (solo si action=route)",
  "memory": "object (opcional)"
}
```
El `Orchestrator` procesa la acción y actualiza la sesión en Postgres.

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
