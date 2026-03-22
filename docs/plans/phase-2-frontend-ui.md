# Variant Matrix — Phase 2: Frontend UI

## Context

Phase 1 (schema, service, API, tests) landed on `feat/variant-matrix` in commit `3cdc933`. The backend is complete and working with 12 passing tests. Phase 2 adds the frontend surfaces so users can actually manage variant families without touching the API directly.

**Problem being solved:** A user with 15+ color/material variations of a product currently duplicates it manually each time. The Variant Matrix UI provides a single modal where they can see all possible color/material combinations in a grid, check the ones they want, and bulk-create the variants in one click.

**Working directory:** `c:\repos\filaops-variant-matrix` (git worktree — do NOT use `c:\repos\filaops`)

---

## Architecture Discoveries

- **No item detail page exists** — everything is modal-based from `AdminItems.jsx`. There are no tabs on item views. BOM and Routing are separate modal editors.
- **API response shape** for `GET /items/{id}/variant-matrix`:
  ```json
  {
    "template": { "id", "sku", "name", "is_template", "variable_material_ids" },
    "variants": [{ "id", "sku", "name", "material_type_code", "color_code", "color_hex", "standard_cost", "selling_price", "on_hand_qty", "active" }],
    "available_combos": [{ "material_type_id", "color_id", "material_type_code", "material_type_name", "color_code", "color_name", "color_hex", "already_exists", "variant_id" }]
  }
  ```
- **`is_variable`** is already in both `RoutingOperationMaterialCreate` and `RoutingOperationMaterialUpdate` schemas, and in the `RoutingOperationMaterialResponse`. No backend changes needed.
- **Dominant patterns:** `useState` hooks, direct `fetch` with `credentials: "include"`, `useToast()` for feedback, `Modal.jsx` wrapper, `ConfirmDialog.jsx` for destructive actions.

---

## Files to Create

### `frontend/src/components/items/VariantMatrixModal.jsx`

Modal triggered from the items table. Three sections:

**Section 1 — Header info:**
- Template SKU + name
- Badge: `{variant_count} variant(s)` (purple)
- If `template.variable_material_ids.length === 0`: warning callout: "No variable materials configured — open Routing Editor and mark materials as Variable before creating variants."

**Section 2 — Combo Grid (selection picker):**
- Derive `uniqueMaterials` and `uniqueColors` from `available_combos`
- Build 2D grid: rows = material types, columns = colors
- Cell states:
  - `already_exists: true` → green checkmark chip (non-interactive, shows variant SKU on hover tooltip)
  - `already_exists: false` + combo in available_combos → checkbox (toggleable, adds to `selectedCombos` Set)
  - Combo not in available_combos → gray dash `—` (disabled)
- Below grid: "Create {selectedCombos.size} variant(s)" button (blue, disabled when 0 selected or `creating`)

**Section 3 — Existing Variants Table:**
Columns: SKU | Color swatch + name | Material | Std Cost | On Hand | Actions (Delete)
- Color swatch: `<span style={{ backgroundColor: v.color_hex }} className="w-4 h-4 rounded-full inline-block border border-gray-600" />`
- Delete button triggers `ConfirmDialog` (danger variant)

**State:**
```js
const [matrixData, setMatrixData] = useState(null);  // full API response
const [loading, setLoading] = useState(false);
const [selectedCombos, setSelectedCombos] = useState(new Set()); // "mtId-colorId"
const [creating, setCreating] = useState(false);
const [deletingId, setDeletingId] = useState(null);  // variantId in confirm
```

**API calls:**
- Fetch: `GET /api/v1/items/{item.id}/variant-matrix`
- Bulk create: `POST /api/v1/items/{item.id}/variants/bulk` body: `{ selections: [...{material_type_id, color_id}] }`
- Delete: `DELETE /api/v1/items/{item.id}/variants/{variantId}`
- After each mutation: clear `selectedCombos`, call `fetchMatrix()`, call `onSuccess()` to refresh the items list

**Reuse:** `Modal.jsx`, `ConfirmDialog.jsx`, `useToast()`

---

## Files to Modify

### `frontend/src/components/items/ItemsTable.jsx`

1. **Template badge** in the Name column (after item name, inline):
   ```jsx
   {item.is_template && (
     <span className="ml-2 px-2 py-0.5 rounded-full text-xs bg-purple-500/20 text-purple-400 border border-purple-500/30">
       Template · {item.variant_count}
     </span>
   )}
   ```

