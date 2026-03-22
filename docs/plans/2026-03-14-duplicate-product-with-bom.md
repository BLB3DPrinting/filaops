# Duplicate Product with Inline BOM Swap — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Allow users to duplicate an existing product (including its active BOM) and swap BOM components inline, enabling fast creation of color variants.

**Architecture:** New `duplicate_item` service function clones a Product record with a new SKU/name, then uses the existing `copy_bom()` service to clone the active BOM. A new `DuplicateItemModal` frontend component shows the new product fields + BOM lines with inline component swapping before saving. The modal POSTs to a new `/api/v1/items/{id}/duplicate` endpoint.

**Tech Stack:** FastAPI + SQLAlchemy (backend), React + Tailwind (frontend), pytest (tests)

---

### Task 1: Backend — Add `duplicate_item` service function

**Files:**
- Modify: `backend/app/services/item_service.py`
- Modify: `backend/app/schemas/item.py`

**Step 1: Add the DuplicateItemRequest schema**

In `backend/app/schemas/item.py`, add at the bottom:

```python
class BOMLineOverride(BaseModel):
    """Override a BOM line's component during duplication."""
    original_component_id: int
    new_component_id: int


class DuplicateItemRequest(BaseModel):
    """Duplicate an existing item with a new SKU and name."""
    new_sku: str = Field(..., min_length=1, max_length=50, description="SKU for the new item")
    new_name: str = Field(..., min_length=1, max_length=255, description="Name for the new item")
    bom_line_overrides: List[BOMLineOverride] = Field(
        default_factory=list,
        description="Optional component swaps for BOM lines"
    )


class DuplicateItemResponse(BaseModel):
    """Response from duplicating an item."""
    id: int
    sku: str
    name: str
    has_bom: bool
    bom_id: Optional[int] = None
    message: str
```

**Step 2: Add the `duplicate_item` service function**

In `backend/app/services/item_service.py`, add:

```python
def duplicate_item(
    db: Session,
    source_item_id: int,
    *,
    new_sku: str,
    new_name: str,
    bom_line_overrides: list[dict] | None = None,
) -> dict:
    """
    Duplicate a product: clone all fields with a new SKU/name,
    copy the active BOM (if any), and apply component overrides.

    Returns dict with: id, sku, name, has_bom, bom_id, message
    """
    from app.models.bom import BOM, BOMLine
    from app.services.bom_management_service import recalculate_bom_cost

    source = get_item(db, source_item_id)

    # Validate new SKU uniqueness
    new_sku_upper = new_sku.upper().strip()
    check_unique_or_400(db, Product, "sku", new_sku_upper)

    # Fields to exclude from copy
    EXCLUDE_FIELDS = {
        "id", "sku", "name", "created_at", "updated_at",
        "woocommerce_product_id", "squarespace_product_id",
        "legacy_sku", "upc",
    }

    # Clone product fields
    clone_data = {}
    for col in Product.__table__.columns:
        if col.name not in EXCLUDE_FIELDS:
            clone_data[col.name] = getattr(source, col.name)

    clone_data["sku"] = new_sku_upper
    clone_data["name"] = new_name.strip()
    clone_data["has_bom"] = False  # Will be set True if BOM is copied

    new_item = Product(**clone_data)
    db.add(new_item)
    db.flush()  # Get the new item's ID

    # Copy active BOM if source has one
    bom_id = None
    active_bom = (
        db.query(BOM)
        .filter(BOM.product_id == source.id, BOM.active.is_(True))
        .first()
    )

    if active_bom:
        new_bom = BOM(
            product_id=new_item.id,
            code=f"{new_sku_upper}-BOM",
            name=f"BOM for {new_item.name}",
            version=1,
            revision=active_bom.revision,
            assembly_time_minutes=active_bom.assembly_time_minutes,
            effective_date=active_bom.effective_date,
            notes=f"Duplicated from {source.sku}",
            active=True,
        )
        db.add(new_bom)
        db.flush()

        # Build override lookup: original_component_id -> new_component_id
        override_map = {}
        if bom_line_overrides:
            for ov in bom_line_overrides:
                orig_id = ov.get("original_component_id") or ov.get("original_component_id")
                new_id = ov.get("new_component_id") or ov.get("new_component_id")
                if orig_id and new_id:
                    # Validate new component exists
                    if not db.query(Product).filter(Product.id == new_id).first():
                        raise HTTPException(
                            status_code=400,
                            detail=f"Override component ID {new_id} not found"
                        )
                    override_map[orig_id] = new_id

        # Copy lines with overrides
        source_lines = (
            db.query(BOMLine)
            .filter(BOMLine.bom_id == active_bom.id)
            .order_by(BOMLine.sequence)
            .all()
        )
        for line in source_lines:
            component_id = override_map.get(line.component_id, line.component_id)
            new_line = BOMLine(
                bom_id=new_bom.id,
                component_id=component_id,
                quantity=line.quantity,
                unit=line.unit,
                sequence=line.sequence,
                consume_stage=line.consume_stage,
                is_cost_only=line.is_cost_only,
                scrap_factor=line.scrap_factor,
                notes=line.notes,
            )
            db.add(new_line)

        db.flush()
        new_bom.total_cost = recalculate_bom_cost(new_bom, db)
        new_item.has_bom = True
        bom_id = new_bom.id

    db.commit()
    db.refresh(new_item)

    return {
        "id": new_item.id,
        "sku": new_item.sku,
        "name": new_item.name,
        "has_bom": new_item.has_bom,
        "bom_id": bom_id,
        "message": f"Duplicated from {source.sku}"
            + (f" with BOM ({len(source_lines)} lines)" if active_bom else " (no BOM)"),
    }
```

