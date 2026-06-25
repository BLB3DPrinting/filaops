"""Schema-foundation smoke tests for #784 (migration 095).

Exercises the new tables/columns end-to-end against the test DB's create_all
schema: defect_reasons (+ severity CHECK), qc_inspections.defect_reason_id /
waiver_user_id, qc_inspection_measurements (exact Numeric), qc_inspection_photos,
and ORM cascade delete of an inspection's children.
"""
from decimal import Decimal

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.models.defect_reason import DefectReason
from app.models.production_order import (
    QCInspection,
    QCInspectionMeasurement,
    QCInspectionPhoto,
)
from app.models.user import User


def _inspection(db, po_id, result="failed", **kw):
    insp = QCInspection(production_order_id=po_id, result=result, **kw)
    db.add(insp)
    db.flush()
    return insp


class TestDefectReason:
    def test_create_and_link_to_inspection(self, db, make_product, make_production_order):
        product = make_product()
        po = make_production_order(product_id=product.id)
        reason = DefectReason(
            code="layer_shift", name="Layer Shift",
            category="dimensional", severity="major",
        )
        db.add(reason)
        db.flush()

        insp = _inspection(db, po.id, result="failed", defect_reason_id=reason.id)
        assert insp.defect_reason.code == "layer_shift"
        assert insp.defect_reason.severity == "major"

    def test_severity_check_rejects_unknown_value(self, db):
        db.add(DefectReason(code="bogus", name="Bogus", severity="catastrophic"))
        with pytest.raises(IntegrityError):
            db.flush()
        db.rollback()

    def test_severity_is_optional(self, db):
        r = DefectReason(code="uncategorized", name="Uncategorized")
        db.add(r)
        db.flush()
        assert r.severity is None  # NULL passes the CHECK

    def test_code_is_unique(self, db):
        db.add(DefectReason(code="dup", name="First"))
        db.flush()
        db.add(DefectReason(code="dup", name="Second"))
        with pytest.raises(IntegrityError):
            db.flush()
        db.rollback()


class TestInspectionMeasurementsAndPhotos:
    def test_measurements_are_exact_numeric(self, db, make_product, make_production_order):
        product = make_product()
        po = make_production_order(product_id=product.id)
        insp = _inspection(db, po.id, result="passed")
        db.add(QCInspectionMeasurement(
            qc_inspection_id=insp.id, characteristic="bore_dia",
            nominal=Decimal("10.0000"), lower_limit=Decimal("9.9500"),
            upper_limit=Decimal("10.0500"), measured_value=Decimal("10.0123"),
            unit="mm",
        ))
        db.flush()
        # Numeric(18,4) — exact, no float drift
        assert insp.measurements[0].measured_value == Decimal("10.0123")
        assert insp.measurements[0].unit == "mm"

    def test_photo_attaches_to_inspection(self, db, make_product, make_production_order):
        product = make_product()
        po = make_production_order(product_id=product.id)
        insp = _inspection(db, po.id, result="failed")
        db.add(QCInspectionPhoto(
            qc_inspection_id=insp.id, file_name="defect.jpg",
            storage_type="local", mime_type="image/jpeg", caption="weld void",
        ))
        db.flush()
        assert len(insp.photos) == 1
        assert insp.photos[0].file_name == "defect.jpg"

    def test_orm_cascade_deletes_children(self, db, make_product, make_production_order):
        """ORM-side delete exercises relationship cascade='all, delete-orphan'."""
        product = make_product()
        po = make_production_order(product_id=product.id)
        insp = _inspection(db, po.id, result="failed")
        db.add(QCInspectionMeasurement(qc_inspection_id=insp.id, characteristic="h"))
        db.add(QCInspectionPhoto(qc_inspection_id=insp.id, file_name="p.jpg"))
        db.flush()
        insp_id = insp.id

        db.delete(insp)
        db.flush()
        assert db.query(QCInspectionMeasurement).filter_by(qc_inspection_id=insp_id).count() == 0
        assert db.query(QCInspectionPhoto).filter_by(qc_inspection_id=insp_id).count() == 0

    def test_db_level_cascade_deletes_children(self, db, make_product, make_production_order):
        """Raw-SQL delete bypasses the ORM cascade, so this exercises the
        migration's DB-side ON DELETE CASCADE — the constraint that protects
        integrity regardless of access path."""
        product = make_product()
        po = make_production_order(product_id=product.id)
        insp = _inspection(db, po.id, result="failed")
        db.add(QCInspectionMeasurement(qc_inspection_id=insp.id, characteristic="h"))
        db.add(QCInspectionPhoto(qc_inspection_id=insp.id, file_name="p.jpg"))
        db.flush()
        insp_id = insp.id

        db.execute(text("DELETE FROM qc_inspections WHERE id = :id"), {"id": insp_id})
        db.expire_all()
        assert db.query(QCInspectionMeasurement).filter_by(qc_inspection_id=insp_id).count() == 0
        assert db.query(QCInspectionPhoto).filter_by(qc_inspection_id=insp_id).count() == 0


class TestWaiverLink:
    def test_waiver_user_is_attributed(self, db, make_product, make_production_order):
        user = db.query(User).first()
        assert user is not None  # conftest seeds a default user
        product = make_product()
        po = make_production_order(product_id=product.id)
        insp = _inspection(db, po.id, result="waived", waiver_user_id=user.id)
        assert insp.waiver_user_id == user.id
        assert insp.waiver is not None
