"""
Price Level Service

CRUD operations for price level management (Core feature).
Customer assignment is handled by PRO via pro_customer_price_levels.
"""
from typing import List

from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.price_level import PriceLevel
from app.schemas.price_level import PriceLevelCreate, PriceLevelUpdate


def list_price_levels(db: Session) -> List[PriceLevel]:
    return db.query(PriceLevel).order_by(PriceLevel.name).all()


def get_price_level(db: Session, price_level_id: int) -> PriceLevel:
    pl = db.query(PriceLevel).filter(PriceLevel.id == price_level_id).first()
    if not pl:
        raise HTTPException(status_code=404, detail="Price level not found")
    return pl


def create_price_level(db: Session, data: PriceLevelCreate) -> PriceLevel:
    existing = db.query(PriceLevel).filter(PriceLevel.name == data.name).first()
    if existing:
        raise HTTPException(status_code=400, detail=f"Price level '{data.name}' already exists")

    pl = PriceLevel(
        name=data.name,
        discount_percent=data.discount_percent,
        description=data.description,
        is_active=data.is_active,
    )
    db.add(pl)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=400, detail=f"Price level '{data.name}' already exists")
    db.refresh(pl)
    return pl


def update_price_level(db: Session, price_level_id: int, data: PriceLevelUpdate) -> PriceLevel:
    pl = get_price_level(db, price_level_id)
    fields = data.model_fields_set

    if "name" in fields and data.name is not None and data.name != pl.name:
        existing = db.query(PriceLevel).filter(PriceLevel.name == data.name).first()
        if existing:
            raise HTTPException(status_code=400, detail=f"Price level '{data.name}' already exists")
        pl.name = data.name

    if "discount_percent" in fields and data.discount_percent is not None:
        pl.discount_percent = data.discount_percent
    if "description" in fields:
        pl.description = data.description  # None clears the field intentionally
    if "is_active" in fields and data.is_active is not None:
        pl.is_active = data.is_active

    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=400, detail=f"Price level '{data.name}' already exists")
    db.refresh(pl)
    return pl


def deactivate_price_level(db: Session, price_level_id: int) -> PriceLevel:
    pl = get_price_level(db, price_level_id)
    pl.is_active = False
    db.commit()
    db.refresh(pl)
    return pl
