# Kickoff: quote line descriptions, quote notes and discounts

Date: 2026-11-22
Requested by: Brandan (project thread)
Branch: `claude/project-thread-tawjxx` (one feature branch, draft PR, not merged)

## Request

Add three features to FilaOps quotes, following the existing quote model, API,
UI and PDF patterns:

1. **Item descriptions.** An optional multi-line description on each quote
   line, shown under the item name on the quote screen and the PDF. Example:
   "Custom trophy / Black Base (PLA Matte Charcoal) / Gold Top (PLA Silk Gold)
   / Gold Plate with words". Follow-up: the item's own Description (Edit Item
   modal) must flow into the line description instead of going nowhere. It is
   copied when the item is added and stays editable on the quote.
2. **Quote notes.** An optional customer-facing notes field rendered in a Notes
   section on the PDF below the totals. Internal notes stay separate and are
   never printed. Decision: reuse the existing `customer_notes` column.
3. **Discounts.** A quote-level discount (percent or fixed amount) with an
   optional label, and an optional per-line discount of the same kind.
   - Order of operations: line totals, line discounts, quote discount,
     subtotal, tax on the discounted subtotal, total.
   - Money is rounded to cents at each displayed step, so the PDF adds up
     exactly.
   - The stored quote total equals the PDF total.
   - Discount lines print on the PDF between the item total and the subtotal,
     as negative amounts.

## Requirements

- Alembic migration with nullable columns and no backfill. Existing quotes
  render exactly as before.
- Descriptions, notes and discounts carry over when a quote converts to an
  order and when the order is invoiced. Discounts must flow through the
  workflow (order recalculation, invoice, payment and GL), not be dead data.
- Every UI screen involved is reviewed and updated.
- Tests: a model/service test for the math, an API test, a PDF render test,
  and a golden test: 2 x $42.56 = $85.12, 10% quote discount = -$8.51,
  subtotal $76.61, 7% tax = $5.36, total $81.97.

## Approved plan (summary)

- One shared, pure money module (`discount_math`) used by quotes, orders and
  invoices. Rounding is ROUND_HALF_UP to cents, and tax keeps the existing
  `calculate_sales_tax`.
- Migration 106 adds nullable columns:
  - quotes and sales_orders: discount type, value, label and amount.
  - quote_lines and sales_order_lines: a description plus the same discount
    columns.
  - invoices: discount label and notes.
  - invoice_lines: description, discount label and amount.
  - A NULL discount means zero.
- `Quote.subtotal` and `SalesOrder.total_price` hold the post-discount
  subtotal. Totals stay equal to what the PDF prints.
- All three quote-to-order conversion paths copy the new fields. Order line
  edits, removals and close-short re-apply the discounts.
- Invoices carry the order discount into `invoice.discount_amount`. GL already
  books revenue as subtotal minus discount.
- New logic goes in new modules, because of the file-size limits on
  `quote_service.py` and `QuoteFormModal.jsx`.
- A staff-only `POST /api/v1/quotes/preview-totals` endpoint lets the quote
  form show the exact totals a save stores.
