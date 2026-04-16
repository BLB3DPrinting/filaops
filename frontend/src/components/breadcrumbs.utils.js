/**
 * Paths that appear in breadcrumb trails but don't map to real pages.
 * These are rendered as plain text instead of links to avoid 404s.
 */
export const NON_NAVIGABLE_PATHS = new Set([
  "/admin/inventory",
  "/admin/materials",
]);

/**
 * Route path → human-readable label map.
 * Intermediate paths (e.g. /admin/inventory) that aren't real pages
 * are included so the breadcrumb trail remains complete.
 */
export const ROUTE_LABELS = {
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

/**
 * Checks if a path segment looks like a dynamic ID (numeric or UUID-like).
 */
export function isDynamicSegment(segment) {
  return /^\d+$/.test(segment) || /^[0-9a-f-]{36}$/i.test(segment);
}

/**
 * Build breadcrumb items from the current URL pathname.
 * Returns an array of { label, path, isLast }.
 */
export function buildBreadcrumbs(pathname) {
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
