# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [3.4.0] - 2026-03-12

### Added
- Raw material/filament as sales order line items — fractional quantities, material cost tracking (#362)
- Nepal locale (ne-NP), NPR currency, Asia/Kathmandu timezone (#387)
- B2B Portal admin pages — Access Requests, Catalogs, Price Levels (PRO-gated)
- Portal nginx proxy with priority prefix matching and bare-path redirect
- T-REX pre-commit hook for branch governance (.githooks/pre-commit)
- Docker entrypoint: atomic portal extract with staging dir, error handling

### Fixed
- Walk-in customer orders — customer_id no longer required (#361)
- PRO feature 403s show "PRO Feature" upgrade cards instead of error toasts (#367)
- Docker security audit "Fix It For Me" handles missing .env (#366)
- Password reset UX for single-admin deployments (#360)
- Await async fetchRequests in access request action handlers
- Re-resolve stale assigningLevel after price level refresh
- Check DELETE response before updating UI state (CustomerDetailsModal)
- Clear setup link banner when switching access request filters
- LICENSE_URL scoping bug in docker-entrypoint.sh

### Dependencies
- sqlalchemy 2.0.46 → 2.0.48, postcss 8.5.6 → 8.5.8
- react-router 7.13.0 → 7.13.1, lucide-react 0.575.0 → 0.577.0
- storybook ecosystem 10.2.11 → 10.2.16
- types-python-dateutil 2.9.0.20260124 → 2.9.0.20260305

## [3.3.0] - 2026-03-01

### Added
- **Internationalization (i18n) foundation** — `LocaleContext` provider fetches company locale/currency at mount and exposes `useFormatCurrency()` and `useFormatNumber()` hooks to the entire component tree. Defaults to USD/en-US. 21 ISO 4217 currencies and 20 BCP-47 locales supported.
- **Regional Settings UI** — New section in Admin Settings with currency and locale dropdowns, wired directly into company settings. Live preview shows how numbers and currency will render.
- **Multi-tax rate system** — New `tax_rates` table with full CRUD API (`/api/v1/tax-rates`). Supports named rates (e.g. "GST 10%", "VAT 20%"), default rate selection, and soft-delete. Tax resolution hierarchy: specific rate > default rate > legacy CompanySettings fallback.
- **Multi-tax frontend** — QuoteFormModal shows legacy checkbox for 0–1 rates, switches to dropdown selector for 2+ rates. Admin Settings gets a Tax Rates management section with inline add, set-default, and remove.
- **PRO extension points** — `plugin_registry.py` module + `/api/v1/system/info` endpoint expose tier/features at runtime. `load_plugin()` in main.py supports environment-variable-driven plugin loading via `register(app)` pattern. Frontend `useApp()` hook fetches tier info at startup.
- **98 new frontend unit tests** — i18n hooks, locale context, currency formatting, number formatting. New `vitest.unit.config.js` isolates unit tests from Storybook. Frontend unit tests now run in CI.
- **Component-level currency integration tests** for all 7 remaining currency-bearing components.

### Fixed
- Replaced 48 hardcoded dollar signs across 10 components with `useFormatCurrency()` hook — all currency displays now respect company locale and currency code
- Upload directory resolution: replaced hardcoded `/app/uploads/...` paths with `Path(__file__)`-based resolution that works in Docker, CI, and local dev (#365)
- `FileStorageService` startup: `mkdir` wrapped in `try/except` so non-writable paths log an error instead of crashing the app at import time (#365)
- Module-level locale defaults synced so non-hook code (PDFs, modals) picks up company currency
- SQLAlchemy boolean filters changed from `== True` to `.is_(True)` for ruff E712 compliance
- Migration 058 seed INSERT made explicit for columns without defaults (PostgreSQL compatibility)

### Refactored
- Replaced 13+ local `formatCurrency` definitions across 15 files with centralized `useFormatCurrency()` hook, `useLocale()` for chart axes, and `formatCurrency` from `lib/number.js` for module-level code
- Currency-aware PDF generation: `quote_service.py _fmt()` helper replaces hardcoded `$` with proper currency symbol from 21-currency symbol map

## [3.2.0] - 2026-02-25

### Refactored
- **Consolidated BOM/routing editors** — Replaced 5 duplicate components (`BOMEditor`, `ManufacturingBOMEditor`, `BOMRoutingSection`, `useRoutingManager`, `AddOperationMaterialForm`) with a single `RoutingEditorContent`. Net -2,852 lines. (#358)

### Fixed
- Material cost UOM conversion: `unit_cost` now divides by `purchase_factor` (e.g. $20/KG ÷ 1000 = $0.02/G) — previously ~1000x too high for filament (#358)
- Same UOM bug in fulfillment queue material consumption (#358)
- Timezone naive/aware datetime mismatches across 9 locations in 7 files: `Quote.is_expired`, quote schemas, quote stats, auth token purge, password reset, command center, operation completion, maintenance, inventory, accounting (#358)
- Work center rate field mismatch: frontend referenced nonexistent `labor_rate`/`machine_rate` instead of `total_rate_per_hour` — unsaved operations showed $0.00 (#358)
- Operation/material cost display: OperationRow now uses backend-computed `calculated_cost` and shows material `extended_cost` (#358)
- CodeRabbit review fixes: stale closure, material fetch fan-out, embedded save button, stale materials on delete (#358)
- BOM page material save restored after OperationMaterialModal refactor (#357)

### Performance
- Fixed N+1 query patterns in items list and dashboard endpoints (#356)

### Added
- Dev seed script for local development (`backend/scripts/seed_dev_data.py`) (#355)
- Walkthrough screenshot Playwright tests (#355)

### Dependencies
- 12 dependency upgrades (Dependabot consolidation) (#354)

## [3.1.1] - 2026-02-23

### Fixed
- Product `customer_id` foreign key now correctly references `customers` table (#338)
- Stack trace exposure prevented in API error responses (#335)
- PostgreSQL session timezone forced to UTC; naive DB datetimes handled correctly (#336)
- Import reordering in `fulfillment_queue.py` for E402 compliance (#337)
- Datetime deprecation warnings, auth cleanup, and frontend fixes (Session 13 code review)
- Pre-push hook scoped to only block pushes to public repo

### Security
- Resolved 6 CodeQL security alerts and dismissed 5 false positives (#339)

### Changed
- Configurable database connection pool size (#338)
- PRO code isolation safeguards added (#301)
- Documentation site branded with BLB3D identity
- User manual replaced developer reference documentation
- README updated for v3.1.0 release (#300)

### Dependencies
- sqlalchemy 2.0.36 → 2.0.46 (#327)
- pydantic-settings 2.12.0 → 2.13.0 (#325)
- email-validator 2.2.0 → 2.3.0 (#318)
- alembic 1.18.3 → 1.18.4 (#329)
- reportlab 4.4.9 → 4.4.10 (#328)
- types-python-dateutil updated (#322)
- lucide-react 0.562.0 → 0.564.0 (#334)
- eslint-plugin-react-refresh updated (#330)
- @types/react 19.2.13 → 19.2.14 (#326)
- actions/checkout 4 → 6 (#317)
- actions/setup-python 5 → 6 (#319)
- actions/upload-pages-artifact 3 → 4 (#320)
- github/codeql-action 3 → 4 (#316)

## [3.1.0] - 2026-02-12

### Added
- Frontend unit testing with Vitest + React Testing Library (56 component tests)
- CI security audits: pip-audit and npm audit run on every push
- Rate limiting on bulk import/export endpoints (30/minute)
- Runtime API URL config for Docker via `window.__FILAOPS_CONFIG__`
- Barrel exports (`index.js`) for 15 frontend component directories
- Shared status color system (`statusColors.js`) for consistent badges
- Comprehensive user guide covering all FilaOps modules
- Deployment docs: Docker quickstart, prerequisites, troubleshooting
- Backup and recovery documentation
- API conventions documentation with response_model patterns

### Changed
- SQLAlchemy 2.0: replaced 33 deprecated `Query.get()` calls with `Session.get()`
- CSS theming: auth pages and forms migrated to CSS custom properties
- Form accessibility: proper labels, ARIA attributes, error announcements
- Docker: non-root container user, correlation IDs in logs
- Removed deprecated `Machine` model alias; use `Resource` from `manufacturing.py` directly
- Expanded `.env.example` to cover all settings groups
- Frontend: all 70+ components migrated from manual `Authorization` header to `credentials: "include"`

### Fixed
- Accounting rounding errors and BOM cost calculation bugs (#209, #211, #212)
- Unicode checkmark crash in migration 039 on Windows (cp1252 encoding)
- UI bugs and performance issues from walkthrough (#216)
- Removed 10 debug console.log statements from production frontend code
- Version sync between backend VERSION file and settings

### Security
- **Auth tokens migrated from localStorage to httpOnly cookies** — prevents XSS token theft
  - All browser-based auth now uses httpOnly cookies with `SameSite=Lax`
  - `AUTH_MODE` env var (`cookie`/`header`) for rollback safety
  - `COOKIE_SECURE` env var — set `true` in production (requires HTTPS)
  - Programmatic API access via `Authorization: Bearer` header still supported
  - Tokens are **no longer returned** in login/register response bodies (cookie mode)
- Password reset approve/deny changed from GET to POST — prevents CSRF and browser prefetch side effects
- Rate limiting added to token refresh endpoint (`10/minute`)
- Rate limiting added to password reset approve/deny endpoints (`10/minute`)
- Server-side refresh token revocation on logout

## [3.0.1] - 2026-02-06

### Added
- Backend test coverage pushed from 65% to 80% (PR #218)
- Review Council CI integration for automated code review
- CSV formula injection prevention in export endpoints
- Health check endpoint with database connectivity verification
- Structured JSON logging with audit trail
- Security headers middleware (X-Frame-Options, X-Content-Type-Options, CSP)
- Rate limiting on authentication endpoints
- Shared Modal component with ARIA accessibility

### Fixed
- Export service: wrong attribute name `p.inventory` → `p.inventory_items` (PR #219)
- Export service: string-to-datetime comparison in date filtering (PR #219)
- Fulfillment reprint: used read-only `quantity` property instead of `quantity_ordered` (PR #219)
- Traceability service: `po.completed_date` → `po.completed_at` (2 occurrences) (PR #219)
- Command center: `so.order_date` → `so.created_at` (PR #219)
- N+1 query in dashboard and BOM endpoints (PR #185)
- MRP test isolation issues (PR #184)
- Alembic migration chain after PRO migration removal

### Changed
- **ARCHITECT-003**: Extracted service layer across all endpoint files (PRs #206-#214)
  - Batch 1: locations, vendors, products, work centers
  - Batch 2: routings, purchase orders, materials, items, sales orders, production orders
  - Batch 3: BOM, quotes, accounting
  - Batch 4: customers, traceability, analytics
  - Batch 5: inventory transactions, orders, imports, exports
- **ARCHITECT-002**: Split 15 frontend god files into focused sub-components (PRs #191-#205)
- Frontend switched to production nginx build (PR #187)

### Security
- Sanitized domain input to prevent command injection (GUARDIAN-001)
- Moved Sentry DSN to environment variable (GUARDIAN-002)
- Used settings.SECRET_KEY instead of direct os.environ (GUARDIAN-004)
- Medium-priority security fixes: GUARDIAN-007/008/009/010 (PR #190)

## [3.0.0] - 2026-01-01

### Added
- Initial open-source Community Edition release
- 37 core features across 8 modules:
  - Sales (quotes, orders, fulfillment, blocking issues)
  - Inventory (multi-location, transactions, cycle counting, spool tracking)
  - Manufacturing (production orders, BOMs, routings, work centers, scrap)
  - Purchasing (purchase orders, receiving, vendor management)
  - MRP (demand calculation, supply netting, planned orders)
  - Accounting (chart of accounts, journal entries, GL reporting)
  - Traceability (lots, serials, material consumption history)
  - Printing (MQTT monitoring, print jobs, resource scheduling)

### Removed
- B2B Portal features (moved to PRO edition)
- Price levels / customer tiers (PRO)
- Shopify and Amazon integrations (PRO)
- AI Invoice Parser (PRO)
- License management (PRO)

[Unreleased]: https://github.com/Blb3D/filaops/compare/v3.4.0...HEAD
[3.4.0]: https://github.com/Blb3D/filaops/compare/v3.3.0...v3.4.0
[3.3.0]: https://github.com/Blb3D/filaops/compare/v3.2.0...v3.3.0
[3.2.0]: https://github.com/Blb3D/filaops/compare/v3.1.1...v3.2.0
[3.1.1]: https://github.com/Blb3D/filaops/compare/v3.1.0...v3.1.1
[3.1.0]: https://github.com/Blb3D/filaops/compare/v3.0.1...v3.1.0
[3.0.1]: https://github.com/Blb3D/filaops/compare/v3.0.0...v3.0.1
[3.0.0]: https://github.com/Blb3D/filaops/releases/tag/v3.0.0
