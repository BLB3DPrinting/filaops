# FilaOps Codebase Analysis

Date: 2026-06-17
Project path: `C:\repos\filaops`
Branch: `codex/codebase-analysis`

## Executive Summary

FilaOps is a full-stack ERP for 3D print farm operations. The public Core repo is a FastAPI/PostgreSQL backend with a React/Vite frontend, backed by Alembic migrations, pytest/Vitest/Playwright tests, and GitHub Actions workflows.

The architecture is feature-rich and mostly organized by business domain: sales, quoting, inventory, production, purchasing, MRP, accounting, traceability, maintenance, printers, settings, and security. The main technical risk is not missing structure; it is accumulated module size and mixed access patterns. Several backend services/endpoints and frontend pages/components are large enough that future work should bias toward extraction before adding responsibility.

## Phase 1: Discovery & Architecture

### Repository Shape

```text
.
├── backend/
│   ├── app/
│   │   ├── api/v1/endpoints/     FastAPI route handlers
│   │   ├── core/                 settings, security, paths, limiter, UOM constants
│   │   ├── db/                   SQLAlchemy engine/session/base
│   │   ├── integrations/         external integration helpers
│   │   ├── middleware/           request middleware
│   │   ├── models/               SQLAlchemy models
│   │   ├── schemas/              Pydantic request/response schemas
│   │   └── services/             business logic
│   ├── migrations/versions/      Alembic migration history
│   └── tests/                    backend tests
├── frontend/
│   ├── src/
│   │   ├── api/                  legacy axios-like fetch wrapper
│   │   ├── components/           shared and domain UI components
│   │   ├── contexts/             app/locale context
│   │   ├── hooks/                API, CRUD, formatting, feature hooks
│   │   ├── lib/                  API client, events, number/time/UOM utilities
│   │   ├── modules/              newer reusable module slices
│   │   └── pages/                route-level pages
│   └── tests/e2e                 Playwright tests
├── docs/                         user, reference, operations, plans
├── scripts/                      repo tooling
└── .github/workflows/            CI, docs, CodeQL, PRO guard, review workflows
```

### Tech Stack

Backend:

- Python 3.11+
- FastAPI `0.136.3`
- SQLAlchemy `2.0.50`
- PostgreSQL via `psycopg`
- Alembic migrations
- Pydantic v2 / pydantic-settings
- PyJWT, bcrypt, httpOnly cookie auth
- pytest, pytest-asyncio, pytest-cov
- Ruff and mypy configuration

Frontend:

- React `19.2.7`
- Vite `8.0.16`
- React Router `7.17.0`
- Tailwind CSS `4.x`
- lucide-react
- Vitest, Testing Library, Storybook, Playwright

Deployment and operations:

- Docker Compose
- FastAPI can optionally serve built frontend surfaces directly.
- Caddy/nginx style reverse proxy support is implied by frontend relative API URL logic.
- Sentry is optional via `SENTRY_DSN`.

### Size Signals

Observed counts:

- Backend application Python files: 264
- Backend Python test files: 149
- Frontend source JS/JSX/TS/TSX files: 338
- Frontend unit/component test files: 51
- Alembic migration files: 75
- Markdown docs files under `docs/`: 55

Largest backend files observed:

| File | Approx. lines | Note |
| --- | ---: | --- |
| `backend/app/services/sales_order_service.py` | 1972 | order lifecycle, conversion, totals, events, PDFs |
| `backend/app/services/inventory_service.py` | 1586 | inventory transactions, reservations, consumption, shipping |
| `backend/app/services/purchase_order_service.py` | 1581 | PO lifecycle, receiving, documents, events, PDFs |
| `backend/app/api/v1/endpoints/production_orders.py` | 1456 | route layer for production workflow |
| `backend/app/api/v1/endpoints/security.py` | 1424 | security audit route layer |
| `backend/app/services/bom_management_service.py` | 1317 | BOM management |
| `backend/app/services/item_service.py` | 1270 | unified item management |
| `backend/app/services/quote_service.py` | 1231 | quote lifecycle, pricing, PDFs |

