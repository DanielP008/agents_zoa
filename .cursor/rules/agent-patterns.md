# Agent Patterns

- **Multi-Level Routing**: 
  1. `Receptionist` determines domain (e.g., Siniestros).
  2. `Domain Classifier` determines intent (e.g., Apertura).
  3. `Specific Agent` handles the task.

- **Naming Convention**: All agents must end in `_agent.py`.
- **Contracts**: Routes and valid agents are defined in `contracts/routes.json`.
- **Statelessness**: Agents rely on `session_id` to retrieve state from store.
- **Deterministic Dispatch**: Routers never guess; they follow `routes.json`.
- **Aggregator**: Merges agent outputs into final response (handled by Router for single-turn).
