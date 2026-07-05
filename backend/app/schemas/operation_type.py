"""
Operation Type Catalog Pydantic Schemas (#876 PR-1, extended in PR-3).

Read-only response shape for GET /api/v1/operation-types (PR-1), plus the
admin CRUD request/response shapes and the audit/classifier report shapes
added in #876 PR-3 (app/api/v1/endpoints/admin/operation_types.py).
"""
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field


class OperationTypeResponse(BaseModel):
    """A single operation-type catalog row, for the future editor picker."""
    model_config = ConfigDict(from_attributes=True)

    id: int
    code: str
    label: str
    description: Optional[str] = None
    category: Optional[str] = None
    consume_stages: List[str]
    is_qc: bool
    is_system: bool
    is_active: bool
    sort_order: int
    created_at: datetime
    updated_at: datetime


# =============================================================================
# #876 PR-3: Admin CRUD
# =============================================================================

class OperationTypeCreate(BaseModel):
    """Create a new (custom, non-system) operation type."""
    code: str = Field(..., min_length=1, max_length=30)
    label: str = Field(..., min_length=1, max_length=100)
    description: Optional[str] = None
    category: Optional[str] = Field(None, max_length=20)
    consume_stages: List[str] = Field(..., min_length=1)
    is_qc: bool = False
    sort_order: int = 0


class OperationTypeUpdate(BaseModel):
    """
    Update an existing operation type.

    For is_system rows, only label/description/category/sort_order/
    is_active are honored — consume_stages/is_qc are LOCKED and any
    attempt to change them is rejected with 400. For custom (non-system)
    rows, editing consume_stages on a type referenced by an operation of a
    NON-terminal production order is rejected with 409.
    """
    label: Optional[str] = Field(None, min_length=1, max_length=100)
    description: Optional[str] = None
    category: Optional[str] = Field(None, max_length=20)
    consume_stages: Optional[List[str]] = Field(None, min_length=1)
    is_qc: Optional[bool] = None
    sort_order: Optional[int] = None
    is_active: Optional[bool] = None


# =============================================================================
# #876 PR-3: Audit
# =============================================================================

class OperationTypeAuditRow(BaseModel):
    operation_code: Optional[str] = None
    operation_name: Optional[str] = None
    routing_op_count: int
    po_op_count: int
    stored_operation_type: Optional[str] = None
    match_source: str
    current_consume_stages: List[str]
    proposed_type: Optional[str] = None
    proposed_consume_stages: Optional[List[str]] = None
    behavior_changed: bool
    material_bearing: bool
    classification_reason: Optional[str] = None
    in_flight_non_terminal_po_count: int


class OperationTypeAuditResponse(BaseModel):
    rows: List[OperationTypeAuditRow]
    total_pairs: int
    total_in_flight_exposure: int


# =============================================================================
# #876 PR-3: Human-gated classifier
# =============================================================================

class ClassifyRequest(BaseModel):
    dry_run: bool = True


class ClassifyProposalRow(BaseModel):
    table: str
    row_id: int
    operation_code: Optional[str] = None
    operation_name: Optional[str] = None
    proposed_type: Optional[str] = None
    reason: Optional[str] = None
    material_bearing: bool
    before_stages: List[str]
    after_stages: Optional[List[str]] = None
    production_order_id: Optional[int] = None
    production_order_status: Optional[str] = None


class ClassifyResponse(BaseModel):
    dry_run: bool
    proposals: List[ClassifyProposalRow]
    applied_count: int
    skipped_manual_decision_count: int
    skipped_no_match_count: int
    non_terminal_exposure_count: int
    applied_by: Optional[str] = None
    applied_at: Optional[datetime] = None
