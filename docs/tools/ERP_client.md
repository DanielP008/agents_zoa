# ERP Client

`tools/erp_client.py` contains ERP-facing functions for policy and customer data. It acts as a bridge to the eBroker Cloud Function.

## Capabilities
- **Get Client Policies**: Retrieve active policies, including assistance phone numbers. Supports filtering by `ramo` (Category).
- **Get Client Details**: Fetch detailed customer information.
- **Get Claims Status**: Check the status of existing claims.
- **Get Documents**: Retrieve policy PDFs and receipts.
- **Get Bank Info**: Fetch default bank account for refunds.

## Key Functions
- `get_assistance_phones_from_erp(nif, ramo)`: Main entry point for assistance agents.
- `get_client_policys(nif, ramo)`: Fetches policies for general inquiries.
- `get_policy_document_from_erp(nif, policy_number)`: Downloads policy documents.

## Configuration
- `ERP_ENDPOINT_URL`: The URL of the ERP Cloud Function.
- `ERP_TIMEOUT`: Request timeout (default 30s).
