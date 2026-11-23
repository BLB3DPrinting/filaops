# CircleCI

Date: 2026-06-04

This repository uses CircleCI as the next primary CI entry point for Core
source validation. GitHub Actions workflows remain `workflow_dispatch` only so
they can be run manually without reintroducing automatic GitHub-hosted Actions
usage.

The starter CircleCI workflow intentionally has no deployment jobs, no
production secrets, and no production database access. Backend tests use a
disposable Postgres service container with explicit test environment values.

## Current Cloud Jobs

- `core-diff`: whitespace/conflict-marker diff check.
- `core-pro-guard`: public Core boundary check; rejects PRO-only paths such as
  `backend/app/pro/` and `license-server/`.
- `core-backend-static`: Python compile check for `backend/app` and
  `backend/tests`.
- `core-backend-tests`: backend pytest against disposable Postgres with JUnit
  stored under `test-results/core-backend`.
- `core-frontend-build`: frontend `npm ci` and `npm run build`.
- `core-frontend-unit`: frontend Vitest unit tests with JUnit stored under
  `test-results/core-frontend-unit`.
- `ai-review`: automated pull-request review with Claude. Replaces CodeRabbit.
  See "AI review" below.

## AI review

`ai-review` runs `scripts/ci/ai_review.py` on every push to a branch other
than `main`. It finds the open pull request for the branch, sends the diff to
the Claude API with the review prompt in `scripts/ci/ai_review_prompt.md`, and
posts the result on the pull request:

- One inline review comment per finding whose line is in the diff, with the
  severity, what goes wrong, and a suggested fix. A finding already posted on
  an earlier run is not posted again.
- One summary comment, updated in place on each push, listing every current
  finding. Findings that cannot be placed on a diff line are written out here.
- The job fails when a finding is `major` or `critical`, so the check shows
  red until the code is fixed and a later push reviews clean.

What it skips: branches with no open pull request yet (re-run the job, or push
again, after opening one), pull requests from forks, docs-only changes,
pull requests labelled `skip-ai-review`, and runs whose reviewable diff has not
changed since the last review (a merge from `main` or a re-run reuses the last
result and makes no API call). Lockfiles, images and other generated files are
never sent.

### Setup

Add two environment variables under CircleCI Project Settings > Environment
Variables. Leave "Pass secrets to builds from forked pull requests" off.

| Name | Value |
| --- | --- |
| `ANTHROPIC_API_KEY` | A Claude API key from a Claude Console workspace with a monthly spend limit. |
| `AI_REVIEW_GITHUB_TOKEN` | A fine-grained GitHub token, resource owner `BLB3DPrinting`, only this repository, permissions Pull requests: Read and write and Contents: Read-only (Metadata: Read-only is added automatically). Use a bot account, not an owner or admin account. |

Optional variables:

| Name | Default | Meaning |
| --- | --- | --- |
| `AI_REVIEW_MODEL` | `claude-opus-5-5` | `claude-sonnet-5-5` costs about half as much per review. |
| `AI_REVIEW_EFFORT` | `medium` | `low`, `medium` or `high`. Lower is cheaper and less thorough. |
| `AI_REVIEW_FAIL_ON` | `major` | `critical`, `major` or `none` (comment only, never fail). |
| `AI_REVIEW_MAX_DIFF_CHARS` | `150000` | Diff size sent per review, about 40k tokens. Files past it are listed as not reviewed. |
| `AI_REVIEW_SKIP_DRAFTS` | `false` | `true` skips draft pull requests. Agent pull requests stay drafts, so leave it off for them to get reviews. |

Each summary comment ends with the tokens used and an estimated cost.
Dependencies are installed from `scripts/ci/ai_review_requirements.txt`, which
pins every package by hash; regenerate it deliberately when upgrading
`anthropic`.

## Smarter Testing

Start with the full-suite CircleCI baseline. Do not enable dynamic splitting or
Test Impact Analysis for Core until this workflow has a green history on PRs and
`main`.

Recommended next steps:

1. Require the CircleCI contexts only after at least one clean PR run.
2. Keep the existing external CI statuses available as rollback until CircleCI
   is the trusted gate.
3. Pilot dynamic splitting on `core-backend-tests` only after backend JUnit
   timings are stable.
4. Treat Test Impact Analysis as advisory before it becomes a required Core
   gate.

## Rollback

If CircleCI setup fails, continue using the external runner documented in
`external-ci-statuses.md`. Reverting this setup should be a config-only PR that
removes `.circleci/config.yml` while leaving manual GitHub Actions workflows
unchanged.
