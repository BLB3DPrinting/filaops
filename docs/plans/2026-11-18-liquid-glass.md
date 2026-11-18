# Liquid Glass — finishing the Workbench design system

Status: proposed
Date: 2026-11-18
Tracking issue: #846
Supersedes: [`2026-09-19-workbench-foundation.md`](2026-09-19-workbench-foundation.md)
(kept as the decision record; all remaining work now lives here)

Design reference: "FilaOps Liquid Glass" handoff
(https://claude.ai/artifact/CmADvXvtJSsqv2mtZzXzjD — `design_handoff_liquid_glass/`:
README, `reference/glass.css`, `reference/CommandPalette.jsx`,
`reference/useCommandPalette.js`, screenshots).

## Why this document exists

The 2026-09-19 foundation plan had seven PRs. Some landed, some stalled on
branches, and the Liquid Glass handoff adds scope (glass top bar, ⌘K palette,
flat opt-out). Two plans with open items is how work gets done twice or not at
all, so this document is now the **only** plan with open items for #846
Phase 1. The foundation plan is frozen as history.

## Decisions carried forward (locked 2026-09-19, unchanged)

- **Two themes**: Day (default) and Dim, one set of markup, `data-theme` on
  `<html>`. First visit forces Day (`INITIAL_THEME_STRATEGY = "light"` on
  `claude/workbench-shell`) so the shop floor is predictable.
- **Accent is petrol, not orange.** One accent, primary actions only, never a
  status. `--accent` `#0F5F66` / `#5EB3B8`, `--accent-ink` `#FFFFFF` /
  `#211E18`, `--accent-press`, `--accent-tint`.
- **Type**: IBM Plex Sans for UI; JetBrains Mono via `.font-mono-data` for data
  that is compared or copied. Rajdhani stays scoped to the printers HUD.
- **Glass is a material for floating chrome only** (top bar, palette). The
  data plane — tables, KPI cards, charts — stays opaque and flat.

## Deviations from the Liquid Glass handoff

The handoff was written against the pre-decision palette. Where it conflicts
with the decisions above, the decisions win:

| Handoff says | We do | Why |
| --- | --- | --- |
| `--orange`, `--orange-tint`, `--orange-press` for the primary palette row and badges | `--accent`, `--accent-tint`, `--accent-press` | Petrol accent (above). The `--orange` aliases are retired by PR-3a. |
| Inter | IBM Plex Sans | Type decision (above). |
| Wrap the palette in Radix `Dialog` | Hand-rolled focus trap | New manifest entries need owner approval (AGENT_POLICY, dependency additions); a trap over one dialog does not justify a dependency. |
| Six hardcoded demo commands | Commands built from `nav/navConfig.js` plus a short action list | The palette must reach every destination, not a demo set. |
| Panel fades in from `opacity: 0` | Resting state visible; entrance driven by a `mounted` flag inside `prefers-reduced-motion: no-preference` | Handoff's own warning: background-tab throttling left the panel stuck invisible. |

## State on `main` (ce860059, 2026-11-18)