Largest frontend files observed:

| File | Approx. lines | Note |
| --- | ---: | --- |
| `frontend/src/pages/Onboarding.jsx` | 1345 | first-run setup flow |
| `frontend/src/pages/admin/AdminInventoryTransactions.jsx` | 1317 | inventory transaction UI |
| `frontend/src/components/SalesOrderWizard.jsx` | 1311 | sales order creation flow |
| `frontend/src/pages/admin/OrderDetail.jsx` | 1274 | order detail workflow |
| `frontend/src/components/production/ProductionOrderModal.jsx` | 1164 | production order modal |
| `frontend/src/components/AdminLayout.jsx` | 1084 | layout, nav, auth guard, PRO entry |
| `frontend/src/pages/admin/AdminPrinters.jsx` | 1048 | printer admin UI |
| `frontend/src/pages/admin/AdminSettings.jsx` | 993 | settings UI |

The repo policy says backend Python files over 1,200 lines and frontend components/pages over 800 lines should not accept new responsibilities without extraction. Many current hotspots already exceed those limits.

### Backend Architecture

`backend/app/main.py` is the application composition root. It handles:

- structured logging setup
- optional Sentry setup
- security headers middleware
- CORS configuration, including PRO origin loading from DB/env
- rate limiting setup
- database connectivity check during lifespan startup
- first-run user existence check
- API router inclusion under `/api/v1`
- uploaded static file mounting
- optional Core SPA and PRO surface SPA hosting
- optional plugin loading via `FILAOPS_PRO_MODULE`
- root and `/health` endpoints
- global exception handlers

`backend/app/api/v1/__init__.py` is the API router registry. It imports and mounts endpoint modules for auth, setup, sales, quotes, products/items, production, operation status, inventory, materials, admin, vendors, purchasing, invoices, notifications, manufacturing resources/routings, MRP, buy list, scheduling, settings, tax, price levels, payments, accounting, printers, system, license, security, spools, quality, traceability, maintenance, command center, and dispatch.

`backend/app/api/v1/deps.py` centralizes core FastAPI dependencies:

- DB session dependency through `get_db`
- auth via httpOnly `access_token` cookie first, then bearer token fallback
- active-user check
- admin guard
- staff guard for admin/operator access
- standardized offset/limit pagination

`backend/app/core/settings.py` is the configuration source. It reads `backend/.env`, supports DB URL or DB parts, rejects placeholder secrets/passwords in production, validates CORS inputs, controls optional frontend/surface dist paths, and contains business defaults for pricing, material costs, MRP, manufacturing, email, shipping, licensing, and storage.

`backend/app/core/uom_config.py` is a critical invariant holder. For default filament materials, storage/consumption is in grams, purchasing is in kilograms, and costs are referenced per kilogram. The policy also states not to duplicate UOM conversion assumptions elsewhere.

### Frontend Architecture

`frontend/src/main.jsx` mounts React under `StrictMode`.

`frontend/src/App.jsx` defines the route tree with `BrowserRouter`, `Routes`, and lazy-loaded route components. Public-ish routes include onboarding/setup, login, forgot/reset password, and pricing. The `/admin` branch uses `AdminLayout` and contains most operational pages: dashboard/command center, orders, quotes, payments, invoices, customers, BOM, items, purchasing, manufacturing, production, shipping, analytics, imports, inventory transactions, cycle count, users, accounting, printers, spools, quality, catalogs, price levels, license, integrations, settings, and security.

`frontend/src/components/AdminLayout.jsx` is a major shell component. It owns navigation groups, sidebar/mobile menu behavior, localStorage hints for `adminUser`, role-based nav filtering, logout behavior, and the admin outlet.

`frontend/src/config/api.js` determines `API_URL` by priority:

