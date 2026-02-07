# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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

### Changed
- Removed deprecated `Machine` model alias; use `Resource` from `manufacturing.py` directly
- Expanded `.env.example` to cover all settings groups
- Frontend: all 70+ components migrated from manual `Authorization` header to `credentials: "include"`

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

[Unreleased]: https://github.com/Blb3D/filaops/compare/v3.0.1...HEAD
[3.0.1]: https://github.com/Blb3D/filaops/compare/v3.0.0...v3.0.1
[3.0.0]: https://github.com/Blb3D/filaops/releases/tag/v3.0.0
