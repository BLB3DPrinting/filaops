# FilaOps Agent Policy

This is the shared source of truth for AI agents working in this repository.
Tool-specific files such as `AGENTS.md` and `.claude/CLAUDE.md` should stay
small and point here instead of duplicating policy.

If an automated hook, CI gate, or T-REX/Aeonyx gate conflicts with prose in
this document, the mechanical gate wins.

## Non-Negotiable Workflow

Agents must follow the full PR loop for repository changes.

1. Create or use a feature branch for all repo changes.
2. Open a pull request before considering the work deliverable.
3. Wait for CI and all bot reviews/checks to complete.
4. Review and triage every bot review comment, review thread, annotation, and
   failed check.
5. Fix actionable findings. If a finding is not applicable, reply with the
   rationale so the reviewer/check is explicitly released or documented.
6. Push fixes and repeat the CI/review loop until the PR is clean or only
   explicitly accepted residual risk remains.
7. Re-check CI and bot reviews after the final push.
8. Merge only after the PR is clean and the user has approved merge or the task
   explicitly includes merge authority.
9. After merge, delete the remote feature branch unless the user explicitly asks
   to keep it.
10. Clean up local worktrees and local branches created for the task once they
    are no longer needed.

Do not report a PR as done just because code was pushed. Done means reviewed,
triaged, fixed, rechecked, and either merged/cleaned up or clearly waiting on a
specific human decision.

## Sacred Rule

No Core changes from PRO. PRO must not break Core.

- Never modify files in Core (`C:\repos\filaops`) from the ecosystem repo.
- Never add Core dependencies on any PRO or `filaops-ecosystem` package.
- Core must run identically with zero PRO code installed.
- PRO integrates via `register(app)`; keep coupling behind extension
  interfaces.

## Canonical Repos And Worktrees

`C:\repos\filaops` is the canonical local Core checkout.

Agents may create task-scoped git worktrees such as
`C:\repos\filaops-<topic>` for isolated PR work. A worktree is not a new
product repo and must not be treated as the canonical Core checkout.

Use `git worktree list` when there is any ambiguity.

## Aeonyx Session Protocol

Follow the session flow before editing:

1. Register or identify the session when the tool is available.
2. Recall relevant memory before major work.
3. Claim files before editing.
4. Work only inside claimed files.
5. Remember decisions, incidents, and reusable patterns.
6. Observe pre-existing issues instead of silently ignoring or casually fixing
   unrelated problems.
7. End or release the session when finished.

Do not store routine file edits, blame attribution, or "started working on X"
as memory.

## Mechanical Gates

Comply with hook and CI feedback instead of routing around it.

- Session registration: no edits until session requirements are met.
- Memory recall: no major work until relevant memory has been checked.
- File claim: no edits until files are claimed.
- Type/test checks: run the narrowest meaningful checks first, then broaden as
  risk requires. CI is the authority.
- Database safety: confirm `DATABASE_URL` before database work. For this repo,
  local development should target `filaops`, never `filaops_prod`.
- Lockfiles: use lockfile-respecting install commands. Do not churn lockfiles
  accidentally.
- Dependency additions: require human approval for any new manifest entry.
- Build artifact audit: do not publish `.map`, `.env`, `.key`, secrets, or
  generated local artifacts.
- Network egress: report unexpected outbound connections.

## Code Quality

- Before refactoring any file over 300 lines, remove dead code in a separate
  commit when practical.
- Keep phases small. Changes touching more than five files need a plan first.
- Ask what a strict reviewer would reject and address structural issues early.
- For broad independent work, split tasks across isolated agents/sessions when
  available.
- Re-read relevant files after long context shifts or after 8-10 messages.
- For files over 500 lines, read focused chunks instead of flooding context.
- Re-read before editing and after editing.
- When renaming or changing a contract, search direct calls, type references,
  string literals, dynamic imports, re-exports, tests, and mocks.

### File-Size Limits (DEBT-1, owner-approved 2026-06-12)

- New functionality goes in NEW modules by default — "match the surrounding
  file" governs style, not placement.
- Files over 1,200 lines (backend Python) or 800 lines (frontend
  components/pages) must NOT accept new responsibilities. Extract the area
  you are touching into a focused module first, or split as part of the
  change.
- Mechanical splits are always SEPARATE PRs from behavior changes — never
  mix moves with logic edits in one diff.
- The decomposition backlog and split conventions live in
  docs/plans/2026-06-12-god-file-decomposition.md.

## Core Vs PRO Architecture

```text
FilaOps Core                         filaops-pro package
Open-source standalone app           Private extension package
FastAPI + React + PostgreSQL   <---  register(app, license_key)
```

PRO imports from Core, never the reverse. PRO may add its own tables with
foreign keys to Core tables, but must not alter Core schema for PRO-only
features.

What belongs in Core:
Inventory, MRP, production, sales, purchase orders, BOM, traceability, UOM,
basic GL, i18n, dashboards, auth/RBAC, and base printer integration.

What belongs in PRO:
B2B Portal, quote engine, QuickBooks/Shopify integrations, advanced accounting,
catalog access control, AI agents, FilaFarm automation, license management, and
subscription-gated capabilities.

## Repo Map

| Repo | Purpose |
| --- | --- |
| `C:\repos\filaops` | Core, open source, public |
| `C:\repos\filaops-ecosystem` | PRO monorepo, private |
| `C:\repos\filaops-relay` | Desktop relay/installer/runtime shell |

## Tech Stack

- Backend: FastAPI, SQLAlchemy, PostgreSQL, Alembic
- Frontend: React, Vite, Tailwind
- Testing: pytest for backend, Vitest for frontend, Playwright for E2E

UOM safety: costs are stored as dollars per kilogram and inventory is stored in
grams. The single source is `backend/app/core/uom_config.py`. Do not hardcode
conversions elsewhere.

## Git Workflow

- Use feature branches off `main`.
- Preferred branch prefixes: `codex/`, `claude/`, `feature/`, `feat/`,
  `fix/`, `docs/`.
- Commit prefixes: `feat:`, `fix:`, `refactor:`, `test:`, `docs:`.
- Pull requests require passing CI and completed bot-review triage.
- Delete merged feature branches unless explicitly retained.

Commit attribution should identify the tool that made the commit. Use the
tool-specific wrapper file for the correct attribution line.
