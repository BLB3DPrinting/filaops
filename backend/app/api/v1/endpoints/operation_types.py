"""
Operation Type Catalog endpoints (#876 PR-1).

GET /operation-types -> list active types ordered by sort_order, feeding
the future routing-editor Type picker (#876 PR-4). Staff read (admin or
operator) only in this PR; admin CRUD (create/update/deactivate) + the
audit/classifier surfaces ship in #876 PR-3.
"""
from typing import List

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.manufacturing import OperationType
from app.models.user import User
from app.api.v1.deps import get_current_staff_user
from app.schemas.operation_type import OperationTypeResponse

# SEC-409: every route here is staff-only (admin or operator). A plain login is
# not enough, because anyone can self-register a customer account, and the
# operation-type catalog is shop configuration.
router = APIRouter(
    prefix="/operation-types",
    tags=["Operation Types"],
    dependencies=[Depends(get_current_staff_user)],
)


@router.get("", response_model=List[OperationTypeResponse])
def list_operation_types(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_staff_user),
):
    """List active operation types, ordered for picker display."""
    return (
        db.query(OperationType)
        .filter(OperationType.is_active.is_(True))
        .order_by(OperationType.sort_order, OperationType.code)
        .all()
    )
