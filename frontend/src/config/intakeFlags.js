/**
 * Intake Studio feature gates.
 *
 * OFF-by-default. The unified flow is gated at RUNTIME, never by a compile-time
 * constant, so the OFF path is byte-identical to today AND the gate is not
 * statically provably-false (which previously tripped the "useless conditional"
 * analyzer).
 *
 * Two independent flip mechanisms, OR'd together by the component
 * (see the `unifiedFlow` derivation in AdminIntakeStudio.jsx):
 *
 *   1. Backend feature flag (preferred, per-tenant, no rebuild) — the backend
 *      adds "intake_unified_flow" to /api/v1/system/info `features_enabled`,
 *      surfaced via `useFeatureFlags().hasFeature("intake_unified_flow")`.
 *      Core returns an empty feature list, so this defaults OFF with no backend
 *      change required.
 *
 *   2. Build-time env override (for a specific frontend build, e.g. the 129
 *      brownfield) — set `VITE_INTAKE_UNIFIED_FLOW=true` in the build env.
 *      `INTAKE_UNIFIED_FLOW` below reads `import.meta.env` at build time;
 *      unset → "" !== "true" → false → OFF.
 *
 * When neither is enabled, Intake Studio behaves exactly as before:
 *   - no pre-parse panel on file drop
 *   - the legacy "Match spools" step (not the catalog "Select material" step)
 *   - no deferred-slice material messaging
 */

/**
 * Build-time default for the unified flow. Evaluated from the Vite env at build
 * time (runtime value, not a literal constant), defaulting to false (OFF) when
 * `VITE_INTAKE_UNIFIED_FLOW` is unset. Flip by setting that env in the build.
 * @type {boolean}
 */
export const INTAKE_UNIFIED_FLOW =
  import.meta.env.VITE_INTAKE_UNIFIED_FLOW === "true";

/**
 * The feature key the backend can add to /api/v1/system/info `features_enabled`
 * to enable the unified flow for a tenant without a frontend rebuild.
 * @type {string}
 */
export const INTAKE_UNIFIED_FLOW_FEATURE = "intake_unified_flow";
