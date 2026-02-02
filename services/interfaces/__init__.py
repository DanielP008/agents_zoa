"""Service interfaces for ZOA and ERP APIs."""

from services.interfaces.zoa_interfaces import (
    ZoaBaseInterface,
    ContactsInterface,
    UsersInterface,
    CardsInterface,
    CardActionsInterface,
    ActivitiesInterface,
    DepartmentsInterface,
    TagsInterface,
    ReadAllInterface,
    EmailInterface,
    ConversationsInterface,
    NotesInterface,
    SchedulerInterface,
)

from services.interfaces.erp_interfaces import (
    # TypedDicts
    BaseRequest,
    DetailCustomerRequest,
    PoliciesRequest,
    ClaimsRequest,
    PolicyDocRequest,
    ReceiptDocRequest,
    BankInfoRequest,
    RenewalsRequest,
    ClaimStatusRequest,
    # Interfaces
    ERPBaseInterface,
    CustomerInterface,
    PoliciesInterface,
    ReceiptsInterface,
    ClaimsInterface as ERPClaimsInterface,
    RefundsInterface,
    ERPClientError,
)

__all__ = [
    # ZOA
    "ZoaBaseInterface",
    "ContactsInterface",
    "UsersInterface",
    "CardsInterface",
    "CardActionsInterface",
    "ActivitiesInterface",
    "DepartmentsInterface",
    "TagsInterface",
    "ReadAllInterface",
    "EmailInterface",
    "ConversationsInterface",
    "NotesInterface",
    "SchedulerInterface",
    # ERP TypedDicts
    "BaseRequest",
    "DetailCustomerRequest",
    "PoliciesRequest",
    "ClaimsRequest",
    "PolicyDocRequest",
    "ReceiptDocRequest",
    "BankInfoRequest",
    "RenewalsRequest",
    "ClaimStatusRequest",
    # ERP Interfaces
    "ERPBaseInterface",
    "CustomerInterface",
    "PoliciesInterface",
    "ReceiptsInterface",
    "ERPClaimsInterface",
    "RefundsInterface",
    "ERPClientError",
]
