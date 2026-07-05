"""
Shared operation-type seed data/helper for tests, mirroring
migrations/versions/101_operation_types.py::SEED_OPERATION_TYPES verbatim.

Imported by BOTH test_operation_type_catalog.py (#876 PR-1's
predicate-equivalence proof) and test_operation_type_classifier.py (#876
PR-3's audit/classifier/CRUD tests) so a drift between the migration seed
and the tests fails loudly in ONE place rather than silently in whichever
file didn't get updated.

This is deliberately a SEPARATE literal from migration 101's own
SEED_OPERATION_TYPES — the migration keeps its own frozen copy on purpose
(see test_operation_type_catalog.py's predicate-equivalence tests), so
that a migration edit and a test-side edit must independently agree,
proving the migration's exact-code backfill is behavior-neutral. Only the
test-to-test duplication (this file vs. having two independent copies in
each test module) is being eliminated here.
"""
from app.models.manufacturing import OperationType

# code: (label, category, consume_stages, is_qc, sort_order)
SEED_OPERATION_TYPES = {
    "FDM_PRINT": ("FDM Print", "print", ["production", "any"], False, 10),
    "RESIN_PRINT": ("Resin Print", "print", ["production", "any"], False, 20),
    "ASSEMBLY": ("Assembly", "assembly", ["assembly", "production", "any"], False, 30),
    "QUALITY_CONTROL": ("Quality Control", "quality", ["any"], True, 40),
    "SUPPORT_REMOVAL": ("Support Removal / Cleanup", "finishing", ["any"], False, 50),
    "SANDING": ("Sanding", "finishing", ["any"], False, 60),
    "PAINTING": ("Painting", "finishing", ["finishing", "any"], False, 70),
    "PACK_SHIP": ("Pack / Ship", "shipping", ["shipping", "any"], False, 80),
    "GENERAL": ("Other (consumes at production)", "other", ["production", "any"], False, 90),
}


def seed_operation_types(db):
    """Idempotent INSERT-if-missing seed helper, mirroring migration 101
    step 2, for use directly against the test DB (no alembic run in
    tests). Consumes the module-level SEED_OPERATION_TYPES constant above
    — no separate inline copy of the seed data in either caller."""
    existing_codes = {code for (code,) in db.query(OperationType.code).all()}
    created = []
    for code, (label, category, stages, is_qc, sort_order) in SEED_OPERATION_TYPES.items():
        if code in existing_codes:
            continue
        row = OperationType(
            code=code,
            label=label,
            category=category,
            consume_stages=stages,
            is_qc=is_qc,
            is_system=True,
            is_active=True,
            sort_order=sort_order,
        )
        db.add(row)
        created.append(code)
    db.flush()
    return created
