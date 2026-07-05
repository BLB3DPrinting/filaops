"""
Admin: Operation Type Catalog — audit, human-gated classifier, hardened CRUD
(#876 PR-3).

GET  /api/v1/admin/operation-types/audit
  Read-only, re-runnable audit of every distinct (operation_code,
  operation_name) pair across routing_operations AND
  production_order_operations: per-table counts, stored type, resolved
  consume stages, match source, old-vs-new stage projection, a
  behavior_changed flag, and an in-flight (non-terminal PO) exposure
  rollup.

POST /api/v1/admin/operation-types/classify
  Human-gated classifier. dry_run=true (default) returns the proposal
  report and WRITES NOTHING. dry_run=false applies NULL-operation_type ->
  proposed type ONLY — never overwrites a human-set type, and a
  material-bearing op that would otherwise match a no-consume type
  (QUALITY_CONTROL/SANDING/SUPPORT_REMOVAL) is always surfaced as "needs
  manual decision" instead of auto-applied. Idempotent: re-running after
  an apply finds no NULL rows left to act on.

POST/PUT/POST .../{code}/deactivate  /api/v1/admin/operation-types
  Hardened CRUD. is_system rows are undeletable and have consume_stages/
  is_qc LOCKED (only label/description/category/sort_order/is_active are
  editable). Editing consume_stages on ANY type (system or custom) that is
  referenced by an operation belonging to a NON-terminal production order
  is rejected with 409 ("create a new type instead"). Custom types support
  deactivate only (no hard delete).

Staff-gated: uses the same router-level dependency as reconciliation.py /
mrp.py (post-#683).
"""
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.api.v1.deps import get_current_staff_user
from app.models.manufacturing import OperationType
from app.models.production_order import ProductionOrder, ProductionOrderOperation
from app.models.user import User
from app.schemas.operation_type import (
    OperationTypeResponse,
    OperationTypeCreate,
    OperationTypeUpdate,
    OperationTypeAuditResponse,
    OperationTypeAuditRow,
    ClassifyRequest,
    ClassifyResponse,
    ClassifyProposalRow,
)
from app.services.operation_type_classifier import (
    PO_TERMINAL_STATUSES,
    build_audit,
    run_classifier,
)

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/operation-types",
    tags=["Admin - Operation Types"],
    dependencies=[Depends(get_current_staff_user)],
)


# =============================================================================
# Audit
# =============================================================================

@router.get("/audit", response_model=OperationTypeAuditResponse)
def get_operation_type_audit(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_staff_user),
):
    """Read-only, re-runnable audit — see module docstring."""
    rows = build_audit(db)
    return OperationTypeAuditResponse(
        rows=[OperationTypeAuditRow(**row.__dict__) for row in rows],
        total_pairs=len(rows),
        total_in_flight_exposure=sum(r.in_flight_non_terminal_po_count for r in rows),
    )


# =============================================================================
# Human-gated classifier
# =============================================================================

@router.post("/classify", response_model=ClassifyResponse)
def classify_operation_types(
    request: ClassifyRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_staff_user),
):
    """dry_run=true (default): proposal report, no writes. dry_run=false:
    apply NULL-only, never overwrite, idempotent. See module docstring."""
    result = run_classifier(db, dry_run=request.dry_run)

    applied_by = None
    applied_at = None
    if not request.dry_run and result.applied_count:
        applied_by = current_user.email
        applied_at = datetime.now(timezone.utc)
        logger.info(
            "operation-type classifier applied %d rows (skipped_manual=%d "
            "skipped_no_match=%d) by %s",
            result.applied_count,
            result.skipped_manual_decision_count,
            result.skipped_no_match_count,
            current_user.email,
        )

    return ClassifyResponse(
        dry_run=result.dry_run,
        proposals=[ClassifyProposalRow(**p.__dict__) for p in result.proposals],
        applied_count=result.applied_count,
        skipped_manual_decision_count=result.skipped_manual_decision_count,
        skipped_no_match_count=result.skipped_no_match_count,
        non_terminal_exposure_count=result.non_terminal_exposure_count,
        applied_by=applied_by,
        applied_at=applied_at,
    )


# =============================================================================
# Hardened admin CRUD
# =============================================================================

def _get_or_404(db: Session, code: str) -> OperationType:
    op_type = db.query(OperationType).filter(OperationType.code == code).first()
    if not op_type:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Operation type not found: {code}")
    return op_type


