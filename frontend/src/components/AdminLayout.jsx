import { Outlet, Link, NavLink, useNavigate } from "react-router-dom";
import { useState, useEffect } from "react";
import SecurityBadge from "./SecurityBadge";
import useActivityTokenRefresh from "../hooks/useActivityTokenRefresh";
import {
  getCurrentVersion,
  getCurrentVersionSync,
  formatVersion,
} from "../utils/version";
import { API_URL } from "../config/api";
import { useFeatureFlags } from "../hooks/useFeatureFlags";
import logoNavbar from "../assets/logo_navbar.png";
import logoBLB3D from "../assets/logo_blb3d.svg";

const DashboardIcon = () => (
  <svg
    className="w-5 h-5"
    fill="none"
    stroke="currentColor"
    viewBox="0 0 24 24"
  >
    <path
      strokeLinecap="round"
      strokeLinejoin="round"
      strokeWidth={2}
      d="M4 6a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2H6a2 2 0 01-2-2V6zM14 6a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2h-2a2 2 0 01-2-2V6zM4 16a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2H6a2 2 0 01-2-2v-2zM14 16a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2h-2a2 2 0 01-2-2v-2z"
    />
  </svg>
);

const BOMIcon = () => (
  <svg
    className="w-5 h-5"
    fill="none"
    stroke="currentColor"
    viewBox="0 0 24 24"
  >
    <path
      strokeLinecap="round"
      strokeLinejoin="round"
      strokeWidth={2}
      d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2m-3 7h3m-3 4h3m-6-4h.01M9 16h.01"
    />
  </svg>
);

const OrdersIcon = () => (
  <svg
    className="w-5 h-5"
    fill="none"
    stroke="currentColor"
    viewBox="0 0 24 24"
  >
    <path
      strokeLinecap="round"
      strokeLinejoin="round"
      strokeWidth={2}
      d="M16 11V7a4 4 0 00-8 0v4M5 9h14l1 12H4L5 9z"
    />
  </svg>
);

const QuotesIcon = () => (
  <svg
    className="w-5 h-5"
    fill="none"
    stroke="currentColor"
    viewBox="0 0 24 24"
  >
    <path
      strokeLinecap="round"
      strokeLinejoin="round"
      strokeWidth={2}
      d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"
    />
  </svg>
);

const PaymentsIcon = () => (
  <svg
    className="w-5 h-5"
    fill="none"
    stroke="currentColor"
    viewBox="0 0 24 24"
  >
    <path
      strokeLinecap="round"
      strokeLinejoin="round"
      strokeWidth={2}
      d="M12 8c-1.657 0-3 .895-3 2s1.343 2 3 2 3 .895 3 2-1.343 2-3 2m0-8c1.11 0 2.08.402 2.599 1M12 8V7m0 1v8m0 0v1m0-1c-1.11 0-2.08-.402-2.599-1M21 12a9 9 0 11-18 0 9 9 0 0118 0z"
    />
  </svg>
);

const MessagesIcon = () => (
  <svg
    className="w-5 h-5"
    fill="none"
    stroke="currentColor"
    viewBox="0 0 24 24"
  >
    <path
      strokeLinecap="round"
      strokeLinejoin="round"
      strokeWidth={2}
      d="M20 13V6a2 2 0 00-2-2H6a2 2 0 00-2 2v7m16 0v5a2 2 0 01-2 2H6a2 2 0 01-2-2v-5m16 0h-2.586a1 1 0 00-.707.293l-2.414 2.414a1 1 0 01-.707.293h-3.172a1 1 0 01-.707-.293l-2.414-2.414A1 1 0 006.586 13H4"
    />
  </svg>
);

const ProductionIcon = () => (
  <svg
    className="w-5 h-5"
    fill="none"
    stroke="currentColor"
    viewBox="0 0 24 24"
  >
    <path
      strokeLinecap="round"
      strokeLinejoin="round"
      strokeWidth={2}
      d="M19.428 15.428a2 2 0 00-1.022-.547l-2.387-.477a6 6 0 00-3.86.517l-.318.158a6 6 0 01-3.86.517L6.05 15.21a2 2 0 00-1.806.547M8 4h8l-1 1v5.172a2 2 0 00.586 1.414l5 5c1.26 1.26.367 3.414-1.415 3.414H4.828c-1.782 0-2.674-2.154-1.414-3.414l5-5A2 2 0 009 10.172V5L8 4z"
    />
  </svg>
);

