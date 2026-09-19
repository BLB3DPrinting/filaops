# Workbench Foundation — Design System Phase 1

Status: proposed
Owner decision date: 2026-09-19
Branch: `claude/workbench-foundation`
Supersedes the stalled preview approach recorded in Aeonyx memory #111
(`workbench.css` + `WORKBENCH_PREVIEW`), which no longer exists in the tree.

## Why

`frontend/` runs four colour systems at once, and the app shell is on the dead
one. This is the measured state of `frontend/src` as of 2026-09-19:

| System | Files | Uses |
| --- | --- | --- |
| Workbench tokens (`--paper`, `--ink`, …) — the intended one | 43 | 1,443 |
| Deprecated Neo tokens (`--bg-primary`, `--primary`) | 10 | 323 |
| Raw Tailwind palette (`bg-blue-600`, `text-gray-400`) | 182 | 5,433 |
| Namespaces that resolve to nothing | — | dead |

`index.css:26` reserves the accent for primary actions only. The code votes
otherwise: **307** uses of `bg-blue-500/600` as the action colour against
**90** of `var(--orange)`.

### Root cause

The tokens live in `:root`, not in Tailwind v4's `@theme`, so the design system
generates **no utilities**. Using it costs `bg-[var(--paper)]` with no
autocomplete; bypassing it costs `bg-blue-600` with autocomplete. The system
lost on ergonomics, not on discipline. Every remedy below follows from making
the correct thing the shorter thing.

### Verified failures (each fails silently, none errors)

1. **`tailwind.config.js` is not loaded.** Tailwind v4 requires an explicit
   `@config`; there is none. Confirmed against built CSS: `bg-neo-card`,
   `shadow-glow`, `animate-pulse-glow`, `animate-logo-breathe` all generate
   **0 rules**.
2. **v3-only utilities generate nothing.** `bg-opacity-*`, `overflow-ellipsis`
   — 83 occurrences across 49 files. Visible consequence: the mobile nav scrim
   (`AdminLayout.jsx:875`, `bg-black bg-opacity-50`) renders **solid black**.
3. **Undefined tokens inherit instead of failing.** `var(--accent-primary)`
   (`AdminLayout.jsx:1109`) and `--color-surface-raised`
   (`CommandCenter.jsx:77`) are defined nowhere.
4. **The body font is never loaded.** `index.css:161` asks for Inter;
   `index.html` fetches Rajdhani + JetBrains Mono. Every screen falls back to
   `system-ui`, while a webfont used on one screen is paid for on all of them.
5. **`data-theme` is never set by any JSX.** The `dim` token set in
   `index.css:77` is unreachable, so `--paper` is always `#FAFAF7` — light
   cards inside the `#0F0F1E` shell.

## Decisions (locked by the owner, 2026-09-19)

- **Both themes.** Light default plus `dim`, with a working toggle. Both token
  sets already exist and use the same names, so screens are written once.
- **Elevation is consistent in both themes**: raised surfaces are lighter
  (`#FAFAF7` over `#F2F0E9`; `#2A2620` over `#211E18`). This is what lets one
  set of markup read correctly in either theme without branching.
- **Accent is petrol, not orange.** Orange was reviewed and rejected. The
  *rule* survives unchanged — one accent, actions only, never a status.

  | token | light | dim |
  | --- | --- | --- |
  | `--accent` | `#0F5F66` | `#5EB3B8` |
  | `--accent-ink` | `#FFFFFF` (7.37:1) | `#211E18` (6.82:1) |
  | `--accent-press` | `#0B4A50` | `#8FCACD` |

  Petrol needs a per-theme value because `#0F5F66` on `#211E18` is only
  **2.26:1** as a shape, under the 3:1 floor for UI components. Any future
  accent gets checked the same way, in both themes.
- **Type is IBM Plex Sans + IBM Plex Mono**, actually loaded. Mono is reserved
  for data that is compared or copied (quantities, durations, IDs, money) and
  never for labels.
- **Strategy**: foundation → mechanical codemod → hand-redesign the few screens
  actually lived in. This document covers the foundation only.

## Out of scope for Phase 1

- The 182 raw-Tailwind files (Phase 2 codemod).
- Redesigning individual screens (Phase 3).
- Any backend change.
- Replacing Rajdhani on the printers HUD (open question below).

## PR sequence

Policy requires a plan for anything over five files, mechanical splits as
separate PRs from behaviour changes, and no new responsibilities in a frontend
file over 800 lines. `AdminLayout.jsx` is **1,166 lines**, so it is split
before it is touched.

### PR-0 — mechanical split of `AdminLayout.jsx`

Pure move. Zero logic edits, zero visual change.

- `frontend/src/components/nav/navIcons.jsx` — the 20+ inline icon components,
  verbatim.
- `frontend/src/components/nav/navConfig.js` — the `navGroups` array, verbatim.
- `frontend/src/components/AdminLayout.jsx` — imports them; ~530 lines after.

Verify: `npm run build` succeeds; existing admin tests pass; `git diff` shows
only moves and imports.

### PR-1 — the token bridge, type, and the guard