1. runtime `window.__FILAOPS_CONFIG__.API_URL`
2. build-time `VITE_API_URL`
3. relative URL when served over HTTPS or non-localhost host
4. `http://localhost:8000` for local dev

`frontend/src/lib/apiClient.js` is the newer fetch wrapper. It includes credentials, JSON parsing, retry behavior, typed `ApiError`, API error events, and single-flight silent refresh on 401 through `/api/v1/auth/refresh`.

`frontend/src/hooks/useApi.js` exposes a memoized shared client from `apiClient.js` and handles genuine unauthorized state by clearing `adminUser` and redirecting to `/admin/login`.

There is also `frontend/src/api/axios.js`, an older axios-like fetch wrapper, still used at least by `frontend/src/components/purchasing/DocumentUploadPanel.jsx`. Many components also call `fetch` directly.

### Data And Domain Model

SQLAlchemy model classes cover:

- Sales: `Customer`, `SalesOrder`, `SalesOrderLine`, `Quote`, `QuoteLine`, `QuoteMaterial`, `Payment`, `Invoice`
- Purchasing: `Vendor`, `PurchaseOrder`, `PurchaseOrderLine`, `PurchaseOrderDocument`, `VendorItem`, `PurchasingEvent`
- Inventory: `Product`, `Inventory`, `InventoryLocation`, `InventoryTransaction`, `MaterialInventory`, `MaterialSpool`
- Manufacturing: `BOM`, `BOMLine`, `ProductionOrder`, production operations/materials, routings, resources, work centers, scrap
- Planning: `MRPRun`, `PlannedOrder`, maintenance windows
- Accounting: GL accounts, fiscal periods, journal entries, journal lines
- Traceability: serial numbers, material lots, production lot consumption, customer traceability profiles
- System: users, refresh tokens, password resets, settings, tax rates, price levels, notifications

The service layer is broad and mostly domain-oriented. Key service clusters include:

- sales/order-to-cash: `sales_order_service.py`, fulfillment/production/requirements helpers, `quote_service.py`, `quote_conversion_service.py`, `invoice_service.py`, `payment_service.py`
- inventory/material movement: `inventory_service.py`, `inventory_transaction_service.py`, `inventory_ledger.py`, `transaction_service.py`, `reservation_reconciliation_service.py`
- manufacturing/MRP: `production_order_service.py`, release/execution services, `mrp.py`, `requirement_explosion.py`, `supply_netting.py`, `routing_service.py`, scheduling/resource services
- purchasing/procurement: `purchase_order_service.py`, `buy_list_service.py`, vendor services
- traceability/quality: `traceability_service.py`, `quality_service.py`, lot policy
- settings/security/ops: license, security audit, command center, notifications, email, file storage

## Phase 2: Component Analysis

### Application Composition And Plugin Boundary

Core uses a clean plugin boundary in `backend/app/main.py`: optional plugins are loaded by dotted module name from `FILAOPS_PRO_MODULE`, and only a callable `register(app)` is invoked. This supports the repo policy that PRO imports Core and Core must not import PRO.

Strengths:

- Core has no hard package dependency on PRO.
- Missing plugin module starts Community mode instead of crashing.
- Registration failure is logged and isolated.
- Optional PRO surfaces are served by configured dist paths rather than Core importing PRO frontend code.

Risks:

- `main.py` is large and operationally dense. Startup configuration, middleware, CORS, plugin loading, SPA serving, and exception handling are all in one file.
- CORS origin loading reaches into endpoint/model code during app construction, which is pragmatic but adds boot-time coupling.

Recommendation: future changes to SPA/static/plugin bootstrapping should move into focused modules such as `app/bootstrap/cors.py`, `app/bootstrap/static_surfaces.py`, and `app/bootstrap/plugins.py` before expanding behavior.

### Authentication And Authorization

Auth is cookie-first with bearer fallback. `get_current_user` resolves the token, decodes it with `get_user_from_token`, loads the user, and rejects inactive users. Guards are simple:

- `get_current_admin_user`: requires `is_admin`
- `get_current_staff_user`: requires account type `admin` or `operator`

