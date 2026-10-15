import { Outlet, Link, NavLink, useNavigate } from "react-router-dom";
import { useState, useEffect, useRef } from "react";
import Breadcrumbs from "./Breadcrumbs";
import SecurityBadge from "./SecurityBadge";
import useActivityTokenRefresh from "../hooks/useActivityTokenRefresh";
import { useApi } from "../hooks/useApi";
import {
  getCurrentVersion,
  getCurrentVersionSync,
  formatVersion,
} from "../utils/version";
import { API_URL } from "../config/api";
import { useFeatureFlags } from "../hooks/useFeatureFlags";
import logoNavbar from "../assets/logo_navbar.png";
import { LogoutIcon, MenuIcon } from "./nav/navIcons";
import { navGroups } from "./nav/navConfig";

/**
 * The sidebar brand mark. A shop's uploaded logo replaces the FilaOps
 * wordmark; without one the wordmark shows. Collapsed, only an uploaded logo
 * shows, at icon width. onLogoError fires if the logo image fails to load,
 * so the caller can fall back to the no-logo layout.
 */
function SidebarBrand({ companyLogoUrl, compact = false, onLogoError }) {
  if (companyLogoUrl) {
    return (
      <img
        src={companyLogoUrl}
        alt="Company Logo"
        onError={onLogoError}
        className={`h-10 w-auto object-contain ${compact ? "max-w-[3rem]" : "max-w-[10rem]"}`}
      />
    );
  }
  if (compact) return null;
  return <img src={logoNavbar} alt="FilaOps" className="h-32" />;
}

/**
 * Attribution at the foot of the sidebar, shown only when a shop logo has
 * replaced the FilaOps wordmark at the top.
 */
function PoweredBy({ companyLogoUrl, compact = false }) {
  if (!companyLogoUrl) return null;
  return (
    <div
      className="shrink-0 px-4 py-3 text-xs text-center"
      style={{
        borderTop: "1px solid var(--border-subtle)",
        color: "var(--text-secondary)",
        opacity: 0.7,
      }}
      title="Powered by FilaOps"
    >
      {compact ? "FilaOps" : "Powered by FilaOps"}
    </div>
  );
}

/**
 * The admin shell: sidebar, top bar, and the outlet every /admin/* route
 * renders into.
 *
 * Owns session validation on entry, the collapsible/mobile sidebar state, and
 * the role- and tier-filtering of nav entries. The nav structure itself lives
 * in ./nav/navConfig and its glyphs in ./nav/navIcons.
 */
