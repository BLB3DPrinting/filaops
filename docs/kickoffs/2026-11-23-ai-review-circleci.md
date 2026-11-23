# Kickoff: AI pull-request review on CircleCI

Date: 2026-11-23
Requested by: Brandan (project thread)
Branch: `claude/project-thread-d4y50f` (one branch, draft PR, not merged)

## Request

Replace the paid CodeRabbit seat with a cheap automated review job in the
existing CircleCI config, to cut costs. GitHub Actions is billing-locked, so
CircleCI is the only CI route.

## Requirements

- A new CircleCI job next to the existing checks, following their patterns.
- Send the PR diff to the Claude API and review like CodeRabbit: correctness,
  security, migrations, missing tests; nitpicks low priority.
- Post findings on the PR: inline where the line is in the diff, plus a
  summary. Agent threads autofix from these comments, so each finding must be
  clear and actionable.
- Fail the check on serious findings.
- Keep cost per review low: diff size cap, sensible model, skip docs-only and
  oversized diffs.
- Secrets (Anthropic API key, GitHub token) live in CircleCI; Brandan creates
  them. Document exactly what to create.
- Do not touch the in-progress UOM work (`uom-rebuild`, PR #1092).
