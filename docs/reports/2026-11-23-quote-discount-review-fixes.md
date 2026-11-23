# Report: quote discount review fixes

Permission mode: auto (cloud session, Claude Code). Kickoff:
`docs/kickoffs/2026-11-23-quote-discount-review-fixes.md`.

Source: CodeRabbit review of PR #1091 (5 inline comments, 3 outside-diff
comments in the review body). The CLAUDE.md nitpick in the same review is not
part of this PR.

## Fixes

| # | Finding | Fix |
|---|---------|-----|
| 1 | 100%-discounted quote converts to a full-price order | `quote_service.convert_quote_to_order`: use `quote.subtotal` whenever it is not `None`; only a missing subtotal falls back. |
| 2 | Re-saving a quote applies the customer's price level again | New optional `price_level_percent_applied` on `QuoteLineCreate`. The quote form sets it on lines reopened from a saved quote (from the saved line's `discount_percent`); `quote_totals.build_line_values` then keeps the price as is and records that percent. Save and preview share this path. A retyped unit price, or a change of customer, clears it (on a customer change the list price is restored as `price / (1 - pct)`, the same formula the PDF uses for its list-price column). |
| 3 | 100%-discounted order line shows its gross | `sales_orders.build_sales_order_response`: `line.total is not None`. |
| 4 | Saved-quote preview drops the stored discount | `quote_totals.preview_for_request`: when `quote_id` is given and `discount_type`/`discount_value` are not in the request, use the stored ones, as `update_quote` does. An explicit null still previews removal. |
| 5 | Discount values with more than 2 decimals | `max_digits=10, decimal_places=2` on `discount_value` in `QuoteLineCreate`, `ManualQuoteCreate`, `QuoteTotalsPreview`, `ManualQuoteUpdate` (422). |
| 6 | Quote form estimate rounds half cents down | `frontend/src/lib/discounts.js`: `roundHalfUp` shifts the decimal point in the number's text, so 1.005 rounds to 1.01. Used by `toCents`, percent discounts and the price-level step (done in cents). Tax uses `taxCents`, integer math that mirrors the server's half-even Decimal quantize in `tax_calculation_service`. Server side, `quote_totals.apply_price_level` and the single-item create path now round half up with `discount_math.to_money` (they used Decimal's default half-even), so server and form agree: $2.01 at 50% is $1.01. |
| 7 | Header-only order's invoice can be a cent off | `invoice_service.create_invoice`: with no order lines, the invoice line is the stored order subtotal plus the order discount (which is subtracted again for the total), not `quantity x unit_price`. |
| 8 | npm audit step passes when the audit did not run | `scripts/ci/check_audit_severity.py`: an npm report without a `vulnerabilities` object exits 2. |

Not changed: `sales_order_service` manual order creation still rounds its
price-level step half-even. It is not part of the quote path or the findings.

## Existing data

- Finding 2 is older than the discount work. Before PR #1089, `update_quote`
  also re-applied the price level to every submitted line price. Any quote
  for a customer on a price level that was reopened and saved may carry a
  compounded price. It only affects installs with PRO price levels.
- Finding 1 needs a quote with a 100% discount converted from the admin
  screen. The discount columns only exist from migration 106 (merged today).
- The database reachable from this session is a local dev copy at migration
  102 with 3 quotes and no price-level lines, so production was not checked.
  Read-only queries to run on production are in the PR description.

## Tests

- New `backend/tests/services/test_quote_discount_review_fixes.py` (16
  tests). 13 fail on `main` and pass with the fix; the other 3 guard behaviour
  that must not change (a typed price still gets the price level once, an
  explicit null removes the discount, 2-decimal values are accepted).
- `scripts/ci/test_audit_severity.py`: 3 new tests (11 total, pass).
- Frontend: new `quoteFormLines.test.js` (6), 5 new cases in
  `discounts.test.js`, 2 in `QuoteFormModal.test.jsx`.
- Local runs: backend, every test file mentioning quotes, invoices, sales
  orders or discounts against PostgreSQL 16: 4289 passed. Frontend unit tests
  for `src/lib`, `src/components/quotes`, `src/components/orders` and
  `AdminInvoices`: all pass. `npm run lint:ci`: 0 errors (warnings are
  pre-existing).

## Status checks

Head `bda0b73`, PR #1093 (draft).

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

GitHub Actions: failure. Every job ended in about 2 seconds with no runner.
The same jobs fail the same way on #1090 and on `main`.

- core-ci: core-guardrails, core-pro-guard, core-version-parity,
  core-backend-static, core-diff, core-dependency-audit
- CodeQL: Analyze (python), Analyze (javascript-typescript)
- check-pro-code

CodeRabbit: did not run, because the PR is a draft.
