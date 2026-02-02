/**
 * Shared UI components used across accounting tabs.
 * ErrorAlert, Skeleton, TableSkeleton, CardSkeleton, HelpIcon.
 */
import { useState } from "react";

// Reusable error alert with retry button
export function ErrorAlert({ message, onRetry }) {
  return (
    <div className="bg-red-900/30 border border-red-700 rounded-xl p-4 flex items-center gap-3">
      <svg className="w-5 h-5 text-red-400 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
      </svg>
      <div className="flex-1">
        <p className="text-red-400 font-medium text-sm">{message}</p>
        <p className="text-gray-500 text-xs mt-1">Check that the backend server is running.</p>
      </div>
      {onRetry && (
        <button
          onClick={onRetry}
          className="px-3 py-1.5 bg-red-600/20 text-red-400 rounded-lg hover:bg-red-600/30 text-sm flex items-center gap-1.5"
        >
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
          </svg>
          Retry
        </button>
      )}
    </div>
  );
}

// Skeleton loading placeholder
export function Skeleton({ className = "", variant = "rect" }) {
  const baseClass = "animate-pulse bg-gray-700/50 rounded";
  if (variant === "text") {
    return <div className={`${baseClass} h-4 ${className}`} />;
  }
  if (variant === "circle") {
    return <div className={`${baseClass} rounded-full ${className}`} />;
  }
  return <div className={`${baseClass} ${className}`} />;
}

// Table skeleton for loading states
export function TableSkeleton({ rows = 5, cols = 3 }) {
  return (
    <div className="bg-gray-900 border border-gray-800 rounded-xl overflow-hidden">
      <div className="p-4 border-b border-gray-800">
        <Skeleton className="h-6 w-48" />
      </div>
      <div className="divide-y divide-gray-800">
        {[...Array(rows)].map((_, i) => (
          <div key={i} className="flex items-center gap-4 p-4">
            {[...Array(cols)].map((_, j) => (
              <Skeleton key={j} className={`h-4 ${j === 0 ? 'w-32' : 'w-20'}`} />
            ))}
          </div>
        ))}
      </div>
    </div>
  );
}

// Card skeleton for summary cards
export function CardSkeleton() {
  return (
    <div className="bg-gray-900 border border-gray-800 rounded-xl p-5">
      <Skeleton className="h-4 w-24 mb-2" />
      <Skeleton className="h-8 w-32" />
    </div>
  );
}

// Help icon with tooltip for contextual help
export function HelpIcon({ label }) {
  const [showTooltip, setShowTooltip] = useState(false);
  return (
    <div className="relative inline-block">
      <svg
        className="w-4 h-4 text-gray-500 hover:text-gray-400 cursor-help"
        fill="none"
        stroke="currentColor"
        viewBox="0 0 24 24"
        role="img"
        aria-label={label}
        tabIndex={0}
        onMouseEnter={() => setShowTooltip(true)}
        onMouseLeave={() => setShowTooltip(false)}
        onFocus={() => setShowTooltip(true)}
        onBlur={() => setShowTooltip(false)}
      >
        <path
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeWidth={2}
          d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"
        />
      </svg>
      {showTooltip && (
        <div className="absolute z-50 bottom-full left-1/2 -translate-x-1/2 mb-2 w-64 p-2 bg-gray-800 border border-gray-700 rounded-lg shadow-lg text-xs text-gray-300 leading-relaxed">
          {label}
          <div className="absolute top-full left-1/2 -translate-x-1/2 -mt-1">
            <div className="border-4 border-transparent border-t-gray-800" />
          </div>
        </div>
      )}
    </div>
  );
}
