# Report: CodeQL on CircleCI

Permission mode: default (desktop session, Claude Code). Kickoff:
`docs/kickoffs/2026-11-26-circleci-codeql.md`.

## What changed

- `.circleci/config.yml`: a new job `codeql`, run once per language as
  `codeql-python` and `codeql-javascript-typescript` in the `core-ci`
  workflow. Each run:
  1. downloads the CodeQL bundle `codeql-bundle-v2.27.5` and checks its
     SHA-256 before unpacking (cached afterwards);
  2. builds a database with `--build-mode=none`, as the Actions workflow does;
  3. analyses with the default query suite and the same category
     (`/language:<language>`);
  4. keeps the SARIF file as a build artifact;
  5. uploads it with `codeql github upload-results`, for
     `refs/pull/<number>/head` on a pull request and `refs/heads/<branch>`
     otherwise.
- The upload reads `CODEQL_UPLOAD_TOKEN` from the CircleCI project's
  environment variables. Without it the job fails, except on a pull request
  from a fork, where secrets are never present: there the analysis runs and
  the upload is skipped.

Not changed: `.github/workflows/codeql.yml`, the ruleset, any repository or
CircleCI setting.

## Not verified

- The job has not run. No CircleCI command-line tool is installed here, so
  the config was only parsed as YAML and never validated by CircleCI.
- Whether the uploaded results satisfy the ruleset's required `CodeQL` check
  and its code scanning rule is expected and untested. The first pull request
  with the token in place shows it.
- How many CircleCI credits the two analyses use per run is not measured.

## Tests

- `python -m unittest scripts.ci.test_guardrail_policy
  scripts.ci.test_workflow_hardening`: 11 tests, OK (run locally).

## Status checks

No checks ran: the branch `ci/circleci-codeql` is committed locally and has
not been pushed.