const ShippingIcon = () => (
  <svg
    className="w-5 h-5"
    fill="none"
    stroke="currentColor"
    viewBox="0 0 24 24"
  >
    <path
      strokeLinecap="round"
      strokeLinejoin="round"
      strokeWidth={2}
      d="M8 7h12m0 0l-4-4m4 4l-4 4m0 6H4m0 0l4 4m-4-4l4-4"
    />
  </svg>
);

const ItemsIcon = () => (
  <svg
    className="w-5 h-5"
    fill="none"
    stroke="currentColor"
    viewBox="0 0 24 24"
  >
    <path
      strokeLinecap="round"
      strokeLinejoin="round"
      strokeWidth={2}
      d="M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 012-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10"
    />
  </svg>
);

const PurchasingIcon = () => (
  <svg
    className="w-5 h-5"
    fill="none"
    stroke="currentColor"
    viewBox="0 0 24 24"
  >
    <path
      strokeLinecap="round"
      strokeLinejoin="round"
      strokeWidth={2}
      d="M3 3h2l.4 2M7 13h10l4-8H5.4M7 13L5.4 5M7 13l-2.293 2.293c-.63.63-.184 1.707.707 1.707H17m0 0a2 2 0 100 4 2 2 0 000-4zm-8 2a2 2 0 11-4 0 2 2 0 014 0z"
    />
  </svg>
);

const ManufacturingIcon = () => (
  <svg
    className="w-5 h-5"
    fill="none"
    stroke="currentColor"
    viewBox="0 0 24 24"
  >
    <path
      strokeLinecap="round"
      strokeLinejoin="round"
      strokeWidth={2}
      d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z"
    />
    <path
      strokeLinecap="round"
      strokeLinejoin="round"
      strokeWidth={2}
      d="M15 12a3 3 0 11-6 0 3 3 0 016 0z"
    />
  </svg>
);

const PrintersIcon = () => (
  <svg
    className="w-5 h-5"
    fill="none"
    stroke="currentColor"
    viewBox="0 0 24 24"
  >
    <path
      strokeLinecap="round"
      strokeLinejoin="round"
      strokeWidth={2}
      d="M17 17h2a2 2 0 002-2v-4a2 2 0 00-2-2H5a2 2 0 00-2 2v4a2 2 0 002 2h2m2 4h6a2 2 0 002-2v-4a2 2 0 00-2-2H9a2 2 0 00-2 2v4a2 2 0 002 2zm8-12V5a2 2 0 00-2-2H9a2 2 0 00-2 2v4h10z"
    />
  </svg>
);

const CustomersIcon = () => (
  <svg
    className="w-5 h-5"
    fill="none"
    stroke="currentColor"
    viewBox="0 0 24 24"
  >
    <path
      strokeLinecap="round"
      strokeLinejoin="round"
      strokeWidth={2}
      d="M17 20h5v-2a3 3 0 00-5.356-1.857M17 20H7m10 0v-2c0-.656-.126-1.283-.356-1.857M7 20H2v-2a3 3 0 015.356-1.857M7 20v-2c0-.656.126-1.283.356-1.857m0 0a5.002 5.002 0 019.288 0M15 7a3 3 0 11-6 0 3 3 0 016 0zm6 3a2 2 0 11-4 0 2 2 0 014 0zM7 10a2 2 0 11-4 0 2 2 0 014 0z"
    />
  </svg>
);

const MaterialImportIcon = () => (
  <svg
    className="w-5 h-5"
    fill="none"
    stroke="currentColor"
    viewBox="0 0 24 24"
  >
    <path
      strokeLinecap="round"
      strokeLinejoin="round"
      strokeWidth={2}
      d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12"
    />
  </svg>
);

const LogoutIcon = () => (
  <svg
    className="w-5 h-5"
    fill="none"
    stroke="currentColor"
    viewBox="0 0 24 24"
  >
    <path
      strokeLinecap="round"
      strokeLinejoin="round"
      strokeWidth={2}
      d="M17 16l4-4m0 0l-4-4m4 4H7m6 4v1a3 3 0 01-3 3H6a3 3 0 01-3-3V7a3 3 0 013-3h4a3 3 0 013 3v1"
    />
  </svg>
);

const MenuIcon = () => (
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
      d="M4 6h16M4 12h16M4 18h16"
    />
  </svg>
);

const InventoryIcon = () => (
  <svg
    className="w-5 h-5"
    fill="none"
    stroke="currentColor"
    viewBox="0 0 24 24"
  >
    <path
      strokeLinecap="round"
      strokeLinejoin="round"
      strokeWidth={2}
      d="M20 7l-8-4-8 4m16 0l-8 4m8-4v10l-8 4m0-10L4 7m8 4v10M4 7v10l8 4"
    />
  </svg>
);

