# Report: AI pull-request review on CircleCI

Permission mode: auto (cloud session, Claude Code). Kickoff:
`docs/kickoffs/2026-11-23-ai-review-circleci.md`.

## What changed

- `.circleci/config.yml`: new `ai-review` job (`cimg/python:3.12`,
  `resource_class: small`) in the `core-ci` workflow, on every branch except
  `main`. It runs the script's unit tests, installs hash-pinned dependencies
  into a venv, and runs the review.
- `scripts/ci/ai_review.py`: the review. Finds the open PR for the branch,
  diffs it against the PR base with git, drops lockfiles, images and other
  generated files, annotates each diff line with its new-file line number,
  and sends it to the Claude API with structured output (a JSON schema of
  findings). Posts one GitHub review with an inline comment per finding on a
  diff line, and one summary comment updated in place. Exit codes: 0 clean or
  skipped, 1 blocking findings, 2 configuration or API error.
- `scripts/ci/ai_review_prompt.md`: the review instructions, including the
  repository rules (UOM conversions, Core vs PRO, money consistency, file-size
  limits, dependency approval) and a rule to treat PR text as untrusted.
- `scripts/ci/test_ai_review.py`: 15 unit tests for diff parsing, file
  selection, line placement, blocking threshold, fingerprints and the summary
  state marker.
- `scripts/ci/ai_review_requirements.txt`: `anthropic==2.3.0` and its 15
  dependencies, pinned by SHA-256 for CPython 3.12 manylinux x86_64.
- `docs/operations/circleci.md`: what the job does and the setup steps.

## Cost controls

- Default model `claude-opus-5-5` ($4 / $20 per million tokens) at effort
  `medium`. `AI_REVIEW_MODEL=claude-sonnet-5-5` halves the price.
- Diff cap of 150,000 characters (about 40k tokens). A typical PR is well
  under that; this PR's own diff is about 50,000 characters, an estimated
  $0.15 to $0.25 per review at the default model.
- No API call when the reviewable diff is unchanged since the last review
  (re-runs, merges from main), for docs-only changes, for forks, or for PRs
  labelled `skip-ai-review`.
- `max_tokens` 32,000 bounds the output cost of a single review.

## Needs a human

- New dependency: `anthropic` (and its dependencies) in a new, CI-only
  requirements file. AGENT_POLICY requires approval for new manifest entries.
  It is not added to `backend/requirements.txt`. `anthropic==2.3.0` was
  published 2026-10-23; some transitive pins (for example `anyio`, `pydantic`)
  are the current releases.
- Secrets: `ANTHROPIC_API_KEY` and `AI_REVIEW_GITHUB_TOKEN` in CircleCI
  project environment variables (see `docs/operations/circleci.md`). Until
  they exist the `ai-review` job fails with a "not configured" message.
- CodeRabbit can be removed once a few PRs have been reviewed by this job.

## Known limits

- CircleCI builds on push. A branch pushed before its PR is opened is
  reviewed on the next push, or by re-running the job.
- Inline comments from earlier runs are not resolved automatically; the
  summary comment is the current list.

## Tests

- `python -m unittest scripts.ci.test_ai_review scripts.ci.test_guardrail_policy scripts.ci.test_workflow_hardening`: 26 passed.
- Dry run of the whole script against this branch with GitHub and Claude
  stubbed: it posted one review and one summary, exited 1 on a `major`
  finding, and a second run reused the result without calling Claude.
- The Claude call against a local mock of the streaming Messages API: request
  carried the model, effort, JSON schema and the fallback beta, and the
  streamed JSON was parsed into findings.
- Hash-pinned install verified on CPython 3.12.
- Not run against the real Claude API: no key in this session.

## Status checks

Pending: filled in after the first CircleCI run on the PR.
