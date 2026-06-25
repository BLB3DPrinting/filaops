"""Defect Reason schemas (#784) — QC defect taxonomy.

Mirrors the scrap-reason schema conventions, adding `category` (free-form) and
`severity` (CHECK-constrained minor|major|critical at the DB).
"""
from typing import List, Optional

from pydantic import BaseModel, Field


class DefectReasonBrief(BaseModel):
    """Compact defect-reason summary embedded in a QC inspection record."""
    id: int
    code: str
    name: str
    severity: Optional[str] = None

    class Config:
        from_attributes = True


class DefectReasonCreate(BaseModel):
    code: str = Field(..., max_length=50, description="Stable code, e.g. 'layer_shift'")
    name: str = Field(..., max_length=100, description="Display name")
    description: Optional[str] = None
    category: Optional[str] = Field(None, max_length=50, description="e.g. dimensional, cosmetic, functional")
    severity: Optional[str] = Field(None, description="minor | major | critical")
    sequence: int = Field(0, description="Ordering in dropdowns")


class DefectReasonUpdate(BaseModel):
    # max_length mirrors the ORM columns (100/50) so an over-long value is a
    # 422 at the boundary, not a 500 IntegrityError at commit.
    name: Optional[str] = Field(None, max_length=100)
    description: Optional[str] = None
    category: Optional[str] = Field(None, max_length=50)
    severity: Optional[str] = None
    sequence: Optional[int] = None
    active: Optional[bool] = None


class DefectReasonDetail(BaseModel):
    id: int
    code: str
    name: str
    description: Optional[str] = None
    category: Optional[str] = None
    severity: Optional[str] = None
    sequence: int = 0
    active: bool

    class Config:
        from_attributes = True


class DefectReasonsResponse(BaseModel):
    """Active defect reasons — codes for quick lookup + full details."""
    reasons: List[str]
    details: List[DefectReasonDetail]
