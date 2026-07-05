"""
Operation Type Catalog Pydantic Schemas (#876 PR-1).

Read-only response shape for GET /api/v1/operation-types. Admin CRUD
(create/update/deactivate/classify) ships later in #876 PR-3.
"""
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel


class OperationTypeResponse(BaseModel):
    """A single operation-type catalog row, for the future editor picker."""
    id: int
    code: str
    label: str
    description: Optional[str] = None
    category: Optional[str] = None
    consume_stages: List[str]
    is_qc: bool
    is_system: bool
    is_active: bool
    sort_order: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
