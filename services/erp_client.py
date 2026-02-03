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
        """
        Get active policies with assistance phones for a specific category (ramo).
        Uses option='get_policies' which returns: number, company_id, company_name, risk, phones
        """
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
        """
        Get client details from the ERP.
        Uses option='detalle_cliente' which returns: id, legal_id, name, surname1, phone, email, address
        """
        interface = CustomerInterface(self.company_id)
        result, status = interface.get_details(nif)

        if status != 200 or "error" in result:
            return {
                "success": False,
                "error": result.get("error", "Unknown error"),
                "client": None
            }

        return {"success": True, "client": result}

    def get_policy_document(self, num_poliza: str) -> Dict[str, Any]:
        """
        Get a policy document from the ERP.
        Uses option='get_doc_policies' which returns: description, filename, data (Base64)
        """
        interface = PoliciesInterface(self.company_id)
        result, status = interface.get_document(num_poliza)

        if status != 200 or "error" in result:
            return {
                "success": False,
                "error": result.get("error", "Unknown error"),
                "documents": []
            }

        # Result is a single document object, wrap in list for consistency
        if isinstance(result, dict) and "data" in result:
            return {"success": True, "documents": [result]}
        
        return {"success": True, "documents": result if result else []}

    def get_receipt_document(self, num_poliza: str) -> Dict[str, Any]:
        """
        Get the most recent receipt document for a policy.
        Uses option='documento_recibo' which returns: description, filename, data (Base64)
        """
        interface = ReceiptsInterface(self.company_id)
        result, status = interface.get_document(num_poliza)

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

    def get_client_claims(self, nif: str) -> Dict[str, Any]:
        """
        Get all claims for a client.
        Uses option='get_claims' which returns: id, opening_date, risk, status
        """
        interface = ClaimsInterface(self.company_id)
        result, status = interface.get_claims(nif)

        if status != 200 or "error" in result:
            return {
                "success": False,
                "error": result.get("error", "Unknown error"),
                "claims": []
            }

        if isinstance(result, list):
            return {"success": True, "claims": result}

        return {"success": True, "claims": result if result else []}

    def get_claim_by_risk(self, nif: str, risk: str) -> Dict[str, Any]:
        """
        Get claim by risk identifier.
        Uses option='get_claim_by_risk' which returns: id, opening_date, risk, status
        """
        interface = ClaimsInterface(self.company_id)
        result, status = interface.get_claim_by_risk(nif, risk)

        if status != 200 or "error" in result:
            return {
                "success": False,
                "error": result.get("error", "Unknown error"),
                "claim": None
            }

        return {"success": True, "claim": result}

    def get_claim_status(self, id_siniestro: int) -> Dict[str, Any]:
        """
        Get status of a specific claim by ID.
        Uses option='get_status_claims' which returns: Status
        """
        interface = ClaimsInterface(self.company_id)
        result, status = interface.get_status(id_siniestro)

        if status != 200 or "error" in result:
            return {
                "success": False,
                "error": result.get("error", "Unknown error"),
                "status": None
            }

        return {"success": True, "status": result.get("Status")}


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


def get_client_policys(
    nif: str,
    ramo: str,
    company_id: str
) -> Dict[str, Any]:
    """Fetch client policies for the provided ramo."""
    client = ERPClient(company_id)
    result = client.get_client_policies_with_phones(nif, ramo=ramo)
    if not result.get("success"):
        return result
    return {"success": True, "policies": result.get("policies", [])}


def get_policy_document_from_erp(
    policy_number: str,
    company_id: str
) -> Dict[str, Any]:
    """Fetch a policy document from ERP by policy number."""
    client = ERPClient(company_id)
    return client.get_policy_document(policy_number)


def get_claims_from_erp(
    nif: str,
    company_id: str
) -> Dict[str, Any]:
    """
    Fetch claims (siniestros) for a NIF from ERP.
    Returns: id, opening_date, risk, status
    """
    client = ERPClient(company_id)
    result = client.get_client_claims(nif)

    if not result.get("success"):
        return result

    # Normalize response format
    claims = []
    for c in result.get("claims", []):
        claims.append({
            "id_claim": str(c.get("id", "")),
            "riesgo": c.get("risk", ""),
            "date": c.get("opening_date", ""),
            "status": c.get("status", ""),
        })
    return {"success": True, "claims": claims}


def get_claim_by_risk_from_erp(
    nif: str,
    risk: str,
    company_id: str
) -> Dict[str, Any]:
    """Fetch a specific claim by risk identifier."""
    client = ERPClient(company_id)
    return client.get_claim_by_risk(nif, risk)


def get_claim_status_from_erp(
    id_siniestro: int,
    company_id: str
) -> Dict[str, Any]:
    """Fetch status of a specific claim by ID."""
    client = ERPClient(company_id)
    return client.get_claim_status(id_siniestro)
