# UX GTM-Readiness Plan

Date: 2026-06-09
Author: Claude (architect/PM session `claude-filaops-ux-review-20260609`)
Status: APPROVED FOR EXECUTION — each PR below is an independent work unit for a coding session
Source: three-domain UX review (order-to-cash, make/stock, IA/first-run) of the Core frontend

## How to use this document

Each PR section is a self-contained spec. A coding session should:

1. Register an Aeonyx session, claim ONLY the files listed for its PR, and work on a
   fresh feature branch off `main` (prefix `fix/` or `feat/` per AGENT_POLICY.md).
2. Read the listed files before editing (re-read after long context shifts).
3. Follow the acceptance criteria exactly; do not expand scope. If reality on `main`
   has drifted from a line reference here, trust the code and the acceptance criteria,
   not the line number.
4. Run the verification commands, open a PR, and complete the full bot-review triage
   loop per AGENT_POLICY.md before reporting done.
5. PRs within a phase are independent and parallelizable UNLESS a dependency is noted.
   Use separate worktrees for parallel sessions (see memory: separate branches do not
   isolate sessions).

Conventions that apply to every PR:

- Frontend tests: `cd frontend && npm run test:unit -- <TestFile>` then `npm run build`.
- Backend tests (where touched): `cd backend && python -m pytest tests/<file> -q` and
  `python -m ruff check app/ --select E712` for any new service code.
- No new dependencies without human approval.
- Tailwind: never build class names from template strings; the purger cannot see them.
- UOM: costs are $/kg, inventory is grams; single source is `backend/app/core/uom_config.py`.

---

## Phase 0 — Verification spikes (do FIRST, they gate two Phase 1 PRs)

### SPIKE-A: Spool weight unit truth

Question: are `spools.initial_weight_kg` / `current_weight_kg` stored in kilograms or
grams in practice?

- Inspect the backend model + schema for the spool table, any service code writing
  those columns, and 3-5 real rows in the local dev DB (`filaops`, never `filaops_prod`).
- Deliverable: a comment on PR-2's issue/branch stating the actual stored unit and
  whether existing data needs migration. PR-2's direction depends on this answer.

### SPIKE-B: Payment path convergence

Question: does `PATCH /api/v1/invoices/{id}` with `amount_paid`
(used by `AdminInvoices.jsx` `handleRecordPayment`) create a Payment record and GL
postings equivalent to the payments API used by `RecordPaymentModal`?

- Trace both backend paths (invoice endpoint vs payments endpoint/service).
- Deliverable: a short written trace. If the paths diverge, PR-7 must include the
  backend fix; if they converge, PR-7 is frontend-only.

---

## Phase 1 — GTM blockers and bug-class fixes (small, independent PRs)

### PR-1: Fix silent PRO tier-limit failures (closes #367)

Problem: `ApiErrorToaster.jsx:56-66` swallows `TIER_LIMIT_EXCEEDED` 403s, emitting a
`tier:limit-reached` event for `UpgradeModal` — but `UpgradeModal.jsx` is never mounted
anywhere. Community users hitting a PRO limit see nothing at all. Plain PRO 403s fall
through to a generic "You don't have permission" message that reads as a bug.

Scope:
- Mount `<UpgradeModal />` once in `App.jsx` next to `<ApiErrorToaster />`.
- In the tier-limit branch of `ApiErrorToaster.jsx`, also show a fallback
  `toast.info` so something always appears even if the modal listener fails.
- For non-tier PRO-feature 403s (identify the structured detail the backend sends),
  show "This is a PRO feature — view upgrade options" with a link to `/admin/license`
  instead of the generic permission message.

Files: `frontend/src/App.jsx`, `frontend/src/components/ApiErrorToaster.jsx`,
`frontend/src/components/UpgradeModal.jsx` (if it needs props/wiring), plus new/updated
unit tests for the toaster branch and modal mount.

Acceptance:
- Simulated `TIER_LIMIT_EXCEEDED` 403 → UpgradeModal opens AND an info toast appears.
- Simulated generic PRO 403 → friendly PRO message with license link, not
  "You don't have permission".
- `npm run build` passes; existing toaster tests still green.

Impact: HIGH — this is the monetization path. GTM blocker.

### PR-2: Spool weight UOM consistency (depends on SPIKE-A)

Problem: `AdminSpools.jsx` labels weight inputs "(g)" (~lines 381-401) but binds
`initial_weight_kg`/`current_weight_kg`, and renders the kg-named field with a "g"
suffix (~line 167). Either labels lie or values are off by 1000x.