**Step 3: Commit**

```bash
git add backend/app/services/item_service.py backend/app/schemas/item.py
git commit -m "feat: add duplicate_item service and schemas (#415)"
```

---

### Task 2: Backend — Add `POST /items/{id}/duplicate` endpoint

**Files:**
- Modify: `backend/app/api/v1/endpoints/items.py`

**Step 1: Add the endpoint**

In `items.py`, after the create_item endpoint (~line 268), add:

```python
@router.post("/{item_id}/duplicate", status_code=201)
async def duplicate_item(
    item_id: int,
    request: DuplicateItemRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Duplicate an existing item with a new SKU and name.
    Copies the active BOM (if any) with optional component overrides.
    """
    result = item_service.duplicate_item(
        db,
        item_id,
        new_sku=request.new_sku,
        new_name=request.new_name,
        bom_line_overrides=[ov.model_dump() for ov in request.bom_line_overrides],
    )
    return result
```

Add `DuplicateItemRequest` to the import from `app.schemas.item`.

**Step 2: Commit**

```bash
git add backend/app/api/v1/endpoints/items.py
git commit -m "feat: add POST /items/{id}/duplicate endpoint (#415)"
```

---

### Task 3: Backend — Write tests

**Files:**
- Create: `backend/tests/test_duplicate_item.py`

**Step 1: Write tests**

