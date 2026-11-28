# Kickoff: CodeQL on CircleCI

The owner's instruction, 2026-11-26: "move codeql to circleci and i need
guidance on switching the actions."

GitHub Actions cannot start for the org (billing lock), so the two CodeQL
analyses required by the "Protect main" ruleset never run. Add a CircleCI job
that runs the same two analyses (python, javascript-typescript, no build) with
the CodeQL command-line bundle and uploads the results to GitHub code
scanning. Leave `.github/workflows/codeql.yml` in place. Do not change the
ruleset or any repository setting: those steps are the owner's.
