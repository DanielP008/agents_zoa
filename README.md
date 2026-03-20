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

### Architectural Principles Applied

**SOLID Principles:**
- **Single Responsibility:** Each module has one clear purpose (agent_factory for LangChain, llm_utils for LLM handling)
- **Open/Closed:** Core abstractions can be extended without modification
- **Dependency Inversion:** Agents depend on abstractions, not concretions

**DRY (Don't Repeat Yourself):**
- Centralized LangChain agent creation eliminates 80+ lines of duplicate code
- Path resolution utilities prevent scattered filesystem logic
- LLM error handling provides consistent behavior across all agents

**Type Safety & Error Handling:**
- Structured memory schema prevents runtime errors from missing keys
- Safe LLM invocation with automatic logging and fallbacks
- Centralized error handling improves debugging and user experience

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
- **Architecture**: Uses `llm.with_structured_output()` for structured decisions
- **Output**: Always `route` with passthrough or `ask` to clarify

### Classifier Siniestros (`classifier_agent.py`)

- **Function**: Determines the specific intent within claims
- **Options**: Assistance, claim opening, status inquiry
- **Architecture**: Uses `llm.with_structured_output()` for structured decisions
- **Output**: `ask` to clarify or `route` to the specialist

### Specialists

| Agent                         | Function                                   | Architecture |
|-------------------------------|--------------------------------------------|-------------|
| `telefonos_asistencia_agent`  | Provides tow truck and assistance numbers  | `agent_factory` with tools |
| `apertura_siniestro_agent`    | Collects data and registers new claim      | `agent_factory` with tools |
| `consulta_estado_agent`       | Checks status of existing claims           | `agent_factory` with tools |

### Classifier Gestion (`classifier_gestion_agent.py`)

- **Function**: Handles policy management inquiries.
- **Specialists**:
  - `consultar_poliza_agent`: Queries policy details.
  - `modificar_poliza_agent`: Handles policy modifications (currently disabled).
  - `devolucion_agent`: Processes returns (currently disabled).

### Classifier Ventas (`classifier_ventas_agent.py`)

- **Function**: Manages sales and renewals.
- **Specialists**:
  - `renovacion_agent`: Handles policy renewals.
  - `nueva_poliza_agent`: Processes new policy applications (currently disabled).
  - `venta_cruzada_agent`: Suggests cross-selling opportunities (currently disabled).
  - `wildix_card_agent`: Handles Wildix card interactions.

### Common Agents

- `generic_knowledge_agent`: Handles general queries not specific to a domain.
- `aichat_receptionist_agent`: Specialized receptionist for AI Chat interactions.


### Implementation Patterns

**All agents follow these established patterns:**

- **LangChain Setup**: Use `agent_factory.create_langchain_agent()` and `run_langchain_agent()` instead of manual boilerplate (eliminates 15+ lines per agent)

- **Memory Access**: Use `get_global_history()` for conversation history, `get_agent_memory()` for agent-specific data

- **Structured Output**: Use `llm.with_structured_output()` for decision agents (routing/classification)

- **Path Resolution**: Use `hooks.get_z_contracts_path()` and `get_config_path()` for consistent file access across the project

- **Prompts Management**: Each agent has a corresponding `*_prompts.py` file in its directory for prompt isolation.

- **Infrastructure Core**: Use `infra/agent_runner.py` for executing agent logic and `infra/llm.py` for multi-provider LLM access.

- **Response Building**: Return standardized dicts with consistent `action`, `message`, `memory` structure

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
      "data": {
        "last_route": "apertura_siniestro_agent",
        "confidence": 0.82
      }
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
| `ZOA_ENDPOINT_URL` | ZOA API URL for WhatsApp             | `https://prod-flow-zoa-...` |
| `ZOA_API_KEY`      | ZOA API Key                          | `sk_test_...`               |

**Optional variables:**

| Variable                   | Description                    | Default                    |
|----------------------------|--------------------------------|----------------------------|
| `GEMINI_OCR_MODEL`         | Model for OCR                  | `gemini-2.0-flash`         |
| `GEMINI_MODEL_FAST`        | Model for fast tasks           | `gemini-2.0-flash`         |
| `LANGSMITH_TRACING`        | Enable tracing                 | `true`                     |
| `LANGSMITH_ENDPOINT`       | LangSmith Endpoint             | `https://eu.api.smith...`  |
| `LANGSMITH_PROJECT`        | LangSmith Project Name         | `agents-repo-test`         |
| `ERP_ENDPOINT_URL`         | ERP API URL                    | `https://prod-flow-erp...` |
| `DB_HOST`                  | Database Host                  | `34.175.165.97`            |
| `WILDIX_API_KEY`           | Wildix API Key                 | `wsk-v1-...`               |
| `MERLIN_BASE_URL`          | Merlin API URL                 | `https://drseguros...`     |

### Extended Configuration

New providers and configurations are supported:

| Variable | Description | Default |
|----------|-------------|---------|
| `LLM_PROVIDER` | Main LLM provider (`gemini`, `mistral`) | `mistral` |
| `MISTRAL_API_KEY` | API Key for Mistral AI | - |
| `FAST_LLM_PROVIDER` | Provider for fast tasks (`openai`, `gemini`) | `openai` |
| `OPENAI_API_KEY` | API Key for OpenAI | - |
| `OPENAI_MODEL_FAST` | Model for fast tasks | `gpt-5.2` |


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

### Routing (`z_contracts/routes.json`)

Defines the agent hierarchy and their labels. Access via `core.hooks.get_routes_path()`:

```json
{
  "default": "receptionist_agent",
  "domains": {
    "siniestros": {
      "enabled": true,
      "receptionist_label": "siniestros",
      "classifier": "classifier_siniestros_agent",
      "specialists": {
        "telefonos_asistencia_agent": {"enabled": true},
        "apertura_siniestro_agent": {"enabled": true},
        "consulta_estado_agent": {"enabled": false}
      }
    },
    "gestion": {
      "enabled": true,
      "receptionist_label": "gestión de una poliza",
      "classifier": "classifier_gestion_agent",
      "specialists": {
        "devolucion_agent": {"enabled": false},
        "consultar_poliza_agent": {"enabled": true},
        "modificar_poliza_agent": {"enabled": false}
      }
    },
    "ventas": {
      "enabled": true,
      "receptionist_label": "contratación o renovación de una póliza",
      "classifier": "classifier_ventas_agent",
      "specialists": {
        "nueva_poliza_agent": {"enabled": false},
        "venta_cruzada_agent": {"enabled": false},
        "renovacion_agent": {"enabled": true}
      }
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
    "mensaje": "BORRAR TODO",
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
│   ├── agent_factory.py                    # Centralized LangChain agent creation (DRY principle)
│   ├── db.py                               # PostgreSQL session manager
│   ├── hooks.py                            # Path resolution utilities (DRY principle)
│   ├── llm_utils.py                        # LLM error handling & response parsing (robustness)
│   ├── memory_schema.py                    # Structured memory helpers (type safety)
│   └── orchestrator.py                     # Flow orchestration
│
├── routers/
│   └── main_router.py                      # Agent dispatch
│
├── tools/
│   ├── communication/                      # Chat/comms tools
│   ├── document_ai/                        # OCR and document parsing
│   ├── erp/                                # ERP-related tools
│   ├── sales/                              # Sales and cross-sell tools
│   └── zoa/                                # ZOA CRM tools
│
├── test/
│   ├── cli_chat.py                         # Interactive CLI
│   └── simulation_script.py                # Simulation script
│
├── .env.example                            # Example environment variables
├── Dockerfile
├── docker-compose.yml
└── requirements.txt

## Updated Module Structure (Current)

```
zoa_agents/
├── agents/
│   ├── domains/
│   │   ├── common/             # Generic knowledge agents
│   │   ├── gestion/            # Policy management agents
│   │   ├── siniestros/         # Claims agents
│   │   └── ventas/             # Sales and renewal agents
│   └── aichat_receptionist_agent.py
│
├── api/                        # API Handlers
│   ├── aichat_handler.py
│   ├── wildix_handler.py
│   └── wildix_card_handler.py
│
├── infra/                      # Infrastructure & Config
│   ├── llm.py                  # Multi-provider LLM factory
│   ├── db.py                   # Database connection
│   └── tracing.py              # Observability
│
├── services/                   # External Services
│   ├── erp_client.py
│   ├── ocr_service.py
│   └── zoa_client.py
│
└── tools/                      # Agent Tools
    ├── communication/
    ├── document_ai/
    ├── erp/
    ├── sales/
    └── zoa/
```

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
| LLM Providers  | Mistral AI, OpenAI              |

## Services & Integrations

The system now includes dedicated services for external integrations:

- **OCR Service** (`services/ocr_service.py`): Handles document parsing and text extraction.
- **ERP Client** (`services/erp_client.py`): Interface for Enterprise Resource Planning system interactions.
- **ZOA Client** (`services/zoa_client.py`): Client for ZOA API interactions.
- **Local CP DB** (`services/local_cp_db.py`): Local database service for postal codes.

## Infrastructure (`infra/`)

Core infrastructure components have been moved to the `infra/` directory for better separation of concerns:

- `llm.py`: Enhanced LLM factory supporting multiple providers (Gemini, Mistral, OpenAI).
- `db.py`: Database connection management.
- `config.py`: Centralized configuration.
- `tracing.py`: OpenTelemetry and LangSmith tracing setup.


## Architecture Highlights

- **Modular Design**: Separation of concerns with dedicated modules for each responsibility
- **DRY Principle**: Centralized utilities eliminate ~80 lines of duplicate code
- **Error Resilience**: Comprehensive error handling with automatic logging and fallbacks
- **Type Safety**: Structured memory access prevents runtime errors
- **Testability**: Abstracted dependencies enable easy mocking and testing
- **Maintainability**: Changes to core functionality affect single modules, not multiple agents

---

## Roadmap

- [x] **Architecture Refactoring**: Centralized LangChain agents, error handling, and memory management
- [x] Implementar `classifier_gestion_agent`
- [x] Implementar `classifier_ventas_agent`
- [x] Migrar credenciales DB a variables de entorno
- [ ] Agregar summary automático de conversación
- [ ] Agregar tests unitarios para nuevos módulos core
- [ ] Add monitoring/metrics for LLM calls and agent performance

## Additional Documentation

- [Agent Contracts](contracts/agent_contracts.md) - Detailed input/output specification
