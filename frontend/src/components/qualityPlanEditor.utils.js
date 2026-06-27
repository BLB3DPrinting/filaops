/**
 * Helpers for QualityPlanEditor, kept in a separate module so the component
 * file only exports components (keeps Fast Refresh working).
 */

/**
 * Derive a stable, rename-proof characteristic code from its display name.
 *   "Bore diameter (mm)" -> "BORE_DIAMETER_MM"
 * Capped at 50 to match the DB column. The display text can be edited freely;
 * the code is what SPC series key on (see backend #828).
 *
 * @param {string} name
 * @returns {string}
 */
export function slugifyCode(name) {
  return (name || "")
    .toUpperCase()
    .replace(/[^A-Z0-9]+/g, "_")
    .replace(/^_+|_+$/g, "")
    .slice(0, 50);
}