Strengths:

- Browser auth uses httpOnly cookies rather than frontend token storage.
- Bearer fallback keeps programmatic/API use possible.
- Frontend client supports silent refresh and shared refresh single-flight.

Risks:

- Some endpoints import auth helpers from `endpoints/auth.py` while others use `api/v1/deps.py`. The newer central dependency file is cleaner.
- Frontend API calls are not consistently routed through the refresh-aware `useApi` path.

Recommendation: standardize backend imports on `app.api.v1.deps` and gradually migrate frontend direct `fetch`/`api/axios` calls to `useApi` or a documented upload-specific wrapper.

### Sales, Quotes, And Order-To-Cash

The sales domain is one of the heaviest areas:

- `sales_order_service.py` handles order number generation, listing, validation, creation, quote conversion, status changes, payment/shipping updates, line edits, close-short logic, external order confirmation/rejection, events, and packing slip PDF generation.
- `quote_service.py` handles quote number generation, stats, detail, tax, customer discounts, create/update/status, conversion, image handling, and PDF generation.
- Frontend pages/components include `AdminOrders`, `OrderDetail`, `SalesOrderWizard`, `AdminQuotes`, quote modals, payment/invoice/admin pages.

Strengths:

- Business workflows are explicit and mostly service-layer driven.
- Quote-to-order conversion exists as a first-class pathway.
- Event history and PDF generation are integrated.

Risks:

- Service files combine orchestration, validation, mutation, total calculation, document generation, and event work.
- PDF generation inside large services makes domain changes and rendering changes collide.
- Frontend order/quote workflows are large and likely hard to test exhaustively.

Recommendation: prioritize extraction around document rendering, line mutation/totals, and lifecycle state transitions. Keep behavior-preserving extraction separate from feature changes.

### Inventory, UOM, And Material Movement

Inventory is central to FilaOps. `inventory_service.py` covers default locations, inventory consistency validation, transactions, production material reservations, operation material allocation sync/backfill, release/consume flows, receiving finished goods, shipping material consumption, and shipment processing.

The UOM architecture is explicit: materials default to storage in grams and purchasing/costing by kilogram. `uom_config.py`, `product_uom_service.py`, `uom_service.py`, and `item_cost_service.py` are important supporting modules.

Strengths:

- UOM rules are documented in code and recognized by repo policy.
- Inventory movement appears transaction/event oriented rather than hidden in UI code.
- Reservation, consumption, receiving, and shipping concerns are visible as separate named functions.

Risks:

- Any feature touching material quantities, cost, reservations, production completion, receiving, or shipping has high blast radius.
- Multiple large services interact with inventory, so regression tests should be workflow-based, not only unit-level.

Recommendation: enforce a rule for future work: if it touches quantity or cost, tests must include UOM conversion and inventory ledger/reservation assertions.

### Manufacturing, Routing, Scheduling, And Dispatch

Manufacturing spans many modules:

- `production_order_service.py` handles order code generation, routing copy, CRUD, cancellation/hold/scheduling, work center queues, QC, scrap, operation updates, material availability, cost breakdown, material variant swaps, and spool assignment.
- `production_order_release_service.py`, `production_order_execution_service.py`, and `production_execution.py` indicate newer extraction points.
- `routing_service.py`, resource scheduling/compatibility services, maintenance windows, and dispatch services provide scheduling capacity.
- API endpoints include production orders, operation status, work centers, resources, routings, scheduling, maintenance windows, and dispatch.

Strengths:

- Production workflows are modeled explicitly: operations, materials, scrap, QC, spools, resource scheduling, maintenance windows.
- Dispatch and scheduling have separate services, suggesting a path away from monolithic production logic.

Risks:

- Production order endpoint/service files remain large enough to be risky for new features.
- Scheduling touches resources, maintenance windows, production operations, and MRP, so local edits can create cross-domain regressions.