| Foundation PR | State |
| --- | --- |
| PR-0 split `AdminLayout.jsx` | **Landed** (#991). `AdminLayout.jsx` is 620 lines. |
| PR-1 token bridge, Plex, delete `tailwind.config.js` | **Landed** (#992). Includes all `--glass-*` tokens (light, dim, `data-glass="off"`) and the token-level `prefers-reduced-transparency` fallback. |
| PR-1b raw-palette lint guard on changed lines | **Unmerged** — `claude/palette-guard` (`91968cde`, 2 commits). |
| PR-2 dead-utility sweep | **Mostly done.** `overflow-ellipsis` gone; one `bg-opacity-*` left (`AdminLayout.jsx`, the mobile scrim); 81 `flex-shrink-0` remain (still valid in v4 — cosmetic, not a bug). |
| PR-3a retire `--orange` aliases | **Unmerged** — `claude/workbench-orange-codemod` (`22983277`), also the base of the shell branch. |
| PR-3 shell (theme store, ThemeContext, toggle, route titles) | **Unmerged** — `claude/workbench-shell` (`e8a8d807`). Deletes the old `.glass` rule but adds no replacement. |
| PR-4 lucide nav icons | **Not started.** `nav/navIcons.jsx` still hand-rolled. |
| PR-5 primitives onto tokens | **Landed** (#1007). |
| PR-6 command palette | **Not started.** |

Glass component classes (`.glass-panel`, `.glass-scrim`, `.glass-sel`,
`.glass-topbar`) do not exist anywhere yet.

## PR sequence

Every PR starts with `npm ci` in its worktree (fresh worktrees have no
`node_modules`). Mechanical changes stay separate from behaviour changes.

### LG-0 — land the stalled branches

In order, each rebased onto current `main`, each its own PR:

1. `claude/palette-guard` (PR-1b). Lands first so every later PR is linted.
2. `claude/workbench-orange-codemod` (PR-3a).
3. `claude/workbench-shell` (PR-3), plus its remaining items: real `<h1>` per
   route, the `var(--accent-primary)` repair, the last `bg-opacity-50` scrim,
   Playwright axe pass in both themes.

The shell PR removes `.glass` from the top bar. To avoid a release where the
bar silently loses its material, **LG-1 merges before or with LG-0.3**, and
the shell PR switches the header to `.glass-topbar` in the same commit that
deletes `.glass`.

Verify: both themes at 1440 / 768 / 390; axe clean in both; theme persists
across reload.

### LG-1 — glass component classes (CSS only, `index.css`)

Add `.glass-scrim`, `.glass-panel`, `.glass-sel`, `.glass-topbar` from the
handoff's `reference/glass.css`, unchanged except as noted above. Tokens are
already on `main`; do not re-add them.

Verify: `npm run build`; built CSS contains all four classes **and an
`-webkit-backdrop-filter` declaration for each `backdrop-filter`** (Safari < 18
needs the prefix; confirm autoprefixer actually emits it through
`@tailwindcss/postcss` rather than assuming).

### LG-2 — glass top bar (`AdminLayout.jsx`)

- Header becomes `.glass-topbar`, 61px tall, `gap: 18px`, `padding: 0 24px`.
- Scroll container below gets `padding-top: 83px` so content starts clear and
  slides under the bar.
- Header search field becomes the palette trigger (inert until LG-3 lands, or
  LG-2 and LG-3 ship together).

**Gate — must pass before merge:** scroll a long table (Items, ~500 rows)
under the bar on the actual shop-floor PC and on the slowest Linux box in use.
Chrome DevTools performance trace; no sustained frame drops. If it fails, the
bar ships solid via `data-glass="off"` scoping on the bar only and the palette
keeps glass. Record the measurement in the PR.

### LG-3 — ⌘K command palette (feature PR)

- `src/hooks/useCommandPalette.js` — open state + global ⌘K / Ctrl-K.
- `src/components/CommandPalette.jsx` — portal-mounted, `role="dialog"`,
  `aria-modal`, labelled input, `listbox` / `option` rows with
  `aria-selected`, Tab focus trap, focus returned on close.
- Commands: every `navConfig.js` destination (wired to `react-router`) plus a
  short action list. Filtering is case-insensitive substring over label + code;
  empty state when nothing matches; active index clamps when the list shrinks.
- Primary row uses `--accent-tint` / `--accent`; all other icon chips use
  `--glass-fill` / `--ink-2`. Identifiers in `.font-mono-data`.
- Mounted once in `App.jsx`.

Tests:
- `CommandPalette.stories.jsx`: Day, Dim, `data-glass="off"`.
- Playwright smoke: ⌘K opens; typing filters; ↓↓ + Enter navigates; Esc closes
  and focus returns to the trigger; Tab cannot leave the dialog.
- Unit: filtering, index clamping, wrap-around.

### LG-4 — glass opt-out preference

Settings → Appearance: a "Translucent surfaces" switch that writes
`data-glass` through the shell's theme store (`GLASS_KEY` already defined
there). Default on; the OS `prefers-reduced-transparency` fallback still
applies on top where the browser supports it.

### LG-5 — nav icons (old PR-4, unchanged)

Replace hand-rolled icons with `lucide-react`, one distinct glyph per
destination. Independent of glass; can run in parallel with LG-2/LG-3.

## Platform support

Glass is a browser feature (`backdrop-filter`), not an OS feature. FilaOps is a
web app, so support follows the browser, on Windows, macOS and Linux alike:

| Browser | `backdrop-filter` | `prefers-reduced-transparency` |
| --- | --- | --- |
| Chrome / Edge (all OSes) | yes (76+) | yes (118+) |
| Firefox (all OSes) | yes (103+) | no — falls back to the LG-4 switch |
| Safari (macOS, iOS) | yes; unprefixed only from 18, `-webkit-` before | no — falls back to the LG-4 switch |

Where it degrades:

- **Performance, not appearance.** Blur is GPU-composited. Machines where the
  browser falls back to software rendering — old or blocklisted GPU drivers
  (most common on Linux), VMs, remote-desktop sessions — pay for it on every
  scroll frame. That is what the LG-2 gate measures and why the bar has a
  solid fallback.
- **Reduced-transparency detection is Chromium-only.** Firefox and Safari users
  who want it off use the LG-4 switch.
- Blur and saturation render slightly differently between engines; this is
  cosmetic and accepted.

Verification matrix for LG-2 and LG-3: Chrome on Windows (shop floor),
Firefox on Linux, Safari on macOS — screenshot both themes and the flat
fallback in each.

## Out of scope

- Phase 2 codemod of the remaining raw-Tailwind files (palette guard keeps it
  from growing).
- Deleting the deprecated Neo tokens and legacy `.glow` / `.shimmer` /
  `.noise-overlay` CSS — end of #846, after Phase 2.
- Any backend change.

## Open questions for the owner

1. **Amber contrast** (carried from the foundation plan, still unresolved):
   `#B45309` on `#FEF3C7` is 4.48:1. Nudge amber to ≈`#9A4A08` or record the
   acceptance.
2. **Command palette scope beyond navigation** — which actions (release order,
   reorder SKU, add lot, …) belong in LG-3, versus a later PR once the palette
   exists?