2. **Variants action button** in the Actions column (after Duplicate button):
   ```jsx
   <button onClick={() => onManageVariants(item)} title="Manage Variants"
     className="p-1.5 rounded text-gray-400 hover:text-purple-400 hover:bg-purple-500/10 transition-colors">
     {/* Grid icon (2×2 squares SVG) */}
   </button>
   ```
   - Add `onManageVariants` to prop list (alongside existing `onEdit`, `onDuplicate`, etc.)

### `frontend/src/pages/admin/AdminItems.jsx`

Pattern mirrors the existing `duplicatingItem` state:
```js
const [variantItem, setVariantItem] = useState(null);
```

Add modal mount (near line ~754 where DuplicateItemModal is):
```jsx
<VariantMatrixModal
  isOpen={!!variantItem}
  onClose={() => setVariantItem(null)}
  item={variantItem}
  onSuccess={fetchItems}
/>
```

Wire `onManageVariants={setVariantItem}` on `<ItemsTable>`.

### `frontend/src/components/routing/OperationRow.jsx`

In the expandable materials sub-row (lines ~172–198), add `is_variable` indicator per material row. After the existing Optional badge:
```jsx
{mat.is_variable && (
  <span className="px-1.5 py-0.5 rounded text-xs bg-blue-500/20 text-blue-400 border border-blue-500/30">
    Variable
  </span>
)}
```
No new interactivity here — editing is done through the modal.

### `frontend/src/components/OperationMaterialModal.jsx`

Add `is_variable` checkbox field alongside the existing `is_cost_only` and `is_optional` checkboxes. In `formData` state, add `is_variable: material?.is_variable ?? false`. In the form JSX (near the Optional checkbox):
```jsx
<label className="flex items-center gap-2 cursor-pointer">
  <input type="checkbox" checked={formData.is_variable}
    onChange={e => setFormData(p => ({ ...p, is_variable: e.target.checked }))}
    className="rounded border-gray-600 bg-gray-800 text-blue-500 focus:ring-blue-500" />
  <span className="text-sm text-gray-300">Variable</span>
  <span className="text-xs text-gray-500">(swap this material per variant)</span>
</label>
```
Include `is_variable` in the PUT payload when saving.

---

## Critical Files

| File | Role |
|------|------|
| `frontend/src/components/items/VariantMatrixModal.jsx` | **New** — main UI |
| `frontend/src/components/items/ItemsTable.jsx` | Badge + action button |
| `frontend/src/pages/admin/AdminItems.jsx` | State wiring + modal mount |
| `frontend/src/components/routing/OperationRow.jsx` | `is_variable` badge in material rows |
| `frontend/src/components/OperationMaterialModal.jsx` | `is_variable` checkbox |
| `backend/app/services/variant_service.py` | Reference for API shape (no changes) |
| `backend/app/schemas/manufacturing.py:437` | Confirms `is_variable` in update schema |

**Reusable components (no changes):**
- `frontend/src/components/Modal.jsx`
- `frontend/src/components/ConfirmDialog.jsx`
- `frontend/src/hooks/useApi.js` — OR direct fetch (match RoutingEditorContent pattern)
- `frontend/src/components/Toast.jsx` via `useToast()`

---

## Build Sequence

1. `OperationMaterialModal.jsx` — add `is_variable` checkbox (smallest, isolated)
2. `OperationRow.jsx` — add `is_variable` badge (read-only display)
3. `VariantMatrixModal.jsx` — new file, full implementation
4. `ItemsTable.jsx` — template badge + Variants button + `onManageVariants` prop
5. `AdminItems.jsx` — wire state + mount modal

---

## Verification

1. **is_variable toggle:**
   - Open Routing Editor on any finished_good with a routing
   - Click a material row to open OperationMaterialModal
   - Check "Variable" → save → material row shows "Variable" badge

2. **Template badge:**
   - Find (or create) a product with `is_template: true` in the DB
   - Items table shows purple "Template · N" badge on that row

3. **Variant Matrix Modal — empty template:**
   - Open modal on a non-template item
   - If no variable materials configured: warning callout is shown
   - If variable materials exist: grid renders available combos as checkboxes

4. **Bulk create:**
   - Check 3 combos in the grid
   - Click "Create 3 variants"
   - After success: grid shows green checkmarks for created variants, table shows new rows

5. **Delete variant:**
   - Click delete on a variant row
   - ConfirmDialog appears (danger)
   - Confirm → variant disappears from table, grid cell reverts to checkbox
   - When last variant deleted: template badge disappears from items table

6. **Run backend tests (no regressions):**
   ```bash
   cd c:\repos\filaops-variant-matrix\backend
   python -m pytest tests/test_variant_service.py -v --tb=short
   ```
