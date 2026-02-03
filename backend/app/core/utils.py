"""
Core utilities shared across the application.

Created as part of ARCHITECT-003 (Service Layer Migration).
"""
from typing import TypeVar, Type

from fastapi import HTTPException
from sqlalchemy.orm import Session

T = TypeVar("T")


def get_or_404(
    db: Session,
    model: Type[T],
    id: int,
    detail: str | None = None,
) -> T:
    """
    Fetch a model instance by primary key or raise 404.

    Args:
        db: Database session
        model: SQLAlchemy model class
        id: Primary key value
        detail: Custom error message (defaults to "{ModelName} not found")

    Returns:
        The model instance

    Raises:
        HTTPException: 404 if not found
    """
    obj = db.query(model).filter(model.id == id).first()
    if not obj:
        raise HTTPException(
            status_code=404,
            detail=detail or f"{model.__name__} not found",
        )
    return obj


def check_unique_or_400(
    db: Session,
    model: Type[T],
    field_name: str,
    value: str,
    exclude_id: int | None = None,
    detail: str | None = None,
) -> None:
    """
    Check that a field value is unique for a model, or raise 400.

    Args:
        db: Database session
        model: SQLAlchemy model class
        field_name: Column name to check
        value: Value to check uniqueness of
        exclude_id: ID to exclude (for updates)
        detail: Custom error message

    Raises:
        HTTPException: 400 if duplicate found
    """
    column = getattr(model, field_name)
    query = db.query(model).filter(column == value)
    if exclude_id is not None:
        query = query.filter(model.id != exclude_id)
    if query.first():
        raise HTTPException(
            status_code=400,
            detail=detail or f"{model.__name__} with {field_name} '{value}' already exists",
        )
