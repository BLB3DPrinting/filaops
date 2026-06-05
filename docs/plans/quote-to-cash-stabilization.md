# Quote-To-Cash Stabilization

Date: 2026-06-05
Session: codex-quotes-audit-20260605-001
Scope: Core ERP quote-to-cash reliability, starting with Quotes.

## Why This Exists

The current product looks like an ERP, but several everyday workflows do not yet behave like a production system. This plan turns the quote-to-cash path into a documented contract before making more UI or deploy decisions.

The immediate user-reported failures are:

- Orders cannot be created without a quote.
- Order part pricing cannot be adjusted after order creation.
- Manual quotes cannot reliably adjust items in the UI.
- Manual quotes cannot be deleted from the UI even when not accepted.
- Payments can be recorded, but dashboards and customer totals do not reflect the real quote/order/payment economics.
- Extra fees such as engineering fees are not consistently represented from quote through order and reporting.

This document starts with Quotes because that is the first object in the flow and because the backend already contains more quote behavior than the UI currently exposes cleanly.

## Stabilization Principles

- Define the business contract first, then make backend/API/UI conform to it.
- Keep Core standalone. PRO can enrich quote automation through extension hooks, but Core quote creation, manual editing, file retention, order conversion, and cash reporting must work without PRO installed.
- Treat quote totals, order totals, payments, and customer totals as different metrics. Do not let quote pipeline value masquerade as revenue or cash received.
- Make every quote-to-cash transition idempotent enough to be safe in production: create, edit, accept, convert, record payment, adjust, cancel, and refund.

## Expected Quote Behavior

### Manual Quote Creation

A staff user can create a manual quote for:

- A linked customer record.
- A one-off customer name/email.
- One or more priced lines.
- Optional shipping, tax, customer notes, admin notes, attached quote files, and product image.

Each quote line should support:

- Catalog product line: linked to a Core product/item.
- Service or fee line: no production inventory, for engineering fee, setup fee, rush fee, design fee, or adjustment.
- Quantity, unit price, line total, notes, optional material/color display fields.

The server owns the authoritative totals:

- `subtotal = sum(line.quantity * line.unit_price - line.discount)` or legacy single-line equivalent.
- `tax_amount = taxable subtotal * selected tax rate`.
- `total_price = subtotal + tax_amount + shipping_cost`.
- Discounts are snapshotted on the quote and must not be double-applied when duplicating or converting.

### Manual Quote Editing

Unconverted manual quotes should be editable in the UI and API.

Minimum editable fields:

- Customer link/name/email.
- Line add/remove/reorder, quantity, unit price, product link, notes.
- Service/fee lines.
- Tax toggle and selected tax rate.
- Shipping cost and shipping address.
- Customer/internal notes.
- Expiration date or valid-days policy.
- Attachments and image.

Converted quotes should be immutable except for safe archival metadata. Accepted/approved quote edit policy needs a product decision:

- Option A: allow edits until conversion.
- Option B: require "revise quote" to return to pending and preserve the customer-facing accepted version.

### Manual Quote Deletion

The API currently permits deleting any quote that is not converted. The UI should make deletion obvious for allowed statuses and show the backend error for disallowed statuses.

Recommended production contract:

- Pending, rejected, and cancelled: delete allowed.
- Approved: delete or cancel allowed, depending on audit policy.
- Accepted: prefer cancel/revise over hard delete.
- Converted: hard delete blocked.

### Quote Status Contract

Current statuses in use:

- `pending`
- `approved`
- `accepted`
- `rejected`
- `cancelled`
- `converted`
- Additional portal status observed in code: `calculating`
- Tests also use `draft` in older integration smoke tests.

Target contract should be explicit:

- `draft`: staff-created quote not ready to send.
- `pending`: ready for review/customer response.
- `approved`: staff-approved or customer-visible offer.
- `accepted`: customer accepted the quote, not yet converted/paid.
- `converted`: sales order exists.
- `rejected`: customer or staff rejected.
- `cancelled`: manually cancelled.
- `expired`: derived from `expires_at`, not necessarily a stored status.
- `calculating`: portal automation transient state only.

Allowed transitions should be codified and tested.

## Current Backend Map

### Tables And Important Fields

`quotes`

