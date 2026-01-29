# Architecture

## Overview
The system processes WhatsApp messages through a deterministic router and a
hierarchy of agents with persistent memory stored in PostgreSQL.

## High-Level Flow
1. `api/handler.py` receives the HTTP request.
2. `core/orchestrator.py` loads session state and executes the agent.
3. `core/routing/main_router.py` dispatches based on `routes.json`.
4. Agents respond with `ask`, `route`, or `finish`.
5. The orchestrator persists state and sends a response via ZOA API.

## Agent Hierarchy (Siniestros Example)
```
receptionist_agent
└── classifier_siniestros_agent
    ├── telefonos_asistencia_agent
    ├── apertura_siniestro_agent
    └── consulta_estado_agent
```

## Message Flow (Simplified)
```
User -> Handler -> Orchestrator -> Router -> Agent
                                 -> Orchestrator -> ZOA API
```

## Agent Actions
- `ask`: send a message and wait for the next user input.
- `route`: move to another agent (optionally passthrough when message is null).
- `finish`: respond and reset session to the receptionist.

## Memory Model
Session memory is JSON with:
- `global` (language, last_agent, last_action)
- `conversation_history` (turn-by-turn records)
- `domains` (domain-specific data)
- `agents` (agent-specific data)

## Memory Schema (Example)
```json
{
  "global": {
    "language": "es",
    "last_agent": "classifier_siniestros_agent",
    "last_action": "ask"
  },
  "conversation_history": [
    {
      "role": "user",
      "text": "I had an accident",
      "agent": "receptionist_agent"
    }
  ],
  "domains": {},
  "agents": {}
}
```
