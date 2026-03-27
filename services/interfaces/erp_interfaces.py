"""ERP API interfaces for eBroker cloud function."""

import os
import requests
import json
import logging
from typing import Optional, Dict, Any, Tuple, TypedDict, List
from infra.timing import Timer, get_current_agent

logger = logging.getLogger(__name__)

# =============================================================================
# Request Type Definitions (matches ERP repo interfaces)
# =============================================================================

class BaseRequest(TypedDict, total=False):
    company_id: str  # Obligatorio
    option: str      # Obligatorio

class DetalleClienteRequest(BaseRequest):
    """option: 'detalle_cliente'"""
    nif: str  # Obligatorio

class GetPoliciesRequest(BaseRequest):
    """option: 'get_policies'"""
    nif: str  # Obligatorio
    lines: Optional[str]  # Opcional

class GetClaimsRequest(BaseRequest):
    """option: 'get_claims'"""
    nif: str  # Obligatorio

class GetClaimByRiskRequest(BaseRequest):
    """option: 'get_claim_by_risk'"""
    nif: str   # Obligatorio
    risk: str  # Obligatorio

class GetDocPoliciesRequest(BaseRequest):
    """option: 'get_doc_policies'"""
    num_poliza: str  # Obligatorio

class GetPolicyByNumRequest(BaseRequest):
    """option: 'get_policy_by_num'"""
    num_poliza: str  # Obligatorio

class DocumentoReciboRequest(BaseRequest):
    """option: 'documento_recibo'"""
    num_poliza: str  # Obligatorio

class InfoBancoDevolucionRequest(BaseRequest):
    """option: 'info_banco_devolucion'"""
    num_poliza: str  # Obligatorio

class RenovacionesAutoSemanaRequest(BaseRequest):
    """option: 'renovaciones_auto_semana'"""
    start_date: Optional[str]
    frequency: Optional[int]

class RenovacionesRecibosRequest(BaseRequest):
    """option: 'renovaciones_recibos'"""
    start_date: Optional[str]
    frequency: Optional[int]

class GetStatusClaimsRequest(BaseRequest):
    """option: 'get_status_claims'"""
    id_siniestro: int  # Obligatorio

# =============================================================================
# Response Type Definitions (matches ERP repo interfaces)
# =============================================================================

class GetClaimsResponse(TypedDict):
    """Response from option: 'get_claims'"""
    id: str
    opening_date: str
    risk: str
    status: str

class GetClaimByRiskResponse(TypedDict):
    """Response from option: 'get_claim_by_risk'"""
    id: str
    opening_date: str
    risk: str
    status: str

class GetPoliciesResponse(TypedDict):
    """Response from option: 'get_policies'"""
    number: str
    company_id: str
    company_name: str
    risk: str
    phones: Dict[str, str]

class GetDocPoliciesResponse(TypedDict):
    """Response from option: 'get_doc_policies'"""
    description: str
    filename: str
    data: str  # Base64

class DocumentoReciboResponse(TypedDict):
    """Response from option: 'documento_recibo'"""
    description: str
    filename: str
    data: str  # Base64

class RenovacionesAutoSemanaResponse(TypedDict):
    """Response from option: 'renovaciones_auto_semana'"""
    client_nif: str
    client_name: str
    gestor: str

class RenovacionesRecibosResponse(TypedDict):
    """Response from option: 'renovaciones_recibos'"""
    client_nif: str
    client_name: str
    gestor: str

class GetStatusClaimsResponse(TypedDict):
    """Response from option: 'get_status_claims'"""
    Status: str

