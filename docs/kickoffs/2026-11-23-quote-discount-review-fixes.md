# Kickoff: quote discount review fixes

Date: 2026-11-23
Requested by: Brandan (project thread)
Branch: `claude/project-thread-fhvy2p` off `main` (one branch, draft PR, not merged)

## Request

CodeRabbit's review of PR #1091 (UOM work) found 8 problems in code that is
already on `main`: the quote discount work from PRs #1089/#1090 and the
CircleCI npm audit step. Fix all 8 on `main` in their own PR, with a
regression test for each, so the UOM PRs stay about units only.

Highest priority:

1. A 100%-discounted quote converts to a full-price order
   (`quote_service.convert_quote_to_order` treats a 0 subtotal as missing).
2. Reopening and saving a quote applies the customer's price-level discount
   again on every save.

The other six: a 100%-discounted order line reports its gross amount; the
saved-quote preview drops the stored discount when the request omits it;
discount values with more than 2 decimals are not rejected; the quote form's
estimate rounds half cents down; a header-only order's invoice total can be a
cent off the order; the npm audit check passes when the audit did not run.

## Constraints

- Do not touch UOM files or PRs #1091/#1092, except a reply on each finding
  there that links the new PR.
- Files over the size limits (`quote_service.py`, `quotes.py`,
  `sales_orders.py`, `QuoteFormModal.jsx`) get call-site edits only.
- Check whether existing quotes or orders could already be affected.
