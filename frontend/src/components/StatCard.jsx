import { Link } from "react-router-dom";

// Shared chevron icon for clickable cards
const ChevronIcon = () => (
  <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
  </svg>
);

// Skeleton pulse component for loading state
const SkeletonPulse = ({ className = "" }) => (
  <div className={`animate-pulse bg-paper-sunk rounded ${className}`} />
);

/**
 * Reusable StatCard component for displaying metrics across admin pages.
 *
 * Industrial Workbench (#846, design-system PR-5): a KPI tile is a flat paper
 * card with a caption label and one number. A tile that counts a status
 * colours its value with that status and its border with the status tint;
 * a plain count stays ink. The accent never appears on a tile — selecting
 * a tile as a filter (`active`) is the one exception, because that is an
 * action.
 *
 * `color` takes a tone: "working" | "cleared" | "blocked" | "neutral".
 * The legacy names consumers still pass map onto those tones (emerald/cyan/
 * blue/purple were the old brand accent and become neutral ink).
 *
 * `variant`:
 * - "gradient" (default, kept for compatibility): the dashboard size — p-6,
 *   30px value. The gradient wash itself is retired.
 * - "simple": the dense tile — p-3, 20px value — used in KPI rows.
 *
 * Optional `to` prop makes the card a link; `onClick` makes it a button.
 */

const TONES = {
  working: { value: "text-status-amber", border: "border-status-amber-tint" },
  cleared: { value: "text-status-green", border: "border-status-green-tint" },
  blocked: { value: "text-status-red", border: "border-status-red-tint" },
  neutral: { value: "text-ink", border: "border-hair" },
};

const LEGACY_TONES = {
  warning: "working", amber: "working", orange: "working", yellow: "working",
  success: "cleared", green: "cleared",
  danger: "blocked", red: "blocked",
  primary: "neutral", secondary: "neutral", emerald: "neutral", cyan: "neutral",
  blue: "neutral", purple: "neutral", white: "neutral",
};

export default function StatCard({
  title,
  value,
  subtitle,
  color = "neutral",
  icon,
  variant = "gradient",
  to,
  onClick,
  active = false,
  loading = false,
}) {
  const tone = TONES[color] || TONES[LEGACY_TONES[color]] || TONES.neutral;
  const large = variant !== "simple";

  // Wrapper component - Link if `to` prop provided, div otherwise
  const Wrapper = to ? Link : "div";
  const wrapperProps = to ? { to, className: "block" } : {};
  const isClickable = to || onClick;

  const baseClasses = `bg-paper border rounded-lg shadow-[var(--shadow-pop)] ${large ? "p-6" : "p-3"}`;
  const borderClasses = active ? "border-accent bg-accent-tint" : tone.border;
  const hoverClasses =
    isClickable && !loading ? "hover:bg-paper-sunk transition-colors cursor-pointer" : "";

  return (
    <Wrapper {...wrapperProps}>
      <div
        className={`${baseClasses} ${borderClasses} ${hoverClasses}`}
        onClick={loading ? undefined : onClick}
        role={onClick && !loading ? "button" : undefined}
        tabIndex={onClick && !loading ? 0 : undefined}
        onKeyDown={onClick && !loading ? (e) => e.key === "Enter" && onClick() : undefined}
      >
        <div className="flex items-start justify-between gap-2">
          <div className="flex-1 min-w-0">
            {loading ? (
              <>
                <SkeletonPulse className="h-4 w-20 mb-2" />
                <SkeletonPulse className={large ? "h-9 w-20" : "h-7 w-16"} />
                {subtitle && <SkeletonPulse className="h-3 w-24 mt-2" />}
              </>
            ) : (
              <>
                <p className="text-ink-3 text-xs">{title}</p>
                <p
                  className={`${large ? "text-3xl leading-9" : "text-xl leading-7"} font-bold font-mono-data ${tone.value}`}
                >
                  {value}
                </p>
                {subtitle && <p className="text-ink-3 text-xs mt-0.5">{subtitle}</p>}
              </>
            )}
          </div>
          <div className="flex items-center gap-2 text-ink-4">
            {icon && !loading && <div>{icon}</div>}
            {isClickable && !loading && <ChevronIcon />}
          </div>
        </div>
      </div>
    </Wrapper>
  );
}
