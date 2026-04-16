# Core

The `core/` modules implement the foundational logic for the agent system, including orchestration, memory management, and database interactions.

## Key Modules

### Orchestration
- `orchestrator.py`: The heart of the system.
  - Manages the conversation loop.
  - Loads/Saves session state.
  - Routes messages to the active agent.
  - Handles tool execution and memory updates.
- `agent_factory.py`: Creates LangChain agents with the appropriate tools and prompts.
- `agent_allowlist.py`: Defines which agents are available and valid for routing.

### Memory & State
- `memory_schema.py`: Defines the structure of the agent memory (Global, Domain, Agent-specific).
- `db.py`: Manages PostgreSQL connections and session persistence.
- `hooks.py`: Provides configuration hooks (e.g., loading routes from JSON).

### Utilities
- `llm.py`: Configures and returns the LLM instance (Gemini).
- `llm_utils.py`: Helpers for safe LLM invocation and structured output parsing.
- `tracing.py`: Utilities for logging and debugging.
