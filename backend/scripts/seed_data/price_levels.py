"""
Seed 4 price-level tiers (A/B/C/D).

Customer assignment to tiers is a PRO feature (pro_customer_price_levels
table lives in filaops-ecosystem). This module creates only the tier
definitions so Core's price-level admin UI has data to display.
"""
from decimal import Decimal
from typing import Any

from sqlalchemy.orm import Session

from app.models.price_level import PriceLevel

from scripts.seed_data import _time


TIERS = [
    ("Tier A", Decimal("0.00"), "Standard retail — no discount"),
    ("Tier B", Decimal("5.00"), "Volume buyers — 5% off"),
    ("Tier C", Decimal("10.00"), "Wholesale — 10% off"),
    ("Tier D", Decimal("15.00"), "Distributor — 15% off"),
]


def seed(db: Session, context: dict[str, Any]) -> None:
    now = _time.now()

    created = []
    for name, discount, description in TIERS:
        pl = PriceLevel(
            name=name,
            discount_percent=discount,
            description=description,
            is_active=True,
            created_at=now,
            updated_at=now,
        )
        db.add(pl)
        created.append(pl)
    db.flush()

    context["price_level_ids"] = {pl.name: pl.id for pl in created}
    print(f"[seed]   4 price-level tiers (A/B/C/D)")
