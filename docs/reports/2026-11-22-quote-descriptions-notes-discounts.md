# Report: quote line descriptions, quote notes and discounts

Permission mode: auto (cloud session, Claude Code). Kickoff:
`docs/kickoffs/2026-11-22-quote-descriptions-notes-discounts.md`.

## What changed

### Backend

**New modules.** New logic lives here, not in the files over the size limits.

- `app/services/discount_math.py`: pure money math.
  - Order: line totals, line discounts, document discount, subtotal.
  - Rounding is HALF_UP to cents at each step. Fixed amounts are capped at
    their base, and percents are limited to 0-100.
- `app/services/quote_totals.py`:
  - Builds quote line values: description, line discount and price-level
    discount.
  - Computes quote subtotals.
  - Previews totals using the same tax resolution as create/update.
- `app/services/document_discount_rows.py`: shared PDF rows (Items total,
  Line discounts, labelled discount), descriptions and labels.
- `app/services/order_discounts.py`: re-applies line and order discounts when
  order lines are edited, removed or closed short. Undiscounted lines keep the
  old rounding formula.

**Migration `106`.** Nullable columns only, no backfill, and the up and down
steps are idempotent.

- `quotes` and `sales_orders`: discount type, value, label and amount.
- `quote_lines.description` and `sales_order_lines.long_description`, plus line
  discount columns on both.
- `invoices`: `discount_label` and `notes`.
- `invoice_lines`: `long_description`, `discount_label` and `discount_amount`.

**Quote API.**
- Create and update accept and return the line `description`, line discounts
  and the quote discount.
- A line's description defaults to the item's own Description when the line is
  added. It stays editable and is never re-synced from the item.
- New staff-only `POST /api/v1/quotes/preview-totals`. It returns the exact
  totals a save stores, and the quote form uses it.

**Quote PDF.**
- The description prints under the item name, and a line discount prints under
  it.
- The amount column shows each line before its discount.
- Items total, Line discounts and the quote discount print as negative rows
  above Subtotal.
- Notes (`customer_notes`) print below the totals. Internal notes
  (`admin_notes`) are never printed.

**Carry-through.**
- All three quote-to-order paths copy the descriptions and discounts: admin
  convert, customer convert and portal convert.
- Order recalculation keeps the discounts.
- Invoices carry:
  - line descriptions and line discounts;
  - the order discount, as `invoice.discount_amount` with its label;
  - the notes.
- Invoice total = subtotal − discount + tax + shipping, which matches the
  existing GL posting (revenue = subtotal − discount).
- The invoice PDF prints the same discount rows and a Notes section.
- Direct sales orders also copy the item Description into the line
  description.

### Frontend

- **Quote form.**
  - Each line gets a description box, prefilled from the item's Description,
    and a line discount.
  - The quote gets a quote discount (None / Percent / Amount, plus a label).
  - Totals come from the preview endpoint, with a local estimate while it
    loads.
  - The notes boxes are relabelled "Notes (printed on the quote)" and
    "Internal Notes (never printed)".
  - New pieces live in their own files, so `QuoteFormModal.jsx` shrank from
    962 to 953 lines:
    - `components/discounts/*`
    - `lib/discounts.js`
    - `QuoteLineExtras`
    - `QuoteTotalsPanel`
    - `useQuoteTotalsPreview`
    - `quoteFormLines`
- **Quote detail.** Line descriptions and line discounts, discount rows above
  Subtotal, and labels that say which notes print.
- **Order detail line items.** Line descriptions and line discounts, plus
  Items total, discount rows and Subtotal in the footer.
- **Invoices.** Line descriptions and line discounts, discount rows with a
  discounted Subtotal, and the Notes. Invoices without a discount label keep
  the old layout.
- **Duplicate quote.** Copies line descriptions, line discounts and the quote
  discount.

## Behaviour on existing data

NULL discounts compute as zero, so existing quotes, orders and invoices
compute and render as before. A script rendered three legacy quote shapes
(multi-line, single-item, price-level discount) on `main` and on this branch.
The extracted PDF text was identical. Undiscounted documents show no new rows
in any screen or PDF.

## Tests

**Backend, new (59 tests).**
- `tests/unit/test_discount_math.py`: golden case, rounding, caps and
  validation.
- `tests/services/test_quote_discounts.py`:
  - create and update math;
  - description defaults and overrides;
  - PDF row order, description and notes printed, internal notes absent;
  - quote → order (admin and customer paths) → order line edit → invoice →
    invoice PDF → payment and GL. GL: AR 81.97, revenue 76.61, tax 5.36.
- `tests/endpoints/test_quote_discounts_api.py`:
  - create and read;
  - 422 and 400 validation;
  - PATCH recompute;
  - preview matches the save, saves nothing and needs auth;
  - the PDF endpoint total equals the stored total.
- Golden quote: 2 × $42.56 = $85.12, 10% = −$8.51, subtotal $76.61, 7% tax
  $5.36, total $81.97. It is asserted in the math, service, API, PDF and
  invoice tests.

**Frontend, new.**
- `lib/__tests__/discounts.test.js`
- `OrderLineItemsTable.test.jsx`
- New cases in `QuoteFormModal`, `QuoteDetailModal` and `AdminInvoices`
  tests: description prefill and send, golden totals, server preview used, an
  incomplete discount is blocked, and edits keep saved values.

**Local runs.**
- Backend full suite: 8021 passed, 3 skipped, 1 failed. The failure is
  `tests/api/v1/test_purchase_order_pdf.py::TestGeneratePoPdfContent::test_purchase_unit_column_in_pdf`.
  It also fails on `main` without these changes (checked by stashing them), so
  it is pre-existing and unrelated.
- Frontend `npm run test:unit`: 99 files, 903 tests passed.
- `npm run lint:ci`: 0 errors, 241 warnings (cap 242). The new files add no
  warnings.
- `npm run build`: OK.

## Known gaps and follow-ups

- **Pre-existing bug in portal quote conversion, not fixed here.**
  `quote_conversion_service.convert_portal_quote_to_order` uses
  `quote.total_price` (tax and shipping included) as the order subtotal, sets
  tax to 0 and then adds shipping again. This PR only adds the discount
  fields to that path. Fixing it belongs in a separate PR.
- The sales order wizard (direct orders) has no discount inputs. Discounts
  start on quotes, as requested.
- The reference docs (`MIGRATIONS-LOG.md`, `SCHEMA-REFERENCE.md`) are
  generated and were not regenerated in this PR.

## Status checks

No checks had run when this report was committed. The PR comment and the
follow-up update to this report list every check by name and result.
