/**
 * routeTitles — route → human title, derived from the sidebar config.
 *
 * NAV_TITLES is a flat { path: label } map built from navGroups, so the
 * browser tab and the active nav item cannot drift. The shell renders no
 * <h1> (every routed admin page owns its own); document.title carries the
 * route title instead.
 *
 * isWorkbenchRoute() is the PR-3 migration gate: AdminLayout wraps <main> in
 * data-theme="dim" unless the route is listed in WORKBENCH_ROUTES. Each page
 * sweep removes its route from that list; when the list is empty the gate
 * goes with it.
 *
 * Usage:
 *   import { documentTitleFor, isWorkbenchRoute } from "./nav/routeTitles";
 *   document.title = documentTitleFor(pathname);   // "Orders · FilaOps"
 *   const gated = !isWorkbenchRoute(pathname);
 */
import { matchPath } from "react-router-dom";
import { navGroups } from "./navConfig";
import { isDynamicSegment } from "../breadcrumbs.utils";

/** Title restored when the shell unmounts; matches index.html <title>. */
export const DEFAULT_DOCUMENT_TITLE = "FilaOps Production Scheduling";

/** Static route path → sidebar label, for every navGroups item. */
export const NAV_TITLES = Object.freeze(
  Object.fromEntries(
    navGroups.flatMap((group) => group.items.map((item) => [item.path, item.label]))
  )
);

/**
 * Routes already repainted on Workbench tokens. Static entries are compared
 * literally; entries with a `:param` are matched with react-router's matchPath
 * and only when the last segment looks like an id, so /admin/orders/import
 * stays gated while /admin/orders/42 does not.
 */
export const WORKBENCH_ROUTES = Object.freeze([
  "/admin/shipping",
  "/admin/production",
  "/admin/production/:orderId",
  "/admin/orders/:orderId",
]);

function cleanPath(pathname) {
  return String(pathname ?? "").replace(/\/+$/, "") || "/";
}

function titleCase(segment) {
  return segment
    .split("-")
    .filter(Boolean)
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
    .join(" ");
}

function hasStaticTitle(path) {
  return Object.prototype.hasOwnProperty.call(NAV_TITLES, path);
}

/**
 * Human title for a pathname: the nav label for static routes, "<parent> #id"
 * for detail routes, title-cased last segment otherwise.
 */
export function resolveRouteTitle(pathname) {
  const path = cleanPath(pathname);
  if (hasStaticTitle(path)) return NAV_TITLES[path];

  const segments = path.split("/").filter(Boolean);
  if (segments.length === 0) return "";

  const last = segments[segments.length - 1];
  if (isDynamicSegment(last)) {
    const parentPath = "/" + segments.slice(0, -1).join("/");
    const parentSegment = segments[segments.length - 2];
    const base = hasStaticTitle(parentPath)
      ? NAV_TITLES[parentPath]
      : parentSegment
        ? titleCase(parentSegment)
        : "";
    return base ? `${base} #${last}` : `#${last}`;
  }

  return titleCase(last);
}

/** document.title for a pathname: "<title> · FilaOps". */
export function documentTitleFor(pathname) {
  const title = resolveRouteTitle(pathname);
  return title ? `${title} · FilaOps` : DEFAULT_DOCUMENT_TITLE;
}

/**
 * Whether the route has been migrated to Workbench tokens (see
 * WORKBENCH_ROUTES). Static nav routes are decided by literal membership;
 * only id-shaped last segments are tried against the dynamic patterns.
 */
export function isWorkbenchRoute(pathname) {
  const path = cleanPath(pathname);
  if (hasStaticTitle(path)) return WORKBENCH_ROUTES.includes(path);

  const segments = path.split("/").filter(Boolean);
  const last = segments[segments.length - 1];
  if (!last || !isDynamicSegment(last)) return false;

  return WORKBENCH_ROUTES.some(
    (route) => route.includes(":") && matchPath(route, path) !== null
  );
}