def _referenced_by_non_terminal_po(db: Session, code: str) -> bool:
    """True if `code` is the operation_type of any operation belonging to
    a NON-terminal production order. See operation_type_classifier.py for
    the PO_TERMINAL_STATUSES rationale (the #850 fork)."""
    exists = (
        db.query(ProductionOrderOperation.id)
        .join(ProductionOrder, ProductionOrder.id == ProductionOrderOperation.production_order_id)
        .filter(
            ProductionOrderOperation.operation_type == code,
            ProductionOrder.status.notin_(PO_TERMINAL_STATUSES),
        )
        .first()
    )
    return exists is not None


@router.post("", response_model=OperationTypeResponse, status_code=status.HTTP_201_CREATED)
def create_operation_type(
    request: OperationTypeCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_staff_user),
):
    """Create a new custom (non-system) operation type."""
    code = request.code.upper()
    existing = db.query(OperationType).filter(OperationType.code == code).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Operation type with code '{code}' already exists",
        )

    op_type = OperationType(
        code=code,
        label=request.label,
        description=request.description,
        category=request.category,
        consume_stages=list(request.consume_stages),
        is_qc=request.is_qc,
        is_system=False,
        is_active=True,
        sort_order=request.sort_order,
    )
    db.add(op_type)
    db.commit()
    db.refresh(op_type)

    logger.info("Created operation type: %s (%s) by %s", op_type.code, op_type.label, current_user.email)
    return op_type


@router.put("/{code}", response_model=OperationTypeResponse)
def update_operation_type(
    code: str,
    request: OperationTypeUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_staff_user),
):
    """
    Update an operation type.

    is_system rows: consume_stages/is_qc are LOCKED — any attempt to
    change them (to a different value than currently stored) is rejected
    with 400. label/description/category/sort_order/is_active remain
    editable on system rows.

    Any row (system or custom): changing consume_stages while the type is
    referenced by an operation of a NON-terminal production order is
    rejected with 409 ("create a new type instead").
    """
    op_type = _get_or_404(db, code.upper())
    update_dict = request.model_dump(exclude_unset=True)

    if op_type.is_system:
        locked_fields = {"consume_stages", "is_qc"}
        for field_name in locked_fields:
            if field_name in update_dict:
                new_value = update_dict[field_name]
                current_value = list(op_type.consume_stages) if field_name == "consume_stages" else op_type.is_qc
                if new_value != current_value:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=(
                            f"'{field_name}' is locked on system operation type '{op_type.code}'. "
                            "Only label/description/category/sort_order/is_active are editable on system types."
                        ),
                    )

    if "consume_stages" in update_dict:
        new_stages = update_dict["consume_stages"]
        if list(new_stages) != list(op_type.consume_stages) and _referenced_by_non_terminal_po(db, op_type.code):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    f"Operation type '{op_type.code}' is referenced by an operation of a "
                    "non-terminal production order — create a new type instead of editing "
                    "consume_stages on one already in flight."
                ),
            )
        op_type.consume_stages = list(new_stages)

    if "label" in update_dict:
        op_type.label = update_dict["label"]
    if "description" in update_dict:
        op_type.description = update_dict["description"]
    if "category" in update_dict:
        op_type.category = update_dict["category"]
    if "sort_order" in update_dict:
        op_type.sort_order = update_dict["sort_order"]
    if "is_active" in update_dict:
        op_type.is_active = update_dict["is_active"]
    if "is_qc" in update_dict and not op_type.is_system:
        op_type.is_qc = update_dict["is_qc"]

    db.commit()
    db.refresh(op_type)

    logger.info("Updated operation type: %s by %s", op_type.code, current_user.email)
    return op_type


@router.post("/{code}/deactivate", response_model=OperationTypeResponse)
def deactivate_operation_type(
    code: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_staff_user),
):
    """
    Deactivate an operation type (soft delete). Both system and custom
    types support deactivate-only — there is no hard-delete endpoint.
    is_system rows are undeletable in the sense that they can never be
    hard-removed; deactivation just hides them from the active picker
    while historical resolution (load_operation_type_stage_map includes
    inactive rows) continues to work.
    """
    op_type = _get_or_404(db, code.upper())
    op_type.is_active = False
    db.commit()
    db.refresh(op_type)

    logger.info("Deactivated operation type: %s by %s", op_type.code, current_user.email)
    return op_type
