"""ERP client with backward-compatible function wrappers."""

from typing import Optional, Dict, Any

from services.interfaces.erp_interfaces import (
    ERPBaseInterface,
    ERPClientError,
    CustomerInterface,
    PoliciesInterface,
    ReceiptsInterface,
    ClaimsInterface,
    RefundsInterface,
)


# =============================================================================
# Legacy ERPClient (backward compatibility)
# =============================================================================

class ERPClient(ERPBaseInterface):
    """Legacy client maintaining backward compatibility."""

    def get_client_policies_with_phones(
        self,
        nif: str,
        ramo: Optional[str] = None
    ) -> Dict[str, Any]:
        """Get active policies with assistance phones for a specific category (ramo)."""
        interface = PoliciesInterface(self.company_id)
        result, status = interface.get_policies(nif, lines=ramo)

        if status != 200 or "error" in result:
            return {
                "success": False,
                "error": result.get("error", "Unknown error"),
                "policies": []
            }

        if isinstance(result, list):
            return {"success": True, "policies": result}

        return {"success": True, "policies": result if result else []}

    def get_client_details(self, nif: str) -> Dict[str, Any]:
        """Get client details from the ERP."""
        interface = CustomerInterface(self.company_id)
        result, status = interface.get_details(nif)

        if status != 200 or "error" in result:
            return {
                "success": False,
                "error": result.get("error", "Unknown error"),
                "client": None
            }

        return {"success": True, "client": result}

    def get_client_claims_status(self, nif: str) -> Dict[str, Any]:
        """Get a client's claims status."""
        interface = ClaimsInterface(self.company_id)
        result, status = interface.get_status(nif)

        if status != 200 or "error" in result:
            return {
                "success": False,
                "error": result.get("error", "Unknown error"),
                "claims": []
            }

        if isinstance(result, list):
            return {"success": True, "claims": result}

        return {"success": True, "claims": result if result else []}

    def get_policy_document(self, nif: str, num_poliza: str) -> Dict[str, Any]:
        """Get a policy document from the ERP."""
        interface = PoliciesInterface(self.company_id)
        result, status = interface.get_document(nif, num_poliza)

        if status != 200 or "error" in result:
            return {
                "success": False,
                "error": result.get("error", "Unknown error"),
                "documents": []
            }

        return {"success": True, "documents": result if result else []}

    def get_receipt_document(self, nif: str, num_poliza: str) -> Dict[str, Any]:
        """Get the most recent receipt document for a policy."""
        interface = ReceiptsInterface(self.company_id)
        result, status = interface.get_document(nif, num_poliza)

        if status != 200 or "error" in result:
            return {
                "success": False,
                "error": result.get("error", "Unknown error"),
                "receipt": {}
            }

        return {"success": True, "receipt": result if result else {}}

    def get_bank_info_for_refund(self, num_poliza: str) -> Dict[str, Any]:
        """Get bank account information for a refund."""
        interface = RefundsInterface(self.company_id)
        result, status = interface.get_bank_info(num_poliza)

        if status != 200 or "error" in result:
            return {
                "success": False,
                "error": result.get("error", "Unknown error"),
                "account_number": None
            }

        return {"success": True, "account_number": result}


# =============================================================================
# Backward-compatible function wrappers
# =============================================================================

def get_assistance_phones_from_erp(
    nif: str,
    ramo: str,
    company_id: str
) -> Dict[str, Any]:
    """Fetch assistance phone numbers for active policies."""
    client = ERPClient(company_id)
    return client.get_client_policies_with_phones(nif, ramo=ramo)


def get_client_info_from_erp(
    nif: str,
    company_id: str
) -> Dict[str, Any]:
    """Fetch client details from the ERP."""
    client = ERPClient(company_id)
    return client.get_client_details(nif)


def get_claims_status_from_erp(
    nif: str,
    company_id: str
) -> Dict[str, Any]:
    """Fetch claims status for a client."""
    client = ERPClient(company_id)
    return client.get_client_claims_status(nif)


def get_client_policys(
    nif: str,
    ramo: str,
    company_id: str
) -> Dict[str, Any]:
    """Fetch client policies for the provided ramo."""
    client = ERPClient(company_id)
    result = client.get_client_policies_with_phones(nif)
    if not result.get("success"):
        return result
    return {"success": True, "policies": result.get("policies", [])}


def get_policy_document_from_erp(
    nif: str,
    policy_number: str,
    company_id: str
) -> Dict[str, Any]:
    """Fetch a policy document from ERP by policy number."""
    client = ERPClient(company_id)
    return client.get_policy_document(nif, policy_number)


def get_claims_from_erp(
    nif: str,
    line: str,
    company_id: str,
    phone: Optional[str] = None,
) -> Dict[str, Any]:
    """Fetch claims (siniestros) for a NIF and ramo/line from ERP. Includes status."""
    interface = ClaimsInterface(company_id)
    result, status = interface.get_claims(nif, lines=line, phone=phone)

    if status != 200 or (isinstance(result, dict) and result.get("error")):
        return {"success": False, "error": result.get("error", "Unknown error"), "claims": []}

    if not isinstance(result, list):
        return {"success": True, "claims": []}

    claims = []
    for c in result:
        claims.append({
            "id_claim": str(c.get("id", c.get("id_claim", ""))),
            "riesgo": c.get("risk", c.get("riesgo", "")),
            "date": c.get("opening_date", c.get("date", "")),
            "status": c.get("status", ""),
        })
    return {"success": True, "claims": claims}
