/**
 * Intake Studio feature gates.
 *
 * OFF-by-default frontend constants — flipping a value here is the single
 * one-line change that enables the new behavior. No backend change required.
 *
 * INTAKE_UNIFIED_FLOW — when true, Intake Studio runs the unified flow:
 *   - pre-parse panel on file drop (detected kind + per-slot color swatches)
 *   - a per-slot "Select material" step (sourced from the purchasable catalog)
 *     replacing the legacy "Match spools" step, eliminating the
 *     zero-suggestions dead-end
 *   - deferred slicing for bare meshes so the chosen material drives the slice
 *
 * When false, Intake Studio behaves exactly as before (byte-identical flow).
 */
export const INTAKE_UNIFIED_FLOW = false;
