# Ventas Agents

The Ventas (Sales) domain focuses on acquiring new business and expanding relationships with existing clients.

## Classifier
`agents/domains/ventas/classifier_agent.py`
- **Role**: Determines if the user is a prospect for a new policy or an existing client suitable for cross-selling.
- **Routes to**:
  - `nueva_poliza_agent`: New quotes and contracts.
  - `venta_cruzada_agent`: Upgrades and complementary products for existing clients.

## Specialists

### `nueva_poliza_agent.py`
- **Role**: Handles quotes and contracting for new policies.
- **Key Logic**: 
  - Identifies needs (Auto, Hogar, etc.).
  - Collects risk data (vehicle details, property size, etc.).
  - Generates quotes.
  - Collects personal data for contracting if accepted.
- **Tools**: 
  - `create_quote_tool`
  - `create_new_policy_tool`

### `venta_cruzada_agent.py`
- **Role**: Identifies opportunities to upsell or cross-sell to existing clients.
- **Key Logic**: 
  - Analyzes current customer portfolio.
  - Suggests upgrades (e.g., Third Party -> All Risk) or complementary products (Auto -> Home).
  - Highlights specific value propositions and discounts.
  - Registers offers for follow-up.
- **Tools**: 
  - `get_customer_policies_tool`
  - `create_cross_sell_offer_tool`