export default function AdminLayout() {
  const navigate = useNavigate();
  const api = useApi();
  // Persist sidebar state in localStorage
  const [sidebarOpen, setSidebarOpen] = useState(() => {
    const saved = localStorage.getItem("sidebarOpen");
    if (saved === null) return true;
    try {
      return JSON.parse(saved);
    } catch {
      return true;
    }
  });
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  // Focus moves into the drawer when it opens and back to the trigger when
  // it closes, so keyboard and screen-reader users don't lose their place.
  const menuTriggerRef = useRef(null);
  const menuCloseRef = useRef(null);
  const menuWasOpen = useRef(false);
  useEffect(() => {
    if (mobileMenuOpen) {
      menuCloseRef.current?.focus();
    } else if (menuWasOpen.current) {
      menuTriggerRef.current?.focus();
    }
    menuWasOpen.current = mobileMenuOpen;
  }, [mobileMenuOpen]);

  // Save sidebar state to localStorage when it changes
  useEffect(() => {
    localStorage.setItem("sidebarOpen", JSON.stringify(sidebarOpen));
  }, [sidebarOpen]);

  // Auto-refresh tokens when user is active to prevent losing work
  useActivityTokenRefresh();
  const [currentVersion, setCurrentVersion] = useState(getCurrentVersionSync());
  const [user] = useState(() => {
    const userData = localStorage.getItem("adminUser");
    if (!userData) return null;

    try {
      return JSON.parse(userData);
    } catch (error) {
      console.error("Failed to parse adminUser from localStorage:", error);
      localStorage.removeItem("adminUser");
      return null;
    }
  });

  // Company logo from settings
  const [companyLogoUrl, setCompanyLogoUrl] = useState(null);

  useEffect(() => {
    const checkCompanyLogo = async () => {
      try {
        const res = await fetch(`${API_URL}/api/v1/settings/company/logo`, {
          credentials: "include",
        });
        if (res.ok) {
          setCompanyLogoUrl(`${API_URL}/api/v1/settings/company/logo`);
        }
      } catch {
        // No logo uploaded - show only the FilaOps logo
      }
    };
    checkCompanyLogo();
  }, []);

  // AI Settings for SecurityBadge
  const [aiSettings, setAiSettings] = useState(null);
  const [aiSettingsFailed, setAiSettingsFailed] = useState(false);
  const [portalLinkLoading, setPortalLinkLoading] = useState(false);

  useEffect(() => {
    const fetchAiSettings = async () => {
      if (!localStorage.getItem("adminUser")) return;

      try {
        const response = await fetch(`${API_URL}/api/v1/settings/ai`, {
          credentials: "include",
        });
        if (response.ok) {
          const data = await response.json();
          setAiSettings(data);
          setAiSettingsFailed(false);
        } else if (response.status === 401 || response.status === 403) {
          // Stop polling on auth failure to avoid console spam
          setAiSettingsFailed(true);
        }
      } catch (error) {
        console.error("Failed to fetch AI settings:", error);
      }
    };

    fetchAiSettings();
    // Refresh every 30 seconds in case settings change, but stop on auth failure
    const interval = setInterval(() => {
      if (!aiSettingsFailed) fetchAiSettings();
    }, 30000);
    return () => clearInterval(interval);
  }, [aiSettingsFailed]);

  // Filter nav items based on user role
  const isAdmin = user?.account_type === "admin";
  const { isPro, hasFeature } = useFeatureFlags();

  const filteredNavGroups = navGroups
    .filter((group) => {
      if (group.adminOnly && !isAdmin) return false;
      if (group.proOnly && !isPro) return false;
      if (group.feature && !hasFeature(group.feature)) return false;
      return true;
    })
    .map((group) => ({
      ...group,
      items: group.items.filter((item) => {
        if (item.adminOnly && !isAdmin) return false;
        if (item.proOnly && !isPro) return false;
        if (item.feature && !hasFeature(item.feature)) return false;
        return true;
      }),
    }))
    .filter((group) => group.items.length > 0);

  useEffect(() => {
    if (!localStorage.getItem("adminUser")) {
      navigate("/admin/login");
    }
  }, [navigate]);

  // Validate the session against the server on entering the admin shell.
  // The localStorage check above is only a fast hint — after a backend
  // restart the cookie session can be dead while adminUser persists,
  // which used to leave users on a 401-riddled page until they manually
  // re-signed in. The shared apiClient attempts a silent token refresh
  // on 401; if that fails, its onUnauthorized clears adminUser and
  // redirects to login, so a dead session bounces cleanly instead of
  // looking broken. Network-level failures (backend fully down) are
  // swallowed — login couldn't succeed either, and the connection
  // banner already communicates the outage.
  useEffect(() => {
    api.get("/api/v1/auth/me").catch(() => {});
  }, [api]);

  useEffect(() => {
    const fetchVersion = async () => {
      try {
        const version = await getCurrentVersion();
        setCurrentVersion(version);
      } catch (error) {
        console.error("Failed to fetch version:", error);
      }
    };
    fetchVersion();
  }, []);

  // The hosted buyer portal, when this farm has one. PRO reports it as
  // buyer_url next to the admin link; a shop with only the Core-served
  // portal gets null and no button.
  const [buyerPortalUrl, setBuyerPortalUrl] = useState(null);
  useEffect(() => {
    if (!isPro || !isAdmin) return;
    let cancelled = false;
    fetch(`${API_URL}/api/v1/pro/portal/admin-link`, { credentials: "include" })
      .then((res) => (res.ok ? res.json() : null))
      .then((data) => {
        if (!cancelled) setBuyerPortalUrl(data?.buyer_url || null);
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, [isPro, isAdmin]);

  const handleOpenPortalAdmin = async () => {
    setPortalLinkLoading(true);
    // Open window synchronously to avoid popup blocker (must be in user-click call stack)
    // NOTE: Cannot use noopener here — it causes window.open to return null,
    // which prevents navigating the window after the fetch completes.
    const portalWindow = window.open("about:blank", "_blank");
    if (!portalWindow) {
      alert("Popup blocked. Please allow popups for this site and try again.");
      setPortalLinkLoading(false);
      return;
    }
    try {
      const res = await fetch(`${API_URL}/api/v1/pro/portal/admin-link`, {
        credentials: "include",
      });
      if (!res.ok) throw new Error("Failed to get portal link");
      const data = await res.json();
      if (!data.url) throw new Error("No portal URL returned");
      portalWindow.location.href = data.url;
    } catch (err) {
      console.error("Portal admin link failed:", err);
      portalWindow.close();
      alert("Could not open Portal Admin. Please try again.");
    } finally {
      setPortalLinkLoading(false);
    }
  };

  const handleLogout = async () => {
    try {
      await fetch(`${API_URL}/api/v1/auth/logout`, {
        method: "POST",
        credentials: "include",
      });
    } catch {
      // Continue with local cleanup even if server call fails
    }
    localStorage.removeItem("adminUser");
    navigate("/admin/login");
  };

  return (
    <>
      {/* Skip to content link for keyboard accessibility */}
      <a
        href="#main-content"
        className="sr-only focus:not-sr-only focus:absolute focus:top-4 focus:left-4 focus:z-[100] focus:px-4 focus:py-2 focus:bg-blue-600 focus:text-white focus:rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-400 focus:ring-offset-2 focus:ring-offset-gray-900"
      >
        Skip to main content
      </a>
      <div
        className="min-h-screen flex"
        style={{ backgroundColor: "var(--bg-primary)" }}
      >
        {/* Mobile menu button. Hidden while the drawer is open: it sits above
            the drawer and would cover the brand mark; the drawer has its own
            close button. */}
        {!mobileMenuOpen && (
          <button
            ref={menuTriggerRef}
            onClick={() => setMobileMenuOpen(true)}
            className="md:hidden fixed top-4 left-4 z-50 p-2 rounded-lg text-white transition-all"
            style={{ backgroundColor: "var(--bg-card)" }}
            aria-label="Open navigation menu"
          >
            <MenuIcon />
          </button>
        )}

        {/* Mobile sidebar overlay */}
        {mobileMenuOpen && (
          <div
            className="md:hidden fixed inset-0 z-40 bg-black bg-opacity-50"
            onClick={() => setMobileMenuOpen(false)}
          >
            <aside
              className="w-64 h-full flex flex-col"
              style={{
                backgroundColor: "var(--bg-secondary)",
                borderRight: "1px solid var(--border-subtle)",
              }}
              onClick={(e) => e.stopPropagation()}
            >
              <div
                className="p-4 flex items-center justify-between"
                style={{ borderBottom: "1px solid var(--border-subtle)" }}
              >
                <Link
                  to="/admin"
                  aria-label="Go to Command Center"
                  className="flex items-center gap-3 min-w-0"
                >
                  <SidebarBrand
                    companyLogoUrl={companyLogoUrl}
                    onLogoError={() => setCompanyLogoUrl(null)}
                  />
                </Link>
                <button
                  ref={menuCloseRef}
                  onClick={() => setMobileMenuOpen(false)}
                  aria-label="Close navigation menu"
                  className="p-2 rounded-lg transition-colors"
                  style={{ color: "var(--text-secondary)" }}
                >
                  <svg
                    className="w-6 h-6"
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
                </button>
              </div>
              <nav className="flex-1 p-4 overflow-y-auto">
                {filteredNavGroups.map((group, groupIndex) => (
                  <div key={groupIndex} className={group.label ? "mt-4" : ""}>
                    {group.label && (
                      <div
                        className="px-3 py-2 text-xs font-semibold uppercase tracking-wider"
                        style={{ color: "var(--text-muted)" }}
                      >
                        {group.label}
                      </div>
                    )}
                    <div className="space-y-1">
                      {group.items.map((item) => (
                        <NavLink
                          key={item.path}
                          to={item.path}
                          end={item.end}
                          onClick={() => setMobileMenuOpen(false)}
                          className={({ isActive }) =>
                            `flex items-center gap-3 px-3 py-2.5 rounded-lg transition-all ${
                              isActive ? "nav-item-active" : "nav-item"
                            }`
                          }
                        >
                          <item.icon />
                          <span>{item.label}</span>
                          {(group.proOnly || item.proOnly) && !isPro && (
                            <svg
                              className="w-3 h-3 ml-auto"
                              style={{ color: "var(--text-muted)" }}
                              fill="none"
                              stroke="currentColor"
                              viewBox="0 0 24 24"
                            >
                              <path
                                strokeLinecap="round"
                                strokeLinejoin="round"
                                strokeWidth={2}
                                d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z"
                              />
                            </svg>
                          )}
                        </NavLink>
                      ))}
                    </div>
                  </div>
                ))}
              </nav>
              <PoweredBy companyLogoUrl={companyLogoUrl} />
            </aside>
          </div>
        )}

        {/* Desktop sidebar */}
        <aside
          className={`hidden md:flex ${
            sidebarOpen ? "w-64" : "w-20"
          } transition-all duration-300 flex-col h-screen sticky top-0`}
          style={{
            backgroundColor: "var(--bg-secondary)",
            borderRight: "1px solid var(--border-subtle)",
          }}
        >
          <div
            className="p-4 flex items-center justify-between"
            style={{ borderBottom: "1px solid var(--border-subtle)" }}
          >
            <Link
              to="/admin"
              aria-label="Go to Command Center"
              className={`flex items-center ${sidebarOpen ? "gap-3" : "justify-center w-full"}`}
            >
              <SidebarBrand
                companyLogoUrl={companyLogoUrl}
                compact={!sidebarOpen}
                onLogoError={() => setCompanyLogoUrl(null)}
              />
            </Link>
            {sidebarOpen && (
              <button
                onClick={() => setSidebarOpen(!sidebarOpen)}
                className="p-2 rounded-lg transition-colors"
                style={{ color: "var(--text-secondary)" }}
              >
                <MenuIcon />
              </button>
            )}
          </div>
          {!sidebarOpen && (
            <div
              className="p-2 flex justify-center"
              style={{ borderBottom: "1px solid var(--border-subtle)" }}
            >
              <button
                onClick={() => setSidebarOpen(!sidebarOpen)}
                className="p-2 rounded-lg transition-colors"
                style={{ color: "var(--text-secondary)" }}
              >
                <MenuIcon />
              </button>
            </div>
          )}
          <nav className="flex-1 p-4 overflow-y-auto">
            {filteredNavGroups.map((group, groupIndex) => (
              <div key={groupIndex} className={group.label ? "mt-4" : ""}>
                {group.label && sidebarOpen && (
                  <div
                    className="px-3 py-2 text-xs font-semibold uppercase tracking-wider"
                    style={{ color: "var(--text-muted)" }}
                  >
                    {group.label}
                  </div>
                )}
                {/* When collapsed, add spacing where header would be */}
                {group.label && !sidebarOpen && <div className="h-4" />}
                <div className="space-y-1">
                  {group.items.map((item) => (
                    <NavLink
                      key={item.path}
                      to={item.path}
                      end={item.end}
                      title={!sidebarOpen ? item.label : undefined}
                      className={({ isActive }) =>
                        `flex items-center gap-3 px-3 py-2.5 rounded-lg transition-all ${
                          isActive ? "nav-item-active" : "nav-item"
                        } ${!sidebarOpen ? "justify-center" : ""}`
                      }
                    >
                      <item.icon />
                      {sidebarOpen && <span>{item.label}</span>}
                      {sidebarOpen &&
                        (group.proOnly || item.proOnly) &&
                        !isPro && (
                          <svg
                            className="w-3 h-3 ml-auto"
                            style={{ color: "var(--text-muted)" }}
                            fill="none"
                            stroke="currentColor"
                            viewBox="0 0 24 24"
                          >
                            <path
                              strokeLinecap="round"
                              strokeLinejoin="round"
                              strokeWidth={2}
                              d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z"
                            />
                          </svg>
                        )}
                    </NavLink>
                  ))}
                </div>
              </div>
            ))}
          </nav>
          <PoweredBy companyLogoUrl={companyLogoUrl} compact={!sidebarOpen} />
        </aside>
        <div className="flex-1 flex flex-col">
          <header
            className="sticky top-0 z-30 glass px-6 py-4"
            style={{ borderBottom: "1px solid var(--border-subtle)" }}
          >
            <div className="flex justify-between items-center">
              <div className="flex items-center gap-3">
                <h1
                  className="text-lg font-semibold font-display"
                  style={{ color: "var(--text-primary)" }}
                >
                  ERP
                </h1>
                <span
                  className="text-xs font-mono-data"
                  style={{ color: "var(--text-muted)" }}
                >
                  v{formatVersion(currentVersion)}
                </span>
                <SecurityBadge
                  aiProvider={aiSettings?.ai_provider}
                  externalBlocked={aiSettings?.external_ai_blocked}
                />
              </div>
              <div className="flex items-center gap-4">
                {isPro && isAdmin && (
                  <button
                    onClick={handleOpenPortalAdmin}
                    disabled={portalLinkLoading}
                    className="flex items-center gap-2 text-sm px-3 py-1.5 rounded-lg transition-all"
                    style={{
                      color: "var(--accent)",
                      border: "1px solid var(--accent)",
                      opacity: portalLinkLoading ? 0.6 : 1,
                    }}
                    title="Open B2B Portal Admin"
                  >
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
                        d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14"
                      />
                    </svg>
                    <span>
                      {portalLinkLoading ? "Opening..." : "Portal Admin"}
                    </span>
                  </button>
                )}
                {isPro && isAdmin && buyerPortalUrl && (
                  <a
                    href={buyerPortalUrl}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-sm px-3 py-1.5 rounded-lg transition-all"
                    style={{
                      color: "var(--text-secondary)",
                      border: "1px solid var(--border-subtle)",
                    }}
                    title="Open the buyer-facing portal"
                  >
                    Buyer Portal
                  </a>
                )}
                {user && (
                  <span
                    className="text-sm"
                    style={{ color: "var(--text-secondary)" }}
                  >
                    <span style={{ color: "var(--text-primary)" }}>
                      {user.first_name} {user.last_name}
                    </span>
                  </span>
                )}
                <button
                  onClick={handleLogout}
                  className="flex items-center gap-2 text-sm transition-colors hover:text-red-400"
                  style={{ color: "var(--text-secondary)" }}
                >
                  <LogoutIcon />
                  <span>Logout</span>
                </button>
              </div>
            </div>
          </header>
          <main
            id="main-content"
            className="flex-1 p-6 overflow-auto grid-pattern"
            tabIndex="-1"
          >
            <Breadcrumbs />
            <Outlet />
          </main>
        </div>
      </div>
    </>
  );
}
