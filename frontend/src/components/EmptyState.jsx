/**
 * EmptyState - Reusable component for displaying empty list states
 *
 * Provides a consistent, branded empty state across the application
 * with optional action button for creating new items.
 */

import { Link } from "react-router-dom";

// Pre-defined icons for common empty states
const icons = {
  orders: (
    <svg
      className="w-16 h-16"
      fill="none"
      stroke="currentColor"
      viewBox="0 0 24 24"
    >
      <path
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeWidth={1.5}
        d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"
      />
    </svg>
  ),
  production: (
    <svg
      className="w-16 h-16"
      fill="none"
      stroke="currentColor"
      viewBox="0 0 24 24"
    >
      <path
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeWidth={1.5}
        d="M19.428 15.428a2 2 0 00-1.022-.547l-2.387-.477a6 6 0 00-3.86.517l-.318.158a6 6 0 01-3.86.517L6.05 15.21a2 2 0 00-1.806.547M8 4h8l-1 1v5.172a2 2 0 00.586 1.414l5 5c1.26 1.26.367 3.414-1.415 3.414H4.828c-1.782 0-2.674-2.154-1.414-3.414l5-5A2 2 0 009 10.172V5L8 4z"
      />
    </svg>
  ),
  inventory: (
    <svg
      className="w-16 h-16"
      fill="none"
      stroke="currentColor"
      viewBox="0 0 24 24"
    >
      <path
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeWidth={1.5}
        d="M20 7l-8-4-8 4m16 0l-8 4m8-4v10l-8 4m0-10L4 7m8 4v10M4 7v10l8 4"
      />
    </svg>
  ),
  items: (
    <svg
      className="w-16 h-16"
      fill="none"
      stroke="currentColor"
      viewBox="0 0 24 24"
    >
      <path
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeWidth={1.5}
        d="M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 012-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10"
      />
    </svg>
  ),
  customers: (
    <svg
      className="w-16 h-16"
      fill="none"
      stroke="currentColor"
      viewBox="0 0 24 24"
    >
      <path
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeWidth={1.5}
        d="M17 20h5v-2a3 3 0 00-5.356-1.857M17 20H7m10 0v-2c0-.656-.126-1.283-.356-1.857M7 20H2v-2a3 3 0 015.356-1.857M7 20v-2c0-.656.126-1.283.356-1.857m0 0a5.002 5.002 0 019.288 0M15 7a3 3 0 11-6 0 3 3 0 016 0zm6 3a2 2 0 11-4 0 2 2 0 014 0zM7 10a2 2 0 11-4 0 2 2 0 014 0z"
      />
    </svg>
  ),
  search: (
    <svg
      className="w-16 h-16"
      fill="none"
      stroke="currentColor"
      viewBox="0 0 24 24"
    >
      <path
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeWidth={1.5}
        d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z"
      />
    </svg>
  ),
  filter: (
    <svg
      className="w-16 h-16"
      fill="none"
      stroke="currentColor"
      viewBox="0 0 24 24"
    >
      <path
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeWidth={1.5}
        d="M3 4a1 1 0 011-1h16a1 1 0 011 1v2.586a1 1 0 01-.293.707l-6.414 6.414a1 1 0 00-.293.707V17l-4 4v-6.586a1 1 0 00-.293-.707L3.293 7.293A1 1 0 013 6.586V4z"
      />
    </svg>
  ),
  error: (
    <svg
      className="w-16 h-16"
      fill="none"
      stroke="currentColor"
      viewBox="0 0 24 24"
    >
      <path
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeWidth={1.5}
        d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"
      />
    </svg>
  ),
  default: (
    <svg
      className="w-16 h-16"
      fill="none"
      stroke="currentColor"
      viewBox="0 0 24 24"
    >
      <path
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeWidth={1.5}
        d="M20 13V6a2 2 0 00-2-2H6a2 2 0 00-2 2v7m16 0v5a2 2 0 01-2 2H6a2 2 0 01-2-2v-5m16 0h-2.586a1 1 0 00-.707.293l-2.414 2.414a1 1 0 01-.707.293h-3.172a1 1 0 01-.707-.293l-2.414-2.414A1 1 0 006.586 13H4"
      />
    </svg>
  ),
};