- Identity: `id`, `quote_number`, `user_id`.
- Customer: `customer_id`, `customer_name`, `customer_email`.
- Legacy/header item: `product_id`, `product_name`, `quantity`, `unit_price`, `material_type`, `color`, `finish`.
- Totals: `subtotal`, `tax_rate`, `tax_amount`, `tax_name`, `shipping_cost`, `total_price`, `discount_percent`.
- Workflow: `status`, `approval_method`, `approved_by`, `approved_at`, `rejection_reason`, `expires_at`.
- Conversion: `sales_order_id`, `converted_at`.
- Portal/shipping snapshots: shipping name/address/rate/carrier/service/cost fields.
- Files/images: image blob metadata and legacy uploaded file metadata.

`quote_lines`

- `quote_id`, `line_number`, `product_id`, `product_name`, `quantity`, `unit_price`, `total`, `material_type`, `color`, `notes`.
- `product_id` is nullable, which allows freeform quote lines today.

`quote_files`

- Retained quote attachments. Core-owned. Manual upload/list/download/delete endpoints exist.

`quote_materials`

- Portal/automation material snapshot rows.

### API Routes

Staff/admin quote routes:

- `GET /api/v1/quotes/`
- `GET /api/v1/quotes/stats`
- `GET /api/v1/quotes/{quote_id}`
- `POST /api/v1/quotes`
- `PATCH /api/v1/quotes/{quote_id}`
- `PATCH /api/v1/quotes/{quote_id}/status`
- `POST /api/v1/quotes/{quote_id}/convert`
- `DELETE /api/v1/quotes/{quote_id}`
- `POST /api/v1/quotes/{quote_id}/image`
- `GET /api/v1/quotes/{quote_id}/image`
- `DELETE /api/v1/quotes/{quote_id}/image`
- `GET /api/v1/quotes/{quote_id}/pdf`
- `GET /api/v1/quotes/{quote_id}/files`
- `POST /api/v1/quotes/{quote_id}/files`
- `GET /api/v1/quotes/{quote_id}/files/{file_id}/download`
- `DELETE /api/v1/quotes/{quote_id}/files/{file_id}`

Portal/automation quote routes:

- `POST /api/v1/quotes/portal`
- `POST /api/v1/quotes/portal/{quote_id}/accept`
- `POST /api/v1/quotes/portal/{quote_id}/checkout`
- `GET /api/v1/quotes/{quote_id}/archive`
- `POST /api/v1/quotes/{quote_id}/create-item`

### Services And Calculations

`backend/app/services/quote_service.py`

- Creates manual quotes with either legacy single item fields or `lines`.
- Applies customer discount from optional PRO price level tables when `customer_id` exists.
- Recalculates subtotal, tax, shipping, and total on create/update.
- Blocks editing only when `status == "converted"`.
- Blocks deletion only when `status == "converted"`.
- Converts approved/accepted quotes into a `SalesOrder`.
- Multi-line conversion requires every `QuoteLine.product_id` to exist because `SalesOrderLine` requires either `product_id` or `material_inventory_id`.

`backend/app/services/quote_conversion_service.py`

- Separate portal conversion path that can create/reuse product and production order artifacts.
- `convert_quote_after_payment` can mark generated order paid.
- This is not the route used by the staff `POST /api/v1/quotes/{quote_id}/convert` endpoint.

## Current UI Map

`frontend/src/pages/admin/AdminQuotes.jsx`

- Fetches quote list and quote stats.
- Opens a list row in `QuoteDetailModal`.
- Creates and updates through `QuoteFormModal`.
- Updates status, converts to order, deletes, duplicates, prints/downloads PDF.

Important UI issue found:

- `QuoteDetailModal` fetches the full quote detail with `lines`, but `AdminQuotes` passes the stale `viewingQuote` list-row object to `QuoteFormModal` when Edit is clicked.
- Because list items do not include full line detail, editing can degrade to the header/single-line representation and make manual quote item editing feel broken.
- Duplicate has the same risk because it is also called with the list-row prop instead of the fetched detail object.

`frontend/src/components/quotes/QuoteFormModal.jsx`

- Supports multi-line quote creation/editing when it receives `quote.lines`.
- Fetches finished goods from `/api/v1/items?limit=500&active_only=true&item_type=finished_good`.
- Fetches customers from `/api/v1/admin/customers?limit=200`.
- Allows line quantity and unit price editing.
- Sends `lines`, `tax_rate_id`, `shipping_cost`, notes, and customer fields on save.

Current limitation:

- It only exposes catalog product selection, not an explicit service/fee line type.
- It sends `tax_rate_id` on save, but `ManualQuoteUpdate` does not currently define `tax_rate_id`, so updating a quote's selected named tax rate is not part of the update contract.