// TODO: Re-enable when Pro analytics are implemented
// const AnalyticsIcon = () => (
//   <svg
//     className="w-5 h-5"
//     fill="none"
//     stroke="currentColor"
//     viewBox="0 0 24 24"
//   >
//     <path
//       strokeLinecap="round"
//       strokeLinejoin="round"
//       strokeWidth={2}
//       d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z"
//     />
//   </svg>
// );

const AccountingIcon = () => (
  <svg
    className="w-5 h-5"
    fill="none"
    stroke="currentColor"
    viewBox="0 0 24 24"
  >
    <path
      strokeLinecap="round"
      strokeLinejoin="round"
      strokeWidth={2}
      d="M9 7h6m0 10v-3m-3 3h.01M9 17h.01M9 14h.01M12 14h.01M15 11h.01M12 11h.01M9 11h.01M7 21h10a2 2 0 002-2V5a2 2 0 00-2-2H7a2 2 0 00-2 2v14a2 2 0 002 2z"
    />
  </svg>
);

const SettingsIcon = () => (
  <svg
    className="w-5 h-5"
    fill="none"
    stroke="currentColor"
    viewBox="0 0 24 24"
  >
    <path
      strokeLinecap="round"
      strokeLinejoin="round"
      strokeWidth={2}
      d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z"
    />
    <path
      strokeLinecap="round"
      strokeLinejoin="round"
      strokeWidth={2}
      d="M15 12a3 3 0 11-6 0 3 3 0 016 0z"
    />
  </svg>
);

const QualityIcon = () => (
  <svg
    className="w-5 h-5"
    fill="none"
    stroke="currentColor"
    viewBox="0 0 24 24"
  >
    <path
      strokeLinecap="round"
      strokeLinejoin="round"
      strokeWidth={2}
      d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z"
    />
  </svg>
);

const InvoicesIcon = () => (
  <svg
    className="w-5 h-5"
    fill="none"
    stroke="currentColor"
    viewBox="0 0 24 24"
  >
    <path
      strokeLinecap="round"
      strokeLinejoin="round"
      strokeWidth={2}
      d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"
    />
  </svg>
);

const FilaFarmIcon = () => (
  <svg
    className="w-5 h-5"
    fill="none"
    stroke="currentColor"
    viewBox="0 0 24 24"
  >
    <path
      strokeLinecap="round"
      strokeLinejoin="round"
      strokeWidth={2}
      d="M19 21V5a2 2 0 00-2-2H7a2 2 0 00-2 2v16m14 0h2m-2 0h-5m-9 0H3m2 0h5M9 7h1m-1 4h1m4-4h1m-1 4h1m-5 10v-5a1 1 0 011-1h2a1 1 0 011 1v5m-4 0h4"
    />
  </svg>
);

const CommandCenterIcon = () => (
  <svg
    className="w-5 h-5"
    fill="none"
    stroke="currentColor"
    viewBox="0 0 24 24"
  >
    <path
      strokeLinecap="round"
      strokeLinejoin="round"
      strokeWidth={2}
      d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z"
    />
  </svg>
);

