# App Entry

`app/handler.py` is the HTTP entry point for the Cloud Run/Functions service.

## Responsibilities
1. **Input Validation**: Ensures the request contains required fields (`wa_id`, `mensaje`, etc.).
2. **Session Management**: Initializes the session context via `core.orchestrator`.
3. **Execution**: Invokes `orchestrator.process_message()` to handle the agent loop.
4. **Response Formatting**: Returns the agent's response (or error) in the JSON format expected by the caller (typically the ZOA flow engine).

## Key Endpoints
- `POST /`: Main webhook for processing messages.
