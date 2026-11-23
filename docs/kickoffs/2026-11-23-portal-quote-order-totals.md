# Kickoff: portal quote-to-order totals

Date: 2026-11-23
Requested by: Brandan (project thread)
Branch: `claude/project-thread-8w09ge` (one branch, draft PR, not merged)

## Request

Fix the pre-existing bug found during PR #1089: the portal / after-payment
conversion (`quote_conversion_service.convert_portal_quote_to_order`) copies
`quote.total_price`, which already includes tax and shipping, into the order
subtotal (`SalesOrder.total_price`), stores zero tax, and adds shipping again
to get `grand_total`.

## Requirements

- The order's subtotal, discount, tax, shipping and total match the quote,
  and so does the invoice made from it.
- Reuse the shared discount/totals modules from PR #1089 (`discount_math`,
  `quote_totals`); keep discounts carried through.
- Add tests.
- Do not interfere with the in-progress unit-of-measure (UOM) work: find open
  UOM branches/PRs first, avoid files they change, flag any overlap.