- `frontend/src/index.css`
  - `@theme inline` mapping Workbench tokens into Tailwind's colour namespace,
    so `bg-paper`, `text-ink-3`, `bg-accent`, `border-hair` exist and stay
    theme-reactive. **`inline` is required** — plain `@theme` bakes values at
    build time and breaks runtime theming.
  - Add `--accent` / `--accent-ink` / `--accent-press` for both themes.
  - Keep `--orange: var(--accent)` as a deprecated alias so the 43 migrated
    files keep working and pick up petrol for free. The alias is removed by the
    Phase 2 codemod.
  - **Precondition**: audit all 90 `var(--orange)` uses and confirm each is an
    action, not a status or decoration, before aliasing. Any that are not get
    listed here and fixed in their own commit.
- Delete `frontend/tailwind.config.js` (verified dead). Its `xs:` breakpoint is
  confirmed unused across `frontend/src`, so nothing is lost with it.
- `frontend/index.html` — load IBM Plex Sans + IBM Plex Mono; drop Rajdhani
  unless the open question below says otherwise.
- `frontend/eslint.config.js` — reject raw palette utilities
  (`bg-blue-600`, `text-gray-400`, …) so this cannot rot back.

  The rule ships at **`error`**, with an `overrides` block switching it `off`
  for the 182 files that already violate it. New and newly-touched files are
  protected from day one; Phase 2 deletes entries from that list as it clears
  them, and the block reaching empty is the definition of Phase 2 being done.
  A `warn`-level rule is NOT viable — 5,433 violations would blow straight
  through the `--max-warnings 242` ceiling in `package.json:14` and turn CI red
  on the first commit.

Additive by construction: arbitrary `var()` values keep working, so no migrated
file breaks.

Verify: built CSS contains `.bg-paper` and `.text-ink`; `bg-neo-card` still
absent; `npm run build`; full vitest suite.

### PR-2 — dead-utility sweep

Mechanical, ~49 files. `bg-opacity-N` → `/N` opacity syntax,
`flex-shrink-0` → `shrink-0`, `overflow-ellipsis` → `text-ellipsis`. Fixes the
solid-black mobile scrim.

Verify: zero occurrences remain; build; visual check of the mobile nav.

### PR-3 — the shell

- `AdminLayout.jsx` onto tokens; the `#0F0F1E` ground and the blue
  `grid-pattern` go.
- A real `<h1>` per route, replacing the literal `"ERP"` on all 45 screens.
- `frontend/src/lib/theme.js` — reads/writes `data-theme` and `data-glass`,
  persists to `localStorage`, exposes `resolveInitialTheme()`.
- Theme toggle in the top bar, matching the existing segmented-control
  structure in `ItemsPageHeader.jsx:35`.
- Repairs: `var(--accent-primary)` (undefined), the `h-32` logo inside a 64px
  header row, `--color-surface-raised` in `CommandCenter.jsx:77`.

Verify: both themes at 1440 / 768 / 390; axe pass in both; keyboard focus
visible throughout.

### PR-4 — icons

Replace the hand-rolled Heroicons-v1 paths with `lucide-react` (already a
dependency, currently unused by the shell), **one distinct glyph per
destination**. Today `QuotesIcon` and `InvoicesIcon` are byte-identical, as are
`CommandCenterIcon` and `AnalyticsIcon`; `InventoryIcon` serves 4 destinations,
`QualityIcon` 4, `SettingsIcon` 3 — so roughly a third of the collapsed
(`w-20`, icon-only) sidebar is ambiguous.

Verify: every nav entry has a unique glyph; collapsed sidebar screenshot.

### PR-5 — primitives

`Button`, `Badge`, `Input`, `Select`, `Table`, `StatCard` onto tokens. Accent
becomes the primary action, enforcing the rule `index.css:26` already states;
amber/green/red stay locked to status. Because these are imported everywhere,
this repaints large parts of screens Phase 1 never opens.

Also: add a theme switcher to Storybook globals so **every story renders in
both themes**, and extend the Playwright axe pass to run twice.

Verify: Storybook a11y addon clean in both themes; existing component tests
pass.

### PR-6 — command palette

⌘K over all ~40 destinations, anticipated by `index.css:210`. Own PR because
it is a feature, not a re-skin.

Verify: keyboard-only operation; focus trap; Escape closes; reduced-motion
respected.

## Risks

- **Type metrics.** Changing the body face changes column widths in dense
  tables. Mitigation: PR-1 lands type before any screen work, so drift shows up
  early and once.
- **The `--orange` alias silently repaints 43 files petrol.** That is the
  intent, but it is a wide blast radius from a one-line change. Mitigation: the
  audit precondition in PR-1, plus a screenshot pass over those 43 files.
- **Contrast in dim.** The amber status pair `#B45309` on `#FEF3C7` measures
  **4.48:1**, marginally under 4.5. Either nudge amber to ≈`#9A4A08` or record
  the acceptance. Owner's call; unresolved at time of writing.
- **Worktree setup.** A fresh worktree does not check out `node_modules`;
  `npm install` is required before lint, build, or tests will run at all. This
  has bitten previous work in this repo (Aeonyx memory #430) — treat it as the
  first step of every PR below, not as a failure signal.

## Open questions for the owner

1. **Rajdhani** — retire it, or keep it scoped to the printers HUD? It is
   currently downloaded on every page load for one screen.
2. **First-visit theme** — follow the OS (`prefers-color-scheme`), or force
   light so the shop floor is predictable regardless of whose machine it is?
   This shapes `resolveInitialTheme()` in PR-3 and is the owner's to decide.

## Reference

Design mockup (light + dim, the rejected accents, and the type/control sheet):
https://claude.ai/artifact/XpMaGDLFZNLheARxf2rKeq
