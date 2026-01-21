# ZOA Agents

Automation app for insurance brokerage. AI agents answer WhatsApp messages and automate processes.

## Architecture

The system follows a hierarchical routing pattern:

1.  **Receptionist Agent** (`receptionist_agent.py`): The first point of contact. Identifies the general **Domain** (e.g., Siniestros, Ventas, Gestión) and routes the user to the Domain Classifier.
2.  **Domain Classifier** (e.g., `classifier_agent.py`): Once inside a domain, this agent chats with the user to understand their specific need (Intent) and routes them to a **Specialist Agent**.
3.  **Specialist Agents**: Perform specific tasks (e.g., `apertura_siniestro_agent.py` to open a claim, `telefonos_asistencia_agent.py` to provide assistance numbers).

## Components

-   **`app/handler.py`**: Entrypoint for Cloud Functions (`handle_whatsapp`).
-   **`core/orchestrator.py`**: Manages the message flow and state.
-   **`core/db.py`**: Handles session persistence (Cloud SQL or Mock).
-   **`routers/main_router.py`**: Central dispatcher that executes the agent code.
-   **`contracts/routes.json`**: Configuration file defining the tree of accessible agents and domains.

## Project Structure
.
```
zoa_agents/
├── agents/
│   ├── domains/
│   │   └── siniestros/          # Domain-specific logic
│   │       ├── classifier_agent.py
│   │       ├── apertura_siniestro_agent.py
│   │       └── ...
│   ├── llm.py                   # LLM configuration
│   └── receptionist_agent.py    # Main entry classifier
├── app/
│   └── handler.py               # Cloud Function entrypoint
├── contracts/
│   ├── routes.json              # Routing configuration
│   └── ...                      # Schemas and contracts
├── core/
│   ├── db.py                    # Database & Session management
│   └── orchestrator.py          # Workflow orchestration
├── routers/
│   └── main_router.py           # Agent dispatch logic
├── tools/                       # External integrations
│   ├── zoa_client.py
│   └── ...
├── Dockerfile
└── requirements.txt
```

## Tech Stack

-   **LangChain**: For agent logic and LLM interaction.
-   **Gemini Models**: Using Google's Gemini Flash/Pro models.
-   **Google Cloud Functions**: Hosting environment.
-   **Cloud SQL (PostgreSQL)**: Session storage.
-   **Python 3.11**

## Setup & Run

### Environment Variables
Copy `.env.example` to `.env` and fill in your keys:
-   `GEMINI_API_KEY`
-   `GEMINI_MODEL`
-   Database credentials (if not using mock)

### Local Run (Docker)
```bash
docker compose up --build
```

### Local Development (venv)
1.  Create venv: `python3 -m venv .venv`
2.  Activate: `source .venv/bin/activate`
3.  Install deps: `pip install -r requirements.txt`