const navGroups = [
  {
    label: null, // No header for dashboard
    items: [
      { path: "/admin", label: "Dashboard", icon: DashboardIcon, end: true },
      {
        path: "/admin/command-center",
        label: "Command Center",
        icon: CommandCenterIcon,
      },
    ],
  },
  {
    label: "SALES",
    items: [
      { path: "/admin/orders", label: "Orders", icon: OrdersIcon },
      { path: "/admin/quotes", label: "Quotes", icon: QuotesIcon },
      {
        path: "/admin/payments",
        label: "Payments",
        icon: PaymentsIcon,
        adminOnly: true,
      },
      {
        path: "/admin/invoices",
        label: "Invoices",
        icon: InvoicesIcon,
        adminOnly: true,
      },
      {
        path: "/admin/customers",
        label: "Customers",
        icon: CustomersIcon,
        adminOnly: true,
      },
      { path: "/admin/messages", label: "Messages", icon: MessagesIcon },
    ],
  },
  {
    label: "INVENTORY",
    items: [
      { path: "/admin/items", label: "Items", icon: ItemsIcon },
      {
        path: "/admin/materials/import",
        label: "Import Materials",
        icon: MaterialImportIcon,
        adminOnly: true,
      },
      { path: "/admin/bom", label: "Bill of Materials", icon: BOMIcon },
      {
        path: "/admin/locations",
        label: "Locations",
        icon: InventoryIcon,
        adminOnly: true,
      },
      {
        path: "/admin/inventory/transactions",
        label: "Transactions",
        icon: InventoryIcon,
        adminOnly: true,
      },
      {
        path: "/admin/inventory/cycle-count",
        label: "Cycle Count",
        icon: InventoryIcon,
        adminOnly: true,
      },
      {
        path: "/admin/spools",
        label: "Material Spools",
        icon: InventoryIcon,
        adminOnly: true,
      },
    ],
  },
  {
    label: "OPERATIONS",
    items: [
      { path: "/admin/production", label: "Production", icon: ProductionIcon },
      {
        path: "/admin/manufacturing",
        label: "Manufacturing",
        icon: ManufacturingIcon,
      },
      { path: "/admin/printers", label: "Printers", icon: PrintersIcon },
      {
        path: "/admin/filafarm",
        label: "FilaFarm",
        icon: FilaFarmIcon,
        proOnly: true,
        feature: "filafarm",
      },
      { path: "/admin/purchasing", label: "Purchasing", icon: PurchasingIcon },
      { path: "/admin/shipping", label: "Shipping", icon: ShippingIcon },
    ],
  },
  {
    label: "B2B PORTAL",
    adminOnly: true,
    proOnly: true,
    items: [
      {
        path: "/admin/access-requests",
        label: "Access Requests",
        icon: CustomersIcon,
        adminOnly: true,
      },
      {
        path: "/admin/catalogs",
        label: "Catalogs",
        icon: ItemsIcon,
        adminOnly: true,
      },
      {
        path: "/admin/price-levels",
        label: "Price Levels",
        icon: AccountingIcon,
        adminOnly: true,
      },
    ],
  },
  {
    label: "QUALITY",
    items: [
      {
        path: "/admin/quality/traceability",
        label: "Material Traceability",
        icon: QualityIcon,
      },
    ],
  },
  {
    label: "ADMIN",
    adminOnly: true,
    items: [
      {
        path: "/admin/accounting",
        label: "Accounting",
        icon: AccountingIcon,
        adminOnly: true,
      },
      {
        path: "/admin/orders/import",
        label: "Import Orders",
        icon: MaterialImportIcon,
        adminOnly: true,
      },
      {
        path: "/admin/users",
        label: "Team Members",
        icon: CustomersIcon,
        adminOnly: true,
      },
      {
        path: "/admin/scrap-reasons",
        label: "Scrap Reasons",
        icon: SettingsIcon,
        adminOnly: true,
      },
      // TODO: Re-enable Analytics when Pro version analytics are implemented
      // {
      //   path: "/admin/analytics",
      //   label: "Analytics",
      //   icon: AnalyticsIcon,
      //   adminOnly: true,
      // },
      {
        path: "/admin/settings",
        label: "Settings",
        icon: SettingsIcon,
        adminOnly: true,
      },
      {
        path: "/admin/security",
        label: "Security Audit",
        icon: QualityIcon,
        adminOnly: true,
      },
    ],
  },
];

export default function AdminLayout() {
  const navigate = useNavigate();
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
        // No logo uploaded - use default
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
        {/* Mobile menu button */}
        <button
          onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
          className="md:hidden fixed top-4 left-4 z-50 p-2 rounded-lg text-white transition-all"
          style={{ backgroundColor: "var(--bg-card)" }}
          aria-label="Open navigation menu"
        >
          <MenuIcon />
        </button>

        {/* Mobile sidebar overlay */}
        {mobileMenuOpen && (
          <div
            className="md:hidden fixed inset-0 z-40 bg-black bg-opacity-50"
            onClick={() => setMobileMenuOpen(false)}
          >
            <aside
              className="w-64 h-full"
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
                <Link to="/admin" className="flex items-center gap-3">
                  <div className="logo-container">
                    <img
                      src={companyLogoUrl || logoBLB3D}
                      alt="Company Logo"
                      className="h-10 w-auto logo-glow"
                    />
                  </div>
                  <img src={logoNavbar} alt="FilaOps" className="h-32" />
                </Link>
                <button
                  onClick={() => setMobileMenuOpen(false)}
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
              className={`flex items-center ${sidebarOpen ? "gap-3" : "justify-center w-full"}`}
            >
              <div className="logo-container">
                <img
                  src={companyLogoUrl || logoBLB3D}
                  alt="Company Logo"
                  className="h-10 w-auto logo-glow"
                />
              </div>
              {sidebarOpen && (
                <img src={logoNavbar} alt="FilaOps" className="h-32" />
              )}
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
                      color: "var(--accent-primary)",
                      border: "1px solid var(--accent-primary)",
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
            <Outlet />
          </main>
        </div>
      </div>
    </>
  );
}
