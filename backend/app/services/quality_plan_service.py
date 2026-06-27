"""Quality Plan service (#784) — CRUD for per-product inspection plans.

Standalone functions, ``db: Session`` first (ARCHITECT-003 convention).
"""
from typing import Optional

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models.product import Product
from app.models.quality_plan import QualityPlan, QualityPlanCharacteristic


def _norm(value: Optional[str]) -> Optional[str]:
    """Trim to a real value or None — a blank/whitespace code must persist as
    NULL (so it follows the text-fallback path, not collide on the index as '')."""
    return (value or "").strip() or None


def _char_kwargs(c, idx: int) -> dict:
    seq = c.sequence
    return dict(
        code=_norm(c.code),
        characteristic=c.characteristic.strip(),
        characteristic_type=c.characteristic_type,
        nominal=c.nominal,
        lower_limit=c.lower_limit,
        upper_limit=c.upper_limit,
        unit=_norm(c.unit),
        acceptance_criteria=_norm(c.acceptance_criteria),
        sequence=seq if seq is not None else idx,
        severity=c.severity,
        routing_operation_id=c.routing_operation_id,
    )


def _validate_unique_codes(characteristics) -> None:
    """Reject duplicate (non-null) characteristic codes within one plan — they
    would collide on the partial-unique index and make the SPC key ambiguous."""
    codes = [code for code in (_norm(c.code) for c in characteristics) if code]
    dupes = sorted({x for x in codes if codes.count(x) > 1})
    if dupes:
        raise HTTPException(
            status_code=400,
            detail=f"duplicate characteristic code(s) within the plan: {', '.join(dupes)}",
        )


def _validate_product(db: Session, product_id: Optional[int]) -> None:
    if product_id is not None and not (
        db.query(Product.id).filter(Product.id == product_id).first()
    ):
        raise HTTPException(
            status_code=400, detail=f"product_id {product_id} does not exist"
        )


def list_quality_plans(
    db: Session, product_id: Optional[int] = None, include_inactive: bool = False
) -> list:
    q = db.query(QualityPlan)
    if product_id is not None:
        q = q.filter(QualityPlan.product_id == product_id)
    if not include_inactive:
        q = q.filter(QualityPlan.is_active.is_(True))
    return q.order_by(QualityPlan.code, QualityPlan.id).all()


def get_quality_plan(db: Session, plan_id: int) -> QualityPlan:
    plan = db.query(QualityPlan).filter(QualityPlan.id == plan_id).first()
    if plan is None:
        raise HTTPException(status_code=404, detail="Quality plan not found")
    return plan


def create_quality_plan(db: Session, data) -> QualityPlan:
    _validate_product(db, data.product_id)
    _validate_unique_codes(data.characteristics)
    plan = QualityPlan(
        product_id=data.product_id,
        code=data.code,
        name=data.name,
        version=data.version,
        revision=data.revision,
        is_active=data.is_active,
        is_template=data.is_template,
        effective_date=data.effective_date,
        notes=data.notes,
    )
    db.add(plan)
    db.flush()
    for idx, c in enumerate(data.characteristics):
        db.add(QualityPlanCharacteristic(quality_plan_id=plan.id, **_char_kwargs(c, idx)))
    db.commit()
    db.refresh(plan)
    return plan


def _validate_scope(is_template: bool, product_id: Optional[int]) -> None:
    if is_template and product_id is not None:
        raise HTTPException(
            status_code=400, detail="a template plan must not have a product_id"
        )
    if not is_template and product_id is None:
        raise HTTPException(
            status_code=400, detail="a product plan requires a product_id"
        )


def update_quality_plan(db: Session, plan_id: int, data) -> QualityPlan:
    plan = get_quality_plan(db, plan_id)
    # is_template is NOT NULL; an explicit `null` patch would otherwise be written
    # by model_dump() and fail at commit. Reject it up front for a clean 400.
    if "is_template" in data.model_fields_set and data.is_template is None:
        raise HTTPException(status_code=400, detail="is_template cannot be null")
    if "product_id" in data.model_fields_set:
        _validate_product(db, data.product_id)
    # Validate the RESULTING scope (the patch may change either field) before
    # mutating, so an invalid combination is a clean 400 rather than a 500 from
    # the DB CHECK at commit.
    new_is_template = (
        data.is_template if "is_template" in data.model_fields_set else plan.is_template
    )
    new_product_id = (
        data.product_id if "product_id" in data.model_fields_set else plan.product_id
    )
    _validate_scope(new_is_template, new_product_id)
    for key, value in data.model_dump(
        exclude_unset=True, exclude={"characteristics"}
    ).items():
        setattr(plan, key, value)
    # A provided characteristics list REPLACES the plan's characteristics
    # wholesale (delete-orphan removes the old ones on flush).
    if data.characteristics is not None:
        _validate_unique_codes(data.characteristics)
        plan.characteristics.clear()
        db.flush()
        for idx, c in enumerate(data.characteristics):
            db.add(QualityPlanCharacteristic(quality_plan_id=plan.id, **_char_kwargs(c, idx)))
    db.commit()
    db.refresh(plan)
    return plan


def deactivate_quality_plan(db: Session, plan_id: int) -> QualityPlan:
    plan = get_quality_plan(db, plan_id)
    plan.is_active = False
    db.commit()
    db.refresh(plan)
    return plan
