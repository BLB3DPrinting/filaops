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

## Independent review (in place of CodeRabbit)

CodeRabbit hit its free review limit on this PR, so the full diff was
reviewed in-session for correctness, security, migrations and missing tests.

Fixed:

- Header-only invoice (finding 7) could over-bill portal orders made before
  PR #1090, whose stored subtotal is the whole quote total (tax and shipping
  included). `invoice_service._header_only_line_total` now uses the stored
  subtotal only when it is within the rounding residue (half a cent per unit)
  of `quantity x unit_price`, or when there is no unit price; otherwise it
  invoices `quantity x unit_price` as before. Test added.
- The quote form did not stop a discount with more than 2 decimal places,
  which the server now rejects (422), so the save would fail with a raw
  validation error. `discountError` now says "Use at most 2 decimal places".
  Test added.

Checked, no change needed:

- Security: `price_level_percent_applied` is accepted only on staff-only
  endpoints (create, update, preview); the customer portal does not use
  `QuoteLineCreate`. It only skips a discount and sets the printed percent.
- Migrations: none; no schema change.
- The audit check fails closed on a non-object report too (AttributeError path).
- Quote duplicate (`AdminQuotes.handleDuplicateQuote`) already drops the
  customer so net prices are not discounted again; unchanged.

Not fixed, noted: an API client that changes a quote's customer while sending
lines marked `price_level_percent_applied` keeps the old customer's pricing.
The quote form restores list prices on a customer change, so it does not do
this.

Re-run after these fixes: the quote, discount and quote-to-cash test files
(56 tests) and the invoice test files (151 tests) pass; frontend unit tests for lib, quotes, orders,
discounts and admin pages: 413 pass; `npm run lint:ci` 0 errors.

## CodeRabbit review

CodeRabbit ran on `bac5de8` with 3 findings (2 inline, 1 outside the diff).
Each was checked against the code; all 3 were real and are fixed in the next
commit, with tests that fail without the fix.

1. Single-item quotes rounded the price level differently from line quotes
   (`quote_service.py`). A $1.005 price at a 10% level saved $0.90 on a
   single-item quote and $0.91 on a line quote. The single-item path now
   rounds the price to cents first, as the line path does.
2. Changing the customer worked the list price back from the rounded net
   price (`quoteFormLines.js`). $2.01 at 50% saves as $1.01, which worked back
   to $2.02; at 100% the $0 net price became the list price. The form now
   restores the list price only when exactly one price in cents gives the
   saved net price (checked with integer arithmetic). When more than one fits,
   or at 100%, the price is left blank for the user to enter; the form will
   not save a blank price. A first attempt used the catalog price as a tie
   break; CodeRabbit pointed out that a matching catalog price does not prove
   it was the quote's price, so that was dropped.
3. The totals preview kept the saved customer when the form sent an explicit
   null customer (`quote_totals.py`), while saving removed it. The preview now
   keeps the saved customer only when the field is left out, like
   `update_quote`.

Re-run after these fixes: `test_quote_discount_review_fixes.py` 21 pass
(the 2 new backend tests fail without the fix); backend tests matching quote,
discount or invoice: 599 pass; frontend quotes and lib unit tests: 159 pass;
`npm run lint:ci` 0 errors.

## Status checks

Head `bda0b73`, PR #1093 (draft at the time). Re-recorded below for the latest head.

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