Scope (direction set by SPIKE-A):
- Make labels, field bindings, table display, and the percent-remaining bar agree on
  one unit end-to-end, converting at the API boundary if needed.
- If stored data is inconsistent, write the Alembic migration in the SAME PR and flag
  it for human approval before merge (DB safety gate).

Files: `frontend/src/pages/admin/AdminSpools.jsx`, possibly backend spool
schema/service, possibly one Alembic migration. Add a unit test asserting the
display math for a known value.

Acceptance: entering a spool weight stores and round-trips the same physical quantity;
the table value, the bar percentage, and the edit form agree.

Impact: HIGH — data integrity; UOM rule violation.

### PR-3: Dead code purge (orphaned surfaces)

Problem: three orphaned surfaces invite drift and one is a data-integrity loaded gun.

Scope (dead-code-removal-only PR per AGENT_POLICY code-quality rule):
- Delete the legacy order-detail modal in `AdminOrders.jsx` (~lines 348-491): the
  `selectedOrder` state, `handleStatusUpdate`, `handleGenerateProductionOrder`, and the
  modal JSX. FIRST verify nothing calls `setSelectedOrder` (it should be dead — cards
  navigate to the route). Its raw status buttons bypass every invoice/production guard.
- Delete `frontend/src/pages/Setup.jsx` and replace the `/setup` route in `App.jsx`
  with a redirect to `/onboarding`. (Login redirects to `/onboarding`; Setup is
  unreachable and duplicates password validation.)
- Remove the commented-out Analytics nav entry in `AdminLayout.jsx` (~lines 582-588)
  OR un-comment it — decided by PR-13's nav design; for this PR just delete the
  commented block and note it.

Files: `frontend/src/pages/admin/AdminOrders.jsx`, `frontend/src/pages/Setup.jsx`
(delete), `frontend/src/App.jsx`, `frontend/src/components/AdminLayout.jsx`.

Acceptance: grep shows no references to the removed symbols; `/setup` redirects;
orders page behavior unchanged (cards still navigate to detail route); build + unit
tests green.

Impact: HIGH (removes unguarded status-override path), zero feature change.

### PR-4: Cross-page dead-end links

Problem: ledger pages strand the operator.

Scope:
- `AdminInvoices.jsx`: make Order # a link to `/admin/orders/{sales_order_id}` in both
  the table row (~377-379) and the detail modal (~487-489); add a "View Order" button
  in the modal action row. (Payments already links orders — match that pattern.)
- `AdminShipping.jsx`: when the `orderId` query param is present but the order is not
  in the fetched ready-to-ship set (~lines 355-378), render a banner: "Order {code}
  isn't ready to ship yet — production must complete." instead of silently showing
  nothing.
- `AdminBOM.jsx` (~line 137) and the `AdminProduction.jsx` create-modal success path:
  navigate to `/admin/production/{newOrderId}` (the detail page) after creating a
  production order, not the filtered list.

Files: `frontend/src/pages/admin/AdminInvoices.jsx`,
`frontend/src/pages/admin/AdminShipping.jsx`, `frontend/src/pages/admin/AdminBOM.jsx`,
`frontend/src/pages/admin/AdminProduction.jsx`.

Acceptance: each click path lands on the intended page; shipping deep-link with a
non-shippable order shows the banner; build green.

Impact: HIGH value / LOW cost.

### PR-5: Shipping tab Tailwind purge bug

Problem: `AdminShipping.jsx` (~610-617) builds classes like `border-${tab.color}-500`
from template strings; Tailwind purges them, so active-tab styling silently never
renders.

Scope: replace with a literal lookup map (`{ blue: "border-blue-500 bg-blue-500/20", ... }`).
Audit the rest of the file (and grep `frontend/src` for `-\$\{` in className contexts)
for the same anti-pattern; fix any other instances found in the same PR if ≤2 files,
otherwise file an issue.

Files: `frontend/src/pages/admin/AdminShipping.jsx` (+ at most one more file).

Acceptance: active tab visibly styled in dev; no template-string class construction
remains in touched files.

Impact: MED — broken styling on the core ship workflow.

### PR-6: Rename "Manufacturing" + distinct icon

Problem: "Manufacturing" (work centers/routings setup) and "Production" (execution)
are adjacent in nav with the identical icon path (`ManufacturingIcon` duplicates
`SettingsIcon` in `AdminLayout.jsx` ~176-196 vs ~346-366).