// Color treatment per design system. "dark" is the legacy default; "workbench"
// is the Industrial Workbench paper treatment (#846) — opt-in per consumer so
// un-migrated dark pages keep their current look (same pattern as Modal's
// variant prop).
const TONES = {
  dark: {
    surface: "bg-gray-900 border border-gray-700",
    surfaceCompact: "bg-gray-900",
    icon: "text-white",
    title: "text-white",
    text: "text-white",
    cta: "bg-emerald-600 hover:bg-emerald-500 text-white",
    clear: "bg-gray-700 hover:bg-gray-600 text-white",
  },
  workbench: {
    surface: "bg-[var(--paper-sunk)] border border-[var(--rule-hair)]",
    surfaceCompact: "bg-[var(--paper-sunk)]",
    icon: "text-[var(--ink-4)]",
    title: "text-[var(--ink)]",
    text: "text-[var(--ink-3)]",
    cta: "bg-[var(--orange)] hover:bg-[var(--orange-press)] text-white",
    clear:
      "bg-[var(--paper)] border border-[var(--rule-hair)] text-[var(--ink-2)] hover:text-[var(--ink)]",
  },
};

export default function EmptyState({
  icon = "default",
  title = "No items found",
  description,
  actionLabel,
  actionTo,
  onAction,
  customIcon,
  variant = "default", // default, compact, inline
  tone = "dark", // dark (legacy), workbench (#846)
  // "No matches" / filter-clear variant — when provided, replaces the action button
  onClearFilters,
}) {
  // Use custom icon if provided, otherwise use predefined
  const iconElement = customIcon || icons[icon] || icons.default;

  const T = TONES[tone] ?? TONES.dark;

  // Render action button inline (not as component to avoid React fast refresh issues)
  const buttonClasses = `inline-flex items-center gap-2 px-4 py-2 ${T.cta} rounded-lg transition-colors text-sm font-medium`;

  const clearFiltersClasses = `inline-flex items-center gap-2 px-4 py-2 ${T.clear} rounded-lg transition-colors text-sm font-medium`;

  const renderActionButton = () => {
    // "Clear filters" variant takes precedence over create CTA
    if (onClearFilters) {
      return (
        <button onClick={onClearFilters} className={clearFiltersClasses}>
          <svg
            className="w-4 h-4"
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={2}
              d="M6 18L18 6M6 6l12 12"
            />
          </svg>
          Clear filters
        </button>
      );
    }

    if (!actionLabel) return null;

    const plusIcon = (
      <svg
        className="w-4 h-4"
        fill="none"
        stroke="currentColor"
        viewBox="0 0 24 24"
      >
        <path
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeWidth={2}
          d="M12 4v16m8-8H4"
        />
      </svg>
    );

    if (actionTo) {
      return (
        <Link to={actionTo} className={buttonClasses}>
          {plusIcon}
          {actionLabel}
        </Link>
      );
    }

    if (onAction) {
      return (
        <button onClick={onAction} className={buttonClasses}>
          {plusIcon}
          {actionLabel}
        </button>
      );
    }

    return null;
  };

  // Compact variant for smaller spaces
  if (variant === "compact") {
    return (
      <div className={`flex flex-col items-center justify-center py-8 text-center ${T.surfaceCompact}`}>
        <div className={`${T.icon} mb-3`}>{iconElement}</div>
        <h3 className={`${T.title} font-medium`}>{title}</h3>
        {description && (
          <p className={`${T.text} text-sm mt-1 max-w-xs`}>{description}</p>
        )}
        {actionLabel && <div className="mt-4">{renderActionButton()}</div>}
      </div>
    );
  }

  // Inline variant for table rows or narrow spaces
  if (variant === "inline") {
    return (
      <div className={`flex items-center justify-center gap-4 py-6 ${T.surface}`}>
        <div className={`${T.icon} w-8 h-8 [&>svg]:w-8 [&>svg]:h-8`}>
          {iconElement}
        </div>
        <div>
          <span className={T.title}>{title}</span>
          {description && (
            <span className={`${T.text} ml-2`}>{description}</span>
          )}
        </div>
        {actionLabel && renderActionButton()}
      </div>
    );
  }

  // Default variant - full empty state
  return (
    <div className={`flex flex-col items-center justify-center py-16 text-center ${T.surface}`}>
      <div className={`${T.icon} mb-4`}>{iconElement}</div>
      <h3 className={`text-lg font-medium ${T.title} mb-2`}>{title}</h3>
      {description && (
        <p className={`${T.text} text-sm max-w-md mb-6`}>{description}</p>
      )}
      {renderActionButton()}
    </div>
  );
}