Recommendation: treat scheduling/dispatch work as integration work. Always test with production operation, resource compatibility, and maintenance-window scenarios.

### MRP And Procurement

`MRPService` in `backend/app/services/mrp.py` runs MRP, explodes BOMs, calculates net requirements, generates planned orders, gathers demand/supply, deletes unfirmed planned orders, and releases planned orders into purchase or production orders.

Purchasing centers on `purchase_order_service.py`, which handles PO lifecycle, receiving, document upload, events, and PDF generation. Buy-list and supply-netting services support procurement decisions.

Strengths:

- MRP concepts are first-class: component requirements, net requirements, MRP results, planned orders, firm/release actions.
- Purchasing and buy-list views connect planning to execution.

Risks:

- `settings.py` documents that some auto-MRP flags are not yet functional. Enabling them before background task wiring would be unsafe.
- MRP release creates downstream purchasing/production records, so transaction boundaries matter.

Recommendation: keep auto-MRP disabled until background execution and idempotency are proven. Add tests around repeated MRP runs, firmed vs unfirmed planned orders, and release side effects.

### Frontend UI Structure

The frontend is operational rather than marketing-oriented: dense admin pages, modals, tables, dashboards, and workflow screens. The current route tree is centralized in `App.jsx`, and the admin shell is centralized in `AdminLayout.jsx`.

Strengths:

- Route-level pages are clear and discoverable.
- Domain components are increasingly grouped under folders such as `production`, `purchasing`, `quotes`, `routing`, `items`, `command-center`, and `settings`.
- Utility libraries for numbers, time, UOM, status colors, and API errors are present.

Risks:

- Several route pages and modal components are above the repo threshold for new responsibilities.
- Direct `fetch` usage is widespread, which can bypass shared auth refresh, retry, and error handling.
- `App.jsx` and `AdminLayout.jsx` are coordination hotspots for routing/navigation changes.

Recommendation: use route-level extraction for large pages and custom hooks for data-loading/mutation logic. For API consistency, prefer `useApi` unless a specialized upload/progress pathway is required.

### Testing And CI

Backend:

- pytest configuration exists in both `pyproject.toml` and `backend/pytest.ini`.
- Tests run against PostgreSQL in CI.
- Coverage reporting is configured but appears informational rather than threshold-gated.
- Ruff runs in the broader `test.yml` workflow.

Frontend:

- Vitest with jsdom for unit/component tests.
- Storybook/Vitest browser integration exists.
- Playwright E2E scripts exist, but E2E jobs in `test.yml` are disabled with `if: false`.
- Root package also exposes Playwright scripts.

CI:

- `.github/workflows/filaops-ci.yml` is a manual workflow that installs dependencies, runs Alembic, boots API, pings `/health`, audits dependencies non-blockingly, and builds frontend.
- `.github/workflows/test.yml` is also manual and broader, with backend tests, frontend tests, build validation, and disabled E2E/sprint jobs.
- `.github/workflows/pro-guard.yml` checks that public Core does not include PRO paths.
- CodeQL, docs, and review workflows are present.

Risks:

- Workflows are `workflow_dispatch` only, so CI may not automatically run on every push/PR unless another system handles that.
- Security audits are non-blocking.
- E2E tests are disabled in CI despite this being a workflow-heavy ERP.

Recommendation: for high-risk domains, run targeted local tests and then manually trigger the relevant CI workflow. Consider re-enabling a small smoke E2E subset before broader E2E.

## Phase 3: Documentation & Recommendations

### Recommended Engineering Priorities

1. Decompose oversized files in behavior-preserving PRs.
   Start with files most frequently touched by feature work: `sales_order_service.py`, `inventory_service.py`, `purchase_order_service.py`, `quote_service.py`, `AdminLayout.jsx`, `SalesOrderWizard.jsx`, and `OrderDetail.jsx`.

2. Standardize frontend API access.
   Document the intended client path. Prefer `useApi`/`apiClient.js` for normal JSON calls and create one approved upload/progress wrapper if needed. Track direct `fetch` as migration debt.

