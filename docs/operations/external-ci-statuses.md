# External CI Statuses

Core PR and main protection is enforced by external commit statuses instead of
automatic GitHub Actions runs. This keeps the gate mechanical while avoiding
GitHub-hosted Actions usage.

Core branch protection is intended to require these status contexts for `main`:

```text
external-ci/core-diff
external-ci/core-pro-guard
external-ci/core-backend-static
external-ci/core-backend-tests
external-ci/core-frontend-build
external-ci/core-frontend-unit
```

`external-ci/core-pro-guard` runs the same public-repo boundary check as
`scripts/ci/check-pro-code.ps1`: Core must not contain `backend/app/pro/`,
`license-server/`, or a PR diff touching those paths.

The external runner lives in `Blb3D/filaops-ecosystem` under
`scripts/ci/run-external-ci.ps1` and `scripts/ci/run-external-ci.sh`. Run it
against a Core PR with:

```powershell
.\scripts\ci\run-external-ci.ps1 `
  -Repository Blb3D/filaops `
  -PrNumber <pr-number> `
  -Profile core
```

```bash
scripts/ci/run-external-ci.sh \
  --repository Blb3D/filaops \
  --pr-number <pr-number> \
  --profile core
```

GitHub-hosted workflows in `.github/workflows/` are intentionally
`workflow_dispatch` only. CodeQL can still be run manually from GitHub, or by an
external security job that posts its own required status once that runner is
available.

CircleCI is being introduced as the replacement hosted CI surface for these
Core checks. Until the CircleCI workflow has green history and branch rules are
updated deliberately, keep the external CI runner available as rollback.
