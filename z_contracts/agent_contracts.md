# Agent Contracts

## Message Flow
User -> Handler -> Orchestrator -> Router -> Agent -> Orchestrator -> Handler -> User

## Session Flag (Postgres)
Agent transitions are persisted in the `sessions` table using the `target_agent` and `domain` fields.
The agent **does not write directly to Postgres**; instead, it returns a `route` action with `next_agent` and `domain`,
and the `Orchestrator` updates the session.

Example:
```json
{
  "action": "route",
  "next_agent": "classifier_agent",
  "domain": "siniestros",
  "message": "I'm transferring you to the claims area.",
  "memory": {}
}
```

## 1. Response Contract (All Agents)
Agents return a dict with:
```json
{
  "action": "ask | route | finish",
  "message": "string | null",
  "next_agent": "string (only if action=route)",
  "domain": "string | null (only if action=route)",
  "memory": "object (optional)"
}
```
The `Orchestrator` processes the action and updates the session in Postgres.

## 1.0.1 Passthrough Routing (Route without message)
When an agent returns `action: "route"` with `message: null`, the Orchestrator
**does not send a message to the user** and instead immediately calls the next agent
in the same turn. This allows for silent routing chains.

### Example: Receptionist -> Classifier (passthrough)
```json
{
  "action": "route",
  "next_agent": "classifier_siniestros_agent",
  "domain": "siniestros",
  "message": null
}
```
The user does not receive "I'm transferring you to claims", instead the classifier responds directly.

### Example: Route with message (traditional behavior)
```json
{
  "action": "route",
  "next_agent": "apertura_siniestro_agent",
  "domain": "siniestros",
  "message": "I'm transferring you to the specialist agent."
}
```
The user receives the message and in the next turn talks to the new agent.

### Chain Limit
The Orchestrator limits to **5 chained passthroughs** to prevent infinite loops.

## 1.1 Agent Memory Schema (Mandatory)
Memory lives in `sessions.agent_memory` and **must respect this structure**.  
The `Orchestrator` is responsible for consolidating and persisting memory; agents should only
write within their namespaces.

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
      "data": "object"
    }
  },
  "metadata": {
    "version": 1,
    "updated_at": "ISO-8601"
  }
}
```

### Mandatory Rules
- Agents **DO NOT** write to `global` or `conversation_history`.
- Agents only write under `agents.<agent_name>` and/or `domains.<domain>`.
- `Orchestrator` appends history and updates `global.last_*`.
- Agents read conversation history from `conversation_history` using `get_global_history()`.

### Example of memory returned by an agent
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

## 3. Agent Implementation Patterns

**Decision Agents** (routing/classification):
- Use `llm.with_structured_output(PydanticModel)` for structured decisions
- Example: `receptionist_agent`, `classifier_siniestros_agent`

**Conversational Agents** (specialists with tools):
- Use `core.agent_factory.create_langchain_agent()` with tools
- Example: `telefonos_asistencia_agent`, `apertura_siniestro_agent`

**Function Signature**: `{agent_name}_agent(payload: dict) -> dict`