```python
"""Tests for the duplicate item feature (#415)."""
import pytest
from app.services import item_service


class TestDuplicateItem:
    """Test item duplication service."""

    def test_duplicate_basic_item(self, db):
        """Duplicate an item without a BOM."""
        source = item_service.create_item(db, data={
            "sku": "DUP-SOURCE-001",
            "name": "Test Source Item",
            "item_type": "finished_good",
            "procurement_type": "make",
            "standard_cost": 10.00,
            "weight_oz": 5.5,
        })

        result = item_service.duplicate_item(
            db, source.id,
            new_sku="DUP-CLONE-001",
            new_name="Test Clone Item",
        )

        assert result["sku"] == "DUP-CLONE-001"
        assert result["name"] == "Test Clone Item"
        assert result["has_bom"] is False

        # Verify cloned fields
        clone = item_service.get_item(db, result["id"])
        assert clone.item_type == source.item_type
        assert clone.procurement_type == source.procurement_type
        assert float(clone.standard_cost) == float(source.standard_cost)
        assert float(clone.weight_oz) == float(source.weight_oz)

    def test_duplicate_item_with_bom(self, db):
        """Duplicate an item that has an active BOM — BOM should be copied."""
        from app.models.bom import BOM, BOMLine

        source = item_service.create_item(db, data={
            "sku": "DUP-BOM-SRC",
            "name": "Source With BOM",
            "item_type": "finished_good",
            "procurement_type": "make",
        })
        component = item_service.create_item(db, data={
            "sku": "DUP-COMP-001",
            "name": "Component A",
            "item_type": "component",
            "standard_cost": 5.00,
        })

        bom = BOM(product_id=source.id, code="DUP-BOM-SRC-BOM", name="Test BOM", active=True)
        db.add(bom)
        db.flush()
        line = BOMLine(bom_id=bom.id, component_id=component.id, quantity=2, unit="EA", sequence=1)
        db.add(line)
        source.has_bom = True
        db.commit()

        result = item_service.duplicate_item(
            db, source.id,
            new_sku="DUP-BOM-CLN",
            new_name="Clone With BOM",
        )

        assert result["has_bom"] is True
        assert result["bom_id"] is not None

        # Verify BOM was copied
        new_bom = db.query(BOM).filter(BOM.id == result["bom_id"]).first()
        assert new_bom is not None
        assert new_bom.product_id == result["id"]
        new_lines = db.query(BOMLine).filter(BOMLine.bom_id == new_bom.id).all()
        assert len(new_lines) == 1
        assert new_lines[0].component_id == component.id
        assert float(new_lines[0].quantity) == 2.0

    def test_duplicate_with_bom_override(self, db):
        """Duplicate with a component swap in the BOM."""
        from app.models.bom import BOM, BOMLine

        source = item_service.create_item(db, data={
            "sku": "DUP-OVR-SRC",
            "name": "Override Source",
            "item_type": "finished_good",
            "procurement_type": "make",
        })
        comp_red = item_service.create_item(db, data={
            "sku": "FIL-PLA-RED",
            "name": "PLA Red",
            "item_type": "supply",
            "standard_cost": 20.00,
        })
        comp_blue = item_service.create_item(db, data={
            "sku": "FIL-PLA-BLU",
            "name": "PLA Blue",
            "item_type": "supply",
            "standard_cost": 20.00,
        })

        bom = BOM(product_id=source.id, code="DUP-OVR-BOM", name="BOM", active=True)
        db.add(bom)
        db.flush()
        line = BOMLine(bom_id=bom.id, component_id=comp_red.id, quantity=500, unit="G", sequence=1)
        db.add(line)
        source.has_bom = True
        db.commit()

        result = item_service.duplicate_item(
            db, source.id,
            new_sku="DUP-OVR-CLN",
            new_name="Override Clone (Blue)",
            bom_line_overrides=[{
                "original_component_id": comp_red.id,
                "new_component_id": comp_blue.id,
            }],
        )

        # Verify the component was swapped
        new_lines = db.query(BOMLine).filter(BOMLine.bom_id == result["bom_id"]).all()
        assert len(new_lines) == 1
        assert new_lines[0].component_id == comp_blue.id

    def test_duplicate_rejects_duplicate_sku(self, db):
        """Duplicate should fail if new SKU already exists."""
        from fastapi import HTTPException

        source = item_service.create_item(db, data={
            "sku": "DUP-EXIST-SRC",
            "name": "Existing Source",
        })
        item_service.create_item(db, data={
            "sku": "DUP-EXIST-TAKEN",
            "name": "Already Taken",
        })

        with pytest.raises(HTTPException) as exc_info:
            item_service.duplicate_item(
                db, source.id,
                new_sku="DUP-EXIST-TAKEN",
                new_name="Should Fail",
            )
        assert exc_info.value.status_code == 400

    def test_duplicate_sku_uppercased(self, db):
        """SKU should be uppercased automatically."""
        source = item_service.create_item(db, data={
            "sku": "DUP-CASE-SRC",
            "name": "Case Source",
        })

        result = item_service.duplicate_item(
            db, source.id,
            new_sku="dup-case-cln",
            new_name="Case Clone",
        )
        assert result["sku"] == "DUP-CASE-CLN"
```

**Step 2: Run tests**

```bash
cd backend && python -m pytest tests/test_duplicate_item.py -v --tb=short -x
```

**Step 3: Commit**

```bash
git add backend/tests/test_duplicate_item.py
git commit -m "test: add tests for duplicate_item service (#415)"
```

---

### Task 4: Frontend — Create DuplicateItemModal component

**Files:**
- Create: `frontend/src/components/items/DuplicateItemModal.jsx`

This modal:
1. Shows new SKU (blank, required) and new Name (pre-filled with "Original (Copy)")
2. If the source item has a BOM, shows BOM lines with a "Swap" button on each
3. Clicking Swap opens a SearchableSelect to pick a replacement component
4. Submit sends POST /api/v1/items/{id}/duplicate with overrides

