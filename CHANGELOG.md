# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [4.3.2] - 2026-10-19

### Fixed

- **Product images survive upgrades.** Uploaded product images were saved inside the backend container (`/app/static/uploads/products`) instead of on the uploads volume, so recreating the container (every Docker upgrade) deleted them. They are now saved to `/app/uploads/products` on the volume. Image links don't change, and images saved before this fix still show for as long as their files exist. In Docker, images uploaded before the last container recreate are already gone and need uploading again.
- **License page with an active license.** It now says the license is active instead of asking for a key and linking to the license site, drops a "Restart Core" banner that never went away, and shows an unknown activation date as "—" instead of Dec 31, 1969. A license cache written without an activation time (as license validation writes it) made the API report 1 January 1970.

### Upgrade notes

- **Docker: copy product images onto the volume before upgrading.** While the old version is still running: `docker compose exec backend sh -c 'set -eu; src=/app/static/uploads/products; dst=/app/uploads/products; mkdir -p "$dst"; if [ -d "$src" ]; then cp -a "$src/." "$dst/"; fi; ls "$dst" | wc -l'`. It prints how many images are now on the volume, including any already there; if it prints an error, don't upgrade until it succeeds. See [Upgrading FilaOps](docs/UPGRADE.md#2-docker-copy-product-images-onto-the-volume).
- **No database migrations.** From 4.3.1, check out `v4.3.2` and rebuild (`docker compose up -d --build`).
- **Coming from 4.1.x or older?** Read [Upgrading FilaOps](docs/UPGRADE.md) first: it starts with the settings 4.2.0 needs, then upgrades straight to 4.3.2.

## [4.3.1] - 2026-10-14

### Changed

- **No staff account limit.** Installs without a licence can add and reactivate as many staff (admin and operator) accounts as they need. 4.2.0 and 4.3.0 allowed one: the Team Members page showed a seat banner, disabled **Add User**, and the API refused a second staff account with 403. Customer accounts were never counted.

### Upgrade notes

- **No database migrations.** From 4.3.0, check out `v4.3.1` and rebuild (`docker compose up -d --build`).
- **Coming from 4.1.x or older?** Read [Upgrading FilaOps](docs/UPGRADE.md) first: it starts with the settings 4.2.0 needs, then upgrades straight to 4.3.1.

## [4.3.0] - 2026-10-14

### Added

- **Serial number prefix setting.** Admins can set the prefix for new serial numbers in **Admin > Settings > Serial Numbers** (letters, digits and dashes; a trailing dash is added). New installs use `SN-`, giving serials like `SN-20261013-0001`. Before, every serial started with `BLB-`.
- **Onboarding asks for a customer contact email.** Step 1 of the setup wizard has a new optional field, "Customer Contact Email": the address customers are told to contact in emails. Left blank, the new admin's email is used. It is saved to Company Settings.

### Changed

