# Variant Axis Generalization — Strategic Plan (B.1 + B.2 + C.1)

> **For agentic workers:** This is a strategic/workstream plan. Each workstream (B.1, B.2, C.1) will spawn its own task-level implementation plan via `superpowers:writing-plans` when execution starts. Definition-of-Done per workstream below sets the merge bar.

**Goal:** Generalize the variant axis from hardcoded `material_type + color` to a registry-dispatched system that supports component-template axes, mixed multi-axis templates, recursive variant configuration, and CTO substitution at SO→PO conversion — without breaking existing material+color templates.

**Architecture:** Three sequenced PRs. B.1 builds the resolver + axis-type registry on the service layer with back-compat synthesis. B.2 generalizes the matrix UI to drive off the registry (free-form labels, axis-type-aware cells). C.1 adds `configuration` to SO/Quote lines, freezes config at SO→PO conversion, and lets PO release substitute via the existing B0 swap path.

**Tech stack:** FastAPI · SQLAlchemy · PostgreSQL JSONB · Alembic · React 19 + Vite · Vitest · pytest

---

## 1. Context & Non-Goals

### Why this exists
On 2026-04-25, FG-004 (Zorble Keychain) live-reproduced two gaps:
- **Variant matrix creation:** `variant_service._find_material_product` (variant_service.py:28) is hardcoded to `material_type_id + color_id`. Templates whose `is_variable` line is a *component* (not a material+color) get "No available material/color combinations found."
- **Demand-side consumption:** PO-2026-0021 making 5x `FG-003_test_assy` was blocked with "material shortage: FG-003" despite 40 EA across BLK+BLU variants — `production_order_service` walks BOM lines and queries the template's own inventory directly, missing the rollup.