**Step 1: Create the component** (see implementation in code)

**Step 2: Commit**

```bash
git add frontend/src/components/items/DuplicateItemModal.jsx
git commit -m "feat: add DuplicateItemModal with inline BOM swap (#415)"
```

---

### Task 5: Frontend — Wire up Duplicate button

**Files:**
- Modify: `frontend/src/pages/admin/AdminItems.jsx`
- Modify: `frontend/src/components/items/ItemsTable.jsx`

**Step 1: Add state and handler in AdminItems.jsx**

- Add `duplicatingItem` state
- Add `handleDuplicateItem` callback
- Render `DuplicateItemModal`
- Pass `onDuplicateItem` prop to `ItemsTable`

**Step 2: Add Duplicate button in ItemsTable.jsx**

- Add `onDuplicateItem` to props
- Add a "Duplicate" button next to "Edit" in the actions column

**Step 3: Commit**

```bash
git add frontend/src/pages/admin/AdminItems.jsx frontend/src/components/items/ItemsTable.jsx
git commit -m "feat: wire up Duplicate button in items table (#415)"
```

---

### Task 6: End-to-end verification

**Step 1: Run backend tests**

```bash
cd backend && python -m pytest tests/test_duplicate_item.py -v --tb=short
```

**Step 2: Run full backend test suite**

```bash
cd backend && python -m pytest tests/ -x -q
```

**Step 3: Run frontend build check**

```bash
cd frontend && npx vite build
```

**Step 4: Final commit (if any fixes needed)**

---
---

# Variant Matrix — Design Plan

> **Evolution of Duplicate Item:** The duplicate feature (above) handles one-off cloning with BOM swaps. The Variant Matrix extends this into a structured template/variant system for managing N color/material variations from a single page.

## Context

BryanDawg (Discord, DAME role) has 15+ color variations per item and finds creating individual product entries unworkable. The current workaround — `duplicate_item()` with `bom_line_overrides` — works but creates N disconnected products with no shared management. This feature adds a variant matrix: one template SKU with shared BOM/routing structure, and child variant SKUs with swappable materials, individual cost/price/gcode, all managed from a single page. Inspired by MRPeasy's Matrix BOM.

**Core feature — no PRO dependencies per sacred rule.**

## Architecture Decision: Variants Are Real Products

Each variant is a real `Product` row with a `parent_product_id` FK pointing to the template. This means:

- Inventory, MRP, production orders, sales orders all work unchanged (they reference `product_id`)
- No downstream system changes needed
- The variant matrix is a management/UI layer on top of existing product infrastructure

## Phase 1: Schema + Backend Core (MVP)

### 1.1 Alembic Migration

Single migration file: `backend/migrations/versions/XXX_add_variant_matrix.py`

**Products table — 3 new columns:**

| Column | Type | Notes |
|--------|------|-------|
| `parent_product_id` | `INTEGER FK→products(id) ON DELETE SET NULL` | Nullable, indexed. Links variant → template |
| `is_template` | `BOOLEAN NOT NULL DEFAULT FALSE` | Denormalized flag, set true when first variant created |
| `variant_metadata` | `JSONB` | Nullable. Stores `{"material_type_id": X, "color_id": Y, "material_type_code": "PLA_BASIC", "color_code": "YEL"}` |

**RoutingOperationMaterial table — 1 new column:**

| Column | Type | Notes |
|--------|------|-------|
| `is_variable` | `BOOLEAN NOT NULL DEFAULT FALSE` | Marks which material lines get swapped per variant. Fixed lines (packaging, hardware) copy as-is. |

### 1.2 Model Changes

`backend/app/models/product.py` — Add columns + self-referential relationship:

```python
parent_product_id = Column(Integer, ForeignKey("products.id", ondelete="SET NULL"), nullable=True, index=True)
is_template = Column(Boolean, default=False, nullable=False)
variant_metadata = Column(JSON, nullable=True)

parent_product = relationship("Product", remote_side=[id], foreign_keys=[parent_product_id], backref="variants")
```

`backend/app/models/manufacturing.py` — Add to `RoutingOperationMaterial`:

```python
is_variable = Column(Boolean, default=False, nullable=False)
```

### 1.3 Schema Updates

