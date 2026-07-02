import { useState } from "react";
import { useFeatureFlags } from "../../hooks/useFeatureFlags";
import DashboardTab from "../../components/accounting/DashboardTab";
import SalesJournalTab from "../../components/accounting/SalesJournalTab";
import PaymentsTab from "../../components/accounting/PaymentsTab";
import COGSTab from "../../components/accounting/COGSTab";
import TaxCenterTab from "../../components/accounting/TaxCenterTab";
import GLReportsTab from "../../components/accounting/GLReportsTab";
import PeriodsTab from "../../components/accounting/PeriodsTab";

export default function AdminAccounting() {
  const [activeTab, setActiveTab] = useState("dashboard");
  const { hasFeature, isEnterprise } = useFeatureFlags();

  const tabs = [
    { id: "dashboard", label: "Dashboard", icon: "chart-bar", tier: "community" },
    { id: "sales", label: "Sales Journal", icon: "receipt", tier: "community" },
    { id: "payments", label: "Payments", icon: "credit-card", tier: "community" },
    { id: "cogs", label: "COGS & Materials", icon: "cube", tier: "community" },
    { id: "tax", label: "Tax Center", icon: "calculator", tier: "community" },
    { id: "glreports", label: "GL Reports", icon: "document-report", tier: "pro" },
    { id: "periods", label: "Periods", icon: "calendar", tier: "pro" },
  ];

  // Check if user can access a tab based on their tier. The GL/period tabs
  // back the PRO-gated accounting endpoints (require_feature("accounting")
  // keystone #861), so route the pro check through hasFeature("accounting")
  // rather than the raw tier — matches the backend gate exactly.
  const canAccessTab = (tier) => {
    if (tier === "community") return true;
    if (tier === "pro") return hasFeature("accounting");
    if (tier === "enterprise") return isEnterprise;
    return false;
  };

  const getTabIcon = (icon) => {
    switch (icon) {
      case "chart-bar":
        return (
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
              d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z"
            />
          </svg>
        );
      case "receipt":
        return (
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
              d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"
            />
          </svg>
        );
      case "credit-card":
        return (
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
              d="M3 10h18M7 15h1m4 0h1m-7 4h12a3 3 0 003-3V8a3 3 0 00-3-3H6a3 3 0 00-3 3v8a3 3 0 003 3z"
            />
          </svg>
        );
      case "cube":
        return (
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
              d="M20 7l-8-4-8 4m16 0l-8 4m8-4v10l-8 4m0-10L4 7m8 4v10M4 7v10l8 4"
            />
          </svg>
        );
      case "calculator":
        return (
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
              d="M9 7h6m0 10v-3m-3 3h.01M9 17h.01M9 14h.01M12 14h.01M15 11h.01M12 11h.01M9 11h.01M7 21h10a2 2 0 002-2V5a2 2 0 00-2-2H7a2 2 0 00-2 2v14a2 2 0 002 2z"
            />
          </svg>
        );
      case "document-report":
        return (
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
              d="M9 17v-2m3 2v-4m3 4v-6m2 10H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"
            />
          </svg>
        );
      case "calendar":
        return (
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
              d="M8 7V3m8 4V3m-9 8h10M5 21h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z"
            />
          </svg>
        );
      default:
        return null;
    }
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold text-white">Accounting</h1>
        <p className="text-gray-400 mt-1">
          Financial overview, sales journal, and tax reports
        </p>
      </div>

      {/* Tab Navigation */}
      <div className="bg-gray-900 border border-gray-800 rounded-xl p-1 flex flex-wrap gap-1">
        {tabs.map((tab) => {
          const accessible = canAccessTab(tab.tier);
          return (
            <button
              key={tab.id}
              onClick={() => accessible && setActiveTab(tab.id)}
              disabled={!accessible}
              title={!accessible ? `Requires ${tab.tier === "pro" ? "Pro" : "Enterprise"} tier` : ""}
              className={`flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
                activeTab === tab.id
                  ? "bg-blue-600 text-white"
                  : accessible
                    ? "text-gray-400 hover:text-white hover:bg-gray-800"
                    : "text-gray-600 cursor-not-allowed"
              }`}
            >
              {getTabIcon(tab.icon)}
              {tab.label}
              {!accessible && (
                <svg className="w-3 h-3 text-gray-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z" />
                </svg>
              )}
            </button>
          );
        })}
      </div>

      {/* Tab Content */}
      {activeTab === "dashboard" && <DashboardTab />}
      {activeTab === "sales" && <SalesJournalTab />}
      {activeTab === "payments" && <PaymentsTab />}
      {activeTab === "cogs" && <COGSTab />}
      {activeTab === "tax" && <TaxCenterTab />}
      {/* GL Reports / Periods back the PRO-gated accounting endpoints. Render
          a locked panel (not the tab component) when the accounting feature is
          absent, so a non-PRO user who reaches the tab sees the upsell rather
          than a 402-driven error state. Disabled tab buttons already block the
          click path; this guards direct/state edge cases too. */}
      {activeTab === "glreports" &&
        (canAccessTab("pro") ? (
          <GLReportsTab />
        ) : (
          <LockedAccountingPanel label="GL Reports" />
        ))}
      {activeTab === "periods" &&
        (canAccessTab("pro") ? (
          <PeriodsTab />
        ) : (
          <LockedAccountingPanel label="Accounting Periods" />
        ))}
    </div>
  );
}

// Locked panel for PRO-gated accounting tabs (GL Reports / Periods). Mirrors
// the AdminIntakeStudio PRO upsell shape.
function LockedAccountingPanel({ label }) {
  return (
    <div className="bg-blue-500/10 border border-blue-500/30 rounded-lg p-6 text-center">
      <svg
        className="w-12 h-12 text-blue-400 mx-auto mb-3"
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
      <h3 className="text-lg font-semibold text-white mb-2">PRO Feature</h3>
      <p className="text-gray-400 mb-4">
        {label} is part of FilaOps PRO accounting — general-ledger reporting and
        period close on top of your community sales journal, payments, and tax
        center.
      </p>
      <a
        href="/pricing"
        className="inline-block bg-blue-600 hover:bg-blue-700 text-white px-6 py-2 rounded-lg transition-colors"
      >
        Upgrade to PRO
      </a>
    </div>
  );
}