3. Protect UOM and inventory invariants.
   Any change involving quantities, costs, reservations, receiving, shipping, or production completion should include tests for storage unit vs purchase unit behavior.

4. Keep Core/PRO boundary explicit.
   Continue config-driven plugin loading only. Do not add Core imports from PRO packages. Keep PRO CORS/surface handling behind config and database settings.

5. Split document/PDF generation out of lifecycle services.
   Quote PDFs, packing slips, and PO PDFs are rendering concerns. Moving them into focused renderer modules will reduce service blast radius.

6. Improve CI confidence for workflow-heavy areas.
   Re-enable or add a small Playwright smoke suite for login, order creation, production release, purchasing receive, and inventory transaction flows.

7. Align backend dependency imports.
   Prefer `app.api.v1.deps` for auth/session dependencies instead of endpoint-to-endpoint imports.

8. Maintain generated reference docs after endpoint/model/migration changes.
   Existing `API-REFERENCE.md`, `SCHEMA-REFERENCE.md`, and `MIGRATIONS-LOG.md` are large and likely important release artifacts.

### Suggested Refactor Sequence

Low-risk first:

1. Extract PDF rendering helpers from sales/quote/purchase services.
2. Extract frontend data hooks from the largest pages without changing UI.
3. Standardize API wrapper usage for one small domain, then repeat.
4. Extract sales order line/totals logic into a focused service.
5. Extract inventory reservation and consumption flows into smaller modules.
6. Extract route registration/bootstrap helpers from `main.py`.

High-risk later:

1. MRP auto-trigger/background execution.
2. Scheduling/dispatch algorithm changes.
3. Production material reservation and consumption changes.
4. Core/PRO plugin activation or licensing contract changes.
5. Auth/session/cookie behavior changes.

### Work Rules For Future Agents

- Read `AGENT_POLICY.md` first.
- Work on a feature branch.
- Claim files before edits when Aeonyx/T-REX tools are available.
- Do not modify Core from PRO or add Core dependencies on PRO.
- For files above policy limits, extract before adding new responsibility.
- Keep behavior-preserving moves separate from behavior changes.
- Re-read touched files before and after edits.
- For DB work, confirm `DATABASE_URL` targets local `filaops`, not production.
- Use lockfile-respecting installs and avoid accidental lockfile churn.
- Run the narrowest meaningful tests first, then broaden as risk requires.

### Suggested Test Strategy By Change Type

| Change type | Minimum local checks |
| --- | --- |
| Backend endpoint/service logic | targeted pytest for endpoint/service, plus affected model/schema tests |
| Inventory/UOM/cost logic | pytest covering UOM conversion, ledger transaction, reservations, and downstream workflow |
| Production/scheduling | pytest for production operation state, resource compatibility, maintenance windows, dispatch side effects |
| MRP/procurement | pytest for BOM explosion, net requirements, planned order generation, firm/release behavior |
| Frontend UI component | targeted Vitest/Testing Library test, visual/manual check if layout-heavy |
| Frontend route/workflow | targeted Vitest plus Playwright smoke when user-facing |
| Auth/session/API client | frontend API client tests, backend auth tests, browser session manual test |
| Migrations | `alembic upgrade head`, migration-specific pytest, schema reference regeneration |
| Docs/reference updates | docs build, reference regeneration skill/process if endpoint/model/migration changed |

### Open Questions

- Should GitHub Actions run on PR/push in addition to manual dispatch, or is CircleCI/the review council the primary automatic gate?
- Which frontend API wrapper is the intended long-term standard for file uploads with progress?
- Should the existing god-file decomposition plan become an enforced roadmap with tracked issues?
- Are the disabled E2E jobs intentionally parked, or should a smoke-only subset be restored?
- Are generated references expected to be regenerated in every endpoint/model PR or only release PRs?

## Session Notes

This analysis did not modify application code. It added this documentation file and `codebase-analysis-progress.md` only.
