# Kickoff: bring #1093 into uom-rebuild

#1093 (quote discount review fixes) merged into `main`. CodeRabbit keeps its
quote and audit findings on #1091 open until those fixes reach `uom-rebuild`.

- Merge `main` into `uom-rebuild` on a branch, by pull request. Do not push to
  `uom-rebuild` directly.
- Keep the migration chain to one head. #1093 adds no migration, so the head
  stays `108`.
- Review the merge for any place the quote changes and the unit changes meet.
- Run the quote, invoice and unit tests. CircleCI runs the full suite.