`backend/app/schemas/item.py` — New schemas:

- `VariantCreateRequest`: `material_type_id`, `color_id`, optional `selling_price`, `gcode_file_path`
- `VariantBulkCreateRequest`: `selections: list[dict]` of `{material_type_id, color_id}`
- `VariantSyncRequest`: `variant_ids` (optional), `sync_routing_times`, `sync_prices` booleans
- `VariantListResponse`: `id`, `sku`, `name`, `material_type_code`, `color_code`, `color_hex`, `standard_cost`, `selling_price`, `on_hand_qty`, `active`
- Extend `ItemListResponse` / `ItemResponse` with: `parent_product_id`, `is_template`, `variant_count`

`backend/app/schemas/manufacturing.py` — Add `is_variable: bool = False` to routing operation material schemas.

### 1.4 Service Layer: `backend/app/services/variant_service.py` (new file)

**`create_variant(db, template_id, material_type_id, color_id, overrides=None) -> Product`**

- Validates template exists; auto-sets `is_template=True` on first variant
- Finds the material product for the chosen material+color combo
- Generates SKU: `{template.sku}-{material_type.code}-{color.code}` (truncated to 50 chars)
- Generates name: `{template.name} - {material_type.name} {color.name}`
- Reuses `duplicate_item()` internal logic (lines 1922-2154 of `item_service.py`):
  - Copies product fields (same `EXCLUDE_FIELDS`)
  - Copies BOM with overrides: swaps `component_id` on lines where the source component has `is_variable=True`
  - Copies routing with same overrides applied to `RoutingOperationMaterial`
  - Sets `parent_product_id`, `variant_metadata`, optional overrides
- Recalculates cost via `calculate_item_cost()`

**`bulk_create_variants(db, template_id, selections) -> list[dict]`**

- Iterates selections, calls `create_variant()` for each
- Skips combos where variant already exists (check by generated SKU)
- Returns `[{id, sku, name, status: "created"|"skipped"}]`

**`list_variants(db, template_id) -> list[dict]`**

- Queries `Product.parent_product_id == template_id`, ordered by SKU
- Enriches with on-hand quantity (batch inventory query)

**`get_variant_matrix(db, template_id) -> dict`**

- Returns `{template, variants, available_combos}`
- `available_combos` from `MaterialColor` table, filtered by the template's variable material's `material_type_id`
- Each combo shows `{material_type_id, color_id, codes, names, hex, already_exists, variant_id}`

**`delete_variant(db, variant_id)`**

- Validates product has `parent_product_id`
- Deletes product (BOM/routing cascade)
- Clears `is_template` on parent if no remaining variants

### 1.5 API Endpoints

Add to `backend/app/api/v1/endpoints/items.py`:

| Method | Path | Function |
|--------|------|----------|
| `GET` | `/{item_id}/variants` | `list_variants` |
| `GET` | `/{item_id}/variant-matrix` | `get_variant_matrix` |
| `POST` | `/{item_id}/variants` | `create_variant` |
| `POST` | `/{item_id}/variants/bulk` | `bulk_create_variants` |
| `DELETE` | `/{item_id}/variants/{variant_id}` | `delete_variant` |

### 1.6 Filter Variants from Main List

Modify `list_items()` in `item_service.py`: add parameter `exclude_variants: bool = True`. When true, add `Product.parent_product_id.is_(None)` to the query. Variants appear only on the template's variant matrix page, not cluttering the main item list.

### 1.7 Tests

`backend/tests/test_variant_service.py` (new):

- Test: create variant, verify SKU generation, BOM/routing copy with material swap
- Test: bulk create, skip existing
- Test: list variants returns enriched data
- Test: delete variant clears `is_template` when last variant removed
- Test: `list_items` excludes variants by default

## Phase 2: Frontend Variant Matrix UI

### 2.1 VariantMatrixTab Component

New: `frontend/src/components/items/VariantMatrixTab.jsx`

A tab on the item detail view showing:

- **Template summary:** SKU, name, which materials are marked as variable
- **MaterialColor grid:** Material types as rows, colors as columns. Cells are checkboxes (checked = variant exists). Grayed out = `MaterialColor` combo doesn't exist
- **"Create Selected Variants" button** → `POST /items/{id}/variants/bulk`
- **Variant list table:** SKU, color swatch (hex), standard_cost, selling_price, on_hand_qty. Inline edit for selling_price and gcode_file_path
- **Sync button** (Phase 3)

