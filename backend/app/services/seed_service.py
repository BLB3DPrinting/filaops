"""
Seed Service — seeds example items and materials for first-run setup.

Extracted from setup.py endpoint (ARCHITECT-001 / #289).
Wraps script functions in a single atomic transaction (#290).
"""
from sqlalchemy.orm import Session

from app.logging_config import get_logger
from scripts.seed_example_data import seed_example_items, seed_materials

logger = get_logger(__name__)


def seed_example_data(db: Session) -> dict:
    """Seed example items and materials in a single atomic transaction.

    Uses a savepoint so that if materials fail, items are also rolled back
    — no partial state.

    Returns:
        Dict with keys: items_created, items_skipped, materials_created,
        colors_created, links_created, material_products_created
    """
    savepoint = db.begin_nested()
    try:
        items_created, items_skipped = seed_example_items(db)
        mt_created, colors_created, links_created, mat_products_created = seed_materials(db)
        savepoint.commit()
        db.commit()
    except Exception:
        savepoint.rollback()
        logger.error("Seed transaction failed, rolled back all changes", exc_info=True)
        raise

    logger.info(
        "Seed complete: %d items created, %d skipped, %d materials, %d colors, %d links",
        items_created, items_skipped, mt_created, colors_created, links_created,
    )
    return {
        "items_created": items_created,
        "items_skipped": items_skipped,
        "materials_created": mt_created,
        "colors_created": colors_created,
        "links_created": links_created,
        "material_products_created": mat_products_created,
    }
