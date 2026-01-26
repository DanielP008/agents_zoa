# ZOA Agents

AI multi-agent system to automate customer service for insurance brokers.  
Processes WhatsApp messages through a hierarchy of specialized agents with persistent memory.

---

## Table of Contents

- [Architecture](#architecture)
- [Message Flow](#message-flow)
- [Agents](#agents)
- [Memory](#memory)
- [Configuration](#configuration)
- [Execution](#execution)
- [Testing](#testing)
- [Project Structure](#project-structure)

---

## Architecture

### General View

```
                                    ┌──────────────────┐
                                    │    WhatsApp      │
                                    │  (Buffer System) │
                                    └────────┬─────────┘
                                             │
                                             ▼
┌────────────────────────────────────────────────────────────────────────────────┐
│                              ZOA AGENTS SERVICE                                │
│  ┌──────────────────────────────────────────────────────────────────────────┐  │
│  │                           app/handler.py                                 │  │
│  │                        (Cloud Function Entry)                            │  │
│  └────────────────────────────────┬─────────────────────────────────────────┘  │
│                                   │                                            │
│                                   ▼                                            │
│  ┌──────────────────────────────────────────────────────────────────────────┐  │
│  │                        core/orchestrator.py                              │  │
│  │  ┌────────────────────────────────────────────────────────────────────┐  │  │
│  │  │  1. Load session from PostgreSQL                                   │  │  │
│  │  │  2. Prepare memory (ensure_memory_shape)                           │  │  │
│  │  │  3. Execute current agent                                          │  │  │
│  │  │  4. Handle passthrough if message=null                             │  │  │
│  │  │  5. Persist changes in DB                                          │  │  │
│  │  │  6. Send response via ZOA API                                      │  │  │
│  │  └────────────────────────────────────────────────────────────────────┘  │  │
│  └────────────────────────────────┬─────────────────────────────────────────┘  │
│                                   │                                            │
│                                   ▼                                            │
│  ┌──────────────────────────────────────────────────────────────────────────┐  │
│  │                        routers/main_router.py                            │  │
│  │                     (Deterministic Dispatch)                             │  │
│  └────────────────────────────────┬─────────────────────────────────────────┘  │
│                                   │                                            │
│           ┌───────────────────────┼───────────────────────┐                    │
│           ▼                       ▼                       ▼                    │
│  ┌─────────────────┐   ┌─────────────────────┐   ┌─────────────────────┐       │
│  │  RECEPTIONIST   │   │  DOMAIN CLASSIFIER  │   │  SPECIALIST AGENT   │       │
│  │                 │   │                     │   │                     │       │
│  │ Classifies      │   │ Classifies intent   │   │ Executes specific   │       │
│  │ domain          │   │ within the domain   │   │ task                │       │
│  └─────────────────┘   └─────────────────────┘   └─────────────────────┘       │
│                                                                                │
└────────────────────────────────────────────────────────────────────────────────┘
                                             │
                    ┌────────────────────────┼────────────────────────┐
                    ▼                        ▼                        ▼
           ┌─────────────────┐     ┌─────────────────┐      ┌─────────────────┐
           │   PostgreSQL    │     │    ZOA API      │      │   Gemini LLM    │
           │   (Sessions)    │     │   (WhatsApp)    │      │                 │
           └─────────────────┘     └─────────────────┘      └─────────────────┘
```

### Agent Hierarchy

```
receptionist_agent
│
├── classifier_siniestros_agent
│   ├── telefonos_asistencia_agent    → Tow truck/assistance numbers
│   ├── apertura_siniestro_agent      → Report new claim
│   └── consulta_estado_agent         → Check existing claim status
│
├── classifier_gestion_agent          → (pending)
│   └── ...
│
└── classifier_ventas_agent           → (pending)
    └── ...
```

---

## Message Flow

### Sequence Diagram

```
User             Handler       Orchestrator      Router         Receptionist    Classifier
   │                │               │               │                │              │
   │  "I had an     │               │               │                │              │
   │   accident"    │               │               │                │              │
   │───────────────>│               │               │                │              │
   │                │  process()    │               │                │              │
   │                │──────────────>│               │                │              │
   │                │               │  get_session()│                │              │
   │                │               │◄──────────────│                │              │
   │                │               │               │                │              │
   │                │               │  route()      │                │              │
   │                │               │──────────────>│                │              │
   │                │               │               │  handle()      │              │
   │                │               │               │───────────────>│              │
   │                │               │               │                │              │
   │                │               │               │  {action:route,│              │
   │                │               │               │   message:null}│              │
   │                │               │               │<───────────────│              │
   │                │               │               │                │              │
   │                │               │  PASSTHROUGH  │                │              │
   │                │               │  (message=null)                │              │
   │                │               │──────────────>│                │              │
   │                │               │               │  handle()      │              │
   │                │               │               │──────────────────────────────>│
   │                │               │               │                │              │
   │                │               │               │  {action:ask,  │              │
   │                │               │               │   message:"Do you want to   │
   │                │               │               │   report or check?"}        │
   │                │               │<──────────────│<──────────────────────────────│
   │                │               │               │                │              │
   │                │               │  save_session()                │              │
   │                │               │  send_whatsapp()               │              │
   │                │               │               │                │              │
   │  "Do you want  │<──────────────│               │                │              │
   │   to report    │               │               │                │              │
   │   or check?"   │               │               │                │              │
   │                │               │               │                │              │
```

### Agent Actions

| Action   | message    | Behavior                                                 |
|----------|------------|----------------------------------------------------------|
| `ask`    | required   | Sends message, waits for response, stays on the agent    |
| `route`  | `null`     | **Passthrough**: calls the next agent immediately        |
| `route`  | string     | Sends message, changes agent for the next turn           |
| `finish` | required   | Sends message, resets session to receptionist            |

### Passthrough Routing

When `message: null`, the orchestrator **does not send a response** and executes the next agent in the same turn:

```python
# Passthrough - the classifier responds immediately
return {
    "action": "route",
    "next_agent": "classifier_siniestros_agent",
    "domain": "siniestros",
    "message": None
}
```

---

## Agents

### Receptionist (`receptionist_agent.py`)

- **Function**: Classifies the message domain (claims, management, sales)
- **First interaction**: Shows welcome message if it cannot classify
- **Subsequent interactions**: Asks for clarification if it cannot classify
- **Output**: Always `route` with passthrough or `ask` to clarify

### Classifier Siniestros (`classifier_agent.py`)

- **Function**: Determines the specific intent within claims
- **Options**: Assistance, claim opening, status inquiry
- **Output**: `ask` to clarify or `route` to the specialist

### Specialists

| Agent                         | Function                                   |
|-------------------------------|--------------------------------------------|
| `telefonos_asistencia_agent`  | Provides tow truck and assistance numbers  |
| `apertura_siniestro_agent`    | Collects data and registers new claim      |
| `consulta_estado_agent`       | Checks status of existing claims           |

---

## Memory

### Schema (`agent_memory`)

```json
{
  "global": {
    "language": "es",
    "summary": "",
    "last_agent": "classifier_siniestros_agent",
    "last_action": "ask",
    "last_domain": "siniestros",
    "preferences": {}
  },
  "conversation_history": [
    {
      "role": "user",
      "text": "I had an accident",
      "timestamp": "2026-01-23T12:45:00Z",
      "agent": "receptionist_agent",
      "domain": null,
      "action": "input"
    },
    {
      "role": "assistant",
      "text": "Do you want to report or check?",
      "timestamp": "2026-01-23T12:45:02Z",
      "agent": "classifier_siniestros_agent",
      "domain": "siniestros",
      "action": "ask"
    }
  ],
  "domains": {},
  "agents": {
    "classifier_siniestros_agent": {
      "last_route": "apertura_siniestro_agent",
      "confidence": 0.82
    }
  },
  "metadata": {
    "version": 1,
    "updated_at": "2026-01-23T12:45:02Z"
  }
}
```

### Writing Responsibilities

| Namespace              | Who writes      | Example                                      |
|------------------------|-----------------|----------------------------------------------|
| `global.*`             | Orchestrator    | `last_agent`, `last_action`                  |
| `conversation_history` | Orchestrator    | Each user/assistant turn                     |
| `agents.<name>.*`      | Each agent      | `classifier_siniestros_agent.last_route`     |
| `domains.<domain>.*`   | Agents          | `siniestros.state`, `siniestros.fields`      |
| `metadata.*`           | Orchestrator    | `version`, `updated_at`                      |

---

## Configuration

### Environment Variables

Create `.env` file based on `.env.example`:

```bash
cp .env.example .env
```

**Required variables:**

| Variable           | Description                          | Example                     |
|--------------------|--------------------------------------|-----------------------------|
| `GEMINI_API_KEY`   | Google AI API key                    | `AIza...`                   |
| `GEMINI_MODEL`     | Main model                           | `gemini-2.5-flash`          |
| `ZOA_ENDPOINT_URL` | ZOA API URL for WhatsApp             | `https://flow-zoa-...`      |

**Optional variables:**

| Variable                   | Description                    | Default                    |
|----------------------------|--------------------------------|----------------------------|
| `GEMINI_OCR_MODEL`         | Model for OCR                  | `gemini-1.5-flash`         |
| `LANGSMITH_API_KEY`        | Key for tracing                | -                          |
| `LANGCHAIN_TRACING_V2`     | Enable tracing                 | `false`                    |

### Database

The PostgreSQL connection is configured in `core/db.py`. Required table:

```sql
CREATE TABLE sessions (
    session_id VARCHAR(255) PRIMARY KEY,
    domain VARCHAR(100),
    target_agent VARCHAR(100),
    agent_memory JSONB,
    updated_at TIMESTAMP DEFAULT NOW()
);
```

### Routing (`contracts/routes.json`)

Defines the agent hierarchy and their labels:

```json
{
  "default": "receptionist_agent",
  "domains": {
    "siniestros": {
      "receptionist_label": "siniestros",
      "classifier": "classifier_siniestros_agent",
      "specialists": [
        "telefonos_asistencia_agent",
        "apertura_siniestro_agent",
        "consulta_estado_agent"
      ]
    }
  }
}
```

---

## Execution

### Docker (Recommended)

```bash
# Build and run
docker compose up --build

# The service will be at http://localhost:8080
```

### Local (venv)

```bash
# Create virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Run (requires external DB configuration)
python -m flask run --port 8080
```

---

## Testing

### CLI Chat

Interactive tool to test conversations:

```bash
python3 test/cli_chat.py
```

### cURL

```bash
# Normal message
curl -X POST http://localhost:8080 \
  -H "Content-Type: application/json" \
  -d '{
    "wa_id": "5491155551234",
    "mensaje": "Hi, I had an accident",
    "phone_number_id": "company_123"
  }'

# Session reset
curl -X POST http://localhost:8080 \
  -H "Content-Type: application/json" \
  -d '{
    "wa_id": "5491155551234",
    "mensaje": "BORRAR_POSTGRESS_INFO",
    "phone_number_id": "company_123"
  }'
```

---

## Project Structure

```
zoa_agents/
├── agents/
│   ├── domains/
│   │   └── siniestros/
│   │       ├── classifier_agent.py         # Classifies intent in claims
│   │       ├── apertura_siniestro_agent.py # Registers new claims
│   │       ├── consulta_estado_agent.py    # Checks existing claim status
│   │       └── telefonos_asistencia_agent.py # Provides assistance numbers
│   ├── llm.py                              # Gemini configuration
│   └── receptionist_agent.py               # Initial domain classifier
│
├── app/
│   └── handler.py                          # Entry point (Cloud Function)
│
├── contracts/
│   ├── agent_contracts.md                  # Contract documentation
│   ├── routes.json                         # Routing configuration
│   └── message_schema.json                 # Message schema
│
├── core/
│   ├── agent_allowlist.py                  # Validation of allowed routes
│   ├── db.py                               # PostgreSQL session manager
│   ├── memory_schema.py                    # Helpers for agent_memory
│   └── orchestrator.py                     # Flow orchestration
│
├── routers/
│   └── main_router.py                      # Agent dispatch
│
├── tools/
│   ├── ocr_client.py                       # OCR client
│   └── zoa_client.py                       # ZOA API client (WhatsApp)
│
├── test/
│   ├── cli_chat.py                         # Interactive CLI
│   └── simulation_script.py                # Simulation script
│
├── .env.example                            # Example environment variables
├── Dockerfile
├── docker-compose.yml
└── requirements.txt
```

---

## Tech Stack

| Component      | Technology                      |
|----------------|---------------------------------|
| LLM            | Google Gemini (Flash/Pro)       |
| Framework      | LangChain                       |
| Hosting        | Google Cloud Run                |
| Database       | PostgreSQL (Cloud SQL)          |
| Runtime        | Python 3.11                     |
| Container      | Docker                          |

---

## Additional Documentation

- [Agent Contracts](contracts/agent_contracts.md) - Detailed input/output specification
