import { useFeatureFlags } from "../hooks/useFeatureFlags";

/**
 * ProBadge — small inline badge for nav items that are PRO-only.
 *
 * Usage in navGroups:
 *   { path: "/admin/catalogs", label: "Catalogs", icon: CatalogIcon, proOnly: true }
 *
 * Then in the NavLink render:
 *   {sidebarOpen && <span>{item.label}</span>}
 *   {sidebarOpen && item.proOnly && !isPro && <ProBadge />}
 */
export function ProBadge() {
  return (
    <span className="ml-auto text-xs font-semibold px-1.5 py-0.5 rounded bg-blue-900/60 text-blue-300 border border-blue-700/50">
      PRO
    </span>
  );
}

// Lock icon rendered at the top of the upgrade card
const LockIcon = () => (
  <svg
    className="w-12 h-12"
    fill="none"
    stroke="currentColor"
    viewBox="0 0 24 24"
    aria-hidden="true"
  >
    <path
      strokeLinecap="round"
      strokeLinejoin="round"
      strokeWidth={1.5}
      d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z"
    />
  </svg>
);

// Checkmark icon for the benefits list
const CheckIcon = () => (
  <svg
    className="w-4 h-4 text-emerald-400 flex-shrink-0 mt-0.5"
    fill="none"
    stroke="currentColor"
    viewBox="0 0 24 24"
    aria-hidden="true"
  >
    <path
      strokeLinecap="round"
      strokeLinejoin="round"
      strokeWidth={2.5}
      d="M5 13l4 4L19 7"
    />
  </svg>
);

const PRO_URL = "https://filaops.blb3dprinting.com";

/**
 * ProGate — wraps PRO-gated page content with an upgrade prompt for community users.
 *
 * When the active license tier is "professional" or "enterprise" (isPro === true)
 * this component is completely invisible — it renders children with zero overhead.
 *
 * When tier is "community" (isPro === false) the children are NOT rendered at all.
 * Instead, a centered upgrade card is shown inline in the page area where the content
 * would have appeared. This is NOT a modal; it slots naturally into the page layout.
 *
 * Props:
 *   feature     — short feature name shown as the card heading, e.g. "Catalogs"
 *   description — one-sentence description of what the feature does
 *   benefits    — array of 3-4 short strings listing what the user unlocks
 *   children    — the actual page content rendered when isPro is true
 *
 * Usage:
 *   <ProGate
 *     feature="Catalogs"
 *     description="Create and manage customer-specific product catalogs with custom pricing."
 *     benefits={[
 *       "Customer-specific price lists",
 *       "Tiered pricing by account level",
 *       "Hidden items per catalog",
 *       "API access for B2B portals",
 *     ]}
 *   >
 *     <CatalogsPage />
 *   </ProGate>
 */
export default function ProGate({ feature, description, benefits = [], children }) {
  const { isPro, loading } = useFeatureFlags();

  // While the tier is still loading from AppContext, render nothing to avoid
  // a flash of the upgrade card on PRO installs.
  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-[60vh]">
        <div className="animate-pulse flex flex-col items-center gap-3">
          <div className="w-12 h-12 rounded-full bg-gray-700/50" />
          <div className="h-4 w-32 rounded bg-gray-700/50" />
        </div>
      </div>
    );
  }

  // PRO or Enterprise tier — transparent passthrough, zero visual overhead
  if (isPro) {
    return children;
  }

  // Community tier — render the upgrade card in place of the locked content
  return (
    <div className="flex items-start justify-center min-h-[60vh] py-16 px-4">
      <div
        className="w-full max-w-lg rounded-2xl border p-8 flex flex-col items-center text-center shadow-2xl"
        style={{
          backgroundColor: "var(--bg-card, #111827)",
          borderColor: "var(--border-subtle, rgba(55,65,81,0.6))",
        }}
      >
        {/* Lock icon badge */}
        <div className="flex items-center justify-center w-20 h-20 rounded-full bg-blue-900/30 border border-blue-700/40 text-blue-400 mb-6">
          <LockIcon />
        </div>

        {/* PRO label */}
        <span className="inline-flex items-center gap-1.5 text-xs font-semibold tracking-widest uppercase text-blue-300 bg-blue-900/40 border border-blue-700/50 px-3 py-1 rounded-full mb-4">
          FilaOps PRO
        </span>

        {/* Feature heading */}
        <h2 className="text-2xl font-bold text-white mb-3">
          {feature}
        </h2>

        {/* Description */}
        {description && (
          <p className="text-gray-400 text-sm leading-relaxed mb-6 max-w-sm">
            {description}
          </p>
        )}

        {/* Benefits list */}
        {benefits.length > 0 && (
          <ul className="w-full text-left space-y-2.5 mb-8">
            {benefits.map((benefit, i) => (
              <li key={i} className="flex items-start gap-2.5 text-sm text-gray-300">
                <CheckIcon />
                <span>{benefit}</span>
              </li>
            ))}
          </ul>
        )}

        {/* Divider */}
        <div className="w-full border-t mb-6" style={{ borderColor: "var(--border-subtle, rgba(55,65,81,0.5))" }} />

        {/* Primary CTA */}
        <a
          href={PRO_URL}
          target="_blank"
          rel="noopener noreferrer"
          className="w-full flex items-center justify-center gap-2 px-6 py-3 rounded-xl bg-gradient-to-r from-emerald-600 to-cyan-600 hover:from-emerald-500 hover:to-cyan-500 text-white font-semibold text-sm transition-all shadow-lg hover:shadow-emerald-500/20 hover:scale-[1.02] active:scale-[0.98]"
        >
          Get PRO &mdash; $49/mo
        </a>

        {/* Secondary link */}
        <a
          href={PRO_URL}
          target="_blank"
          rel="noopener noreferrer"
          className="mt-4 text-sm text-gray-500 hover:text-gray-300 transition-colors underline underline-offset-2"
        >
          Learn More
        </a>
      </div>
    </div>
  );
}
