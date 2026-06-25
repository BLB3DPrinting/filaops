/**
 * NextActionCard — renders a single NextAction (UX Foundation F4, epic #808).
 *
 * Consumes the unified next-action shape from `lib/nextActions.js` rather than a
 * raw ActionItem, so every surface that emits NextActions (cockpit, blocking
 * issues, order guards) renders identically. Severity drives the accent; the
 * primary deep-link is the one quick action. Disabled actions show their reason
 * instead of a dead link.
 */
import { Link } from "react-router-dom";
import { Badge } from "../ui";
import { severityTone } from "./axisMeta";

// Severity → left-accent classes (mirrors the cockpit's prior priority styling).
const SEVERITY_ACCENT = {
  critical: "border-red-500/50 bg-red-500/10",
  high: "border-orange-500/50 bg-orange-500/10",
  medium: "border-yellow-500/50 bg-yellow-500/10",
  low: "border-blue-500/40 bg-blue-500/5",
};

const SEVERITY_LABEL = {
  critical: "Critical",
  high: "High",
  medium: "Medium",
  low: "Low",
};

export default function NextActionCard({ action }) {
  if (!action || typeof action !== "object") return null;

  const accent = SEVERITY_ACCENT[action.severity] || SEVERITY_ACCENT.low;
  const code = action.target?.code;
  const canLink = action.enabled !== false && !!action.href;

  return (
    <div className={`border rounded-lg p-4 ${accent}`} data-testid="next-action-card">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <h4 className="text-white font-medium truncate">{action.label}</h4>
            {code && <span className="text-xs text-gray-400">{code}</span>}
          </div>
          {action.reason && (
            <p className="text-gray-400 text-sm mt-1">{action.reason}</p>
          )}
        </div>
        <Badge variant={severityTone(action.severity)} size="sm">
          {SEVERITY_LABEL[action.severity] || "Low"}
        </Badge>
      </div>

      {(canLink || action.disabledReason) && (
        <div className="mt-3">
          {canLink ? (
            <Link
              to={action.href}
              className="inline-block text-sm px-3 py-1 bg-gray-700 hover:bg-gray-600 text-gray-200 rounded transition-colors"
            >
              {action.verbLabel || "Open"} →
            </Link>
          ) : (
            <span
              className="text-xs text-gray-500"
              title={action.disabledReason || undefined}
            >
              {action.disabledReason}
            </span>
          )}
        </div>
      )}
    </div>
  );
}
