# Routers

Routing logic determines which agent should handle a user's message.

## Main Router
`core/routing/main_router.py` is the entry point for routing. It uses `core/routing/routes.json` to map intent or state to a specific agent.

## Configuration (`core/routing/routes.json`)
This JSON file defines the structure of the agent network:
- **`default_agent`**: Usually the `receptionist_agent`.
- **`domains`**: Definitions for each domain (Siniestros, Ventas, Gestión).
  - **`classifier`**: The agent responsible for routing within the domain.
  - **`specialists`**: List of valid agents within the domain.

## Flow
1. **Global Routing**: If the user is not in a specific flow, the `receptionist_agent` (or Main Router logic) decides the domain.
2. **Domain Routing**: The Domain Classifier (`classifier_agent.py`) analyzes the message to pick a Specialist.
3. **Specialist Handling**: The selected agent handles the interaction until it returns `finish` or routes elsewhere.
