import { Link, useLocation } from "react-router-dom";

/**
 * Paths that appear in breadcrumb trails but don't map to real pages.
 * These are rendered as plain text instead of links to avoid 404s.
 */
const NON_NAVIGABLE_PATHS = new Set([
  "/admin/inventory",
  "/admin/quality",
]);

/**
 * Route path → human-readable label map.
 * Intermediate paths (e.g. /admin/inventory) that aren't real pages
 * are included so the breadcrumb trail remains complete.
 */
const ROUTE_LABELS = {
  "/admin": "Dashboard",
  // Sales
  "/admin/orders": "Orders",
  "/admin/orders/import": "Import Orders",
  "/admin/quotes": "Quotes",
  "/admin/payments": "Payments",
  "/admin/invoices": "Invoices",
  "/admin/customers": "Customers",
  "/admin/messages": "Messages",
  // Inventory
  "/admin/items": "Items",
  "/admin/bom": "Bill of Materials",
  "/admin/materials": "Materials",
  "/admin/materials/import": "Import Materials",
  "/admin/inventory": "Inventory",
  "/admin/inventory/transactions": "Transactions",
  "/admin/inventory/cycle-count": "Cycle Count",
  "/admin/locations": "Locations",
  "/admin/spools": "Material Spools",
  // Operations
  "/admin/production": "Production",
  "/admin/manufacturing": "Manufacturing",
  "/admin/printers": "Printers",
  "/admin/filafarm": "FilaFarm",
  "/admin/purchasing": "Purchasing",
  "/admin/shipping": "Shipping",
  // Quality
  "/admin/quality": "Quality",
  "/admin/quality/traceability": "Material Traceability",
  // B2B Portal
  "/admin/access-requests": "Access Requests",
  "/admin/catalogs": "Catalogs",
  "/admin/price-levels": "Price Levels",
  // Admin
  "/admin/accounting": "Accounting",
  "/admin/users": "Team Members",
  "/admin/scrap-reasons": "Scrap Reasons",
  "/admin/analytics": "Analytics",
  "/admin/settings": "Settings",
  "/admin/security": "Security Audit",
  "/admin/command-center": "Command Center",
};

const HomeIcon = () => (
  <svg
    className="w-4 h-4 shrink-0"
    fill="none"
    stroke="currentColor"
    viewBox="0 0 24 24"
    aria-hidden="true"
  >
    <path
      strokeLinecap="round"
      strokeLinejoin="round"
      strokeWidth={2}
      d="M3 12l2-2m0 0l7-7 7 7M5 10v10a1 1 0 001 1h3m10-11l2 2m-2-2v10a1 1 0 01-1 1h-3m-4 0a1 1 0 01-1-1v-4a1 1 0 011-1h2a1 1 0 011 1v4a1 1 0 01-1 1h-2z"
    />
  </svg>
);

const ChevronIcon = () => (
  <svg
    className="w-4 h-4 shrink-0"
    fill="none"
    stroke="currentColor"
    viewBox="0 0 24 24"
    style={{ color: "var(--text-muted)" }}
    aria-hidden="true"
  >
    <path
      strokeLinecap="round"
      strokeLinejoin="round"
      strokeWidth={2}
      d="M9 5l7 7-7 7"
    />
  </svg>
);

/**
 * Checks if a path segment looks like a dynamic ID (numeric or UUID-like).
 */
function isDynamicSegment(segment) {
  return /^\d+$/.test(segment) || /^[0-9a-f-]{36}$/i.test(segment);
}

/**
 * Build breadcrumb items from the current URL pathname.
 * Returns an array of { label, path, isLast }.
 */
function buildBreadcrumbs(pathname) {
  // Strip trailing slash
  const cleanPath = pathname.replace(/\/$/, "") || "/admin";

  // Don't show breadcrumbs on dashboard
  if (cleanPath === "/admin") return [];

  const segments = cleanPath.split("/").filter(Boolean); // ['admin', 'orders', '123']
  const crumbs = [];

  // Always start with Dashboard
  crumbs.push({ label: "Dashboard", path: "/admin" });

  // Build cumulative paths from segments (skip 'admin' since it's the root)
  for (let i = 1; i < segments.length; i++) {
    const cumulativePath = "/" + segments.slice(0, i + 1).join("/");
    const segment = segments[i];

    if (isDynamicSegment(segment)) {
      crumbs.push({ label: `#${segment}`, path: cumulativePath });
    } else {
      const label =
        ROUTE_LABELS[cumulativePath] ||
        segment
          .split("-")
          .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
          .join(" ");
      crumbs.push({ label, path: cumulativePath });
    }
  }

  // Mark the last item
  if (crumbs.length > 0) {
    crumbs[crumbs.length - 1].isLast = true;
  }

  return crumbs;
}

export default function Breadcrumbs() {
  const { pathname } = useLocation();
  const crumbs = buildBreadcrumbs(pathname);

  // Don't render anything on the dashboard
  if (crumbs.length === 0) return null;

  return (
    <nav aria-label="Breadcrumb" className="mb-4">
      <ol className="flex items-center gap-1.5 text-sm">
        {crumbs.map((crumb, index) => (
          <li key={crumb.path} className="flex items-center gap-1.5">
            {index > 0 && <ChevronIcon />}
            {crumb.isLast ? (
              <span
                className="font-medium"
                style={{ color: "var(--text-primary)" }}
                aria-current="page"
              >
                {crumb.label}
              </span>
            ) : NON_NAVIGABLE_PATHS.has(crumb.path) ? (
              <span
                style={{ color: "var(--text-secondary)" }}
              >
                {crumb.label}
              </span>
            ) : (
              <Link
                to={crumb.path}
                className="transition-colors hover:underline"
                style={{ color: "var(--text-secondary)" }}
                {...(index === 0 ? { "aria-label": "Dashboard" } : {})}
              >
                {index === 0 ? (
                  <HomeIcon />
                ) : (
                  crumb.label
                )}
              </Link>
            )}
          </li>
        ))}
      </ol>
    </nav>
  );
}

// Exported for testing
export { buildBreadcrumbs, ROUTE_LABELS, NON_NAVIGABLE_PATHS };
