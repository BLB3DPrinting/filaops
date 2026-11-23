# Report: portal quote-to-order totals

Permission mode: auto (cloud session, Claude Code). Kickoff:
`docs/kickoffs/2026-11-23-portal-quote-order-totals.md`.

## The bug

`convert_portal_quote_to_order` built the order like this:

- `total_price` (the order subtotal) = `quote.total_price` (subtotal + tax + shipping)
- `tax_amount` = 0
- `grand_total` = `quote.total_price` + shipping

A $90.00 quote with $7.43 tax and $8.50 shipping ($105.93) became an order
with a $105.93 subtotal and a $114.43 total. An invoice made from it would
have charged $114.43 for a quote the customer accepted at $105.93.

## What changed

- New `backend/app/services/quote_order_money.py`:
  `order_money_from_quote(db, quote, shipping_cost=None, ship_to_state=None)`
  returns the order's money columns as the quote stored them: subtotal (after
  line and quote discounts), tax amount/rate/name, shipping, and
  `grand_total = subtotal + tax + shipping`.
  - A legacy quote with no `subtotal` is inferred as total - tax - shipping,
    the same rule `sales_order_service.convert_quote_to_sales_order` uses.
  - When the caller ships to a different cost or state than the quote and the
    quote has a tax rate, tax is recomputed with `calculate_sales_tax`, the
    calculator the portal accept uses. Otherwise the quote's tax is kept.
  - Unit price falls back to (subtotal + discount) / quantity, so the
    invoice's single-line subtotal minus the discount equals the order
    subtotal.
- `quote_conversion_service.py`: call-site edit only. Uses the helper and
  `quote_totals.order_discount_fields` for the discount columns.
- Behaviour change: a `ShippingInfo.shipping_cost` of 0 is now honoured
  (free shipping). Before, 0 fell back to the quote's shipping cost.

## UOM work

Checked before editing. No open UOM pull requests. Branches `uom-rebuild` and
`fix/standard-cost-kg-stock-unit` change none of the files in this PR. No
migration is added here.

Found, not changed: `uom-rebuild` has its own migration `106` (unit table)
and `107`, both chained from `105`. Main now has `106` from PR #1089 (quote
discounts), also chained from `105`. The UOM migrations need renumbering when
that branch meets main.

## Tests

- New `backend/tests/services/test_quote_order_money.py` (12 tests): the
  helper (stored totals, legacy inference, shipping override, tax recompute)
  and the conversion end to end, including after payment and the invoice.
- The 4 conversion tests fail on the old code and pass with the fix.
- Local run against PostgreSQL 16: the quote, invoice, sales-order and
  discount test files in `tests/services` and `tests/unit` (8 files):
  360 passed.

## Status checks

Head `5f8b1a5`, PR #1090 (draft).

CircleCI:

- ci/circleci: core-guardrails: success
- ci/circleci: core-pro-guard: success
- ci/circleci: core-version-parity: success
- ci/circleci: core-backend-static: success
- ci/circleci: core-diff: success
- ci/circleci: core-dependency-audit: success
- ci/circleci: core-frontend-build: success
- ci/circleci: core-frontend-unit: success
- ci/circleci: core-backend-tests: success

GitHub Actions: failure. Every job ended in about 2 seconds with empty output
and no runner. The same jobs fail the same way on #1089 and on `main`.

- core-ci: core-guardrails, core-pro-guard, core-version-parity,
  core-backend-static, core-diff, core-dependency-audit
- CodeQL: Analyze (python), Analyze (javascript-typescript)
- check-pro-code

CodeRabbit: did not run, because the PR is a draft.