Workstream A (PR #559) shipped the inventory rollup view (template rows show summed variant on-hand). B0 (PR #560) shipped the tactical PO operation-material variant swap (`swap_material_variant` in production_order_service.py:1636). Standard_cost auto-sync (PR #562) closed a related test gap. **A, B0, and #562 are all merged to main as of 2026-04-26.** Cost cascade is parked at issue #561.

### What this plan covers
- **B.1** — service-layer generalization: axis-type registry, resolver, back-compat synthesis of legacy `{material_type_id, color_id}` metadata into the new `axis_selections` shape, on read.
- **B.2** — matrix UI generalization: drive off `available_combos` returned per axis-type, render free-form differentiator labels, axis-type-aware cell components.
- **C.1** — SO/Quote line `configuration` field, frozen at SO→PO conversion, PO release substitutes per the B.1 resolver. Reuses B0's variant swap mechanism for in-flight overrides.

### Non-goals (explicit)
- **C.2 (PRO storefront widget):** lives in `filaops-ecosystem`, not this repo. Core gets admin-edit only.
- **C.3 (backorder, MRP, reservation timing):** locked decisions exist (option (b) — accept order, MRP triggers replenishment; stay with PO-release reservation), but the implementation is its own plan.
- **Cost cascade on PO receipt:** parked at #561, separate concern (cost rollup ≠ inventory rollup — see `pattern_rollup_terminology.md`).
- **Lazy variant minting at PO release:** explicitly forbidden — leaf variants are user-created via the matrix only.
- **Phase 3 of `project_variant_matrix.md` (checkbox→text-input UX):** distinct workstream, not affected here.
- **Axis grouping (matched-set products):** schema must not preclude it, but no v1 work.
- **Variable quantity / optional-line axes:** registry must leave room, no v1 work.

---

## 2. Locked Decisions (verbatim from `project_variant_consumption_rollup.md`)

> **Do not re-litigate. These came out of the 2026-04-25 design conversation.**

- **Mixed axis types in v1:** YES. A template can have one variable line of type `material_color` and another of type `component_template` simultaneously. Resolver dispatches per-axis-type via a registry pattern, not if/else.
- **Recursive variants:** YES, but config-on-PO, NOT lazy variant creation. Customer picks ball color AND ball's filament finish independently → SO line carries recursive `variant_configuration` (same shape as `variant_metadata.axis_selections`, just nested). At PO release, resolver walks the tree and substitutes leaf variants per-axis at consume time. Do not auto-mint `FG-004-BLK-RED`-style SKUs at PO release.
- **Axis cap:** soft 4 with warning, hard 6. Counted across the full recursion depth, not just top-level.
- **Substitution timing:** SO→PO conversion (frozen on PO creation, operator can still edit via B0 mechanism before release).
- **Storefront widget:** PRO. Core gets admin-edit only.
- **Backorder behavior:** option (b) — accept order, MRP triggers replenishment. Make-to-order print farm.
- **Partial config:** reject at submit.
- **Reservation timing:** stay with PO-release reservation.

### Three rules that MUST hold across B and C
1. **Resolver must NOT branch on `item_type`.** Works identically for manufactured, component, and supply (purchased) templates. Resolver query is `parent_product_id = template.id AND active`.
2. **Variant differentiator is free-form, read from `variant_metadata`.** UI must not hardcode "Color." Backend returns the label; frontend renders it.
3. **Fixed BOM lines are first-class.** A 5-line template (1 variable, 4 fixed) is still 5 lines per variant. Variant clone copies the 4 fixed lines verbatim and substitutes the 1 variable. Preserve current `sync_routing_to_variants` semantics (variant_service.py:407–545).

### Coverage matrix (one passing test per row, target lives in C.1 test suite)

| BOM line type | Variable? |
|---|---|
| Material+color | yes |
| Material+color | no (fixed) |
| Manufactured component-template | yes |
| Manufactured component | no (fixed) |
| Purchased component | no |
| Purchased component-template (size/finish variants) | yes |
| Mixed: 1 var material + 1 var manuf + 1 var purchased + 2 fixed in one BOM | yes (3 axes) |
| Recursive: FG with variable manuf component, that component has its own variable material | yes (2-deep) |

---

## 3. Data Shape (load-bearing — the rest of the plan depends on this)

### 3.1 `Product.variant_metadata` (existing JSONB column, recursion-aware shape from B.1 onwards)

```jsonc
{
  "axis_selections": {
    "<template_routing_material_id>": {
      "type": "material_color | component_template",
      "label": "Color",                   // free-form differentiator label
      "value": {
        // Type-specific payload. For material_color:
        //   { "material_type_id": 7, "color_id": 12,
        //     "material_type_code": "PLA_BASIC", "color_code": "BLK" }
        // For component_template:
        //   { "component_id": 4218, "component_sku": "COMP-005-PLA_BASIC-BLK",
        //     "component_label": "PLA Basic Black" }
        // OR nested for recursion:
        //   { "axis_selections": { ... } }   // same shape, walked depth-first
      }
    }
  },
  "axis_count": 3,                          // denormalized for cap-checking; >4 warn, >6 reject
  "schema_version": 2                       // bump from 1 (legacy material+color flat shape)
}
```

### 3.2 `SalesOrderLine.configuration` and `QuoteLine.configuration` (NEW JSONB column from C.1)

Same shape as `variant_metadata.axis_selections`, but represents customer choices for a non-stocked template at order time. PO conversion freezes this; PO release walks it through the resolver to substitute concrete variants on `ProductionOrderOperationMaterial.component_id`.

```jsonc
{
  "axis_selections": { /* same as 3.1 */ },
  "schema_version": 2
}
```

### 3.3 Axis-type registry contract (`backend/app/services/variant_axis_registry.py`, NEW in B.1)

Each axis type is a callable trio:

```python
class AxisTypeResolver(Protocol):
    type_name: str  # "material_color" | "component_template"

    def list_options(
        self, db: Session, *, template: Product, routing_material: RoutingOperationMaterial
    ) -> list[AxisOption]:
        """Returns options for the matrix UI (label, value payload, preview SKU/name)."""

    def resolve_to_component(
        self, db: Session, *, value: dict
    ) -> Product:
        """Resolves an axis_selections.value payload to a concrete Product (leaf component).
        For nested values, walks recursion. Raises HTTPException(404) if not resolvable."""

    def synthesize_legacy(
        self, *, variant_metadata_legacy: dict
    ) -> dict | None:
        """Optional. Lifts schema_version=1 metadata into schema_version=2 axis_selections.
        Only material_color implements this; component_template returns None."""
```

Registry registration is module-level dict keyed by `type_name`. Adding `"variable_quantity"` later = one new file + one registration line.

### 3.4 Back-compat synthesis (CRITICAL — no migration runs in B.1)

- `variant_service` and the resolver always read `variant_metadata` through a single helper `read_axis_selections(meta: dict) -> dict`.
- If `meta.schema_version != 2` (or missing), call `material_color.synthesize_legacy(meta)` to produce the v2 shape **in memory**. Never persist the synthesized form during B.1.
- **Variants written before B.1 lack `schema_version`; the synthesizer treats absent as v1 (assume legacy `{material_type_id, color_id, ...}` shape).** This covers every existing variant in dev and prod DBs as of merge time.
- Variant rows continue to write the legacy shape during B.1 (new variants from `create_variant` keep writing `{material_type_id, color_id, ...}` for safety). Schema-version bump-and-write happens lazily in C.1 when a variant is touched, OR via a one-shot `alembic upgrade` data migration scheduled at the end of C.1.
- Acceptance: any existing variant in the dev DB read through the resolver returns identical leaf component as the legacy code path.

### 3.5 Axis cap enforcement

Counted in `compute_axis_count(meta) -> int` walking nested `value` dicts. Soft limit 4 emits a `logger.warning` and surfaces in API response as `axis_count_warning: true`. Hard limit 6 raises `HTTPException(400)` from `create_variant` and from `SalesOrderLine.configuration` validation.

---

## 4. Workstream B.1 — Service-layer generalization

**Branch:** `feat/variant-axis-registry-b1`
**Worktree:** `C:\repos\filaops-variant-b1` (cut fresh from current `main`)
**PR target:** ~6–8 files changed, all backend, no migration, no schema change

### Files

**Create:**
- `backend/app/services/variant_axis_registry.py` — `AxisTypeResolver` Protocol, registry dict, `register()`/`get()`/`all_types()` functions.
- `backend/app/services/variant_axis/material_color.py` — `MaterialColorResolver` (lifts existing `_find_material_product` logic + legacy synthesis).
- `backend/app/services/variant_axis/component_template.py` — `ComponentTemplateResolver` (resolves to active children of `parent_product_id`; no `item_type` branching).
- `backend/app/services/variant_axis/__init__.py` — registers both resolvers on import.
- `scripts/verify_variant_synthesis.py` — pre-merge correctness guard (~30 lines). Loads every `is_template=True` product in the connected DB, walks each variant, asserts `legacy_resolve(meta) == registry_resolve(meta)`. Run against dev DB before merge; CI runs against `filaops_test` fixtures. This is the strongest correctness check in the workstream — if it fails, do not merge.
- `backend/tests/services/test_variant_axis_registry.py` — registry contract tests.
- `backend/tests/services/test_variant_axis_material_color.py` — back-compat synthesis + resolution tests using existing dev fixtures.
- `backend/tests/services/test_variant_axis_component_template.py` — FG-004 / COMP-005 style fixtures, multi-axis, recursive 2-deep, **plus a perf assertion: a 6-deep recursive resolve completes in <100 ms against the existing dev DB fixture sizes** (cheap quadratic-blowup canary; satisfies the §8 O(N²) risk flag).

**Modify:**
- `backend/app/services/variant_service.py` — add `read_axis_selections()` helper, refactor `_find_material_product` and `create_variant` to delegate to registry; preserve existing function signatures (callers untouched). `sync_routing_to_variants` (lines 407–545) uses the new resolver to find target component for each variable line — material_color path returns identical product to today.
- `backend/app/services/production_order_service.py` — refactor the child-of-current check inside `swap_material_variant` (line 1636) to delegate to the registry's component_template resolver. Accepted inputs unchanged: a swap is still permitted only when the new component is an active child of the current `component_id`. The 8 existing B0 tests stay green as the refactor guard.
- `backend/app/services/item_service.py` — wherever `variant_count_map` / `variants_on_hand_map` / `variants_available_map` are computed (PR #559's blocks), no logic change; just ensure helpers don't assume material+color shape on `variant_metadata` reads.

**Do NOT touch in B.1:**
- `mrp.py` (does not reference `is_variable` today; deferred until C.1 explicitly)
- Any frontend file
- Any alembic migration
- `SalesOrderLine` / `QuoteLine` models or schemas

### Test plan
- Registry contract: register both types; `get()` returns the right one; unknown type raises.
- Material+color resolver: round-trip a legacy variant_metadata through `synthesize_legacy → resolve_to_component`, assert leaf product identical to `_find_material_product` output.
- Component-template resolver: build a fixture template with 9 component children, `list_options` returns 9, `resolve_to_component` returns the named child.
- Recursive: build a 2-deep fixture (FG with variable manuf component, component has its own variable material). Resolver walks both axes.
- Mixed-axis: build a single template with 1 material_color line + 1 component_template line. `axis_count == 2`, both resolve.
- Soft/hard cap: 4-axis emits warning, 5-axis still accepted, 6-axis on `create_variant` raises 400.
- 6-deep recursive perf canary: <100 ms against dev fixture sizes (asserts via `time.perf_counter`; logged as warning, not skip, on slower hardware).
- B0 swap regression: existing 8 swap tests stay green unchanged.

### Definition of Done (B.1)
- All new + existing pytest passing locally and in CI
- `python -m ruff check app/ --select E712` clean (use `.is_(True)` per memory)
- `npx tsc --noEmit` not relevant (no frontend); `npx vitest run` should still pass (no frontend touched, but smoke-run required)
- `scripts/verify_variant_synthesis.py` passes against dev DB pre-merge (every existing variant resolves identically through legacy and registry paths)
- 6-deep recursive resolver perf assertion passes (<100 ms)
- A sub-agent review confirms: zero `if item_type ==` branches in the new resolver code, free-form `label` field present in axis-type return shape, legacy variants resolve identically.
- PR description references the three rules and shows which tests cover which coverage-matrix rows that this PR implements (the manuf and supply rows; recursive will be covered fully by C.1's test suite).
- Squash merge to main; bump no version.

---

## 5. Workstream B.2 — Matrix UI generalization

**Branch:** `feat/variant-axis-matrix-b2`
**Worktree:** cut fresh from `main` after B.1 merges
**PR target:** ~4–5 files changed, frontend + backend response shape

### Files

**Create:**
- `frontend/src/components/items/VariantAxisGrid.jsx` — generic 1-D or 2-D axis grid component. Receives `axes: [{type, label, options}]` and renders a checkbox grid (1 axis = list, 2 axes = grid, 3+ axes = stacked grids with selector). No `material × color` strings anywhere.
- `frontend/src/components/items/__tests__/VariantAxisGrid.test.jsx` — render tests for 1/2/3-axis cases, free-form labels, existing-variant indicator.

**Modify:**
- `frontend/src/components/items/VariantMatrixModal.jsx` — replace the hardcoded `uniqueMaterials × uniqueColors` derived state and the inline grid table with a `<VariantAxisGrid axes={matrixData.axes} ... />`. Bulk-create handler now POSTs `axis_selections` payload instead of `material_type_id + color_id`.
- `backend/app/api/v1/endpoints/items.py` (or wherever `/api/v1/items/{id}/variant-matrix` lives) — response shape becomes `{ axes: [{type, label, options}], existing: [...] }` instead of `{ available_combos: [...] }`. Maintain the legacy field as deprecated alias for one PR cycle, removed in C.1.
- `backend/app/services/variant_service.py` (small) — new `build_matrix_payload(template)` that walks the template's variable BOM lines and asks each axis type's resolver for `list_options`.
- `backend/app/api/v1/endpoints/items.py` (POST `/items/{id}/variants`) — accept `axis_selections` body; map to `create_variant` call. Old body shape `{material_type_id, color_id}` accepted via shim for one PR cycle.

### Test plan
- Backend: `/variant-matrix` returns axes for an FG-004-style template; old material_color template returns one axis with `label="Color"` (read from registry).
- Frontend: render 1-axis (size-only template), 2-axis (FG-004 ball+holder), 3-axis (synthetic). Free-form label rendered in column header. Bulk-create POSTs `axis_selections` payload shape.
- Regression: existing material+color matrix still creates variants identical to today (snapshot test on `Product.sku` and `variant_metadata`).
- Vitest: all existing `ItemsTable.test.jsx` cases (the rollup tests from PR #559) stay green.

### Definition of Done (B.2)
- pytest, vitest, tsc, ruff all clean
- Live test in dev env: open VariantMatrixModal on an FG-004-style template, see component-template axis populated; create one variant successfully; verify it appears in `ItemsTable` rollup row (PR #559 mechanism still works).
- Live test on existing material+color template: matrix renders identically to pre-B.2.
- Sub-agent review confirms: zero hardcoded "Color" / "Material" strings in the grid component, no `material_type_id` / `color_id` fields outside the material_color resolver and its tests.
- Deprecation warning logged when legacy POST shape is used.

---

## 6. Workstream C.1 — SO/Quote line config + SO→PO substitution

**Branch:** `feat/variant-config-cto-c1`
**Worktree:** cut fresh from `main` after B.2 merges
**PR target:** ~8–10 files changed, includes one alembic migration (additive, two NULL JSONB columns)

### Files

**Create:**
- `backend/migrations/versions/<auto>_add_line_configuration.py` — additive: `sales_order_lines.configuration JSONB NULL`, `quote_lines.configuration JSONB NULL`. Down-rev drops both columns. No data backfill.
- `backend/app/services/variant_config_service.py` — `validate_configuration(db, product, payload)` (rejects partial), `freeze_configuration(db, so_line)` called at SO→PO conversion, `apply_configuration_to_po(db, po, configuration)` called at PO release to substitute via the existing B0 `swap_material_variant` mechanism (one swap per leaf in the resolved tree).
- `backend/tests/services/test_variant_config_service.py` — covers all 8 rows of the coverage matrix in §2.
- `backend/tests/integration/test_so_to_po_cto.py` — end-to-end: SO line with FG-004 + 2-axis configuration → SO→PO convert → PO has correct substituted component_ids on its operation materials.

**Modify:**
- `backend/app/models/sales_order.py` (line 180+) — add `configuration = Column(JSONB, nullable=True)` to `SalesOrderLine`.
- `backend/app/models/quote.py` — add `configuration` to `QuoteLine`.
- `backend/app/schemas/sales_order.py` — add `configuration: Optional[dict] = None` to create/update/response schemas (lines 21, 164, 189, 214 area).
- `backend/app/schemas/quote.py` — same.
- `backend/app/services/sales_order_service.py` — accept `configuration` on line create/update; call `validate_configuration` if line product is `is_template=True`.
- `backend/app/services/quote_service.py` — same.
- `backend/app/services/sales_order_service.py` (SO→PO conversion path, wherever `production_order_service.create_production_order` is called from a SO line) — call `freeze_configuration` then `apply_configuration_to_po` after PO creation.
- `backend/app/services/production_order_service.py` — wrap the existing `swap_material_variant` (line 1636) into a batch helper `apply_axis_selections(po, axis_selections)` that the C.1 conversion path calls. Single transaction, all-or-nothing per Three Rules.
- `backend/app/api/v1/endpoints/items.py` — REMOVE the deprecated legacy `/variant-matrix` response alias and POST shim from B.2 (one-cycle deprecation expires here).

**Out of scope for C.1 (already covered in §1 non-goals, repeated for emphasis):**
- Storefront widget (PRO)
- Backorder/MRP changes
- Reservation timing changes
- Cost cascade

### Test plan
- All 8 coverage matrix rows pass with one dedicated test each.
- SO line with `configuration` for a non-template product → 400.
- Partial configuration (one of two axes left out) → 400.
- 7-axis configuration → 400 (hard cap).
- 5-axis configuration → 200 with warning surfaced in response.
- SO→PO conversion freezes configuration: subsequent SO line edit does not change PO operation materials.
- B0 swap still works on a PO that came from a CTO conversion (operator can re-swap before release).
- Down-migration drops the two columns cleanly.
- Pre-existing variant rows in dev DB still render and resolve identically (regression on B.1's back-compat synthesis).

### Definition of Done (C.1)
- pytest, vitest, tsc, ruff all clean; CI green
- Alembic migration runs forward and backward in a fresh `filaops_test`
- Live test in dev: create FG-004 quote with 2-axis configuration, convert to SO, convert to PO, release PO, observe correct variant components consumed
- Live test on existing material+color SO without configuration → unchanged behavior
- Sub-agent review confirms: deprecated legacy paths from B.2 are removed, no hardcoded axis-type names outside the registry, all three Rules hold under recursion
- Issue #561 (cost cascade) explicitly cross-linked in PR description as out-of-scope

---

## 7. Sequencing & Dependencies

```
main (post-PR #562)
  │
  └── B.1 (registry + resolver + synthesis)        ← merge to main
        │
        └── B.2 (matrix UI on registry)            ← cut from main, merge to main
              │
              └── C.1 (line config + SO→PO + alembic) ← cut from main, merge to main
```

> **Note:** C.2 and C.3 stubs in §9 are NOT on this critical path — they are independent successor work, scheduled separately, and their absence does not block any of B.1/B.2/C.1 from merging.

- **Hard dependency chain:** B.2 needs B.1's registry to populate `axes`. C.1 needs B.1's resolver for substitution and B.2's UI for admin to test the flow end-to-end.
- **Each PR ships independently green** — no flag-gating, no dark code paths. B.1 produces zero behavior changes for end users; only the resolver internals change.
- **Worktree discipline (per `feedback_worktree_isolation.md`):** each workstream gets its own worktree. Do not reuse `feat/variant-inventory-rollup` or `feat/po-variant-swap` (both A and B0 worktrees are stale).
- **No parallel B.1 + B.2.** B.1 must merge first because B.2 modifies the same `variant_service.py` regions and an in-flight registry refactor would generate spurious conflicts.

---

## 8. Risks & Mitigations

| Risk | Likelihood | Mitigation |
|---|---|---|
| Back-compat synthesis returns a different component than legacy `_find_material_product` for some edge case (deactivated material product, archived color) | Medium | B.1 includes `scripts/verify_variant_synthesis.py` (listed in §4 Create) — loads every existing `is_template=True` product, walks each variant, asserts `legacy_resolve(meta) == registry_resolve(meta)`. Run pre-merge against dev DB with PR #559 fixtures + manual FG-003/FG-004 variants. |
| `swap_material_variant` refactor (B.1) breaks the B0 invariant that the new component must be a child of the current `component_id` | Low | The 8 existing B0 tests explicitly cover sibling-template rejection and child-only acceptance — leave them as the refactor guard. The check semantics are unchanged; only the implementation moves into the registry. |
| Mixed-axis template's sync_routing_to_variants (variant_service.py:407–545) silently picks one axis when target_material is ambiguous | High if untested | B.1 adds a test that builds a mixed-axis variant and asserts each variable line's resolved component matches its own axis selection. Current code's `mat_type_id, color_id_meta` flat lookup must be replaced with per-line axis lookup. |
| Alembic migration in C.1 collides with another in-flight branch | Low | Run `alembic heads` before generating; if multiple heads, write a merge migration first (per memory, prior alembic 069/070 merge precedent). |
| C.1 SO→PO freeze captures stale axis options if user edits SO line between submit and conversion | Medium | `freeze_configuration` runs at conversion, not submit. Re-validate at conversion time; reject if any axis option no longer resolves. |
| Recursion depth makes resolver O(N²) on pathological 6-axis recursive templates | Low | Hard cap of 6 across full depth (per locked decisions §2). B.1's perf-canary test asserts <100 ms for a 6-deep recursive resolve against dev fixture sizes (see §4). Add a recursion-depth assertion in resolver. |
| `pattern_rollup_terminology.md` confusion: someone "fixes the rollup" thinking they fixed cost when they fixed inventory (or vice versa) | High historically | Each PR description explicitly states "this PR does not touch cost rollup (#561)" or "this PR does not touch inventory rollup (PR #559 territory)". |
| Variant matrix UI (B.2) regresses existing material+color flow | Medium | Snapshot test on `Product.sku` and `variant_metadata` for create from material_color matrix path. Live regression test pre-merge. |

---

## 9. Out of Scope (explicit, not in any of B.1/B.2/C.1)

### Successor workstreams (chain visibility — not blocked, just not in this plan)

- **C.2 — PRO storefront variant configuration widget.** Lives in `filaops-ecosystem/portal` (B2B) and `filaops-ecosystem/quoter` (public-facing quote engine). Consumes the C.1 `configuration` API once shipped. Per-line dropdown UX for each `is_variable` BOM line, axis-type-aware (color picker, size selector, etc.) reading from the registry's `list_options` response. Full context in `project_variant_consumption_rollup.md` §"Workstream C — CTO at Sales-Order Time" (the storefront-widget paragraph).
- **C.3 — Backorder behavior, MRP integration, reservation-timing rework.** Locked decisions exist (option (b) accept-and-replenish, PO-release reservation, no SO-confirm reservation), but the implementation is its own plan and touches `mrp.py` (which today does not reference `is_variable` at all). Full context in `project_variant_consumption_rollup.md` §"Locked decisions" — backorder/reservation bullets.

### Other items explicitly out of scope

- **Cost cascade on PO receipt (issue #561).** Distinct subsystem (cost rollup ≠ inventory rollup per `pattern_rollup_terminology.md`). Independent triage.
- **Phase 3 of `project_variant_matrix.md`** (checkbox→text-input UX in matrix grid). Distinct workstream; coordinate at sequencing time but no shared code.
- **Lazy variant SKU minting at PO release.** Explicitly forbidden per locked decisions (defeats no-proliferation goal).
- **Axis grouping (matched-set products like "ball color = holder color").** Schema preserves room (`axis_selections` keyed by `template_routing_material_id` so an `axis_group_id` slots in later); no v1 work.
- **Variable quantity / optional-line axes.** Registry leaves room (per-axis-type resolver); no v1 work.
- **Persisting v2 schema_version on existing variant rows.** B.1 reads through synthesis. C.1 may include a tail-end one-shot migration; the bulk write of v2 metadata is itself optional and can defer to a later PR.

---

## 10. Definition of Done (per workstream — restated for the merge bar)

### B.1
- [ ] All new + existing pytest pass; ruff E712 clean; vitest smoke-runs
- [ ] `scripts/verify_variant_synthesis.py` passes against dev DB pre-merge
- [ ] 6-deep recursive resolver perf canary passes (<100 ms)
- [ ] Resolver code contains zero `if item_type ==` branches
- [ ] Free-form `label` field present and round-trips through API
- [ ] Existing variants resolve identically via legacy code and registry
- [ ] B0 swap tests unchanged and green
- [ ] PR description maps tests → coverage-matrix rows it implements
- [ ] Sub-agent code review confirms Three Rules hold

### B.2
- [ ] pytest, vitest, tsc, ruff clean
- [ ] Live: FG-004-style template renders component-template axis; create variant; appears in PR #559 rollup
- [ ] Live: existing material+color template renders identically to pre-B.2
- [ ] Zero hardcoded axis-type strings in `VariantAxisGrid.jsx`
- [ ] Legacy POST/response shape logged as deprecated
- [ ] Sub-agent review

### C.1
- [ ] pytest, vitest, tsc, ruff clean; CI green
- [ ] Alembic up + down migration runs cleanly on fresh `filaops_test`
- [ ] All 8 coverage-matrix rows pass with dedicated tests
- [ ] Live: FG-004 quote → SO → PO → release → correct components consumed
- [ ] Live: existing material+color SO without configuration unchanged
- [ ] Deprecated B.2 legacy aliases removed
- [ ] Sub-agent review confirms Three Rules hold under recursion
- [ ] PR description cross-links #561 as explicitly out-of-scope
