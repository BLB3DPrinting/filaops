/**
 * Presentation layer for next-action lanes (UX Foundation F4, epic #808).
 *
 * The axis taxonomy itself lives in `lib/nextActions.js` (the pure data layer).
 * This module holds only display concerns — lane labels, Badge tones, and the
 * canonical lane order — so the adapters stay free of UI vocabulary.
 *
 * Tones are the 6 Badge variants from F2 (success/warning/danger/info/neutral/
 * purple), so lanes and status badges share one visual language.
 */

export const AXIS_META = {
  production: { label: "Production", tone: "purple" },
  fulfillment: { label: "Fulfillment", tone: "info" },
  payment: { label: "Payment", tone: "warning" },
  supply: { label: "Supply", tone: "warning" },
  qc: { label: "Quality", tone: "info" },
  maintenance: { label: "Maintenance", tone: "warning" },
  other: { label: "Other", tone: "neutral" },
};

// Canonical lane order so the cockpit layout is stable across refreshes.
// Floor-work axes first, commercial axes after, catch-all last.
export const AXIS_ORDER = [
  "production",
  "qc",
  "fulfillment",
  "supply",
  "payment",
  "maintenance",
  "other",
];

// severity → Badge tone (the F2 6-tone vocabulary).
const SEVERITY_TONE = {
  critical: "danger",
  high: "warning",
  medium: "info",
  low: "neutral",
};

const titleCase = (s) =>
  String(s || "")
    .split(/[_\s-]+/)
    .filter(Boolean)
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
    .join(" ") || "Other";

/** Lane display label for an axis; unknown axes are title-cased. */
export function axisLabel(axis) {
  return AXIS_META[axis]?.label || titleCase(axis);
}

/** Lane Badge tone for an axis; unknown axes are neutral. */
export function axisTone(axis) {
  return AXIS_META[axis]?.tone || "neutral";
}

/** Severity → Badge tone; unknown severity is neutral. */
export function severityTone(severity) {
  return SEVERITY_TONE[severity] || "neutral";
}

/**
 * Order an axis-keyed map (the output of mergeByAxis) into a stable
 * [axis, actions][] array by AXIS_ORDER. Axes not in AXIS_ORDER sort last,
 * alphabetically. Empty/falsy input yields [].
 */
export function orderedLanes(byAxis) {
  const rank = (a) => {
    const i = AXIS_ORDER.indexOf(a);
    return i === -1 ? AXIS_ORDER.length : i;
  };
  return Object.keys(byAxis || {})
    .sort((a, b) => rank(a) - rank(b) || a.localeCompare(b))
    .map((axis) => [axis, byAxis[axis]]);
}
