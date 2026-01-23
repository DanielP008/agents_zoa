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
  "message": "string | null",
  "next_agent": "string (solo si action=route)",
  "domain": "string | null (solo si action=route)",
  "memory": "object (opcional)"
}
```
El `Orchestrator` procesa la acción y actualiza la sesión en Postgres.

## 1.0.1 Passthrough Routing (Route sin mensaje)
Cuando un agente devuelve `action: "route"` con `message: null`, el Orchestrator
**no envía mensaje al usuario** y en cambio llama inmediatamente al siguiente agente
en el mismo turno. Esto permite cadenas de routing silenciosas.

### Ejemplo: Receptionist -> Classifier (passthrough)
```json
{
  "action": "route",
  "next_agent": "classifier_siniestros_agent",
  "domain": "siniestros",
  "message": null
}
```
El usuario no recibe "te paso con siniestros", sino que el classifier responde directamente.

### Ejemplo: Route con mensaje (comportamiento tradicional)
```json
{
  "action": "route",
  "next_agent": "apertura_siniestro_agent",
  "domain": "siniestros",
  "message": "Te derivo con el agente especializado."
}
```
El usuario recibe el mensaje y en el siguiente turno habla con el nuevo agente.

### Límite de cadena
El Orchestrator limita a **5 passthroughs encadenados** para prevenir loops infinitos.

## 1.1 Agent Memory Schema (Obligatorio)
La memoria vive en `sessions.agent_memory` y **debe respetar esta estructura**.  
El `Orchestrator` es quien consolida y persiste la memoria, los agentes solo deben
escribir dentro de sus namespaces.

```json
{
  "global": {
    "language": "string",
    "summary": "string",
    "last_agent": "string | null",
    "last_action": "string | null",
    "last_domain": "string | null",
    "preferences": "object"
  },
  "conversation_history": [
    {
      "role": "user | assistant",
      "text": "string",
      "timestamp": "ISO-8601",
      "agent": "string | null",
      "domain": "string | null",
      "action": "string | null"
    }
  ],
  "domains": {
    "<domain>": {
      "state": "string",
      "fields": "object"
    }
  },
  "agents": {
    "<agent_name>": {
      "history": [
        {
          "role": "user | assistant",
          "text": "string",
          "timestamp": "ISO-8601"
        }
      ],
      "data": "object"
    }
  },
  "metadata": {
    "version": 1,
    "updated_at": "ISO-8601"
  }
}
```

### Reglas obligatorias
- Los agentes **NO** escriben en `global` ni en `conversation_history`.
- Los agentes solo escriben bajo `agents.<agent_name>` y/o `domains.<domain>`.
- `Orchestrator` agrega historial y actualiza `global.last_*`.

### Ejemplo de memoria devuelta por un agente
```json
{
  "memory": {
    "agents": {
      "classifier_siniestros_agent": {
        "data": {
          "last_route": "apertura_siniestro_agent",
          "confidence": 0.82
        }
      }
    }
  }
}
```

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
