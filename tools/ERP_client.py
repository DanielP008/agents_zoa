"""ERP client for the eBroker cloud function."""

import os
import requests
import json
from typing import Optional, Dict, Any, List


class ERPClientError(Exception):
    """ERP client error."""
    pass


class ERPClient:
    """Client for the eBroker cloud function."""

    def __init__(self, company_id: str = ""):
        """Initialize the ERP client with a company identifier."""
        self.endpoint_url = os.environ.get(
            "ERP_ENDPOINT_URL",
            "https://ebroker-api-673887944015.europe-southwest1.run.app"
        )
        self.company_id = company_id
        self.timeout = int(os.environ.get("ERP_TIMEOUT", "30"))

    def _make_request(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Make a POST request to the ERP cloud function."""
        if not self.endpoint_url:
            raise ERPClientError("ERP_ENDPOINT_URL not configured")

        try:
            headers = {"Content-Type": "application/json"}
            response = requests.post(
                self.endpoint_url,
                json=payload,
                headers=headers,
                timeout=self.timeout
            )
            response.raise_for_status()

            try:
                return response.json()
            except json.JSONDecodeError:
                return {"status": response.status_code, "text": response.text}

        except requests.exceptions.Timeout:
            raise ERPClientError("Request timeout - ERP service took too long to respond")
        except requests.exceptions.ConnectionError as e:
            raise ERPClientError(f"Connection failed: {str(e)}")
        except requests.exceptions.HTTPError as e:
            raise ERPClientError(f"HTTP error: {str(e)}")
        except Exception as e:
            raise ERPClientError(f"Unexpected error: {str(e)}")

    def get_client_policies_with_phones(
        self,
        nif: str,
        ramo: Optional[str] = None,
        company_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Get active policies with assistance phones for a specific category (ramo)."""
        payload = {
            "company_id": company_id or self.company_id,
            "option": "get_policies",
            "nif": nif,
            "lines": ramo  # 'lines' corresponds to 'ramo' in the cloud function
        }

        try:
            response = self._make_request(payload)

            if isinstance(response, list):
                return {
                    "success": True,
                    "policies": response
                }

            if isinstance(response, dict) and "error" in response:
                return {
                    "success": False,
                    "error": response.get("error"),
                    "policies": []
                }

            return {
                "success": True,
                "policies": response if response else []
            }

        except ERPClientError as e:
            return {
                "success": False,
                "error": str(e),
                "policies": []
            }

    def get_client_details(
        self,
        nif: str,
        company_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Get client details from the ERP."""
        payload = {
            "company_id": company_id or self.company_id,
            "option": "detalle_cliente",
            "nif": nif
        }

        try:
            response = self._make_request(payload)
            return {
                "success": True,
                "client": response
            }
        except ERPClientError as e:
            return {
                "success": False,
                "error": str(e),
                "client": None
            }

    def get_client_claims_status(
        self,
        nif: str,
        company_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Get a client's claims status."""
        payload = {
            "company_id": company_id or self.company_id,
            "option": "estado_siniestros",
            "nif": nif
        }

        try:
            response = self._make_request(payload)

            if isinstance(response, list):
                return {
                    "success": True,
                    "claims": response
                }

            return {
                "success": True,
                "claims": response if response else []
            }

        except ERPClientError as e:
            return {
                "success": False,
                "error": str(e),
                "claims": []
            }

    def get_policy_document(
        self,
        nif: str,
        num_poliza: str,
        company_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Get a policy document from the ERP."""
        payload = {
            "company_id": company_id or self.company_id,
            "option": "documento_polizas",
            "nif": nif,
            "num_poliza": num_poliza
        }

        try:
            response = self._make_request(payload)
            return {
                "success": True,
                "documents": response if response else []
            }
        except ERPClientError as e:
            return {
                "success": False,
                "error": str(e),
                "documents": []
            }

    def get_receipt_document(
        self,
        nif: str,
        num_poliza: str,
        company_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Get the most recent receipt document for a policy."""
        payload = {
            "company_id": company_id or self.company_id,
            "option": "documento_recibo",
            "nif": nif,
            "num_poliza": num_poliza
        }

        try:
            response = self._make_request(payload)
            return {
                "success": True,
                "receipt": response if response else {}
            }
        except ERPClientError as e:
            return {
                "success": False,
                "error": str(e),
                "receipt": {}
            }

    def get_bank_info_for_refund(
        self,
        num_poliza: str,
        company_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Get bank account information for a refund."""
        payload = {
            "company_id": company_id or self.company_id,
            "option": "info_banco_devolucion",
            "num_poliza": num_poliza
        }

        try:
            response = self._make_request(payload)
            return {
                "success": True,
                "account_number": response
            }
        except ERPClientError as e:
            return {
                "success": False,
                "error": str(e),
                "account_number": None
            }


def get_assistance_phones_from_erp(
    nif: str,
    ramo: str,
    company_id: str = ""
) -> Dict[str, Any]:
    """Fetch assistance phone numbers for active policies."""
    client = ERPClient(company_id=company_id)
    return client.get_client_policies_with_phones(nif, ramo=ramo)


def get_client_info_from_erp(
    nif: str,
    company_id: str = ""
) -> Dict[str, Any]:
    """Fetch client details from the ERP."""
    client = ERPClient(company_id=company_id)
    return client.get_client_details(nif)


def get_claims_status_from_erp(
    nif: str,
    company_id: str = ""
) -> Dict[str, Any]:
    """Fetch claims status for a client."""
    client = ERPClient(company_id=company_id)
    return client.get_client_claims_status(nif)

## TO-DO: RE DO WHEN THIS FUNCTION IS CREATED BY GUILLEM
def get_client_policys(
    nif: str,
    ramo: str,
    company_id: str = ""
) -> Dict[str, Any]:
    """Fetch client policies for the provided ramo."""
    client = ERPClient(company_id=company_id)
    result = client.get_client_policies_with_phones(nif)
    if not result.get("success"):
        return result
    return {"success": True, "policies": result.get("policies", [])}


def get_policy_document_from_erp(
    nif: str,
    policy_number: str,
    company_id: str = ""
) -> Dict[str, Any]:
    """Fetch a policy document from ERP by policy number."""
    client = ERPClient(company_id=company_id)
    return client.get_policy_document(nif, policy_number)