### 2.2 Template Indicator in Items Table

Modify `AdminItems.jsx` / `ItemsTable.jsx`:

- Show template badge + variant count on template rows
- Click navigates to variant matrix tab
- Variants hidden from main list (backend filter)

### 2.3 Mark Variable Materials in Routing Editor

Add `is_variable` toggle/checkbox on each material line in the routing operation material form. Checkbox label: "Variable (swap per variant)"

### 2.4 "Configure as Template" Action

On item detail view: button that sets `is_template=true`, prompts to mark variable materials, opens the Variants tab.

## Phase 3: Sync from Template

### 3.1 `sync_from_template()` in `variant_service.py`

For each variant (or specified subset):

- Get template's active routing/BOM and variant's active routing/BOM
- **Fixed material lines:** Update quantity, scrap_factor, notes from template
- **Variable material lines:** Keep variant's component_id (the swapped material), update quantity/scrap from template
- **Structural changes:** Add/remove operations to match template's structure
- **Optional:** Sync routing times, selling_price (opt-in flags)
- Recalculate cost on each variant

### 3.2 API Endpoint

| Method | Path | Function |
|--------|------|----------|
| `POST` | `/{item_id}/variants/sync` | `sync_variants` |

### 3.3 Frontend Sync Dialog

"Sync from Template" button with checkboxes: sync routing times, sync prices. Shows confirmation before applying.

## Phase 4: Migration Tool + Polish

### 4.1 Migration Script

`backend/scripts/migrate_duplicates_to_variants.py`

- Groups existing products by common SKU prefix
- Identifies template (shortest SKU or original)
- Sets `parent_product_id` on siblings, `is_template` on parent
- Populates `variant_metadata` from `material_type_id` + `color_id`
- Marks appropriate routing materials as `is_variable`
- **Dry-run by default**, `--commit` to write

### 4.2 "Adopt Existing Products" UI

Manual alternative: search for existing products to link as variants under a template.

### 4.3 Suggest Prices Integration

When running Suggest Prices on a template, offer "Apply to all variants" — calculates per variant using each variant's own `standard_cost × margin`.

### 4.4 `is_variable` on BOMLine (if needed)

Add `is_variable` to `bom_lines` table if routing-only marking proves insufficient for sync logic.

## Integration Impact Summary (Core)

| System | Changes Needed | Why |
|--------|---------------|-----|
| MRP | None | Variants are real products, exploded independently |
| Inventory | None | Each variant has its own inventory rows |
| Production Orders | None | POs reference variant's product_id directly |
| Sales/Purchase Orders | None | Order lines reference variant's product_id |
| Cost Rollup | None | `calculate_item_cost()` works per-product |
| Suggest Prices | Phase 4 | Add "propagate to variants" option |
| Item List | Phase 1 | Filter out variants by default |

## Critical Files

| File | Changes |
|------|---------|
| `backend/app/models/product.py` | Add `parent_product_id`, `is_template`, `variant_metadata`, relationship |
| `backend/app/models/manufacturing.py:261` | Add `is_variable` to `RoutingOperationMaterial` |
| `backend/app/services/item_service.py:1922` | Reuse `duplicate_item()` logic in variant creation |
| `backend/app/services/item_service.py:284` | Add variant exclusion to `list_items()` |
| `backend/app/services/item_service.py:1146` | `calculate_item_cost()` — call after variant creation |
| `backend/app/services/variant_service.py` | New — all variant CRUD + sync logic |
| `backend/app/schemas/item.py` | New variant schemas, extend item responses |
| `backend/app/schemas/manufacturing.py` | Add `is_variable` to routing material schemas |
| `backend/app/api/v1/endpoints/items.py` | New variant endpoints |
| `frontend/src/components/items/VariantMatrixTab.jsx` | New — variant matrix UI |
| `frontend/src/pages/admin/AdminItems.jsx` | Template indicators, variant filtering |

## Verification Plan

