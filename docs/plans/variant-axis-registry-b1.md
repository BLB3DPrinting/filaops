# Variant Axis Registry — B.1 Implementation Plan (Task-Level)

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Strategic context:** `docs/plans/variant-axis-generalization.md` §4 ("Workstream B.1") — read it first.

**Goal:** Generalize the variant axis from hardcoded `material_type + color` to a registry-dispatched resolver, with read-only back-compat synthesis of legacy variant_metadata. Zero migrations. Zero behavior changes for end users. Eight existing B0 tests stay green.

**Architecture:** New `app/services/variant_axis/` package with a Protocol-based registry. Two resolvers shipped: `MaterialColorResolver` (preserves today's behavior + lifts legacy metadata into the v2 shape on read) and `ComponentTemplateResolver` (resolves to active children of `parent_product_id` — no `item_type` branching). `variant_service` and `production_order_service` are refactored to delegate through the registry; their existing function signatures and behaviors stay intact.

**Tech stack:** Python 3.11 · FastAPI · SQLAlchemy · pytest · ruff

**Branch:** `feat/variant-axis-registry-b1`
**Worktree:** `C:\repos\filaops-variant-b1` (already cut from `main` at `e2cf0c8`)

---

## Pre-flight

Before starting Task 0, run a baseline check from the worktree root:

```bash
cd C:/repos/filaops-variant-b1/backend
python -m pytest tests/services/test_production_order_service.py -k swap_material_variant -q
python -m ruff check app/ --select E712
```

Expected: 8 passing B0 swap tests, ruff clean. If either fails, stop and triage — the baseline must be green before refactoring.

---

## Task 0: Skeleton + registry Protocol

**Files:**
- Create: `backend/app/services/variant_axis/__init__.py`
- Create: `backend/app/services/variant_axis/registry.py`
- Create: `backend/tests/services/variant_axis/__init__.py`
- Create: `backend/tests/services/variant_axis/test_registry.py`

- [ ] **Step 1: Write the failing test** (`backend/tests/services/variant_axis/test_registry.py`)

```python
"""Registry contract tests — no resolvers registered yet."""
import pytest
from app.services.variant_axis import registry


def test_register_and_get():
    class FakeResolver:
        type_name = "fake"
    registry.register(FakeResolver())
    try:
        got = registry.get("fake")
        assert got.type_name == "fake"
    finally:
        registry._REGISTRY.pop("fake", None)


def test_get_unknown_raises():
    with pytest.raises(KeyError):
        registry.get("nonexistent_axis_type")


def test_all_types_returns_registered_names():
    class A: type_name = "a_test"
    class B: type_name = "b_test"
    registry.register(A())
    registry.register(B())
    try:
        names = set(registry.all_types())
        assert {"a_test", "b_test"}.issubset(names)
    finally:
        registry._REGISTRY.pop("a_test", None)
        registry._REGISTRY.pop("b_test", None)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest backend/tests/services/variant_axis/test_registry.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.services.variant_axis'`

- [ ] **Step 3: Implement minimal registry** (`backend/app/services/variant_axis/__init__.py`)

```python
"""Variant axis package — registry + per-axis-type resolvers.

Resolvers register themselves on import. Add a new axis type by creating
a module here and importing it from this file's bottom.
"""
from app.services.variant_axis import registry  # noqa: F401

# Resolvers are registered by importing their modules. Order doesn't matter.
# (Imports added in later tasks: material_color, component_template.)
```

```python
# backend/app/services/variant_axis/registry.py
"""Axis-type resolver registry. Module-level dict, keyed by type_name."""
from typing import Protocol, runtime_checkable

_REGISTRY: dict[str, "AxisTypeResolver"] = {}


@runtime_checkable
class AxisTypeResolver(Protocol):
    type_name: str


def register(resolver: AxisTypeResolver) -> None:
    """Register a resolver under its type_name. Last-write-wins for tests."""
    _REGISTRY[resolver.type_name] = resolver


def get(type_name: str) -> AxisTypeResolver:
    """Lookup. Raises KeyError if type_name not registered."""
    return _REGISTRY[type_name]


def all_types() -> list[str]:
    """Return registered type_names in insertion order."""
    return list(_REGISTRY.keys())
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest backend/tests/services/variant_axis/test_registry.py -v`
Expected: 3 passes

- [ ] **Step 5: Commit**

```bash
cd C:/repos/filaops-variant-b1
git add backend/app/services/variant_axis/ backend/tests/services/variant_axis/
PRE_COMMIT_ALLOW_NO_CONFIG=1 git commit -m "feat(variant-axis): skeleton registry + Protocol contract

Co-authored-by: Claude <claude@anthropic.com>
Agent-Session: <session-id>"
```

---

## Task 1: AxisOption + Resolver Protocol surface

**Files:**
- Create: `backend/app/services/variant_axis/types.py`
- Modify: `backend/app/services/variant_axis/registry.py`
- Modify: `backend/tests/services/variant_axis/test_registry.py`

- [ ] **Step 1: Add Protocol contract test**

Append to `test_registry.py`:

```python
def test_protocol_requires_three_methods():
    """AxisTypeResolver must expose list_options, resolve_to_component, synthesize_legacy."""
    from app.services.variant_axis.registry import AxisTypeResolver
    expected = {"list_options", "resolve_to_component", "synthesize_legacy", "type_name"}
    assert expected.issubset(set(dir(AxisTypeResolver)))


def test_axis_option_dataclass_shape():
    from app.services.variant_axis.types import AxisOption
    opt = AxisOption(value={"k": 1}, label="L", preview_sku="X-1", preview_name="X 1")
    assert opt.value == {"k": 1}
    assert opt.label == "L"
```

- [ ] **Step 2: Run → expect FAIL** on import of `AxisOption` and on missing methods.

Run: `python -m pytest backend/tests/services/variant_axis/test_registry.py -v`

- [ ] **Step 3: Implement** (`backend/app/services/variant_axis/types.py`)

```python
"""Shared types for variant-axis resolvers."""
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class AxisOption:
    """One selectable option on a variant axis (one row in the matrix UI).

    `value` is the type-specific payload that gets stored verbatim in
    Product.variant_metadata.axis_selections[<id>].value and on
    SalesOrderLine.configuration. The resolver is the only code that
    interprets it.
    """
    value: dict[str, Any]
    label: str  # human-readable (e.g., "PLA Basic — Black", "M5 × 12mm")
    preview_sku: str | None = None  # for matrix preview cells
    preview_name: str | None = None  # for matrix preview cells
    extras: dict[str, Any] = field(default_factory=dict)  # axis-specific (e.g., color_hex)
```

Then update `registry.py`'s `AxisTypeResolver` Protocol to include the three methods:

```python
# Replace existing AxisTypeResolver Protocol in registry.py:
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sqlalchemy.orm import Session
    from app.models import Product
    from app.models.manufacturing import RoutingOperationMaterial
    from app.services.variant_axis.types import AxisOption


@runtime_checkable
class AxisTypeResolver(Protocol):
    type_name: str

    def list_options(
        self,
        db: "Session",
        *,
        template: "Product",
        routing_material: "RoutingOperationMaterial",
    ) -> list["AxisOption"]: ...

    def resolve_to_component(
        self, db: "Session", *, value: dict
    ) -> "Product": ...

    def synthesize_legacy(
        self, *, variant_metadata_legacy: dict
    ) -> dict | None: ...
```

- [ ] **Step 4: Run → PASS**

Run: `python -m pytest backend/tests/services/variant_axis/test_registry.py -v`

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/variant_axis/ backend/tests/services/variant_axis/
PRE_COMMIT_ALLOW_NO_CONFIG=1 git commit -m "feat(variant-axis): AxisOption + AxisTypeResolver Protocol surface"
```

---

## Task 2: MaterialColorResolver — list_options + resolve_to_component

**Files:**
- Create: `backend/app/services/variant_axis/material_color.py`
- Create: `backend/tests/services/variant_axis/test_material_color.py`
- Modify: `backend/app/services/variant_axis/__init__.py`

- [ ] **Step 1: Write failing test**

```python
"""MaterialColorResolver — list options + resolve to Product."""
from app.services.variant_axis import registry
from app.services.variant_axis.material_color import MaterialColorResolver


def test_resolver_registered_under_material_color():
    r = registry.get("material_color")
    assert isinstance(r, MaterialColorResolver)


def test_resolve_to_component_returns_active_supply_product(
    db, material_type_pla, color_black, supply_product_pla_black
):
    r = registry.get("material_color")
    p = r.resolve_to_component(
        db,
        value={"material_type_id": material_type_pla.id, "color_id": color_black.id},
    )
    assert p.id == supply_product_pla_black.id
    assert p.active is True


def test_resolve_to_component_404_when_no_active_match(db, material_type_pla, color_black):
    """Inactive supply product → 404 (matches legacy _find_material_product behavior)."""
    from fastapi import HTTPException
    import pytest
    r = registry.get("material_color")
    with pytest.raises(HTTPException) as exc:
        r.resolve_to_component(
            db, value={"material_type_id": 99_999, "color_id": 99_999}
        )
    assert exc.value.status_code == 404


def test_list_options_returns_one_per_materialcolor_row(
    db, fg004_template_with_material_color_axis
):
    r = registry.get("material_color")
    template = fg004_template_with_material_color_axis["template"]
    routing_material = fg004_template_with_material_color_axis["variable_material"]
    opts = r.list_options(db, template=template, routing_material=routing_material)
    assert len(opts) == fg004_template_with_material_color_axis["expected_combo_count"]
    for opt in opts:
        assert "material_type_id" in opt.value
        assert "color_id" in opt.value
        assert opt.label  # non-empty
```

(Note: fixtures `material_type_pla`, `color_black`, `supply_product_pla_black`, and `fg004_template_with_material_color_axis` need to be added to `backend/tests/conftest.py`. Cribbing from existing `_make_template_with_variant` in `test_production_order_service.py` is fine — keep them small.)

- [ ] **Step 2: Run → FAIL** (`ModuleNotFoundError` for `material_color`).

- [ ] **Step 3: Implement** (`backend/app/services/variant_axis/material_color.py`)

```python
"""MaterialColorResolver — preserves legacy material_type+color axis.

Lifted from variant_service._find_material_product + get_variant_matrix's
MaterialColor join logic. The resolver is the canonical source of truth;
variant_service delegates to it in Task 6.
"""
from typing import Any

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.logging_config import get_logger
from app.models import Product
from app.models.material import MaterialType, Color, MaterialColor
from app.models.manufacturing import RoutingOperationMaterial
from app.services.variant_axis import registry
from app.services.variant_axis.types import AxisOption

logger = get_logger(__name__)


class MaterialColorResolver:
    type_name = "material_color"

    def list_options(
        self,
        db: Session,
        *,
        template: Product,
        routing_material: RoutingOperationMaterial,
    ) -> list[AxisOption]:
        """Return MaterialColor combos available for the variable material's material_type."""
        component = (
            db.query(Product).filter(Product.id == routing_material.component_id).first()
        )
        if not component or component.material_type_id is None:
            return []

        rows = (
            db.query(MaterialColor, MaterialType, Color)
            .join(MaterialType, MaterialColor.material_type_id == MaterialType.id)
            .join(Color, MaterialColor.color_id == Color.id)
            .filter(MaterialColor.material_type_id == component.material_type_id)
            .all()
        )

        return [
            AxisOption(
                value={
                    "material_type_id": mt.id,
                    "color_id": c.id,
                    "material_type_code": mt.code,
                    "color_code": c.code,
                },
                label=f"{mt.name} — {c.name}",
                preview_sku=f"{template.sku}-{mt.code}-{c.code}"[:50],
                preview_name=f"{template.name} - {mt.name} {c.name}"[:255],
                extras={"color_hex": c.hex_code},
            )
            for (_mc, mt, c) in rows
        ]

    def resolve_to_component(self, db: Session, *, value: dict) -> Product:
        """Find the active supply Product for this material+color combo."""
        mat_type_id = value.get("material_type_id")
        color_id = value.get("color_id")
        if mat_type_id is None or color_id is None:
            raise HTTPException(
                status_code=400,
                detail=(
                    "material_color value missing material_type_id or color_id "
                    f"(got: {value!r})"
                ),
            )
        product = (
            db.query(Product)
            .filter(
                Product.material_type_id == mat_type_id,
                Product.color_id == color_id,
                Product.active.is_(True),
            )
            .first()
        )
        if not product:
            raise HTTPException(
                status_code=404,
                detail=(
                    f"No active product found for material_type_id={mat_type_id}, "
                    f"color_id={color_id}"
                ),
            )
        return product

    def synthesize_legacy(self, *, variant_metadata_legacy: dict) -> dict | None:
        """Lift legacy flat shape into v2 axis_selections.

        Implementation deferred to Task 3. Return None for now — Task 3 adds
        the actual lift, with a test that asserts a round-trip.
        """
        return None  # placeholder; Task 3 fills in


registry.register(MaterialColorResolver())
```

Update `__init__.py` to import the module:

```python
from app.services.variant_axis import registry  # noqa: F401
from app.services.variant_axis import material_color  # noqa: F401  registers
```

- [ ] **Step 4: Run → PASS** all four tests in `test_material_color.py`.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/variant_axis/material_color.py \
        backend/app/services/variant_axis/__init__.py \
        backend/tests/services/variant_axis/test_material_color.py \
        backend/tests/conftest.py
PRE_COMMIT_ALLOW_NO_CONFIG=1 git commit -m "feat(variant-axis): MaterialColorResolver list_options + resolve_to_component"
```

---

## Task 3: MaterialColorResolver — synthesize_legacy

**Files:**
- Modify: `backend/app/services/variant_axis/material_color.py`
- Modify: `backend/tests/services/variant_axis/test_material_color.py`

- [ ] **Step 1: Add failing test**

Append to `test_material_color.py`:

```python
def test_synthesize_legacy_lifts_flat_shape_to_v2():
    r = registry.get("material_color")
    legacy = {
        "material_type_id": 7,
        "color_id": 12,
        "material_type_code": "PLA",
        "color_code": "BLK",
    }
    out = r.synthesize_legacy(variant_metadata_legacy=legacy)
    assert out is not None
    assert out["schema_version"] == 2
    assert "axis_selections" in out
    sel = next(iter(out["axis_selections"].values()))
    assert sel["type"] == "material_color"
    assert sel["value"]["material_type_id"] == 7
    assert sel["value"]["color_id"] == 12


def test_synthesize_legacy_returns_none_for_already_v2():
    r = registry.get("material_color")
    v2 = {"schema_version": 2, "axis_selections": {}}
    assert r.synthesize_legacy(variant_metadata_legacy=v2) is None


def test_synthesize_legacy_returns_none_for_empty_or_missing_keys():
    r = registry.get("material_color")
    assert r.synthesize_legacy(variant_metadata_legacy={}) is None
    assert r.synthesize_legacy(variant_metadata_legacy={"material_type_id": 7}) is None
```

- [ ] **Step 2: Run → FAIL** (current impl returns `None`).

- [ ] **Step 3: Implement**

Replace `synthesize_legacy` in `material_color.py`:

```python
def synthesize_legacy(self, *, variant_metadata_legacy: dict) -> dict | None:
    """Lift legacy {material_type_id, color_id, ...} flat shape into v2 axis_selections.

    Returns None if the input is already v2 or doesn't carry both keys (the
    synthesis sentinel — caller treats absent as no-op, not as error).

    The synthesized record uses key '__legacy__' for the axis_selections entry
    because we don't know the original RoutingOperationMaterial.id. Read-side
    callers must accept this sentinel and not persist it back. Write-side code
    that creates v2 records uses the actual routing_operation_material_id.
    """
    if variant_metadata_legacy.get("schema_version") == 2:
        return None
    mat_type_id = variant_metadata_legacy.get("material_type_id")
    color_id = variant_metadata_legacy.get("color_id")
    if mat_type_id is None or color_id is None:
        return None
    return {
        "schema_version": 2,
        "axis_selections": {
            "__legacy__": {
                "type": "material_color",
                "label": "Color",
                "value": {
                    "material_type_id": mat_type_id,
                    "color_id": color_id,
                    "material_type_code": variant_metadata_legacy.get("material_type_code"),
                    "color_code": variant_metadata_legacy.get("color_code"),
                },
            }
        },
        "axis_count": 1,
    }
```

- [ ] **Step 4: Run → PASS** all three new tests + previous four still green.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/variant_axis/material_color.py \
        backend/tests/services/variant_axis/test_material_color.py
PRE_COMMIT_ALLOW_NO_CONFIG=1 git commit -m "feat(variant-axis): material_color synthesize_legacy lifts flat to v2"
```

---

## Task 4: ComponentTemplateResolver

**Files:**
- Create: `backend/app/services/variant_axis/component_template.py`
- Create: `backend/tests/services/variant_axis/test_component_template.py`
- Modify: `backend/app/services/variant_axis/__init__.py`

- [ ] **Step 1: Write failing test**

```python
"""ComponentTemplateResolver — resolves to active children of parent_product_id.

CRITICAL: must NOT branch on item_type. Same code path for manufactured,
component, and supply (purchased) templates. Resolver query is just
parent_product_id == template.id AND active.
"""
import pytest
from fastapi import HTTPException

from app.services.variant_axis import registry


def test_resolver_registered_under_component_template():
    from app.services.variant_axis.component_template import ComponentTemplateResolver
    r = registry.get("component_template")
    assert isinstance(r, ComponentTemplateResolver)


def test_list_options_returns_one_per_active_child(db, fg004_component_template_axis):
    """Variable BOM line has 9 active children → 9 options."""
    r = registry.get("component_template")
    fixt = fg004_component_template_axis
    opts = r.list_options(db, template=fixt["template"], routing_material=fixt["variable_material"])
    assert len(opts) == 9
    for opt in opts:
        assert "component_id" in opt.value
        assert opt.preview_sku  # non-empty


def test_list_options_excludes_inactive_children(db, fg004_component_template_axis_with_inactive):
    r = registry.get("component_template")
    fixt = fg004_component_template_axis_with_inactive
    opts = r.list_options(db, template=fixt["template"], routing_material=fixt["variable_material"])
    assert len(opts) == fixt["active_count"]
    returned_ids = {o.value["component_id"] for o in opts}
    assert fixt["inactive_child_id"] not in returned_ids


def test_resolve_to_component_returns_named_child(db, fg004_component_template_axis):
    r = registry.get("component_template")
    fixt = fg004_component_template_axis
    target = fixt["children"][3]
    p = r.resolve_to_component(db, value={"component_id": target.id})
    assert p.id == target.id


def test_resolve_to_component_404_for_unknown_id(db):
    r = registry.get("component_template")
    with pytest.raises(HTTPException) as exc:
        r.resolve_to_component(db, value={"component_id": 99_999_999})
    assert exc.value.status_code == 404


def test_resolve_to_component_400_for_missing_component_id(db):
    r = registry.get("component_template")
    with pytest.raises(HTTPException) as exc:
        r.resolve_to_component(db, value={})
    assert exc.value.status_code == 400


def test_synthesize_legacy_always_returns_none(db):
    """component_template has no legacy shape — only material_color did."""
    r = registry.get("component_template")
    assert r.synthesize_legacy(variant_metadata_legacy={"anything": 1}) is None


def test_resolver_does_not_branch_on_item_type(db, manufactured_template_with_children, supply_template_with_children):
    """Same resolver works for manufactured AND supply templates — Rule 1 from §2."""
    r = registry.get("component_template")
    for fixt in (manufactured_template_with_children, supply_template_with_children):
        opts = r.list_options(db, template=fixt["template"], routing_material=fixt["variable_material"])
        assert len(opts) == fixt["expected_count"]
```

(Add fixtures `fg004_component_template_axis`, `fg004_component_template_axis_with_inactive`, `manufactured_template_with_children`, `supply_template_with_children` to conftest. Each builds a template Product + N child Products linked via `parent_product_id`. Keep them ~15 lines each.)

- [ ] **Step 2: Run → FAIL** on `ModuleNotFoundError`.

- [ ] **Step 3: Implement** (`backend/app/services/variant_axis/component_template.py`)

```python
"""ComponentTemplateResolver — variants are children via parent_product_id.

RULE 1 from the strategic plan §2: this resolver MUST NOT branch on
item_type. The query is identical for manufactured, component, and
supply templates: parent_product_id == template.id AND active.
"""
from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models import Product
from app.models.manufacturing import RoutingOperationMaterial
from app.services.variant_axis import registry
from app.services.variant_axis.types import AxisOption


class ComponentTemplateResolver:
    type_name = "component_template"

    def list_options(
        self,
        db: Session,
        *,
        template: Product,  # unused for this resolver but part of Protocol
        routing_material: RoutingOperationMaterial,
    ) -> list[AxisOption]:
        """Return active children of the variable BOM line's component."""
        children = (
            db.query(Product)
            .filter(
                Product.parent_product_id == routing_material.component_id,
                Product.active.is_(True),
            )
            .order_by(Product.sku)
            .all()
        )
        return [
            AxisOption(
                value={
                    "component_id": c.id,
                    "component_sku": c.sku,
                    "component_name": c.name,
                },
                label=c.name,
                preview_sku=c.sku,
                preview_name=c.name,
            )
            for c in children
        ]

    def resolve_to_component(self, db: Session, *, value: dict) -> Product:
        cid = value.get("component_id")
        if cid is None:
            raise HTTPException(
                status_code=400,
                detail=f"component_template value missing component_id (got: {value!r})",
            )
        product = (
            db.query(Product)
            .filter(Product.id == cid, Product.active.is_(True))
            .first()
        )
        if not product:
            raise HTTPException(
                status_code=404,
                detail=f"No active product found with id={cid}",
            )
        return product

    def synthesize_legacy(self, *, variant_metadata_legacy: dict) -> dict | None:
        return None


registry.register(ComponentTemplateResolver())
```

Update `__init__.py`:

```python
from app.services.variant_axis import registry  # noqa: F401
from app.services.variant_axis import material_color  # noqa: F401  registers
from app.services.variant_axis import component_template  # noqa: F401  registers
```

- [ ] **Step 4: Run → PASS** all 8 tests.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/variant_axis/ backend/tests/services/variant_axis/test_component_template.py backend/tests/conftest.py
PRE_COMMIT_ALLOW_NO_CONFIG=1 git commit -m "feat(variant-axis): ComponentTemplateResolver — children of parent_product_id, no item_type branching"
```

---

## Task 5: read_axis_selections() helper + axis_count

**Files:**
- Create: `backend/app/services/variant_axis/reader.py`
- Create: `backend/tests/services/variant_axis/test_reader.py`

- [ ] **Step 1: Write failing test**

```python
"""read_axis_selections — single read path for variant_metadata.

Always returns a v2 dict, lifting legacy shape via material_color.synthesize_legacy.
Variants written before B.1 lack schema_version → treat absent as v1.
"""
from app.services.variant_axis.reader import read_axis_selections, compute_axis_count


def test_read_v2_passthrough_unchanged():
    v2 = {
        "schema_version": 2,
        "axis_selections": {
            "55": {"type": "material_color", "label": "Color", "value": {"material_type_id": 7, "color_id": 12}},
        },
    }
    out = read_axis_selections(v2)
    assert out == v2


def test_read_legacy_flat_shape_synthesizes_to_v2():
    legacy = {"material_type_id": 7, "color_id": 12, "material_type_code": "PLA", "color_code": "BLK"}
    out = read_axis_selections(legacy)
    assert out["schema_version"] == 2
    assert "axis_selections" in out


def test_read_absent_schema_version_treated_as_v1():
    """The strategic plan §3.4 sentence: 'absent treated as v1'."""
    legacy_no_version = {"material_type_id": 7, "color_id": 12}
    out = read_axis_selections(legacy_no_version)
    assert out["schema_version"] == 2


def test_read_none_or_empty_returns_empty_v2():
    assert read_axis_selections(None) == {"schema_version": 2, "axis_selections": {}, "axis_count": 0}
    assert read_axis_selections({}) == {"schema_version": 2, "axis_selections": {}, "axis_count": 0}


def test_compute_axis_count_flat():
    sel = {
        "schema_version": 2,
        "axis_selections": {
            "55": {"type": "material_color", "value": {}},
            "56": {"type": "component_template", "value": {}},
        },
    }
    assert compute_axis_count(sel) == 2


def test_compute_axis_count_recursive_2_deep():
    """Recursion: nested value carries another axis_selections."""
    sel = {
        "schema_version": 2,
        "axis_selections": {
            "55": {
                "type": "component_template",
                "value": {
                    "component_id": 100,
                    "axis_selections": {
                        "61": {"type": "material_color", "value": {"material_type_id": 1, "color_id": 1}},
                    },
                },
            },
        },
    }
    assert compute_axis_count(sel) == 2  # 1 outer + 1 inner
```

- [ ] **Step 2: Run → FAIL** on import.

- [ ] **Step 3: Implement** (`backend/app/services/variant_axis/reader.py`)

```python
"""Single read path for variant_metadata + configuration JSONB.

Lifts legacy flat shape into v2 axis_selections via the material_color
resolver's synthesizer. Never persists synthesized output (B.1 is read-only;
write-path crossover is B.2's responsibility).
"""
from typing import Any

from app.services.variant_axis import registry


def read_axis_selections(meta: dict | None) -> dict:
    """Return a v2 axis_selections dict.

    - v2 input → passthrough
    - legacy material+color flat shape → synthesized to v2 in memory
    - None / empty / unknown → empty v2 envelope
    """
    if not meta:
        return {"schema_version": 2, "axis_selections": {}, "axis_count": 0}
    if meta.get("schema_version") == 2:
        return meta
    # Try material_color synthesis (the only legacy shape we know about)
    try:
        mc = registry.get("material_color")
    except KeyError:
        return {"schema_version": 2, "axis_selections": {}, "axis_count": 0}
    synthesized = mc.synthesize_legacy(variant_metadata_legacy=meta)
    if synthesized is not None:
        return synthesized
    return {"schema_version": 2, "axis_selections": {}, "axis_count": 0}


def compute_axis_count(meta_v2: dict) -> int:
    """Count axes across full recursion depth (per locked-decision: cap counts depth-aware)."""
    selections = meta_v2.get("axis_selections", {})
    total = 0
    for sel in selections.values():
        total += 1
        nested = (sel.get("value") or {}).get("axis_selections")
        if isinstance(nested, dict):
            total += compute_axis_count({"axis_selections": nested})
    return total
```

- [ ] **Step 4: Run → PASS** all 6 tests.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/variant_axis/reader.py \
        backend/tests/services/variant_axis/test_reader.py
PRE_COMMIT_ALLOW_NO_CONFIG=1 git commit -m "feat(variant-axis): read_axis_selections + recursion-aware compute_axis_count"
```

---

## Task 6: Axis cap enforcement

**Files:**
- Modify: `backend/app/services/variant_axis/reader.py`
- Modify: `backend/tests/services/variant_axis/test_reader.py`

- [ ] **Step 1: Add failing test**

Append to `test_reader.py`:

```python
import pytest
from fastapi import HTTPException
from app.services.variant_axis.reader import enforce_axis_cap

SOFT = 4
HARD = 6


def _build_n_axis_meta(n: int) -> dict:
    return {
        "schema_version": 2,
        "axis_selections": {
            str(i): {"type": "material_color", "label": "x", "value": {"material_type_id": 1, "color_id": i}}
            for i in range(n)
        },
    }


def test_enforce_axis_cap_under_soft_no_warning(caplog):
    enforce_axis_cap(_build_n_axis_meta(2))
    assert not [r for r in caplog.records if r.levelname == "WARNING"]


def test_enforce_axis_cap_at_soft_warns(caplog):
    import logging
    with caplog.at_level(logging.WARNING):
        enforce_axis_cap(_build_n_axis_meta(SOFT + 1))
    assert any("axis count" in r.message.lower() for r in caplog.records)


def test_enforce_axis_cap_above_hard_raises():
    with pytest.raises(HTTPException) as exc:
        enforce_axis_cap(_build_n_axis_meta(HARD + 1))
    assert exc.value.status_code == 400
    assert "axis cap" in exc.value.detail.lower()
```

- [ ] **Step 2: Run → FAIL** on import.

- [ ] **Step 3: Implement**

Append to `reader.py`:

```python
from fastapi import HTTPException

from app.logging_config import get_logger

logger = get_logger(__name__)

AXIS_CAP_SOFT = 4
AXIS_CAP_HARD = 6


def enforce_axis_cap(meta_v2: dict) -> int:
    """Walk axis_selections, count depth-aware, warn at soft cap, raise 400 above hard.

    Returns the computed axis_count for callers that want to surface it
    (e.g. /variant-matrix response → axis_count_warning: true when ≥ soft).
    """
    n = compute_axis_count(meta_v2)
    if n > AXIS_CAP_HARD:
        raise HTTPException(
            status_code=400,
            detail=(
                f"axis cap exceeded: {n} axes across recursion depth "
                f"(hard cap = {AXIS_CAP_HARD})"
            ),
        )
    if n > AXIS_CAP_SOFT:
        logger.warning("variant axis count %d exceeds soft cap %d", n, AXIS_CAP_SOFT)
    return n
```

- [ ] **Step 4: Run → PASS**.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/variant_axis/reader.py backend/tests/services/variant_axis/test_reader.py
PRE_COMMIT_ALLOW_NO_CONFIG=1 git commit -m "feat(variant-axis): soft (4) + hard (6) axis cap enforcement"
```

---

## Task 7: Refactor variant_service._find_material_product → delegate to registry

**Files:**
- Modify: `backend/app/services/variant_service.py`
- Test: `backend/tests/test_variant_service.py` (existing — must stay green)

- [ ] **Step 1: Run baseline**

```bash
python -m pytest backend/tests/test_variant_service.py -q
```

Expected: all green. If anything fails, stop and triage.

- [ ] **Step 2: Refactor `_find_material_product` to delegate**

Replace lines 28–44 of `variant_service.py`:

```python
def _find_material_product(db: Session, material_type_id: int, color_id: int) -> Product:
    """Find the supply Product for a material+color combo.

    Now a thin shim over MaterialColorResolver.resolve_to_component to keep
    the existing call sites in this module working. The resolver is the
    canonical source.
    """
    from app.services.variant_axis import registry
    return registry.get("material_color").resolve_to_component(
        db, value={"material_type_id": material_type_id, "color_id": color_id}
    )
```

- [ ] **Step 3: Run existing tests**

```bash
python -m pytest backend/tests/test_variant_service.py -q
python -m pytest backend/tests/services/variant_axis/ -q
```

Expected: all green. The `_find_material_product` shim returns the same product the legacy code did; behavior unchanged.

- [ ] **Step 4: Verify no behavior change in `create_variant`**

Manual smoke (or add an explicit regression test if one isn't already there):

```bash
python -m pytest backend/tests/test_variant_service.py -k create_variant -v
```

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/variant_service.py
PRE_COMMIT_ALLOW_NO_CONFIG=1 git commit -m "refactor(variant-service): _find_material_product delegates to MaterialColorResolver"
```

---

## Task 8: Refactor sync_routing_to_variants for per-line axis resolution

**Files:**
- Modify: `backend/app/services/variant_service.py` (lines 407–545 region)
- Modify: `backend/tests/test_variant_service.py` (or add a new mixed-axis test file)

- [ ] **Step 1: Add failing mixed-axis test**

```python
# backend/tests/test_variant_service_mixed_axis.py
"""Mixed-axis sync_routing_to_variants — Rule 3 from strategic plan §2.

A template with 1 variable material_color line + 1 variable component_template
line + 2 fixed lines must produce variants where:
- the material_color line's component is swapped to the variant's material+color target
- the component_template line's component is swapped to the variant's chosen child
- the 2 fixed lines are preserved verbatim
"""
import pytest
from app.services import variant_service


def test_sync_routing_to_variants_resolves_each_axis_independently(
    db, mixed_axis_template_with_one_variant
):
    fixt = mixed_axis_template_with_one_variant
    template = fixt["template"]
    variant = fixt["variant"]
    expected_color_target_id = fixt["expected_color_target_id"]
    expected_component_target_id = fixt["expected_component_target_id"]
    fixed_component_ids = fixt["fixed_component_ids"]  # list of 2

    variant_service.sync_routing_to_variants(db, template.id)

    db.refresh(variant)
    routing = variant.routings[0]
    materials = [m for op in routing.operations for m in op.materials]
    component_ids = sorted(m.component_id for m in materials)

    assert expected_color_target_id in component_ids
    assert expected_component_target_id in component_ids
    for fid in fixed_component_ids:
        assert fid in component_ids
```

(Fixture `mixed_axis_template_with_one_variant` is the most complex one in this plan: build a template with 4 BOM lines (2 variable + 2 fixed), one variant whose `variant_metadata.axis_selections` carries both axis types, then run the test.)

- [ ] **Step 2: Run → FAIL** (current code uses flat `mat_type_id, color_id_meta` lookup which only resolves the material_color axis).

- [ ] **Step 3: Refactor `sync_routing_to_variants`**

Replace the per-variant resolution block (currently around lines 454–490) with:

```python
for variant in variants:
    savepoint = db.begin_nested()
    try:
        # Resolve each variable line's target via the registry. Falls back to
        # legacy flat shape via read_axis_selections() back-compat.
        from app.services.variant_axis import registry
        from app.services.variant_axis.reader import read_axis_selections

        meta_v2 = read_axis_selections(variant.variant_metadata)
        axis_selections = meta_v2.get("axis_selections", {})

        # Build per-routing-material-id -> resolved Product map
        resolved_per_line: dict[int, Product] = {}
        for sel_key, sel in axis_selections.items():
            try:
                resolver = registry.get(sel["type"])
                target = resolver.resolve_to_component(db, value=sel["value"])
            except (KeyError, HTTPException) as e:
                logger.warning(
                    "Variant %s: cannot resolve axis %s (type=%s): %s",
                    variant.sku, sel_key, sel.get("type"), e,
                )
                continue
            # sel_key is either a routing_operation_material_id (int as str) or "__legacy__"
            if sel_key == "__legacy__":
                # Apply to all is_variable lines (legacy single-axis behavior)
                resolved_per_line["__legacy_target__"] = target
            else:
                try:
                    resolved_per_line[int(sel_key)] = target
                except ValueError:
                    pass

        # Get or create variant routing (unchanged)
        variant_routing = (
            db.query(Routing)
            .filter(Routing.product_id == variant.id, Routing.is_active.is_(True))
            .first()
        )
        if not variant_routing:
            variant_routing = Routing(
                product_id=variant.id,
                name=f"Routing for {variant.name}"[:200],
                code=f"RTG-{variant.sku}"[:50],
                version=1,
                revision="1.0",
                is_active=True,
            )
            db.add(variant_routing)
            db.flush()
        variant_routing.operations = []
        db.flush()

        for t_op in template_ops:
            new_op = RoutingOperation(
                routing_id=variant_routing.id,
                sequence=t_op.sequence,
                operation_code=t_op.operation_code,
                operation_name=t_op.operation_name,
                description=t_op.description,
                work_center_id=t_op.work_center_id,
                setup_time_minutes=t_op.setup_time_minutes,
                run_time_minutes=t_op.run_time_minutes,
                wait_time_minutes=t_op.wait_time_minutes,
                move_time_minutes=t_op.move_time_minutes,
                runtime_source=t_op.runtime_source,
                units_per_cycle=t_op.units_per_cycle,
                scrap_rate_percent=t_op.scrap_rate_percent,
                labor_rate_override=t_op.labor_rate_override,
                machine_rate_override=t_op.machine_rate_override,
                is_active=t_op.is_active,
            )
            db.add(new_op)
            db.flush()

            for t_mat in op_materials[t_op.id]:
                # Per-line resolution: prefer keyed match, fall back to legacy
                target = resolved_per_line.get(t_mat.id) or resolved_per_line.get("__legacy_target__")
                if t_mat.is_variable and not target:
                    logger.warning(
                        "Variable material on op %s (component_id=%s) has no resolved target for variant %s",
                        t_op.operation_code, t_mat.component_id, variant.sku,
                    )
                component_id = (
                    target.id
                    if t_mat.is_variable and target
                    else t_mat.component_id
                )
                new_mat = RoutingOperationMaterial(
                    routing_operation_id=new_op.id,
                    component_id=component_id,
                    quantity=t_mat.quantity,
                    quantity_per=t_mat.quantity_per,
                    unit=t_mat.unit,
                    scrap_factor=t_mat.scrap_factor,
                    is_cost_only=t_mat.is_cost_only,
                    is_optional=t_mat.is_optional,
                    is_variable=t_mat.is_variable,
                    notes=t_mat.notes,
                )
                db.add(new_mat)

        db.flush()
        recalculate_routing_totals(variant_routing, db)
        # ... rest unchanged
```

- [ ] **Step 4: Run all variant_service tests + new mixed-axis test**

```bash
python -m pytest backend/tests/test_variant_service.py backend/tests/test_variant_service_mixed_axis.py -v
```

Expected: pre-existing tests stay green (back-compat via `__legacy_target__`); new mixed-axis test passes.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/variant_service.py backend/tests/test_variant_service_mixed_axis.py backend/tests/conftest.py
PRE_COMMIT_ALLOW_NO_CONFIG=1 git commit -m "refactor(variant-service): per-line axis resolution in sync_routing_to_variants"
```

---

## Task 9: Refactor swap_material_variant child-of-current via registry

**Files:**
- Modify: `backend/app/services/production_order_service.py` (around line 1716–1734)
- Test: `backend/tests/services/test_production_order_service.py` (8 existing B0 tests — refactor guard)

- [ ] **Step 1: Run baseline B0 tests**

```bash
python -m pytest backend/tests/services/test_production_order_service.py -k swap_material_variant -v
```

Expected: 8 passing.

- [ ] **Step 2: Refactor the child-of-current check**

Replace lines 1716–1733 of `production_order_service.py`:

```python
new_component = db.query(Product).filter(Product.id == new_component_id).first()
if not new_component:
    raise HTTPException(status_code=404, detail=f"Product {new_component_id} not found")
if not new_component.active:
    raise HTTPException(status_code=400, detail="Target component is not active")

is_no_op = new_component_id == mat.component_id

if not is_no_op:
    # Delegate child-of-current check to ComponentTemplateResolver.
    # The resolver's list_options(parent=current_component) is the canonical
    # set of valid swap targets — we just check membership.
    from app.services.variant_axis import registry

    resolver = registry.get("component_template")
    # A "fake" routing_material wrapper exposing component_id is enough for
    # list_options' filter — same shape as a real RoutingOperationMaterial.
    class _MaterialStub:
        component_id = mat.component_id

    valid_target_ids = {
        opt.value["component_id"]
        for opt in resolver.list_options(
            db,
            template=new_component,  # unused by component_template resolver
            routing_material=_MaterialStub(),  # type: ignore[arg-type]
        )
    }
    if new_component_id not in valid_target_ids:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Target {new_component.sku} is not a variant of current component "
                f"{mat.component_id} (expected parent_product_id={mat.component_id})"
            ),
        )
```

- [ ] **Step 3: Run B0 tests**

```bash
python -m pytest backend/tests/services/test_production_order_service.py -k swap_material_variant -v
```

Expected: all 8 still passing. Behavior unchanged; only the implementation moved.

- [ ] **Step 4: Run full pytest sweep**

```bash
python -m pytest backend/tests/services/ -q
python -m ruff check app/ --select E712
```

Expected: green, ruff clean.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/production_order_service.py
PRE_COMMIT_ALLOW_NO_CONFIG=1 git commit -m "refactor(production-order): swap_material_variant delegates child-of-current check to registry"
```

---

## Task 10: Recursive 2-deep test + 6-deep perf canary (env-gated)

**Files:**
- Modify: `backend/tests/services/variant_axis/test_component_template.py`

- [ ] **Step 1: Add failing recursive resolve test**

```python
def test_resolve_recursive_2_deep(db, fg_with_variable_manuf_component_with_variable_material):
    """FG → variable manuf component → has its own variable material.

    Customer config: outer chooses ball variant; inner chooses ball's filament finish.
    Resolver walks both axes.
    """
    from app.services.variant_axis import registry
    from app.services.variant_axis.reader import read_axis_selections

    fixt = fg_with_variable_manuf_component_with_variable_material
    cfg = {
        "schema_version": 2,
        "axis_selections": {
            str(fixt["outer_routing_material_id"]): {
                "type": "component_template",
                "value": {
                    "component_id": fixt["chosen_ball_id"],
                    "axis_selections": {
                        str(fixt["inner_routing_material_id"]): {
                            "type": "material_color",
                            "value": {
                                "material_type_id": fixt["chosen_finish_mt_id"],
                                "color_id": fixt["chosen_finish_color_id"],
                            },
                        },
                    },
                },
            },
        },
    }

    # Outer axis resolves to chosen ball
    outer_resolver = registry.get("component_template")
    outer = outer_resolver.resolve_to_component(
        db, value=cfg["axis_selections"][str(fixt["outer_routing_material_id"])]["value"]
    )
    assert outer.id == fixt["chosen_ball_id"]

    # Inner axis resolves to chosen finish supply product
    inner_sel = cfg["axis_selections"][str(fixt["outer_routing_material_id"])]["value"]["axis_selections"]
    inner_axis = inner_sel[str(fixt["inner_routing_material_id"])]
    inner_resolver = registry.get(inner_axis["type"])
    inner = inner_resolver.resolve_to_component(db, value=inner_axis["value"])
    assert inner.material_type_id == fixt["chosen_finish_mt_id"]
    assert inner.color_id == fixt["chosen_finish_color_id"]


def test_perf_canary_6_deep_recursive_resolve(db, deeply_nested_template_6_axes, caplog):
    """Quadratic-blowup canary. Log-only by default; env-var gates a hard threshold.

    Per strategic plan §4 + §8 mitigation: VARIANT_AXIS_PERF_THRESHOLD_MS unset
    in CI = log-only (no flake). Local benchmarks set the env to enforce.
    """
    import os
    import time
    from app.services.variant_axis import registry

    fixt = deeply_nested_template_6_axes  # 6 nested axes built via fixture

    start = time.perf_counter()
    for resolver_type, value in fixt["resolve_calls"]:  # 6 calls, one per axis
        registry.get(resolver_type).resolve_to_component(db, value=value)
    elapsed_ms = (time.perf_counter() - start) * 1000

    threshold_env = os.environ.get("VARIANT_AXIS_PERF_THRESHOLD_MS")
    if threshold_env:
        assert elapsed_ms < float(threshold_env), (
            f"6-deep recursive resolve took {elapsed_ms:.1f}ms, "
            f"threshold {threshold_env}ms"
        )
    else:
        # Log-only mode (CI default). Visible in test output for trend tracking.
        print(f"[perf-canary] 6-deep recursive resolve elapsed: {elapsed_ms:.1f}ms")
```

(Fixtures `fg_with_variable_manuf_component_with_variable_material` and `deeply_nested_template_6_axes` go in conftest. The 6-deep one builds 6 chained templates each with one child + one variable material; small but exercises the worst-case recursion.)

- [ ] **Step 2: Run → expected: recursive test asserts; perf canary prints elapsed.**

```bash
python -m pytest backend/tests/services/variant_axis/test_component_template.py -v -s
```

- [ ] **Step 3: No implementation needed** — Tasks 4+5 already cover the resolver behavior; these are exercises of the already-implemented code.

- [ ] **Step 4: Run perf canary with env to verify gating works**

```bash
VARIANT_AXIS_PERF_THRESHOLD_MS=100 python -m pytest \
  backend/tests/services/variant_axis/test_component_template.py::test_perf_canary_6_deep_recursive_resolve -v
```

Expected: passes (the resolve should be well under 100ms on dev hardware).

- [ ] **Step 5: Commit**

```bash
git add backend/tests/services/variant_axis/test_component_template.py backend/tests/conftest.py
PRE_COMMIT_ALLOW_NO_CONFIG=1 git commit -m "test(variant-axis): recursive 2-deep resolve + 6-deep env-gated perf canary"
```

---

## Task 11: scripts/verify_variant_synthesis.py

**Files:**
- Create: `scripts/verify_variant_synthesis.py`

- [ ] **Step 1: Write the script**

```python
"""Pre-merge correctness guard — read every existing variant through both
the legacy code path and the new registry; assert they resolve to the same
leaf component.

Run pre-merge against dev DB. CI runs against filaops_test fixtures.

Usage:
    python scripts/verify_variant_synthesis.py
    DATABASE_URL=postgresql://... python scripts/verify_variant_synthesis.py
"""
import sys

from app.db.session import SessionLocal
from app.models import Product
from app.services import variant_service
from app.services.variant_axis import registry  # noqa: F401  triggers registration
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
        for tmpl in templates:
            variants = (
                db.query(Product).filter(Product.parent_product_id == tmpl.id).all()
            )
            for v in variants:
                meta = v.variant_metadata or {}
                mat_type_id = meta.get("material_type_id")
                color_id = meta.get("color_id")
                if mat_type_id is None or color_id is None:
                    # No legacy shape → nothing for the legacy code to resolve;
                    # registry path also returns nothing. Skip.
                    continue
                try:
                    legacy = variant_service._find_material_product(
                        db, mat_type_id, color_id
                    )
                    meta_v2 = read_axis_selections(meta)
                    sel = meta_v2["axis_selections"].get("__legacy__")
                    if not sel:
                        print(f"  ! {v.sku}: synthesis returned no legacy entry")
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
        print(f"\nChecked {checked} variants; {mismatches} mismatch(es).")
        return 0 if mismatches == 0 else 1
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: Run against dev DB**

```bash
cd C:/repos/filaops-variant-b1/backend
python scripts/verify_variant_synthesis.py
```

Expected: `0 mismatch(es)` — every existing variant resolves identically.

If anything mismatches: stop, capture the SKU(s) listed, and triage. The synthesis logic in Task 3 is wrong somewhere.

- [ ] **Step 3: Smoke against `filaops_test`** (CI surface)

```bash
DATABASE_URL=postgresql://localhost/filaops_test python scripts/verify_variant_synthesis.py
```

Expected: 0 mismatches (or 0 variants, if the test DB is empty — that's fine).

- [ ] **Step 4: Add a tiny pytest wrapper so CI runs it**

```python
# backend/tests/scripts/test_verify_variant_synthesis.py
"""Smoke that the pre-merge guard script runs cleanly under CI."""
import subprocess
import sys


def test_script_exits_zero():
    result = subprocess.run(
        [sys.executable, "scripts/verify_variant_synthesis.py"],
        cwd="backend",
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, (
        f"verify_variant_synthesis.py failed:\n{result.stdout}\n{result.stderr}"
    )
```

Run: `python -m pytest backend/tests/scripts/ -v`

- [ ] **Step 5: Commit**

```bash
git add scripts/verify_variant_synthesis.py backend/tests/scripts/
PRE_COMMIT_ALLOW_NO_CONFIG=1 git commit -m "feat(variant-axis): pre-merge correctness guard verify_variant_synthesis.py"
```

---

## Task 12: Pre-merge sweep + PR open

- [ ] **Step 1: Full pytest**

```bash
python -m pytest backend/tests/ -q
```

Expected: all green. Note the run time and the count.

- [ ] **Step 2: Ruff E712**

```bash
python -m ruff check backend/app/ --select E712
```

Expected: clean.

- [ ] **Step 3: Frontend smoke (no frontend touched, but plan requires it)**

```bash
cd C:/repos/filaops-variant-b1/frontend
npx vitest run
```

Expected: green. If not, the failure is unrelated to B.1; capture and surface.

- [ ] **Step 4: Push and open PR**

```bash
cd C:/repos/filaops-variant-b1
git push -u origin feat/variant-axis-registry-b1
gh pr create --repo Blb3D/filaops --title "feat(variant-axis): registry + resolvers + back-compat synthesis (B.1)" --body "$(cat <<'EOF'
## Summary

Implements Workstream B.1 from docs/plans/variant-axis-generalization.md.

- Adds backend/app/services/variant_axis/ package with Protocol-based registry
- MaterialColorResolver preserves today's material+color behavior
- ComponentTemplateResolver resolves to active children of parent_product_id (no item_type branching — Rule 1)
- read_axis_selections() lifts legacy flat metadata into v2 axis_selections in memory; never persists (Rule 2 / write-path stays B.2)
- Soft (4) / hard (6) axis cap with depth-aware recursion counting
- variant_service._find_material_product and sync_routing_to_variants now delegate to the registry
- production_order_service.swap_material_variant's child-of-current check delegates to ComponentTemplateResolver
- 8 existing B0 tests stay green as the refactor guard

## Coverage matrix rows implemented (per strategic plan §2)

- [x] Material+color (variable): `test_material_color.py` resolution + synthesis
- [x] Manufactured component-template (variable): `test_component_template.py` 8 cases
- [x] Purchased component-template (variable): no item_type branching test
- [x] Recursive 2-deep: `test_resolve_recursive_2_deep`
- [ ] Mixed-axis end-to-end: covered by `test_variant_service_mixed_axis.py` (Task 8)
- [ ] Material+color (fixed), Manufactured (fixed), Purchased (fixed): covered by C.1's coverage matrix; B.1 verifies fixed lines aren't touched via the existing variant_service tests staying green

## Pre-merge correctness

- scripts/verify_variant_synthesis.py: 0 mismatches on dev DB
- 6-deep recursive resolver: <X ms (env-gated; CI runs in log-only mode)
- B0 swap tests: 8/8 green
- Ruff E712: clean

Three Rules from §2:
- Rule 1 (no item_type branching): `test_resolver_does_not_branch_on_item_type`
- Rule 2 (free-form label): `AxisOption.label` is non-empty in every fixture
- Rule 3 (fixed lines first-class): mixed-axis sync test asserts fixed lines preserved

## Out of scope

- B.2 write-path crossover to schema_version=2 (next PR)
- mrp.py — does not reference is_variable today; deferred to C.1
- Cost cascade #561

## Test plan
- [x] Full pytest passing
- [x] Ruff E712 clean
- [x] Vitest smoke
- [x] B0 regression: 8/8
- [x] verify_variant_synthesis.py: 0 mismatches

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

- [ ] **Step 5: Final**

After PR is open: paste the PR URL in the chat. Wait for CodeRabbit + Copilot review. Apply feedback. Squash-merge.

After merge: cut `feat/variant-axis-matrix-b2` worktree from fresh `main` and start B.2.

---

## Self-Review checkpoints (run before each commit)

- Does the new code branch on `item_type`? It must not.
- Does the new code hardcode "Color" or "Material" anywhere outside the material_color resolver? It must not.
- Are any `db.commit()` calls added that aren't atomic with their callers? Avoid (lesson from PR #213).
- Are any `==` boolean filters used? Use `.is_(True)` / `.is_(False)` (ruff E712).
- After 3 edits to a file, re-read it before the next edit (CLAUDE.md Edit Integrity).

---

## Definition of Done (mirrors strategic plan §10)

- [ ] All new + existing pytest pass; ruff E712 clean; vitest smoke
- [ ] `scripts/verify_variant_synthesis.py` passes against dev DB pre-merge
- [ ] 6-deep recursive perf canary completes (CI log-only; local with env-var passes <100 ms)
- [ ] Resolver code contains zero `if item_type ==` branches
- [ ] Free-form `label` field round-trips through API
- [ ] Existing variants resolve identically via legacy code and registry
- [ ] B0 swap tests unchanged and green
- [ ] PR description maps tests → coverage-matrix rows
- [ ] Sub-agent code review confirms Three Rules hold