Scope:
- Rename nav label and page title to "Work Centers & Routings".
- Give it a distinct icon (any existing unused glyph or a simple new SVG path).
- Add a one-line page subtitle on `AdminManufacturing.jsx`: setup, not execution
  ("Define where and how things get made. Day-to-day orders live in Production.").
- Keep the route path unchanged (`/admin/manufacturing`) to avoid breaking links.

Files: `frontend/src/components/AdminLayout.jsx`,
`frontend/src/pages/admin/AdminManufacturing.jsx`.

Acceptance: nav shows new label + distinct icon; route unchanged; grep for hardcoded
"Manufacturing" strings in tests and update.

Impact: HIGH comprehension / trivial cost.

---

## Phase 2 — Consolidation (finish the abandoned migrations)

### PR-7: Single payment-recording path (depends on SPIKE-B)

Problem: `AdminInvoices.jsx` `handleRecordPayment` (~151-175) PATCHes the invoice with
`amount_paid` — a different path than the shared `RecordPaymentModal` used by
OrderDetail and AdminPayments. The two can produce different payment/GL state for the
same money.

Scope:
- Replace the bespoke inline payment form in `AdminInvoices.jsx` (~654-718) with the
  shared `RecordPaymentModal`, pre-filled with the invoice's order and open balance.
- If SPIKE-B found backend divergence: converge both endpoints on the same payment +
  GL posting service (backend change, pytest coverage for both entry points).

Files: `frontend/src/pages/admin/AdminInvoices.jsx`,
`frontend/src/components/payments/RecordPaymentModal.jsx` (props for invoice prefill),
plus backend service/endpoint + tests if SPIKE-B requires.

Acceptance: recording a payment from the Invoices page creates the identical Payment
record and GL entries as recording it from the order; the old PATCH path is no longer
reachable from the UI.

Impact: HIGH — cash/AR accuracy.

### PR-8: OrderDetail — one action surface

Problem: `OrderDetail.jsx` exposes Create Invoice / Generate PO / Ship in up to three
places (header ~997-1063, workflow card ~1066-1128, Quick Actions ~1130-1257) with
different gating logic.

Scope:
- The workflow card is canonical: every state-changing action appears there exactly
  once, gated by the existing guard functions with blocked-state tooltips.
- Slim the header to identity + status + Refresh.
- Reduce Quick Actions to idempotent tools only (Check Material Availability, View in
  Production, Open Invoice as a *link*), or remove the panel if nothing remains.
- While here: humanize the raw `{order.status}` string in Order Summary (~1316) with
  the same `.replace(/_/g, " ")` treatment used elsewhere.

Files: `frontend/src/pages/admin/OrderDetail.jsx` + its tests.

Acceptance: each state-changing action renders in exactly one place; all existing
workflow tests pass; no raw snake_case status visible.

Impact: HIGH — removes the worst "which button is real?" confusion.

### PR-9: ProductionOrderDetail — action dedupe + release guidance

