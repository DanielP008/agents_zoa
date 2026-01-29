# Configuration

## Environment Variables
Copy `.env.example` to `.env` and set the required values.

Required:
- `GEMINI_API_KEY`
- `GEMINI_MODEL`
- `ZOA_ENDPOINT_URL`

Optional:
- `GEMINI_OCR_MODEL`
- `LANGSMITH_API_KEY`
- `LANGCHAIN_TRACING_V2`

## Database
PostgreSQL sessions table:
```sql
CREATE TABLE sessions (
    session_id VARCHAR(255) PRIMARY KEY,
    domain VARCHAR(100),
    target_agent VARCHAR(100),
    agent_memory JSONB,
    updated_at TIMESTAMP DEFAULT NOW()
);
```

## Routing
`routers/routes.json` defines the default agent, domain classifiers, and
specialists. Use `core.hooks.get_routes_path()` for consistent path access.

## Execution
Docker:
```bash
docker compose up --build
```

Local:
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m flask run --port 8080
```
