import { Link, useLocation } from "react-router-dom";
import { buildBreadcrumbs, NON_NAVIGABLE_PATHS } from "./breadcrumbs.utils";

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
              <span style={{ color: "var(--text-secondary)" }}>
                {crumb.label}
              </span>
            ) : (
              <Link
                to={crumb.path}
                className="transition-colors hover:underline"
                style={{ color: "var(--text-secondary)" }}
                {...(index === 0 ? { "aria-label": "Dashboard" } : {})}
              >
                {index === 0 ? <HomeIcon /> : crumb.label}
              </Link>
            )}
          </li>
        ))}
      </ol>
    </nav>
  );
}