`frontend/src/components/quotes/QuoteDetailModal.jsx`

- Shows full quote details after it fetches `/api/v1/quotes/{id}`.
- Allows status actions, conversion, PDF, duplicate, edit, delete, image upload/delete, and quote file upload/download/delete.
- Deletion is visible when `q.status !== "converted"`.

## Current Test Map

Backend quote tests cover:

- Auth required for quote routes.
- Manual quote create/update/delete.
- Unit price update recalculates totals.
- Shipping cost is included in quote totals and PDF.
- Converted quotes cannot be edited, deleted, or re-converted.
- Rejected and cancelled quotes can be deleted.
- Quote files can be uploaded, listed, downloaded, and deleted by staff.
- Portal quote ownership and file retention contracts.

Gaps:

- UI test does not assert that Edit receives the full detail quote, including `lines`.
- No test protects service/fee quote lines from conversion loss or failure.
- No end-to-end test covers manual quote with extra fee -> order -> payment -> customer total.
- Older quote-to-cash integration smoke tests construct models directly and use statuses that are not part of the active service contract.

## P0 Findings

### P0.1 UI Edit Uses List Object Instead Of Full Quote Detail

Backend supports line editing, and the detail modal fetches line detail, but the Edit callback in `AdminQuotes` uses the original `viewingQuote` list object. This is likely the direct cause of "manual quote was created but I cannot adjust the items."

Fix:

- Let `QuoteDetailModal` call `onEdit(q)` with its `fullQuote`.
- Update `AdminQuotes` to set `editingQuote` from that argument.
- Do the same for duplicate, PDF, copy link, and conversion-adjacent actions where full quote data matters.
- Add a frontend regression test that a quote opened from the list fetches detail and opens edit with all lines.

### P0.2 Service/Fee Lines Do Not Survive Quote Conversion

Quotes allow `QuoteLine.product_id = null`, but conversion to `SalesOrderLine` rejects lines without `product_id` because `sales_order_lines` enforces `ck_sol_product_or_material`.

This blocks normal business charges such as:

- Engineering fee.
- Setup fee.
- Rush fee.
- Design fee.
- Manual adjustment.

Fix needs a Core data decision:

- Add a first-class order/quote line type for service/fee lines, or
- Represent fees as non-inventory catalog items that still use `product_id`, or
- Add an order adjustment table for charges/credits.

Recommended direction: first-class line type for `product`, `service`, `fee`, and `discount` so quote/order/payment/reporting all share the same economics.

### P0.3 Two Conversion Paths Disagree

The staff quote conversion endpoint uses `quote_service.convert_quote_to_order`, creating a SalesOrder and optional SalesOrderLines. The portal/payment service uses `quote_conversion_service`, which can create product and production artifacts and mark an order paid.

This creates different outcomes depending on which path converts the quote.

Fix:

- Define one canonical conversion service.
- Let manual/admin and portal/payment routes call that same service with options such as `payment_status`, `create_production_order`, and `source`.

### P0.4 Customer Totals Use The Wrong SalesOrder Customer Field

Customer stats currently aggregate `SalesOrder.user_id == customer_id`. Quote conversion sets `SalesOrder.user_id = quote.user_id` and separately sets `SalesOrder.customer_id = quote.customer_id`.

For staff-created quotes, `user_id` is the staff/admin owner, not the customer. This explains customer totals not reflecting quote-converted orders and payments.

Fix:

- Customer stats should aggregate by `SalesOrder.customer_id`.
- If legacy data used `user_id` as customer, migration/backfill or compatibility query is needed.
- Tests should create a staff-owned quote for a linked customer, convert it, record payment, and assert customer totals reflect the customer.

### P0.5 Quote Stats Are Pipeline Value, Not Revenue Or Cash

`GET /api/v1/quotes/stats` sums `Quote.total_price` for all quotes. That is quote pipeline value. It should not be used as paid revenue, customer spend, or cash received.

Fix:

- Rename UI labels to "Quote Pipeline Value" where it shows quote totals.
- Revenue should come from orders or invoices.
- Cash received should come from payments.

### P0.6 Quote Update Cannot Change Named Tax Rate

Create schema accepts `tax_rate_id`; update schema does not. The UI sends `tax_rate_id` during update, but the backend update contract ignores it.

Fix:

- Add `tax_rate_id` to `ManualQuoteUpdate`.
- Update `quote_service.update_quote` to resolve tax from that ID when supplied.
- Add tests for changing named tax rate on an existing quote.