Problem: Release/Start/Complete appear in both the header row (~362-400) and the
workflow step cards; Release ignores material readiness; draft orders look broken
(operations only exist after release, and the list's default filter hides drafts).

Scope:
- Keep workflow-card buttons (they carry context); slim the header to Refresh.
- Add a hint on the draft workflow card: "Operations are created when you release
  this order."
- Soft-warn on Release when the blocking-issues check reports `can_produce: false`
  (confirm dialog: "Materials are short — release anyway?"). Do NOT hard-block.
- `AdminProduction.jsx`: change the default status filter (~243) so newly created
  draft orders are visible (default to "all active" or include drafts).

Files: `frontend/src/pages/admin/ProductionOrderDetail.jsx`,
`frontend/src/pages/admin/AdminProduction.jsx`, + tests
(`ProductionOrderDetail.test.jsx` exists — extend it).

Acceptance: one button per action; releasing a short order shows the warning path;
fresh draft appears in the default Production list view.

Impact: HIGH for new-operator trust.

### PR-10: Adopt EmptyState everywhere

Problem: `components/EmptyState.jsx` is polished and tested with per-domain icons and
a CTA button — and has zero importers. Every list shows a bare "No X found" string.

Scope: replace hand-rolled empty strings with `<EmptyState>` + a create CTA on, at
minimum: AdminItems, AdminCustomers, AdminQuotes, AdminSpools, AdminOrders,
AdminInvoices, AdminPayments, AdminProduction, AdminBOM, AdminPurchasing. Distinguish
"no rows at all" (CTA to create) from "no rows matching filters" (CTA to clear
filters).

Files: ~10 page files + `EmptyState.jsx` if it needs a "clear filters" variant.
NOTE: exceeds the 5-file guideline — this plan doc is the required plan; keep the diff
mechanical (no behavior changes beyond the empty branch). Split into two PRs
(Sales pages / Inventory+Production pages) if review load demands.

Acceptance: every listed page shows an icon + title + CTA when empty; filtered-empty
shows "clear filters"; build + tests green.

Impact: HIGH for first-run experience (post-onboarding user sees blank tables today).

### PR-11: Adopt ConfirmDialog for destructive actions

Problem: 14 pages call native `window.confirm`; `ConfirmDialog.jsx` has one importer.
Native confirms break theming, can't be tested, and are easy to mis-click for
destructive ERP actions.

Scope: replace every `window.confirm` / bare `confirm(` in `frontend/src/pages` and
`frontend/src/components` with `ConfirmDialog`, with danger styling for
delete/cancel/void actions. Grep first; list all call sites in the PR description.

Files: ~14 page files + `ConfirmDialog.jsx`. Same >5-file note as PR-10; split
Sales/Ops if needed.

Acceptance: `grep -r "window.confirm\|[^a-zA-Z]confirm(" frontend/src --include="*.jsx"`
returns only ConfirmDialog internals/tests.

Impact: MED visual, HIGH destructive-action safety.

### PR-12: Adopt PaginationControls + badge unification

Scope:
- Wire `components/PaginationControls.jsx` (currently zero importers) into the highest-
  traffic lists (Orders, Items, Invoices, Customers, Production). Where search is
  client-side over a server-capped result set (100-200 rows), either move search
  server-side for that page or show a "showing first N" cap label — no silent misses.
- Unify status badges on the dark palette: `SalesOrderCard.jsx` (~10-17) uses
  light-theme `bg-green-100 text-green-800` badges on the dark UI; convert to the
  `/20`-opacity dark badge pattern used everywhere else. Extract a shared
  `StatusBadge` if one doesn't exist.

Files: ~5-7 pages + `SalesOrderCard.jsx` + possibly new `StatusBadge.jsx`.

Acceptance: paginated lists page correctly; no light-theme badges remain; cap labels
visible where search is client-side.

Impact: MED.

### PR-13: Navigation regroup + landing page swap

Problem: SALES nav order teaches the flow backwards (Orders, Quotes, Payments,
Invoices); Accounting hides under ADMIN; two dashboards compete; CommandCenter
double-pads inside AdminLayout.

Scope (one PR, mostly `AdminLayout.jsx` + `App.jsx`):
- Regroup nav:
  - SALES: Customers, Quotes, Orders, Shipping (moved from OPERATIONS)
  - MONEY (new): Invoices, Payments, Accounting (moved from ADMIN)
  - OPERATIONS (Make): Production, Work Centers & Routings, Printers, Spools
  - INVENTORY (Stock): unchanged + Cycle Count, Locations, Transactions
  - PURCHASING (Buy): Purchasing, Import Materials (moved from INVENTORY)
  - ADMIN: Users, Security, Settings, Integrations, License, Import Orders
  - Keep B2B PORTAL and QUALITY groups as-is.
- Make CommandCenter the `/admin` index route; rename AdminDashboard nav entry to
  "Analytics" (route can stay `/admin/dashboard`); remove the duplicated Action Items
  panel from AdminDashboard (CommandCenter keeps it); cross-link the two.
- Fix CommandCenter wrapper (~line 122): drop `min-h-screen p-6 bg-gray-900` when
  rendered inside AdminLayout's padded main.
- Migrate hardcoded `bg-gray-900/text-white` in CommandCenter + AdminDashboard to the
  CSS-variable tokens AdminLayout uses.

Files: `frontend/src/components/AdminLayout.jsx`, `frontend/src/App.jsx`,
`frontend/src/pages/CommandCenter.jsx`, `frontend/src/pages/admin/AdminDashboard.jsx`.

Acceptance: nav groups match the list above; `/admin` lands on CommandCenter with no
double padding; all old routes still resolve (no broken bookmarks); E2E smoke
(Playwright) over nav still passes.

Impact: HIGH — the home screen and the mental model.

DEPENDENCY: do after PR-6 (label rename) to avoid churn.

---

## Phase 3 — Feature work (design-first; backend + frontend)

### PR-14: Material consumption visibility (the big one)

Problem: consumption is backflushed silently server-side on operation completion. The
operator can never see what an order consumed — no planned-vs-actual, no spool/lot
attribution in the order view. Biggest trust gap for a filament farm.

Scope:
- Backend: expose a consumption ledger for a production order (planned qty per BOM
  line, consumed-so-far, remaining, and lot/spool attribution from existing
  inventory-transaction records). Likely a read-only endpoint composed from existing
  tables — verify with traceability_service before adding anything new.
- Frontend: "Materials" card on `ProductionOrderDetail.jsx` showing the ledger;
  completion toast surfaces the backflush result ("Consumed 412g PLA Black from
  SPL-0007") via the response of the existing `/complete` call in
  `OperationCompletionModal.jsx` (~219-236) — extend the response if needed.
- Spool linkage: show "assigned printer" on the production order (printers already
  poll `active-work`; reverse the link) — stretch goal, separate commit.

Process: design note (endpoint shape + card mock) reviewed by the user BEFORE
implementation. This is the one Phase 3 item worth a short design round-trip.

Impact: HIGH — traceability story is a GTM differentiator for this product.

### PR-15: Production create-modal parity

Problem: creating a production order from the BOM page is material-aware (max
producible, limiting component, backorder offer); creating from the Production page is
a bare form.

Scope: extract the availability-preview logic from
`components/bom/CreateProductionOrderModal.jsx` into a shared hook/component and use
it in `AdminProduction.jsx`'s create modal once a product is selected.

Impact: HIGH — prevents releasing un-buildable orders from the obvious entry point.

### PR-16: Inventory Transactions — simple/advanced mode

Problem: the New Transaction form exposes `reference_type`, raw `reference_id`, and
ledger-internal types (`consumption`, `issue`) that let a solo operator corrupt the
ledger (e.g. double-counting backflush).

Scope: default to three guided modes — Adjust / Receive / Transfer — with reason
codes; move raw type + reference plumbing behind an "Advanced" toggle (admin-role
only if RBAC supports it).

Impact: MED-HIGH — stock accuracy protection.

### PR-17: Cycle Count review step

Scope: before "Submit Count" posts adjustments + GL entries, insert a review screen:
"N adjustments, total variance $X — Confirm". Keep "Fill Current Qty" but move it away
from the submit button.

Impact: MED — guards an otherwise excellent flow against fat-fingers.

### PR-18: Onboarding — printer + money config

Problem: the 7-step onboarding (account, example data, 4 CSV imports, done) never asks
a *print farm* to add a printer, and captures no currency/locale, leaving invoices and
accounting misconfigured on day one.

Scope: add two steps to `Onboarding.jsx`: (a) "Connect your first printer" with a
skip option linking to `/admin/printers`; (b) expand the company step with
currency + locale (writes to company_settings — note the locale-column migration
gotcha in project memory).

Impact: HIGH for GTM first-run, MED effort.

### PR-19: Unified BOM/Routing recipe page (post-GTM candidate)

The existing parked design (`project_unified_bom_routing_page` in memory): make BOM
detail the canonical product-recipe surface — BOM lines + routing operations +
materials in tabs on one page; demote Manufacturing's Routings tab to a read-only list
deep-linking in. Routing is currently editable from two places, which is a
consistency hazard.

Process: full design doc first. Largest item in this plan; recommend scheduling after
GTM unless routing-edit conflicts bite sooner.

---

## Sequencing summary

```
Phase 0:  SPIKE-A  SPIKE-B            (half a day, gates PR-2 / PR-7)
Phase 1:  PR-1  PR-2  PR-3  PR-4  PR-5  PR-6     (all parallel, small)
Phase 2:  PR-7  PR-8  PR-9  PR-10  PR-11  PR-12  PR-13(after PR-6)
Phase 3:  PR-14(design first)  PR-15  PR-16  PR-17  PR-18  PR-19(post-GTM)
```

GTM-critical set (minimum to ship): SPIKEs, PR-1 through PR-6, PR-7, PR-10, PR-13,
PR-18. Everything else improves quality but does not block launch.

## Out of scope (explicitly deferred)

- Bulk actions on O2C lists (batch mark-sent / batch ship) — fine at current volume.
- Shared FilterBar extraction (five filter patterns exist; unify after PR-12 settles
  pagination/search semantics).
- Breadcrumb label resolution for detail routes — spot-check during PR-13; file an
  issue if raw IDs show.