- **Customer emails use the business name and email from Company Settings.** Password reset emails (approved, denied, changed) now take the shop name and contact address from **Admin > Settings > Company Information**. They fall back to `BUSINESS_NAME`, `BUSINESS_EMAIL` and `SMTP_FROM_NAME` in `.env`, then to "FilaOps" and "contact your administrator". Before, they used the `.env` values or their shipped placeholders (`Your Company Name`, `info@yourcompany.com`), and three of them ended with a hard-coded "BLB3D Printing" footer.
- **The shop's own logo in the sidebar and on the login page.** An uploaded company logo now replaces the FilaOps wordmark at the top of the sidebar, with a small "Powered by FilaOps" line at the bottom. The login page shows the shop's logo above the FilaOps logo. With no logo uploaded, FilaOps shows as before. Before, the login page always showed the BLB3D logo, and an uploaded logo was squeezed to zero width in the sidebar.
- **AI settings: the Claude model list comes from Anthropic.** The model dropdown now lists the models your saved API key can use (Anthropic's Models API, cached for 10 minutes; admins only) instead of three hard-coded models. If Anthropic can't be reached, a short built-in list of current models is shown with the reason. The per-document cost estimates are gone; the page links to Anthropic's pricing instead.
- **AI settings: Test Connection checks the selected model.** It now sends a one-token request to Anthropic with the model picked on the page, so a rejected key or a retired or mistyped model ID is reported at setup time. Before, it only checked that the key started with `sk-`.
- **New default Claude model: `claude-sonnet-5-5`.** The settings page and the API now use the same default. The page's built-in default and its "Haiku 3.5" option used `claude-haiku-3-5-20241022`, which was never a valid model ID; the API defaulted to `claude-sonnet-4-20250514`, which Anthropic has deprecated.

### Upgrade notes

- **Upgrading from 4.1.x or older?** Read [docs/UPGRADE-4.2.0.md](docs/UPGRADE-4.2.0.md) first. 4.3.0 includes 4.2.0's security fixes and its required configuration changes.
- **Check Company Settings before customers get email.** The shop name and email in **Admin > Settings > Company Information** now win over `BUSINESS_NAME`, `BUSINESS_EMAIL` and `SMTP_FROM_NAME` in `.env`. If they are filled in, customer emails will use them.
- **Serial numbering carries on unchanged.** The upgrade runs database migration 104. An install that already has serials starting with `BLB-` keeps `BLB-` as its prefix, so the next serial follows on from the last one; every other install gets `SN-`. Existing serial numbers are never renamed. Changing the prefix later affects new serials only.
- **Saved Claude models are not changed.** Check the model in **Admin > Integrations > AI Assistant** after upgrading. If someone picked "Haiku 3.5", the install has `claude-haiku-3-5-20241022` stored, which Anthropic does not recognise; installs that never picked a model have `claude-sonnet-4-20250514`, which is deprecated. A saved model Anthropic no longer lists stays selected and is marked "not listed by Anthropic (may be retired)"; pick a listed model, use Test Connection and save.
- **Docker: re-enter the AI API key once if it shows as not set after upgrading.** The backend's instance ID (`install_uuid`, under `/var/lib/filaops/config`) now lives in a named volume, `filaops_config`. Before this release it was lost whenever the backend container was recreated, including by `docker compose up -d --build`, and stored secrets encrypted with it could no longer be read. The upgrade cannot bring back an ID that is already gone: the container keeps whatever ID it has when the volume is first attached. If **Admin > Integrations > AI Assistant** shows no key afterwards, enter it again; from then on it survives upgrades. If you already mount your own volume or directory at `/var/lib/filaops/config` in an override file, yours still takes precedence (`docker compose config` shows the result).
- **Back up the `filaops_config` volume with the database.** A database restored without it cannot decrypt stored secrets. `docker compose down -v` now deletes this volume as well as the database volume.
- **Docker: the backend now runs as `appuser`, not root.** The image always meant to, but the entrypoint never switched user. At startup it gives `appuser` the files in `/app/uploads` (on a Linux host, the owner of files in `./uploads` changes to uid 100) and the config directory. If one of them cannot be made writable, it logs a warning and keeps running as root. `docker compose exec` still opens a root shell; `docker compose run backend <command>` now runs as `appuser`.

### Fixed

- **Docker: stored secrets survive recreating the backend container.** `docker-compose.yml` mounts the `filaops_config` volume at `/var/lib/filaops/config`, and a test checks that every shipped compose file that runs the backend persists that directory.
- **Docker: the backend no longer runs as root.** The entrypoint installs plugins as root, then runs migrations and the API server as `appuser`. A test checks that every command the entrypoint runs goes through that switch.
- **Onboarding saves the company name again.** Since #513 the setup wizard silently failed to save the company name (a broken import inside a `try`), so every fresh install started with an empty Company Settings name.
- **Mobile navigation button no longer covers the open menu.** The floating "Open navigation menu" button is hidden while the mobile drawer is open; the drawer has its own close button.

## [4.2.0] - 2026-10-12

### Upgrade notes

This is a security release; every install should upgrade. **Read [docs/UPGRADE-4.2.0.md](docs/UPGRADE-4.2.0.md) before upgrading.** In short:

- **Set a real `SECRET_KEY`.** Production refuses to start with an empty, placeholder or published example key. Other environments start with a temporary random key that signs everyone out on every restart. Setting or changing the key signs everyone out once.
- **Customer self-registration and public quote intake are off by default.** `ENABLE_PUBLIC_QUOTER=true` turns them on; set it only if you need them. Before 4.2.0 self-registration was always on.
- **Customer accounts can only use their own quotes and account.** Scripts or integrations that sign in as a customer account need a staff account.
- **Set `ADMIN_APPROVAL_EMAIL` to a real address if you send email.** Email counts as off until it is set. Docker installs now pass the SMTP settings through to the backend.
- **Password reset always waits for an administrator.** Reset links issued earlier without an administrator's approval no longer work.
- **Scrap reasons and AI (Ollama) settings are admin-only.**
- **The database is published on `127.0.0.1` only (Docker).** Other machines can no longer reach port 5432. If your install still uses the default `DB_PASSWORD`, set a real one; the guide explains how to change it on an existing install and what to do if another machine needs the database.
- **Without a licence, FilaOps allows one staff account.** Existing installs keep all their current users but can't add or reactivate staff. Customer accounts don't count.
- **Order, shipping and invoice steps are enforced by the server.** An order is marked shipped only by the Ship action, once it is ready to ship; it is cancelled only by the Cancel action; and its production is released only after billing has started (a payment recorded or an invoice sent). An invoice's status can only go from draft to sent directly; voiding uses the new Void action. Scripts that set these statuses directly now get an error.
- **A manual inventory adjustment adds or removes the quantity you enter** (`+5` adds five, `-5` removes five) instead of setting the on-hand quantity. Use Reconciliation to set an exact count.
- **Accounting figures may change.** Reports count posted journal entries only, COGS comes from the general ledger, and completing production now posts to the ledger. Production completed before 4.2.0 has no ledger entries; `backend/scripts/backfill_production_completion_gl.py` can add them (dry run by default; read its `--help` first).
- **Manual (non-Docker) installs need Node.js 24 or newer** to build the frontend.
- **This release runs database migrations (093 to 102).** Back up first; rolling back means restoring that backup. The upgrade stops if two sales orders share the same imported order ID; the guide shows how to check for that before you start.

### Added

- **Item Quality Plans (#784).** New per-product inspection plans: `quality_plans` + `quality_plan_characteristics` (migration 097) with CRUD at `/api/v1/quality-plans` (list / create / get / patch / deactivate). A plan defines which characteristics to measure (nominal + LSL/USL + unit + minor/major/critical severity), each optionally pinned to a routing operation; a plan with no `product_id` is a reusable template. Each characteristic also carries an optional stable `code` (migration 098), unique within a plan — the rename-/edit-proof key that future SPC series will key on. A later PR seeds the QC measurement form from a product's active plan.
- **Quality Plans UI (#784).** New **Admin → Quality → Quality Plans** page lists plans and opens an editor to create/edit a plan: scope (product vs reusable template, with a server-backed product typeahead), header fields (code/name/version/revision/effective date/notes/active), and a characteristic grid (code, characteristic, nominal, LSL/USL, unit, severity). Characteristic `code` is auto-derived from the name (rename-proof) and overridable; lower>upper and duplicate-code are caught client-side before submit. A banner notes that plans drive the inspection form only in **Full** quality mode.
- **Attribute (Pass/Fail) characteristics (#784).** Quality-plan characteristics now have a `characteristic_type` (`variable` | `attribute`, migration 099, default `variable`). **Variable** characteristics are measured against nominal + spec limits (today's behavior, unchanged); **attribute** characteristics are Go/No-Go with no limits and an optional `acceptance_criteria` describing what counts as a pass. The plan editor adds a per-row **Type** selector that swaps the numeric spec-limit cells for an acceptance-criteria field; the API rejects spec limits on attribute characteristics.
- **Configurable QC inspection gate (#784).** A new `quality_gate_action` setting (`off` | `warn` | `block`, default `warn`) governs what happens when a **pass** is recorded in **Full** mode against an incomplete or out-of-spec inspection: `off` records as-is, `warn` records and returns a non-blocking warning, `block` rejects the pass (the inspector must complete it or record fail/conditional). Conformance is derived **server-side** — variable characteristics from `measured_value` vs spec limits, attribute from the recorded pass/fail — so a client can't claim a pass it didn't earn; completeness = every active-plan characteristic measured. Exposed via the policy read-model (`GET /quality/policy` now returns `gate_action`); the legacy boolean `quality_gate_close` is honored as a back-compat fallback (`true` → `block`). Basic/Off mode never gates. No migration — the gate is a `system_settings` value.
- **Inspection gate UI (#784).** **Settings → Quality (QC)** replaces the old boolean "Block close" toggle with a 3-level **Inspection Gate** radio selector (`Off` / `Warn` / `Block`), reading the resolved `gate_action` from the policy endpoint and writing `quality_gate_action`. The selector is disabled when the mode is not Full. The QC Inspection modal now surfaces server-side gate warnings (from `warn` mode) as toast notifications after a successful inspection.
- **Plan-driven QC inspection (#784).** In **Full** quality mode, the QC Inspection modal now seeds its measurement grid from the product's active quality plan (`GET /quality-plans/active`): each variable characteristic becomes a locked-spec row (nominal/LSL/USL/unit read-only from the plan; the inspector enters only the measured value), and each **attribute** characteristic becomes a **Pass/Fail** toggle with its acceptance criteria. Recorded measurements carry the `quality_plan_characteristic_id` link, the stable code, and (for attribute rows) `conforms`. Basic/Off mode is unchanged — the grid stays empty and fully manual. Closes the loop from plan authoring to inspection.
- **QC measurement ↔ plan-characteristic link (#784).** `qc_inspection_measurements` gains `quality_plan_characteristic_id` (FK → `quality_plan_characteristics`, **ON DELETE SET NULL**, migration 100), a denormalized `characteristic_code` (so `(product_id, code)` SPC series survive a plan edit/delete), and `conforms` (per-row pass/fail for attribute characteristics; `NULL` for variable rows, whose conformance is computed from value vs limits). The QC inspection API accepts and round-trips all three. New `GET /api/v1/quality-plans/active?product_id=` returns a product's single active plan (or `null`) — the seed source for the plan-driven inspection form (see above).
- **Selectable QC rigor — the quality "dial" (#784).** A new company-wide `quality_mode` system setting (`off` | `basic` | `full`, default `basic`) plus `quality_gate_action` (`off` | `warn` | `block`), exposed via `GET /api/v1/quality/policy`. The endpoint returns the resolved policy (the raw `mode` plus the derived `surfaces_enabled` / `plan_driven` / `gates_close` the UI keys off) so shops that don't do formal QC see nothing, while regulated shops can opt into plan-driven inspection. Default `basic` keeps existing behavior byte-for-byte; later PRs layer plan-driven inspection and gating behind `full`. A missing or corrupt setting falls back to `basic` — the dial fails safe. The dial is configurable from **Settings → Quality (QC)** (mode selector + a 3-level inspection gate selector).
- **QC inspection capture UI (#784).** The QC Inspection modal now records the full inspection in one step: result (pass / fail / **waive** / conditional), partial pass/fail quantities, a **defect-reason** picker (shown for non-pass results), the **operation** inspected, and an **SPC measurement grid** (characteristic / nominal / LSL / USL / measured / unit) with a live in/out-of-spec indicator — surfacing the measurements, defect-taxonomy, waive, and operation-target backends behind one form.
- **QC inspection photo UI (#784).** After recording an inspection, the modal offers an optional **photo step**: upload, thumbnail grid, and delete for that inspection (`QCInspectionPhotos`), wired to the photo endpoints. Thumbnails are fetched with credentials so the auth-gated images render in dev and behind the prod proxy alike.
- **QC grouping keys (#784).** Each `qc_inspections` row now denormalizes `printer_id` / `work_center_id` / `operator_id` (migration 096), copied from the inspected operation at record time. Upcoming grouped metrics (by printer / work-center / operator) read these directly, so order-level inspections with no operation group as "unassigned" instead of being silently dropped from the aggregate.
- **Operation-targeted QC inspections (#784).** `POST /api/v1/production-orders/{id}/qc` now accepts an optional `operation_id` to record the inspection against a specific routing operation (validated to belong to the order) — supporting routings with more than one inspection step. Without it, the inspection still attributes to the first QC-coded operation (`ilike '%QC%'`) as before. The inspection history already surfaces `production_operation_id`.
- **QC inspection photos (#784).** Attach defect/evidence images to a QC inspection: `POST`/`GET /api/v1/production-orders/qc-inspections/{inspection_id}/photos`, `GET .../{photo_id}/download`, `PATCH .../{photo_id}` (caption), and `DELETE .../{photo_id}`. Images only (jpg/jpeg/png/webp/gif/heic/heif), 25 MB cap, stored in a dedicated `uploads/qc_photos` directory (override `UPLOAD_QC_PHOTOS_DIR`). The surface respects the QC dial — every route 403s when `quality_mode=off`.
- **QC inspection measurements (#784).** `POST /api/v1/production-orders/{id}/qc` accepts a `measurements` list (characteristic, nominal, lower/upper limit, measured value, unit) stored as exact `Numeric` (SPC-ready). The inspection history returns each measurement with a computed `is_within_spec` (true/false vs the limits, or null when no value or no limits are defined).
- **QC defect taxonomy + waive attribution (#784).** New configurable defect reasons (`GET/POST /api/v1/production-orders/defect-reasons`, `/all`, `PATCH /{id}`) with free-form category and a `minor|major|critical` severity. Recording a QC inspection (`POST /production-orders/{id}/qc`) now accepts a `defect_reason_id` and, on a `waived` result, attributes the waive to the operator (`waiver_user_id`); the inspection history exposes the defect reason and waiver.
- **Invoice void (#894).** `POST /api/v1/invoices/{invoice_id}/void` with a required reason voids an invoice and posts a reversing journal entry that mirrors the original one. An invoice with payments must have them voided or refunded first. The void is recorded on the invoice (who, when, why; migration 102). (#912, #919)
- **Operation types (#876).** Routing operations now carry a type from a catalog (print, assembly, quality control, pack and ship, and others; migration 101), and material consumption follows the type instead of the free-text operation code. The routing editor asks for the type first and shows it as a badge on every operation. Admins can review existing operations with `GET /api/v1/admin/operation-types/audit` and type them with a classifier that previews first; nothing is reclassified automatically. (#898, #900, #901, #905, #906)
- **Ledger health and backfill (#880).** A GL-health count shows completed production with no ledger entry, and `backend/scripts/backfill_production_completion_gl.py` posts the missing entries: dry run by default, `--apply` only with a recent backup, and `--rollback` to undo. (#892)
- **Command Center next actions (#808).** Command Center shows each order's next actions in lanes, and the sales and purchase order lists return the `can_*` / `is_*` flags the screens use. (#810, #811, #812, #813, #814)
- **Operation-level scrap.** The Scrap button on an operation and its preview of what the scrap affects now work; both routes were missing. (#868)
- **Printer catalog refresh.** 28 printer models with checked bed size, enclosure, chamber and nozzle details; discontinued models are marked as such. (#908)
- **Workbench look.** New design tokens and a petrol accent colour; the Production, Shipping and order detail screens use them. (#847, #854, #870, #991, #992, #1007)

### Changed

- **Quality metrics — true first-pass yield (#784).** `GET /api/v1/quality/metrics` now derives `first_pass_yield`, `passed`, `failed`, and `total_inspections` from each order's **first `qc_inspections` row** instead of the `ProductionOrder.qc_status` cache. The cache is last-write-wins, so an order that failed initial inspection and was later re-inspected or waived to "passed" previously counted as a first-pass success and inflated the yield. **Expect FPY to move** (typically downward) where re-inspections occur — this is the corrected value, not a regression. Orders inspected before inspection rows were recorded are not counted in the metric.
- **Role refusals use the shared checks.** Most routes that checked the admin or staff role inside the handler now use the shared dependencies. A refused caller gets 403 `Admin access required` or `Staff access required`, and gets it before the request body is validated (some routes answered 422 first). Operators keep the access they had, except for scrap-reason changes (see **Upgrade notes**). On the sales-order routes that still means only the orders an operator owns; admins reach every order, as before.
- **Customer quote acceptance refuses amounts a quote cannot store.** `POST /api/v1/quotes/portal/{quote_id}/accept` answers 422 when `shipping_cost` or `adjusted_unit_price` is finer than a cent or above 99,999,999.99, and when subtotal + tax + shipping would be above 99,999,999.99. These requests used to fail with a 500.
- **Approving a quote clears its review reason.** Setting a quote to `approved` (`PATCH /api/v1/quotes/{quote_id}/status`) now clears `requires_review_reason` (for example customer notes or a colour choice that needs review), because the approval is the review. The cleared reason is written to the log. Other status changes keep it.
- **Putting a quote back to pending holds it for staff.** Setting a quote to `pending` now also marks it as manually approved (`approval_method` becomes `manual`), so a customer accepting it again doesn't re-approve it on their own; it stays pending until staff approve it.
- **A status change adds its note instead of replacing the admin notes.** An `admin_notes` value sent with `PATCH /api/v1/quotes/{quote_id}/status` is added on a new line after the existing notes, so it can't erase what is already there. If the notes would go over 1,000 characters, the request is refused with 400 and nothing changes. Editing a quote still replaces its notes.
- **`ENVIRONMENT` is read the same way everywhere.** Every production check now ignores case and surrounding spaces. `ENVIRONMENT=Production` or `production ` already refused a placeholder `SECRET_KEY`; it now also turns off the API docs (`/docs`, `/redoc`, `/openapi.json`), sends the HSTS header and keeps the test endpoints off, as `ENVIRONMENT=production` does.
- **Shipping goes through the Ship action.** A general status change can no longer set an order to `shipped`; `POST /api/v1/sales-orders/{order_id}/ship` is the only way, so stock and COGS are always recorded. Only orders that are ready to ship can ship; the ship step checks stock before changing anything, records the shipped quantity on each line, and refuses a second, concurrent ship. Marking an order shipped with an outside label, and consolidated shipments, now relieve stock and post to the ledger for every order. (#838, #840, #841, #843, #893)
- **Cancelling goes through the Cancel action.** A status change to `cancelled` is refused; the Cancel action records when and why and releases linked production orders and reservations. (#874)
- **Production release needs billing.** Releasing production for an order answers 400 until a payment is recorded or an invoice is sent. Net-terms customers don't have to pay first. (#853)
- **Invoice status.** `PATCH /api/v1/invoices/{invoice_id}` changes the status only from `draft` to `sent`; other status values are refused. Use the Void action to void an invoice. (#912)
- **Manual inventory adjustments are signed.** The quantity is added (`+`) or removed (`-`) and can't take stock below zero; receipts, issues, consumption, scrap and transfers refuse zero or negative quantities. The adjustment reason is now saved. (#851)
- **Accounting reports.** The trial balance and account ledger count posted entries only (`include_unposted=true` gives the old totals); COGS on the dashboard, profit summary and COGS report comes from the general ledger; and completing production posts to the ledger. (#890, #891, #892, #897)
- **Fiscal periods.** Closing a period marks it closed for reporting; it does not lock entries. The screens and API docs now say so. (#987)
- **Imported orders.** A sales order's imported order ID (`source_order_id`) must be unique (migration 094), so importing the same file twice can't create the same order twice. (#785, #803)
- **Node.js 24.** The frontend build, CI and the Docker builder use Node.js 24 LTS. (#934)

### Fixed

- **Quality.** The Quality module's crashes, queue and metrics (#791); scrapping a completed or QC-held order writes off the finished goods and posts to the ledger, and the Scrap button is reachable (#780, #781, #794, #799); purchase orders show as ready for QC when they are complete (#809).
- **Production.** Completing fewer units than ordered recorded the full quantity, and closing short was impossible; splitting an order failed (#867). The scrap and the QC-and-completion flows work end to end (#856, #860).
- **Inventory and costing.** Products built from a routing consume their materials and get COGS at completion, and packaging on a routing is consumed at shipping (#875). Completion and operation consumption post to the right inventory account for each item type (#914).
- **Payments and invoices.** Voiding or refunding a payment updates the linked invoice, and a refund larger than what was collected is refused (#852).
- **Accounting.** Delivered orders no longer drop out of the sales journal and Tax Center (#913). Journal entries keep their entry date, shipping can't post twice, and purchase receipts post by item type (#891).
- **Orders.** CSV order import numbers orders correctly, uses the chosen source, and no longer creates duplicates (#803, #805). New orders can be cancelled (#874). Products built from a routing can be sold, and raw materials no longer appear in the customer order picker (#887, #888).
- **Scheduling.** Operations scheduled on a printer show their machine, and the capacity view and auto-schedule use real bookings (#863, #864).
- **Routings.** Copying a routing to a product or its variants no longer duplicates operations when the request is repeated (#907).
- **Other.** The analytics dashboard no longer fails with a 500 (#768); production order pages such as scrap reasons are no longer hidden behind the order detail route (#818); the login connection banner is readable again (#993); a `backend/.dockerignore` keeps local files out of the backend image (#921).

### Security

This release fixes five security problems. Details are in the linked advisories.

- **Access control on the Core API.** Customer accounts could use API routes meant for shop staff, including quotes, payments and purchase orders, and a few routes answered without a login. Every Core route now requires a staff or admin account unless it is on a short, reviewed list of public and customer routes, and a test fails if a new route is added without a check. ([GHSA-jgwx-xrmr-26fv](https://github.com/BLB3DPrinting/filaops/security/advisories/GHSA-jgwx-xrmr-26fv), [GHSA-f9mr-93x7-cq5q](https://github.com/BLB3DPrinting/filaops/security/advisories/GHSA-f9mr-93x7-cq5q), [GHSA-vrr8-gpvm-732v](https://github.com/BLB3DPrinting/filaops/security/advisories/GHSA-vrr8-gpvm-732v))
- **Login signing key.** FilaOps no longer signs logins with a placeholder or published example `SECRET_KEY`. ([GHSA-r4j7-j592-gchw](https://github.com/BLB3DPrinting/filaops/security/advisories/GHSA-r4j7-j592-gchw))
- **Password reset.** Reset requests always need an administrator's approval, and the reset response never contains a reset link. ([GHSA-f9mr-93x7-cq5q](https://github.com/BLB3DPrinting/filaops/security/advisories/GHSA-f9mr-93x7-cq5q))
- **Outbound requests from AI settings.** The Ollama URL is validated when saved and again before every request, and some special-purpose addresses are refused. Local and LAN addresses still work. ([GHSA-vmrm-qwq2-8xj3](https://github.com/BLB3DPrinting/filaops/security/advisories/GHSA-vmrm-qwq2-8xj3))
- **Customer quote acceptance.** The server now works out the price and total when a customer accepts a quote, and ignores pricing sent by the browser.
- **Database port.** The stock `docker-compose.yml` now publishes the database on the local machine only, instead of on every network interface, and a test fails if a compose file the repo ships publishes it more widely. FilaOps itself still reaches the database over Docker's internal network.
- **Other hardening.** Staff-only fields are hidden from customer accounts, stored printer connection secrets are masked in responses, a very long field name in printer settings no longer ties up the server, QC photo uploads are kept inside their folder (#972), and this release ships access fixes merged after 4.1.0 (#859, #872, #973).
- **Dependencies.** Unused `python-jose` and its `ecdsa` dependency are removed, and other Python and JavaScript dependencies are updated to clear published advisories (#948, #956, #957, #997, #1008, #1012).

Thanks to the people who reported these problems; see [SECURITY.md](SECURITY.md).

## [4.1.0] - 2026-06-20

### Added

- **Production Scheduler (Gantt) & Dispatch** — new scheduling suite: a suggest-and-confirm dispatch engine (#718), machine-lane × time-axis Gantt view (#727), reschedule/unschedule operations with modal edit mode (#722), dispatch chips with an `auto_dispatch` setting (#723), a guided initial-schedule wizard on production release (#724), one-click earliest-valid-start for predecessor conflicts (#721), and first-class maintenance-window scheduler blocks (SCHED-7, #733).
- **Intake Studio** — PRO-gated operator UI for parts intake (#759).
- **Inventory reconciliation** — reconciliation report (HARD-4b, #694), count-entry tool with explicit fallback (HARD-4c, #695), and a canonical inventory-posting function routing all on-hand writers through one ledger (HARD-4a, #690).
- **Consolidated buy list** — Layer 1 live view (HARD-7, #705).
- **Landed cost capitalization** — landed cost capitalized into item cost and inventory GL (HARD-8, #701).
- **Cycle count variance review** — review variance before posting (HARD-16, #706).
- **Onboarding & navigation** — onboarding printer + currency/locale steps (PR-18, #710), nav regroup with a MONEY group and flow-ordered SALES plus a CommandCenter landing page (PR-13, #711), and `EmptyState` CTAs across list pages (PR-10, #712).
- **Order workflow guidance** — guided order-workflow actions (#667) with the invoice workflow kept on orders (#660).
- Quotes and quote-based orders retain Core-owned pricing, component, packaging, shipping, artifact, and slicer diagnostic snapshots for durable public-quoter handoff (#629).
- Manual quotes support Core-owned file attachments with staff upload, download, list, and delete actions (#618), plus an authenticated download endpoint (#616).
- Item create/edit exposes optional weight and dimensions for shipping; a new packaging item type requires physical metadata (#624, #625).
- Public quoter endpoints are explicitly gated by `ENABLE_PUBLIC_QUOTER`, leaving Core manual quote creation independent of PRO (#614); portal quote creation passes selected component add-on ids through to the optional automation provider (#626).
- Quotes expose a Core-owned read-only archive response, and staff can create a Core item/product from an approved quote through a deliberate action.
- PRO Bambuddy connector UI (#621) and locally served PRO surfaces (#632).

### Changed

- **DEBT-1 god-file decomposition** — `customer_service`, `item_service`, `sales_order_service`, and `production_order_service` were split into focused modules; `OrderDetail` and `OperationScheduler` UI were decomposed into components (closes #428). `AGENT_POLICY` now documents file-size limits to prevent regrowth.

### Fixed

- **Inventory/MRP hardening (HARD series)** — auth-gated `/mrp` and admin/material/system endpoints (#683, #687, #698); honest MRP triggers (#688); PO receiving routed exclusively through the receive workflow (#689); reservation reconciliation and stranded-allocation release (#696, #716); routing-aware material reservation with release-time self-heal (#728); consumption idempotency (#704); net on-order supply folded into shortage calculations (#703); regex+numeric-cast PO/MRP sequence generation (#685).
- **Order workflow** — PR-8 consolidated action surface with backend-aligned gating and closed_short reconcile (#713), restored Delete Order trigger and hidden Close Short when already closed (#714) (closes #680); separated order confirmation from production release (#666); brownfield order data health — legacy WO linkage, fulfillment evidence, guided resolution (LEGACY-1, #725).
- **Invoicing & accounting** — sales accounting entries posted (#669); invoice payments recorded in the ledger (#648); invoice/order line totals, service-line descriptions, and discount handling preserved (#645, #646, #647); invoices linked to customer orders (#644); customer paid/outstanding totals shown (#643); Indiana seller-billed shipping taxed correctly (#650) and shipping excluded from dashboard revenue (#649).
- **Auth/session** — dead sessions bounce to login instead of a 401-riddled admin shell (#730); root route defaults to the login screen (#729); license cache reader tolerates a missing `activated_at` (#754).
- Scheduler datetime-local inputs render local wall time and parse Numeric-as-string durations (#731, #720).
- Quote file downloads reject unsafe stored filenames; portal quote uploads retain `.obj`/`.step`/`.stp` for manual review; portal quote creation falls back to a pending manual-review quote when the optional PRO automation provider fails; multi-color selections are snapshotted to `QuoteMaterial` rows.

### Security

- `@babel/core` dev/build dependency bumped `7.29.0` → `7.29.7` to resolve CVE-2026-49356 / GHSA-4x5r-pxfx-6jf8 (arbitrary file read via `sourceMappingURL` comment; low severity, dev-only, transitive in `frontend/`).
- Dev seed data and the walkthrough E2E suite no longer hardcode an admin password. Credentials are read from `SEED_ADMIN_PASSWORD` / `WALKTHROUGH_PASSWORD`; when unset, the seed script generates a random password and prints it once. The `walkthrough` Playwright project is also excluded from CI runs (#748).
- E2E flow specs now reference the shared `E2E_CONFIG` credential instead of inline literals, and the intentional `admin@filaops.test` test-fixture password is allowlisted in `.gitguardian.yaml` so GitGuardian no longer flags it as a leak (#750).

## [4.0.0] - 2026-04-14

### Added

- **Quality Dashboard** — inspection queue, pass/fail metrics by product/inspector, scrap analysis, and trend charts for QC managers (#525)
- **Print Cost Estimation Engine** — auto-estimates material and labor cost on PO creation using work center rates (machine + labor + overhead); estimated/actual breakdown visible in the PO modal (#521, #539)
- **Material-Printer Compatibility Validation** — validates filament material type and diameter against printer nozzle and platform specs before scheduling; suggests compatible alternatives on mismatch (#522)
- **Scheduling Sequence Enforcement** — operations must be scheduled in sequence order; out-of-order attempts return a validation error with the next-available slot suggestion (#526)
- **Purchase Order PDF** — printable PO document with vendor info, line items, and totals; matches invoice/quote visual style (#523)
- **Breadcrumb Navigation** — contextual breadcrumb trail across all admin pages with clickable path segments (#524)
- **FilaFarm Admin Page** — PRO-gated admin panel for FilaFarm printer farm management and automation settings (#518, #520)
- **Silent Token Refresh** — 401 responses trigger background token refresh without interrupting in-progress form work (#517)

### Fixed

- Production order modal rendered its content block twice due to rebase conflict residue — removed duplicate 119-line section (#539)
- Cost estimation silently skipped on new POs — `db.flush()` now called before relationship access so operations are populated at estimation time (#539)
- `ProductionOrderListResponse` did not include cost fields — modal received a lean list object with no cost data; fields added to list schema and `build_list_response` (#539)
- FilaFarm API response shape — extract printers/jobs arrays from nested response object (#520)

### Documentation

- Regenerated API-REFERENCE.md (444 endpoints across 49 files), SCHEMA-REFERENCE.md (65 models), MIGRATIONS-LOG.md (62 migrations)
- Updated FEATURE-CATALOG.md: 51 → 60 features

## [3.7.1] - 2026-04-07

### Fixed

- **Self-hosted deployment** — proxy headers (`--proxy-headers --forwarded-allow-ips`) added to uvicorn so mixed-content redirects no longer error behind nginx/Traefik (#510)
- **Onboarding company name** — company name now saved to CompanySettings during initial setup so sidebar header is populated after onboarding (#510)
- **GL entries for SO shipment** — shipping an order now creates a balanced journal entry (DR COGS 5000 / CR FG Inventory 1220); entries were previously missing (#468)
- **Price Levels on Core** — price level CRUD moved to Core API (`/api/v1/price-levels`); was previously only accessible with PRO installed (#476)
- **PO receiving for non-material items** — maintenance/supply items purchased in a different unit class (e.g. PTFE tubing in metres, product unit EA) can now be received without a 400 error (#514)

## [3.7.0] - 2026-04-06

### Added

- **Close-short workflow** — accept partial fulfillment when full quantity cannot be produced or shipped; close-short preview shows per-line achievable quantities before executing (#495, #501)
- **PO accept-short** — complete a production order with less than the ordered quantity; BOM-aware guard prevents breaking assembly dependencies (#499)
- **SO line editing** — edit quantities on confirmed/in-production/on-hold/pending orders with reason tracking (#495)
- **SO line removal** — remove a line from an editable order; guarded by shipped quantity, active PO check, and minimum one-line requirement (#505, #506)
- **PO refresh-routing** — re-snapshot a product's current active routing onto an existing production order; solves POs created before routing existed (#505)
- **Quote PDF redesign** — professional B2B layout with brand colors, two-column header, itemized lines, and terms (#497)
- **Invoice PDF redesign** — professional layout with full customer info, payment terms, calculated due date, and packing slip match (#504)
- **Packing slip redesign** — matches invoice/quote style with brand header, dark table header, and alternating row stripes (#504)
- **Admin messaging** — admin-initiated direct messaging (PRO-gated; professional/enterprise tier only) (#493)

### Fixed

- Pending orders now included in editable statuses — line edits and removal were hidden on `pending` orders (#506)
- Quote-converted orders used `source='portal'` incorrectly — now `source='quote'`; PRO portal passes `source='portal'` explicitly (#505)
- `sales_orders.unit_price` was NOT NULL — caused conversion failures for multi-line quotes where header price is null by design (migration 077, #505)
- Packing slip header collision — "PACKING SLIP" title overlapped SO number; fixed with adequate `spaceAfter` spacing (#505)
- Close-short UI clarity — Short Closed state and multi-line Order Summary display (#502)

### Documentation

- Regenerated API-REFERENCE.md (438 endpoints), SCHEMA-REFERENCE.md (64 models), MIGRATIONS-LOG.md (60 migrations)
- Added close-short, line editing, and line removal workflows to orders user guide
- Added accept-short and refresh-routing sections to production user guide
- Added production shortfall path to quote-to-cash workflow
- Updated FEATURE-CATALOG.md: 41 → 50 features
- Removed stale planning document (496-architecture-review.md)

## [3.6.0] - 2026-03-30

### Added
- **Invoice engine** — PDF invoice templates, payment recording, and invoice line items (#466, PR #471)
- **Customer payment terms** — COD, net-15, net-30 with credit limits and aging (#465, PR #469)
- **Sales order price level auto-apply** — automatic tier-based pricing on order creation (#464, PR #470)
- **Variant matrix** — bulk create color/material variants from template products with BOM material swaps (#458)
- **External order ingestion** — portal order import with operator notification inbox (#475)
- **Suggest Prices tool** — margin-based bulk pricing suggestions for items (#440)
- **Multi-line item quotes** — quote line items with per-line discount and customer discount support (#488)

### Fixed
- Routing cost calculation — setup time, materials, deduplication (#441)
- Routing material unit_cost double-division by purchase_factor (#459), then reverted to correct division (#460)
- Product image upload — nginx limit, URL handling, schema (#444)
- Bulk update status not applying — field name mismatch (#446)
- Routing cost review followup — Decimal consistency, N+1, currency precision (#448)
- Prevent duplicate materials on BOM lines and routing operations (#442, PR #455)
- Price level assignment shows current tier, supports reassignment (#461)
- Allow routing-only items in sales orders (#462) and quotes (#478)
- Items list endpoint missing has_bom/has_routing fields (#481)
- Quote product picker filtered to finished goods only (#480)
- Don't expose exception details in variant sync API response (#477)
- Merge Alembic heads 069 and 070 (#472)

### Security
- Pin flatted to 3.4.2 — prototype pollution (CVE-2026-33228) (#453)
- Bump requests 2.32.5 → 2.33.1 — insecure temp file reuse (#474, #490)
- Bump picomatch 4.0.3 → 4.0.4 — method injection in POSIX character classes (#473)

### Documentation
- Full regeneration of API, schema, and migration reference docs (#447)

### Dependencies
- codecov/codecov-action 5 → 6, actions/deploy-pages 4 → 5
- fastapi 0.135.1 → 0.135.2, uvicorn 0.41.0 → 0.42.0
- react-router 7.13.1 → 7.13.2, vitest 4.1.0 → 4.1.2
- storybook ecosystem 10.3.1 → 10.3.3
- lucide-react 0.577.0 → 1.7.0

## [3.5.0] - 2026-03-20

### Added
- **Duplicate item with BOM component swap** — clone items with inline material substitution (#415, PR #425)
- Portal Admin button in admin header (PRO-gated) (#424)

### Fixed
- Copy routing and operation materials when duplicating an item (#426)
- PO modal product dropdown empty on first open (#417)
- Consistent PRO upgrade card on Access Requests page (#412)

### Documentation
- MkDocs site synced with v3.5.0 features (#435)
- README and docs accuracy pass (#433)

### Dependencies
- jsdom 25.0.1 → 29.0.0
- pyjwt updated in pip-minor-patch group
- npm-minor-patch group (7 updates)

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

[Unreleased]: https://github.com/BLB3DPrinting/filaops/compare/v3.7.1...HEAD
[3.7.1]: https://github.com/BLB3DPrinting/filaops/compare/v3.7.0...v3.7.1
[3.7.0]: https://github.com/BLB3DPrinting/filaops/compare/v3.6.0...v3.7.0
[3.6.0]: https://github.com/BLB3DPrinting/filaops/compare/v3.5.0...v3.6.0
[3.5.0]: https://github.com/BLB3DPrinting/filaops/compare/v3.4.0...v3.5.0
[3.4.0]: https://github.com/BLB3DPrinting/filaops/compare/v3.3.0...v3.4.0
[3.3.0]: https://github.com/BLB3DPrinting/filaops/compare/v3.2.0...v3.3.0
[3.2.0]: https://github.com/BLB3DPrinting/filaops/compare/v3.1.1...v3.2.0
[3.1.1]: https://github.com/BLB3DPrinting/filaops/compare/v3.1.0...v3.1.1
[3.1.0]: https://github.com/BLB3DPrinting/filaops/compare/v3.0.1...v3.1.0
[3.0.1]: https://github.com/BLB3DPrinting/filaops/compare/v3.0.0...v3.0.1
[3.0.0]: https://github.com/BLB3DPrinting/filaops/releases/tag/v3.0.0
