"""
schemas.py

Pydantic request/response models for the dispute endpoints. Separate from
db_models.py (the SQLAlchemy ORM models) so API contracts can evolve
independently of storage.
"""

from datetime import datetime
from decimal import Decimal
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


class DisputeCreate(BaseModel):
    customer_id: str
    amount: float
    description: Optional[str] = None


class DisputeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    customer_id: str = Field(validation_alias="card_member_id")
    reason_code: str
    amount: float
    status: str
    created_at: datetime


class StatusOut(BaseModel):
    dispute_id: int
    status: str
    billing_evidence_count: int = 0
    reconciliation_stale: bool = False


class BillingEvidenceCreate(BaseModel):
    evidence_type: Literal["invoice_line_item", "contract_rule", "usage_event", "payment_adjustment"]
    data: dict[str, Any]
    submitted_by: Literal["customer", "reviewer"] = "customer"


class BillingEvidenceOut(BaseModel):
    id: int
    dispute_id: int
    evidence_type: str
    submitted_by: str
    payload: Any
    created_at: datetime
    duplicate_ignored: bool = False


class ReviewerActionCreate(BaseModel):
    action: Literal["accept", "edit", "reject", "request_information"]
    note: Optional[str] = None
    edited_findings: Optional[list[dict[str, Any]]] = None


class MockAdjustmentCreate(BaseModel):
    amount: Decimal
    reason: str
    approved_by: str = "reviewer"


class MockAdjustmentOut(BaseModel):
    id: int
    dispute_id: int
    amount: Decimal
    reason: str
    approved_by: str
    created_at: datetime