1. **Schema:** Run migration, verify columns exist with `\d products` and `\d routing_operation_materials`
2. **Create variant:** Mark a routing material as `is_variable`, create variant via API, verify SKU generated correctly, BOM/routing copied with material swapped
3. **Bulk create:** Select 3 MaterialColor combos, create all, verify 3 new products with correct parent link
4. **List items:** Verify variants hidden from main list, visible via `/items/{id}/variants`
5. **Cost:** Verify each variant's `standard_cost` reflects its specific material cost
6. **MRP:** Run MRP explosion on a variant — should use variant's own routing materials
7. **Production order:** Create PO for a variant — should work identically to any other product
8. **Sync:** Change template's BOM quantity, sync to variants, verify fixed materials updated, variable materials kept
9. **Tests:** `pytest tests/test_variant_service.py -v`

---
---

# PRO Considerations and Changes

> **Sacred Rule applies:** All variant matrix logic lives in Core. PRO modules consume the new fields — they never create or modify variant relationships.

## What Works Unchanged in PRO

The "variants are real products" decision means most PRO systems work without modification:

| PRO Component | Why It's Fine |
|---|---|
| **License server** | No product awareness |
| **FilaFarm** | Printer automation, no product model |
| **Cortex** | AI agents, no direct product dependency |
| **filaops-pro pricing routes** | Price levels apply per-product. Each variant has its own `selling_price`. Tier discounts calculated from variant's price. Works. |
| **filaops-pro accounting routes** | GL entries, journal entries reference product_id. Variants are products. Works. |
| **Portal cart + checkout** | Cart items reference `product_id` — variant is a product. Works. |
| **QuickBooks export** | Each variant is a product with its own cost/price. Exports individually. Works. |

## What Needs Changes

### PRO Phase 1: Portal Catalog Sync (ship with Core Phase 1)

**Problem:** The sync endpoint pushes all products flat. Without filtering, buyers see 15 separate Gummy Bears instead of 1 template with a color picker.

**Files to modify:**

| File | Change |
|------|--------|
| `portal-api/app/models/catalog.py` | Add `parent_product_id` (int, nullable), `is_template` (bool), `variant_metadata` (JSON) to `PortalProduct` |
| `portal-api/app/api/v1/sync.py` | Accept + store the 3 new fields in `SyncProduct` schema |
| `portal-api/app/api/v1/products.py` | Default filter `parent_product_id IS NULL` on product list. Templates show in catalog, variants don't. |
| `portal-api/app/api/v1/products.py` | New endpoint: `GET /products/{id}/variants` — returns variants for a template with `variant_metadata` for color swatches + material labels |

**Migration:** `portal-api/alembic/versions/XXXX_add_variant_fields.py` — adds 3 columns to `portal_products`.

**Sync schema update:**

```python
class SyncProduct(BaseModel):
    # ... existing fields ...
    parent_product_id: int | None = None
    is_template: bool = False
    variant_metadata: dict | None = None
```

**Variant list endpoint:**

```python
@router.get("/products/{product_id}/variants", response_model=ProductListResponse)
def get_product_variants(product_id: str, ...):
    """List variants for a template product."""
    product = ...  # fetch template
    variants = db.execute(
        select(PortalProduct).where(
            PortalProduct.tenant_id == tenant.tenant_id,
            PortalProduct.parent_product_id == product.core_product_id,
            PortalProduct.active == True,
        ).order_by(PortalProduct.name)
    ).scalars().all()
    # Apply buyer's discount to each variant
    ...
```

### PRO Phase 2: Portal Frontend (ship with Core Phase 2)

**Problem:** Template product detail pages need a variant selector (color swatches, material tabs) instead of a flat "Add to Cart".

**Files to modify/create:**

| File | Change |
|------|--------|
| `portal/src/lib/filaops/types.ts` | Extend `PortalProduct` with `parent_product_id`, `is_template`, `variant_count`, `variant_metadata` |
| `portal/src/components/catalog/product-card.tsx` | For templates: show "X colors available" badge using `variant_count` |
| `portal/src/pages/portal/ProductDetailPage.tsx` | For templates: fetch + render `VariantSelector` instead of direct "Add to Cart" |
| `portal/src/components/portal/variant-selector.tsx` | **New.** Color swatch grid + material type tabs. Selecting a variant updates price display + Add to Cart target. |

**VariantSelector component design:**

