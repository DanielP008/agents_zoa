# Core

The `core/` modules implement orchestration, memory, and agent utilities.

## Key Modules
- `orchestrator.py` executes agent turns and persists memory.
- `agent_factory.py` builds LangChain agents.
- `llm_utils.py` provides safe LLM invocation helpers.
- `memory_schema.py` defines memory shape helpers.
- `db.py` manages PostgreSQL session storage.
