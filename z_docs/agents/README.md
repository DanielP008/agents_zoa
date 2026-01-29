# Agents

Agents are the core decision-makers in the ZOA architecture. They are organized by **Domain**, each having a **Classifier** and several **Specialists**.

## Structure

### Domains
1. **Siniestros (Claims)**: Accidents, assistance, claim status.
   - [Documentation](siniestros.md)
2. **Ventas (Sales)**: New policies, cross-selling.
   - [Documentation](ventas.md)
3. **Gestión (Management)**: Policy updates, refunds, inquiries.
   - [Documentation](gestion.md)

### Common Components
- **Classifiers**: `classifier_agent.py` in each domain. They analyze user intent and route to the correct specialist.
- **Specialists**: Perform specific tasks (e.g., `apertura_siniestro_agent.py`, `nueva_poliza_agent.py`). They use Tools to interact with external systems (ERP, ZOA, OCR).
- **Generic Knowledge**: `agents/domains/common/generic_knowledge_agent.py` handles general insurance questions that don't require specific user data.

## Flow
1. **Main Router**: `routers/main_router.py` receives the message and routes to a Domain Classifier based on high-level intent.
2. **Domain Classifier**: Routes to a Specialist.
3. **Specialist**: Interacts with the user, calls Tools, and updates Memory.
