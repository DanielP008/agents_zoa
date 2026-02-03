"""Service interfaces for ZOA and ERP APIs."""

from services.interfaces.zoa_interfaces import (
    ZoaBaseInterface,
    ContactsInterface,
    ConversationsInterface,
    CardActionsInterface,
)

from services.interfaces.erp_interfaces import (
    # Request TypedDicts
    BaseRequest,
    DetalleClienteRequest,
    GetPoliciesRequest,
    GetClaimsRequest,
    GetClaimByRiskRequest,
    GetDocPoliciesRequest,
    GetPolicyByNumRequest,
    DocumentoReciboRequest,
    InfoBancoDevolucionRequest,
    RenovacionesAutoSemanaRequest,
    RenovacionesRecibosRequest,
    GetStatusClaimsRequest,
    # Response TypedDicts
    GetClaimsResponse,
    GetClaimByRiskResponse,
    GetPoliciesResponse,
    GetDocPoliciesResponse,
    DocumentoReciboResponse,
    RenovacionesAutoSemanaResponse,
    RenovacionesRecibosResponse,
    GetStatusClaimsResponse,
    DetalleClienteResponse,
    # Interfaces
    ERPBaseInterface,
    ERPClientError,
    CustomerInterface,
    PoliciesInterface,
    ReceiptsInterface,
    ClaimsInterface,
    RefundsInterface,
    RenewalsInterface,
)

__all__ = [
    # ZOA Interfaces
    "ZoaBaseInterface",
    "ContactsInterface",
    "ConversationsInterface",
    "CardActionsInterface",
    # ERP Request TypedDicts
    "BaseRequest",
    "DetalleClienteRequest",
    "GetPoliciesRequest",
    "GetClaimsRequest",
    "GetClaimByRiskRequest",
    "GetDocPoliciesRequest",
    "GetPolicyByNumRequest",
    "DocumentoReciboRequest",
    "InfoBancoDevolucionRequest",
    "RenovacionesAutoSemanaRequest",
    "RenovacionesRecibosRequest",
    "GetStatusClaimsRequest",
    # ERP Response TypedDicts
    "GetClaimsResponse",
    "GetClaimByRiskResponse",
    "GetPoliciesResponse",
    "GetDocPoliciesResponse",
    "DocumentoReciboResponse",
    "RenovacionesAutoSemanaResponse",
    "RenovacionesRecibosResponse",
    "GetStatusClaimsResponse",
    "DetalleClienteResponse",
    # ERP Interfaces
    "ERPBaseInterface",
    "ERPClientError",
    "CustomerInterface",
    "PoliciesInterface",
    "ReceiptsInterface",
    "ClaimsInterface",
    "RefundsInterface",
    "RenewalsInterface",
]
