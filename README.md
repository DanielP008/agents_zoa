# ZOA Agents

Automation app for insurance brokerage. AI agents answer WhatsApp messages and automate processes.

## Components
1. **Receptionist Agent** (`receptionist_agent.py`): Level 1 router (routes to Domain).
2. **Domain Router** (`router.py`): Dispatches to domain-specific agents.
3. **Domain Classifier** (`classifier_agent.py`): Level 2 router (understands user intent within a domain).
4. **Specific Agents**: e.g., `apertura_siniestro_agent.py`.

## Tech
- LangChain + LangSmith
- Gemini models (API key and model name in `.env`)
- Python 3.11 + Docker

## Structure
```
agents/
  receptionist_agent.py  # Entrypoint classifier
  router.py              # Logic dispatcher
  domains/
    siniestros/
      classifier_agent.py
      apertura_siniestro_agent.py
      ...
```


## Tech
- LangChain + LangSmith
- Gemini models (API key and model name in `.env`)

## Local run (Docker)
1. Copy `.env.example` to `.env`
2. `docker compose up --build`

## Local dev (venv)
1. Create venv: `python3 -m venv .venv`
2. Activate: `source .venv/bin/activate`
3. Install deps: `pip install -r requirements.txt`

## Handler entrypoint
The HTTP handler lives at `app/handler.py` as `handle_whatsapp`.
