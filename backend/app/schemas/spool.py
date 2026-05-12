"""
Material Spool Pydantic Schemas

Body schemas for spool CRUD endpoints. PATCH uses ``model_dump(exclude_unset=True)``
in the endpoint so callers can distinguish three intents:

- field absent from body          -> leave column unchanged
- field present with concrete value -> set column to value
- field present with explicit null -> clear column (location_id, notes only)

Without this, a UI sending ``location_id: null`` could not differentiate
"don't touch this" from "set this to NULL" — the bug Copilot flagged on
PR #603 where picking "No location" in AdminSpools failed to clear an
existing location.

Weight fields keep the existing project quirk: form / API field names use
the ``_kg`` suffix while values are GRAMS. The suffix matches the
``current_weight_kg`` DB column name; correcting the naming is out of
scope here.
"""
from typing import Optional
from datetime import datetime

from pydantic import BaseModel, Field


class SpoolCreate(BaseModel):
    """Body for ``POST /api/v1/spools/``."""
    spool_number: str = Field(..., min_length=1, description="Unique spool identifier")
    product_id: int = Field(..., description="Product/material ID")
    initial_weight_kg: float = Field(..., gt=0, description="Initial weight in grams")
    current_weight_kg: Optional[float] = Field(
        None, ge=0,
        description="Current weight in grams (defaults to initial_weight_kg)",
    )
    location_id: Optional[int] = Field(None, description="Storage location")
    supplier_lot_number: Optional[str] = Field(None, description="Supplier lot/batch number")
    expiry_date: Optional[datetime] = Field(None, description="Material expiry date")
    notes: Optional[str] = Field(None, description="Additional notes")


class SpoolUpdate(BaseModel):
    """Body for ``PATCH /api/v1/spools/{spool_id}``.

    The endpoint inspects ``model_dump(exclude_unset=True)`` so a caller can
    omit a field to leave it unchanged or send it explicitly as ``null`` to
    clear it (location_id, notes). Status is left under a truthy-check in
    the endpoint to preserve its prior behavior — sending ``"status": null``
    will NOT clear status, matching how the field worked before this refactor.
    """
    current_weight_g: Optional[float] = Field(
        None, ge=0,
        description="Update current weight in grams; requires ``reason``",
    )
    status: Optional[str] = Field(None, description="Update status")
    location_id: Optional[int] = Field(
        None,
        description="Update storage location; send explicit null to clear",
    )
    notes: Optional[str] = Field(
        None,
        description="Update notes; send explicit null or empty string to clear",
    )
    reason: Optional[str] = Field(
        None,
        description="Reason for weight adjustment (required when current_weight_g is set)",
    )
