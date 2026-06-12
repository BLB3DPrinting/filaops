# DEBT-1: God-File Decomposition Plan

**Date:** 2026-06-12
**Status:** APPROVED (owner, 2026-06-12)
**Supersedes/absorbs:** issue #428 (customer_service.py, Code Conclave findings ARCHITECT-001/002/003 + NAVIGATOR-002), memory note on item_service.py split.

## Problem

Feature velocity has concentrated code into god files, and the pattern is
self-reinforcing: review guidance says "match the surrounding file," so every
fix lands in place. Survey (2026-06-12):

| File | Lines | 3-day growth |
|---|---|---|
| services/sales_order_service.py | 3,541 | +439 |
| services/item_service.py | 2,403 | (long-standing, split designed) |
| services/production_order_service.py | 2,055 | +240 |
| pages/admin/OrderDetail.jsx | 2,021 | +719 |
| services/inventory_service.py | 1,826 | |
| services/purchase_order_service.py | 1,794 | |
| endpoints/production_orders.py | 1,639 | |
| components/production/OperationSchedulerModal.jsx | 1,199 | +529 |
| components/AdminLayout.jsx | 1,129 | |
| services/customer_service.py | 1,088 | issue #428 |

Beyond maintainability, god files are an **agent-mortality factor**: three
mid-task agent deaths (HARD-4b, RESERVE-1, SCHED-7) cluster on tasks that
read/edit 2,000+-line files. Smaller modules → smaller tasks → fewer zombies
and fewer serialize-or-conflict coordination constraints.

## Rules of engagement

1. **Mechanical splits only, one file per PR.** Move code + fix imports +
   re-export from the original module for backward compatibility where other
   files import from it. Zero behavior change; full test suite green is the
   review bar. CodeRabbit reviews every split.
2. **Behavior fixes ride separately.** #428's error-handling, savepoint, and
   preview-truncation findings are their own PR(s) AFTER the customer split —
   never mixed into a move-only diff.
3. **Service-layer convention** (ARCHITECT-003 pattern): standalone functions,
   `db: Session` first param, focused module names
   (`<domain>_<concern>_service.py`).
4. **Frontend extraction convention:** sections become components under a
   folder named for the page (`components/orders/...` exists — continue it);
   logic becomes hooks. Props stay explicit; no context-grab refactors.
5. **No new functionality in any DEBT-1 PR.**

## Batches (each = one agent, one PR; disjoint files → parallel-safe)

### Wave 1 (dispatch immediately; no overlap with SCHED-7 in flight)
- **D1-A** `sales_order_service.py` (3,541) →
  `sales_order_service.py` (CRUD/status/lifecycle, keeps public surface),
  `sales_order_fulfillment_service.py` (ship/fulfillment/legacy-resolution),
  `sales_order_requirements_service.py` (material requirements/explosion glue),
  `sales_order_production_service.py` (generate_production_orders + helpers).
- **D1-B** `item_service.py` (2,403) → per the standing design:
  `item_cost_service.py`, `item_duplicate_service.py`,
  `item_import_service.py`, slim `item_service.py` core.
- **D1-C** `OrderDetail.jsx` (2,021) → extract `OrderWorkflowPanel`,
  `LegacyFulfillmentBanner`, `OrderLineItemsTable`, `OrderHeaderActions` into
  `components/orders/`; page keeps state orchestration.

### Wave 2 (after SCHED-7 merges — it touches these areas)
- **D2-A** `production_order_service.py` (2,055) → release/gating module,
  completion/scrap module, core CRUD.
- **D2-B** `OperationSchedulerModal.jsx` (1,199) → extract conflict panels +
  slot-suggestion logic into hooks/subcomponents; modal keeps the form.
- **D2-C** `customer_service.py` (1,088) → split per #428 step 1
  (`customer_import_service.py`, validation module). Closes the ARCHITECT-001
  finding; remaining #428 findings spawn D2-D.
- **D2-D** #428 behavior fixes: typed exceptions, `begin_nested()` savepoints
  in bulk import, preview truncation indicator + validation-scope alignment.

### Wave 3 (owner pull, lower urgency)
inventory_service.py, purchase_order_service.py, endpoints/production_orders.py,
AdminLayout.jsx (nav config extraction), Onboarding.jsx, SalesOrderWizard.jsx.

## Regrowth prevention (lands with Wave 1)
- **AGENT_POLICY.md** gains: "New functionality goes in new modules. Files
  >1,200 lines (backend) / >800 lines (frontend components) must not accept
  new responsibilities — extract first or split as part of the change.
  Mechanical splits are always separate PRs from behavior changes."
- Multi-stack features dispatch as **separate backend and frontend tasks**
  (PM decision after the zombie cluster).

## Acceptance per PR
- `git diff --stat` shows moves, not rewrites (reviewer spot-checks bodies
  unchanged); imports updated; original module re-exports public names it
  previously exposed.
- Backend: ruff clean, full pytest green. Frontend: full vitest green, build
  green.
- No endpoint signature, response shape, or UI behavior changes.

## Outcome log
- (append per merge)