```
┌─────────────────────────────────────────────┐
│  Material: [PLA Basic] [PLA Silk] [PETG]    │  ← tabs from variant_metadata.material_type
│                                             │
│  Color:                                     │
│  [🟡] [🔴] [🔵] [🟢] [⚫] [⚪] [🟣] [🟤]  │  ← swatches from variant_metadata.color_hex
│                                             │
│  Selected: PLA Basic — Yellow               │
│  $14.84  ~~$19.79~~  -25%                   │  ← variant's customer_price
│                                             │
│  [+ Add to Cart]                            │  ← uses variant's product_id
└─────────────────────────────────────────────┘
```

- Fetches variants via `GET /products/{template_id}/variants`
- Groups by `variant_metadata.material_type_code` for tabs
- Renders color swatches with `variant_metadata.color_hex`
- On selection: updates `PriceDisplay` props + sets the cart target to the variant's `id`
- If template has no variants yet (admin hasn't created any), falls back to normal "Add to Cart" using template's own price

### PRO Phase 3: Shopify Sync (ship with Core Phase 3 or after)

**Problem:** Shopify natively supports product variants. Currently each Core product = one Shopify product. With variant matrix, we should map templates to Shopify products and Core variants to Shopify variants.

**Mapping:**

| Core | Shopify |
|------|---------|
| Template product | Shopify Product (title, description, images) |
| Variant products | Shopify Variants (price, inventory, option values) |
| `variant_metadata.color` | Variant option "Color" |
| `variant_metadata.material_type` | Variant option "Material" |

**Files to modify:**

| File | Change |
|------|--------|
| `filaops-pro/filaops_pro/routes/shopify.py` | Detect `is_template` — create one Shopify product with N variants instead of N products |
| `filaops-pro/filaops_pro/models/` | New: `ProShopifyVariantMap` — maps `core_variant_id → shopify_product_id, shopify_variant_id` |
| `filaops-pro/filaops_pro/services/shopify_sync.py` | Template sync logic: create/update Shopify product with variant options, map inventory per variant |

**Key behaviors:**

- **Create:** When syncing a template, create a Shopify product with option "Material" + "Color". Each Core variant → Shopify variant with its own price + inventory.
- **Update:** When Core variant's price/inventory changes, update the corresponding Shopify variant (not the whole product).
- **Delete:** When a Core variant is deleted, delete the Shopify variant. If template is deleted, delete the Shopify product.
- **Standalone products** (non-template, non-variant): Continue to sync as individual Shopify products (no behavior change).

**Migration:** `filaops-pro/migrations/XXXX_add_shopify_variant_map.py`

```python
class ProShopifyVariantMap(Base):
    __tablename__ = "pro_shopify_variant_map"
    id = Column(Integer, primary_key=True)
    core_product_id = Column(Integer, nullable=False, index=True)       # Core variant product.id
    shopify_product_id = Column(BigInteger, nullable=False)             # Shopify product ID (template level)
    shopify_variant_id = Column(BigInteger, nullable=False, unique=True) # Shopify variant ID
    created_at = Column(DateTime, server_default=func.now())
```

## PRO Phase Summary

| Phase | PRO Work | Depends On | Priority |
|-------|----------|------------|----------|
| **P1: Portal sync** | Migration + sync schema + filter + variant endpoint | Core Phase 1 schema | **Must ship together** |
| **P2: Portal frontend** | VariantSelector component + product card badge + detail page | Core Phase 2 frontend | **Must ship together** |
| **P3: Shopify** | Template→product mapping, variant map table, sync logic | Core Phase 3 sync or after | Can lag behind Core |
| **Deferred: Quoter** | Only if "quote from catalog template" is built | N/A | Not planned |
| **No change: QB export** | Variants are products, export works | N/A | N/A |
| **No change: Accounting** | GL entries per product_id, works | N/A | N/A |

## PRO Testing Checklist

- [ ] Sync a catalog with templates + variants → portal DB has correct `parent_product_id`, `is_template`, `variant_metadata`
- [ ] Portal product list excludes variants (only templates + standalone)
- [ ] Portal template detail page shows variant selector with correct swatches
- [ ] Selecting a variant updates price display with buyer's tier discount
- [ ] Adding a variant to cart uses variant's `product_id` (not template's)
- [ ] Account page discount badge still works (no regression)
- [ ] Shopify sync: template creates 1 Shopify product with N variants
- [ ] Shopify sync: standalone product still creates 1 Shopify product (no regression)
- [ ] Shopify sync: deleting Core variant removes Shopify variant
