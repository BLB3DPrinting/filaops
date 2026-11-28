# Report: CodeQL on CircleCI

Permission mode: default (desktop session, Claude Code). Kickoff:
`docs/kickoffs/2026-11-26-circleci-codeql.md`.

## What changed

- `.circleci/config.yml`, in the `core-ci` workflow:
  - `codeql`, run once per language as `codeql-python` and
    `codeql-javascript-typescript`. It installs the CodeQL bundle
    `codeql-bundle-v2.27.5` (SHA-256 checked before unpacking, cached
    afterwards), builds a database with `--build-mode=none` as the Actions
    workflow does, analyses with the default query suite and the same
    category (`/language:<language>`), keeps the SARIF file as a build
    artifact and hands it on. It runs on the 8 GB class with `--ram=6000`:
    on 4 GB the first query ran out of Java heap. It holds no secret.
  - `codeql-upload`, after both analyses. It sends each SARIF file with
    `codeql github upload-results`, for `refs/pull/<number>/head` on a pull
    request and `refs/heads/<branch>` otherwise. It is the only job given the
    CircleCI context `codeql-upload`, which holds `CODEQL_UPLOAD_TOKEN`. It
    checks out nothing and installs nothing but the bundle.
- Without the token the upload job fails, except on a pull request from a
  fork, which gets no context: there the analyses run and the upload is
  skipped.

Not changed: `.github/workflows/codeql.yml`, the ruleset, any repository or
CircleCI setting.

## Review

CodeRabbit ran on `f3e40340`: 2 findings, both applied.

1. The token was a project environment variable, which every job receives,
   the ones that install dependencies and run tests included. The upload is
   now its own job, and the token belongs in a context only that job is
   given.
2. This report lacked the owner's cutover procedure. It is below.

## The owner's steps

None of these is done by this pull request. They are settings, and they are
the owner's.

**A. Move the token into a context (before the next run of this branch).**

1. CircleCI, Organization Settings, Contexts, Create Context, named
   `codeql-upload`.
2. In that context, add the environment variable `CODEQL_UPLOAD_TOKEN` with
   the fine-grained token (this repository only; "Code scanning alerts: read
   and write").
3. In the filaops project's settings, Environment Variables, delete
   `CODEQL_UPLOAD_TOKEN`. While it stays there, every job still receives it.

**B. Confirm the analyses and the upload on a pull request.**

1. `ci/circleci: codeql-python` and
   `ci/circleci: codeql-javascript-typescript` succeed.
2. `ci/circleci: codeql-upload` succeeds, and its log shows one "Uploading"
   line per language.
3. A check named `CodeQL`, from GitHub code scanning and not from CircleCI,
   appears on the pull request.

**C. Re-point the required status checks** (repository Settings, Rules,
Rulesets, "Protect main"; it covers `main` and `uom-rebuild`). Only after B,
and only once this pull request is on `main`.

1. Under "Require status checks to pass", remove the seven entries bound to
   GitHub Actions: `core-backend-static`, `core-backend-tests`,
   `core-dependency-audit`, `core-diff`, `core-frontend-build`,
   `core-guardrails`, `core-pro-guard`.
2. Add the same seven as CircleCI reports them, picked from the search box
   so that each binds to CircleCI: `ci/circleci: core-backend-static` and so
   on.
3. Leave the entry `CodeQL` in that list as it is. It is reported by GitHub
   code scanning when results are uploaded, whichever CI produced them.
4. Leave the separate rule "Require code scanning results" as it is. That
   rule is not a status check: it blocks a merge on open CodeQL alerts of
   high severity or above, and it reads the same uploaded results.
5. Save.

**D. Afterwards.** Merge `main` into `uom-rebuild`, so that branch has the
CodeQL jobs too. Optionally disable the Actions workflows that cannot start,
to stop their failed marks on every pull request.

## Verified, and not

- On `f3e40340`, with the token as a project variable and one job doing both
  analysis and upload: both CodeQL jobs succeeded on CircleCI, and a `CodeQL`
  check from code scanning appeared on the pull request as successful.
- The split into `codeql` and `codeql-upload` has not run when this was
  written. Until the context of step A exists, `codeql-upload` cannot pass.
- No CircleCI command-line tool is installed here, so the config was parsed
  as YAML only before each push.
- How many CircleCI credits the analyses use per run is not measured.

## Tests

- `python -m unittest scripts.ci.test_guardrail_policy
  scripts.ci.test_workflow_hardening`: 11 tests, OK (run locally).

## Status checks

On `f3e40340`, the head before the split, read on 2026-11-26:

- CodeQL (GitHub code scanning): success
- ci/circleci: codeql-python: success
- ci/circleci: codeql-javascript-typescript: success
- ci/circleci: core-guardrails: success
- ci/circleci: core-backend-static: success
- ci/circleci: core-backend-tests: success
- ci/circleci: core-dependency-audit: success
- ci/circleci: core-diff: success
- ci/circleci: core-frontend-build: success
- ci/circleci: core-frontend-unit: success
- ci/circleci: core-pro-guard: success
- ci/circleci: core-version-parity: success
- GitHub Actions (core-guardrails, core-backend-static, core-version-parity,
  core-dependency-audit, core-diff, core-pro-guard, check-pro-code,
  Analyze (python), Analyze (javascript-typescript)): failure, not started
  (the org's billing lock).

On the head that carries the split: not read when this was written.
