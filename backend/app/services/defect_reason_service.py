"""Defect Reason service (#784) — manage the QC defect taxonomy.

Standalone functions over the DefectReason reference table (free-form category +
CHECK-constrained severity). Mirrors the scrap-reason service conventions. No
hard delete: defect reasons are referenced by immutable qc_inspections rows, so
they are deactivated (active=False), never removed.
"""
from typing import Optional

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models.defect_reason import DefectReason

# Mirrors the migration 095 / model CHECK on defect_reasons.severity.
VALID_SEVERITIES = ("minor", "major", "critical")


def _validate_severity(severity: Optional[str]) -> None:
    if severity is not None and severity not in VALID_SEVERITIES:
        raise HTTPException(
            status_code=400,
            detail=f"severity must be one of {VALID_SEVERITIES}, got '{severity}'",
        )


def get_defect_reasons(db: Session, include_inactive: bool = False) -> list[DefectReason]:
    """List defect reasons (active-only by default), ordered for dropdowns."""
    query = db.query(DefectReason)
    if not include_inactive:
        query = query.filter(DefectReason.active.is_(True))
    return query.order_by(DefectReason.sequence, DefectReason.name).all()


def get_defect_reason(db: Session, reason_id: int) -> DefectReason:
    """Fetch one defect reason or 404."""
    reason = db.query(DefectReason).filter(DefectReason.id == reason_id).first()
    if not reason:
        raise HTTPException(status_code=404, detail="Defect reason not found")
    return reason


def create_defect_reason(
    db: Session,
    *,
    code: str,
    name: str,
    description: Optional[str] = None,
    category: Optional[str] = None,
    severity: Optional[str] = None,
    sequence: int = 0,
) -> DefectReason:
    """Create a defect reason. Code must be unique."""
    _validate_severity(severity)
    existing = db.query(DefectReason).filter(DefectReason.code == code).first()
    if existing:
        raise HTTPException(
            status_code=400, detail=f"Defect reason with code '{code}' already exists"
        )
    reason = DefectReason(
        code=code,
        name=name,
        description=description,
        category=category,
        severity=severity,
        sequence=sequence,
        active=True,
    )
    db.add(reason)
    return reason


def update_defect_reason(
    db: Session,
    reason_id: int,
    *,
    name: Optional[str] = None,
    description: Optional[str] = None,
    category: Optional[str] = None,
    severity: Optional[str] = None,
    sequence: Optional[int] = None,
    active: Optional[bool] = None,
) -> DefectReason:
    """Patch a defect reason; pass active=False to deactivate."""
    reason = get_defect_reason(db, reason_id)
    if severity is not None:
        _validate_severity(severity)
        reason.severity = severity
    if name is not None:
        reason.name = name
    if description is not None:
        reason.description = description
    if category is not None:
        reason.category = category
    if sequence is not None:
        reason.sequence = sequence
    if active is not None:
        reason.active = active
    return reason