## P1 Findings

- Quote statuses are string fields with no database or service transition contract.
- Accepted/approved edit and delete policy is not explicit.
- Quote line schema duplicates exist between `app/schemas/quote.py` and route-local schemas in `endpoints/quotes.py`.
- Manual quote file APIs exist and the detail UI has upload controls, but this needs smoke coverage in the full quote workflow.
- Duplicate intentionally avoids `customer_id` to avoid double discount. That is pragmatic but should become an explicit "copy net prices" contract.
- Staff quote conversion sets `source="portal"` even for manual conversion. Manual conversions should set `source="manual"`.
- The order model has header product fields and line records; quote/order UI should consistently treat line records as the source of truth for multi-line orders.

## First Repair Sequence

### Phase 1: Make Existing Quote UI Match Existing Backend

Status: started 2026-06-05. The detail modal now passes its fetched full quote object into edit, duplicate, PDF, copy-link, convert, and delete actions. The parent edit handler now opens `QuoteFormModal` with the hydrated quote instead of the list-row shell.

Files expected:

- `frontend/src/pages/admin/AdminQuotes.jsx`
- `frontend/src/components/quotes/QuoteDetailModal.jsx`
- `frontend/src/components/quotes/__tests__/QuoteDetailModal.test.jsx` or a new AdminQuotes test.

Work:

- Pass `fullQuote` from detail modal into edit/duplicate actions.
- Preserve all `lines` when editing.
- Keep delete visible for every non-converted status.
- Add frontend tests for edit and duplicate from a list-opened quote.

Acceptance:

- Open quote list row -> detail fetches full quote -> Edit receives all lines.
- Change line unit price -> save -> detail/list totals update.
- Delete pending/rejected/cancelled manual quote works from UI.

### Phase 2: Close Backend Quote Update Gaps

Files expected:

- `backend/app/api/v1/endpoints/quotes.py`
- `backend/app/services/quote_service.py`
- `backend/tests/api/v1/test_quotes.py`
- `backend/tests/services/test_quote_service.py`

Work:

- Add `tax_rate_id` to update schema.
- Add tests for named tax rate changes.
- Decide accepted/approved edit policy and encode it.
- Normalize manual conversion source to `manual`.

Acceptance:

- Existing quote can change named tax rate.
- Manual quote conversion source is accurate.
- Status/edit/delete behavior is tested by status.

### Phase 3: Add Fee/Service Line Contract

Files expected after design approval:

- Quote line schema/model/migration if line type is persisted.
- Sales order line or adjustment schema/model/migration.
- Quote service conversion.
- Order detail and order edit UI.
- Payments/customer/accounting tests.

Work:

- Decide whether fee lines are order lines or order adjustments.
- Ensure engineering fee can be quoted, converted, paid, refunded, reported, and shown in customer totals.
- Ensure product/inventory fulfillment ignores service/fee lines.

Acceptance:

- Manual quote with product line plus engineering fee converts to an order.
- Order total equals product plus fee plus tax/shipping.
- Payment dashboard and order payment status use the real grand total.
- Customer totals include the order under the linked customer.

### Phase 4: Align Conversion And Quote-To-Cash Tests

Files expected:

- `backend/app/services/quote_conversion_service.py`
- `backend/app/services/quote_service.py`
- `backend/tests/integration/test_quote_to_cash.py`
- API endpoint tests for quotes/orders/payments/customers.

Work:

- Create one conversion service used by staff, portal, and payment checkout.
- Add API-level quote-to-cash tests rather than direct model construction.
- Include customer totals and payments in the flow.

Acceptance:

- Create quote -> edit line -> approve/accept -> convert -> record payment -> customer totals and payment summary all agree.

## Open Product Decisions

- Should a quote have a true draft status, or is pending the first editable state?
- Should approved quotes remain directly editable, or should editing create a revision?
- Should accepted quotes be deletable, cancellable only, or revisable only?
- Should manual quote conversion create production orders automatically, or only create a sales order?
- Should engineering fees be service lines, non-inventory products, or order adjustments?
- Which dashboard cards should show quote pipeline value, booked order revenue, paid cash, and outstanding A/R?

## Recommended Next Move

Finish the remaining Phase 1 UI smoke coverage, then move to Phase 2. The first Phase 1 repair is already in place: full quote detail now reaches edit/duplicate actions instead of the list-row shell.

Then make the fee/service-line decision before attempting to fix payments or revenue dashboards, because fee representation determines what order totals and customer totals should mean.
