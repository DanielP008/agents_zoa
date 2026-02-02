"""ERP API interfaces for eBroker cloud function."""

import os
import requests
import json
import logging
from typing import Optional, Dict, Any, Tuple, TypedDict

logger = logging.getLogger(__name__)


# =============================================================================
# Request Type Definitions (Interface Documentation)
# =============================================================================

class BaseRequest(TypedDict, total=False):
    company_id: str  # Obligatorio
    option: str      # Obligatorio


class DetailCustomerRequest(BaseRequest):
    nif: str         # Obligatorio


class PoliciesRequest(BaseRequest):
    nif: str         # Obligatorio
    lines: Optional[str]  # Opcional: Ramo a filtrar (hogar, auto...)


class ClaimsRequest(BaseRequest):
    nif: str         # Obligatorio
    lines: Optional[str]  # Opcional: Ramo/línea a filtrar
    phone: Optional[str]  # Opcional


class PolicyDocRequest(BaseRequest):
    nif: str         # Obligatorio
    num_poliza: str  # Obligatorio


class ReceiptDocRequest(BaseRequest):
    nif: str         # Obligatorio
    num_poliza: str  # Obligatorio


class BankInfoRequest(BaseRequest):
    num_poliza: str  # Obligatorio


class RenewalsRequest(BaseRequest):
    start_date: Optional[str]  # Opcional: YYYY-MM-DD
    frequency: Optional[int]   # Opcional: Días de rango




# =============================================================================
# Exceptions
# =============================================================================

class ERPClientError(Exception):
    """ERP client error."""
    pass


# =============================================================================
# ERP Base Interface
# =============================================================================

class ERPBaseInterface:
    """Base class for ERP API interactions."""
    
    def __init__(self, company_id: str):
        self.company_id = company_id
        self.endpoint_url = os.environ.get(
            "ERP_ENDPOINT_URL",
            "https://ebroker-api-673887944015.europe-southwest1.run.app"
        )
        self.timeout = int(os.environ.get("ERP_TIMEOUT", "30"))

    def _make_request(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Make a POST request to the ERP cloud function."""
        if not self.endpoint_url:
            raise ERPClientError("ERP_ENDPOINT_URL not configured")

        try:
            headers = {"Content-Type": "application/json"}
            logger.debug(f"ERP request: {payload}")
            response = requests.post(
                self.endpoint_url,
                json=payload,
                headers=headers,
                timeout=self.timeout
            )
            response.raise_for_status()

            try:
                result = response.json()
                logger.debug(f"ERP response: {result}")
                return result
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

    def execute(
        self,
        option: str,
        request_data: Optional[Dict[str, Any]] = None
    ) -> Tuple[Dict[str, Any], int]:
        """
        Execute a specific ERP operation.
        
        Args:
            option: Operation to execute (get_policies, detalle_cliente, etc.)
            request_data: Additional data for the request
            
        Returns:
            Tuple of (response_dict, status_code)
        """
        if request_data is None:
            request_data = {}

        # Validate required fields
        if not self.company_id:
            return {"error": "El campo 'company_id' es obligatorio."}, 400
        
        if not option:
            return {"error": "El campo 'option' es obligatorio."}, 400

        # Build payload with required fields
        payload = {
            "company_id": self.company_id,
            "option": option,
            **request_data
        }

        try:
            result = self._make_request(payload)
            status = 200 if "error" not in result else 400
            return result, status
        except ERPClientError as e:
            return {"error": str(e)}, 500


# =============================================================================
# Specialized Interfaces
# =============================================================================

class CustomerInterface(ERPBaseInterface):
    """Interface for customer/client operations."""
    
    def get_details(self, nif: str) -> Tuple[Dict[str, Any], int]:
        """Get client details. option='detalle_cliente'"""
        if not nif:
            return {"error": "El campo 'nif' es obligatorio."}, 400
        return self.execute("detalle_cliente", {"nif": nif})


class PoliciesInterface(ERPBaseInterface):
    """Interface for policies operations."""
    
    def get_policies(self, nif: str, lines: Optional[str] = None) -> Tuple[Dict[str, Any], int]:
        """Get client policies. option='get_policies'"""
        if not nif:
            return {"error": "El campo 'nif' es obligatorio."}, 400
        data: Dict[str, Any] = {"nif": nif}
        if lines:
            data["lines"] = lines
        return self.execute("get_policies", data)
    
    def get_document(self, nif: str, num_poliza: str) -> Tuple[Dict[str, Any], int]:
        """Get policy document. option='documento_polizas'"""
        if not nif:
            return {"error": "El campo 'nif' es obligatorio."}, 400
        if not num_poliza:
            return {"error": "El campo 'num_poliza' es obligatorio."}, 400
        return self.execute("documento_polizas", {"nif": nif, "num_poliza": num_poliza})


class ReceiptsInterface(ERPBaseInterface):
    """Interface for receipts operations."""
    
    def get_document(self, nif: str, num_poliza: str) -> Tuple[Dict[str, Any], int]:
        """Get receipt document. option='documento_recibo'"""
        if not nif:
            return {"error": "El campo 'nif' es obligatorio."}, 400
        if not num_poliza:
            return {"error": "El campo 'num_poliza' es obligatorio."}, 400
        return self.execute("documento_recibo", {"nif": nif, "num_poliza": num_poliza})


class ClaimsInterface(ERPBaseInterface):
    """Interface for claims (siniestros) operations."""
    
    def get_claims(
        self, 
        nif: str, 
        lines: Optional[str] = None,
        phone: Optional[str] = None
    ) -> Tuple[Dict[str, Any], int]:
        """Get client claims. option='get_claims'"""
        if not nif:
            return {"error": "El campo 'nif' es obligatorio."}, 400
        data: Dict[str, Any] = {"nif": nif}
        if lines:
            data["lines"] = lines
        if phone:
            data["phone"] = phone
        return self.execute("get_claims", data)
    
    def get_status(self, nif: str) -> Tuple[Dict[str, Any], int]:
        """Get claims status for a client. option='estado_siniestros'"""
        if not nif:
            return {"error": "El campo 'nif' es obligatorio."}, 400
        return self.execute("estado_siniestros", {"nif": nif})
    


class RefundsInterface(ERPBaseInterface):
    """Interface for refund-related operations."""
    
    def get_bank_info(self, num_poliza: str) -> Tuple[Dict[str, Any], int]:
        """Get bank account info for refund. option='info_banco_devolucion'"""
        if not num_poliza:
            return {"error": "El campo 'num_poliza' es obligatorio."}, 400
        return self.execute("info_banco_devolucion", {"num_poliza": num_poliza})
