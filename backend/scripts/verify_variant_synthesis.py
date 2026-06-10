"""Pre-merge correctness guard — read every existing variant through both
the legacy code path and the new registry; assert they resolve to the same
leaf component.

Run pre-merge against dev DB. CI runs against filaops_test fixtures.

Usage (from backend/ directory):
    DB_PASSWORD=Admin python scripts/verify_variant_synthesis.py
    DATABASE_URL=postgresql://... python scripts/verify_variant_synthesis.py
"""
import os
import sys

# Allow running from backend/ without installing the package.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.db.session import SessionLocal
from app.models import Product
from app.services import variant_service
from app.services.variant_axis import registry  # noqa: F401  triggers registration of all resolvers
from app.services.variant_axis.reader import read_axis_selections


def main() -> int:
    db = SessionLocal()
    try:
        templates = (
            db.query(Product).filter(Product.is_template.is_(True)).all()
        )
        print(f"Found {len(templates)} templates")
        mismatches = 0
        checked = 0
        skipped = 0
        for tmpl in templates:
            variants = (
                db.query(Product).filter(Product.parent_product_id == tmpl.id).all()
            )
            for v in variants:
                meta = v.variant_metadata or {}
                mat_type_id = meta.get("material_type_id")
                color_id = meta.get("color_id")
                if mat_type_id is None or color_id is None:
                    # No legacy shape → nothing to compare for this variant.
                    skipped += 1
                    continue
                try:
                    legacy = variant_service._find_material_product(
                        db, mat_type_id, color_id
                    )
                    meta_v2 = read_axis_selections(meta)
                    sel = meta_v2["axis_selections"].get("__legacy__")
                    if not sel:
                        print(f"  ! {v.sku}: synthesis returned no __legacy__ entry")
                        mismatches += 1
                        continue
                    via_registry = registry.get(sel["type"]).resolve_to_component(
                        db, value=sel["value"]
                    )
                    if legacy.id != via_registry.id:
                        print(
                            f"  ! {v.sku}: legacy={legacy.id} ({legacy.sku}) "
                            f"vs registry={via_registry.id} ({via_registry.sku})"
                        )
                        mismatches += 1
                    checked += 1
                except Exception as e:
                    print(f"  ! {v.sku}: error {type(e).__name__}: {e}")
                    mismatches += 1
        print(f"\nChecked {checked} variants; skipped {skipped}; {mismatches} mismatch(es).")
        return 0 if mismatches == 0 else 1
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