class DetalleClienteResponse(TypedDict):
    """Response from option: 'detalle_cliente'"""
    id: int
    legal_id: str
    name: str
    surname1: str
    phone: str
    email: str
    address: Dict

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
        # Increased default timeout to 300s to allow long-running operations like Merlin retarification
        self.timeout = int(os.environ.get("ERP_TIMEOUT", "300"))

    def _make_request(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Make a POST request to the ERP cloud function."""
        if not self.endpoint_url:
            raise ERPClientError("ERP_ENDPOINT_URL not configured")

        option = payload.get("option", "unknown")
        parent = get_current_agent()
        with Timer("erp", f"erp_{option}", parent=parent):
            try:
                headers = {"Content-Type": "application/json"}
                logger.debug(f"ERP request: {payload}")
                response = requests.post(
                    self.endpoint_url,
                    json=payload,
                    headers=headers,
                    timeout=self.timeout
                )

                try:
                    result = response.json()
                except json.JSONDecodeError:
                    if response.status_code >= 400:
                        raise ERPClientError(f"HTTP {response.status_code}: {response.text[:300]}")
                    return {"status": response.status_code, "text": response.text}

                if response.status_code >= 500:
                    raise ERPClientError(f"HTTP {response.status_code}: {result}")

                logger.debug(f"ERP response: {result}")
                return result

            except requests.exceptions.Timeout:
                raise ERPClientError("Request timeout - ERP service took too long to respond")
            except requests.exceptions.ConnectionError as e:
                raise ERPClientError(f"Connection failed: {str(e)}")
            except ERPClientError:
                raise
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

        if not self.company_id:
            return {"error": "El campo 'company_id' es obligatorio."}, 400
        
        if not option:
            return {"error": "El campo 'option' es obligatorio."}, 400

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
        """
        Get client policies. option='get_policies'
        Returns: List[GetPoliciesResponse] with number, company_id, company_name, risk, phones
        """
        if not nif:
            return {"error": "El campo 'nif' es obligatorio."}, 400
        data: Dict[str, Any] = {"nif": nif}
        if lines:
            data["lines"] = lines
        return self.execute("get_policies", data)
    
    def get_document(self, num_poliza: str) -> Tuple[Dict[str, Any], int]:
        """
        Get policy document. option='get_doc_policies'
        Returns: GetDocPoliciesResponse with description, filename, data (Base64)
        """
        if not num_poliza:
            return {"error": "El campo 'num_poliza' es obligatorio."}, 400
        return self.execute("get_doc_policies", {"num_poliza": num_poliza})
    
    def get_policy_by_num(self, num_poliza: str) -> Tuple[Dict[str, Any], int]:
        """
        Get policy by number. option='get_policy_by_num'
        """
        if not num_poliza:
            return {"error": "El campo 'num_poliza' es obligatorio."}, 400
        return self.execute("get_policy_by_num", {"num_poliza": num_poliza})

class ReceiptsInterface(ERPBaseInterface):
    """Interface for receipts operations."""
    
    def get_document(self, num_poliza: str) -> Tuple[Dict[str, Any], int]:
        """
        Get receipt document. option='documento_recibo'
        Returns: DocumentoReciboResponse with description, filename, data (Base64)
        """
        if not num_poliza:
            return {"error": "El campo 'num_poliza' es obligatorio."}, 400
        return self.execute("documento_recibo", {"num_poliza": num_poliza})

class ClaimsInterface(ERPBaseInterface):
    """Interface for claims (siniestros) operations."""
    
    def get_claims(self, nif: str) -> Tuple[Dict[str, Any], int]:
        """
        Get client claims. option='get_claims'
        Returns: List[GetClaimsResponse] with id, opening_date, risk, status
        """
        if not nif:
            return {"error": "El campo 'nif' es obligatorio."}, 400
        return self.execute("get_claims", {"nif": nif})
    
    def get_claim_by_risk(self, nif: str, risk: str) -> Tuple[Dict[str, Any], int]:
        """
        Get claim by risk. option='get_claim_by_risk'
        Returns: GetClaimByRiskResponse with id, opening_date, risk, status
        """
        if not nif:
            return {"error": "El campo 'nif' es obligatorio."}, 400
        if not risk:
            return {"error": "El campo 'risk' es obligatorio."}, 400
        return self.execute("get_claim_by_risk", {"nif": nif, "risk": risk})
    
    def get_status(self, id_siniestro: int) -> Tuple[Dict[str, Any], int]:
        """
        Get claim status by ID. option='get_status_claims'
        Returns: GetStatusClaimsResponse with Status
        """
        if not id_siniestro:
            return {"error": "El campo 'id_siniestro' es obligatorio."}, 400
        return self.execute("get_status_claims", {"id_siniestro": id_siniestro})

class RefundsInterface(ERPBaseInterface):
    """Interface for refund-related operations."""
    
    def get_bank_info(self, num_poliza: str) -> Tuple[Dict[str, Any], int]:
        """Get bank account info for refund. option='info_banco_devolucion'"""
        if not num_poliza:
            return {"error": "El campo 'num_poliza' es obligatorio."}, 400
        return self.execute("info_banco_devolucion", {"num_poliza": num_poliza})

class RenewalsInterface(ERPBaseInterface):
    """Interface for renewals operations."""
    
    def get_auto_renewals(
        self, 
        start_date: Optional[str] = None, 
        frequency: Optional[int] = None
    ) -> Tuple[Dict[str, Any], int]:
        """
        Get auto renewals for the week. option='renovaciones_auto_semana'
        Returns: List[RenovacionesAutoSemanaResponse]
        """
        data: Dict[str, Any] = {}
        if start_date:
            data["start_date"] = start_date
        if frequency:
            data["frequency"] = frequency
        return self.execute("renovaciones_auto_semana", data)
    
    def get_receipt_renewals(
        self, 
        start_date: Optional[str] = None, 
        frequency: Optional[int] = None
    ) -> Tuple[Dict[str, Any], int]:
        """
        Get receipt renewals. option='renovaciones_recibos'
        Returns: List[RenovacionesRecibosResponse]
        """
        data: Dict[str, Any] = {}
        if start_date:
            data["start_date"] = start_date
        if frequency:
            data["frequency"] = frequency
        return self.execute("renovaciones_recibos", data)

class MerlinInterface(ERPBaseInterface):
    """Interface for Merlin/Retarificacion operations."""
    
    def consulta_vehiculo(self, matricula: str) -> Tuple[Dict[str, Any], int]:
        """Consulta DGT por matrícula. option='merlin_consulta_vehiculo'"""
        if not matricula:
            return {"error": "El campo 'matricula' es obligatorio."}, 400
        return self.execute("merlin_consulta_vehiculo", {"matricula": matricula})

    def get_town_by_cp(self, cp: str) -> Tuple[Dict[str, Any], int]:
        """Obtiene población por CP. option='merlin_get_town_by_cp'"""
        if not cp:
            return {"error": "El campo 'cp' es obligatorio."}, 400
        return self.execute("merlin_get_town_by_cp", {"cp": cp})

    def consultar_catastro(self, data: Dict[str, Any]) -> Tuple[Dict[str, Any], int]:
        """Consulta Catastro y calcula capitales. option='merlin_consultar_catastro'"""
        return self.execute("merlin_consultar_catastro", data)

    def create_project(self, data: Dict[str, Any]) -> Tuple[Dict[str, Any], int]:
        """Crea proyecto en Merlin. option='merlin_create_project'"""
        return self.execute("merlin_create_project", data)

    def finalizar_proyecto_hogar(self, data: Dict[str, Any]) -> Tuple[Dict[str, Any], int]:
        """Finaliza proyecto HOGAR con capitales elegidos. option='merlin_finalizar_proyecto_hogar'"""
        return self.execute("merlin_finalizar_proyecto_hogar", data)
