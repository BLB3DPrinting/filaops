/**
 * DashboardTab - Accounting dashboard with revenue, payments, tax, COGS, and profit cards.
 */
/* eslint-disable react-hooks/exhaustive-deps */
import { useState, useEffect } from "react";
import { API_URL } from "../../config/api";

export default function DashboardTab() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    fetchDashboard();
  }, []);

  const fetchDashboard = async () => {
    setError(null);
    try {
      const res = await fetch(`${API_URL}/api/v1/admin/accounting/dashboard`, {
        credentials: "include",
      });
      if (res.ok) {
        setData(await res.json());
      } else {
        setError(`Failed to load: ${res.status} ${res.statusText}`);
      }
    } catch (err) {
      console.error("Error fetching dashboard:", err);
      setError(`Network error: ${err.message}`);
    } finally {
      setLoading(false);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-500"></div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="bg-red-900/30 border border-red-700 rounded-xl p-4 flex items-center gap-3">
        <svg className="w-5 h-5 text-red-400 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
        </svg>
        <div className="flex-1">
          <p className="text-red-400 font-medium text-sm">{error}</p>
          <p className="text-gray-500 text-xs mt-1">Check that the backend server is running.</p>
        </div>
        <button
          onClick={fetchDashboard}
          className="px-3 py-1 bg-red-600/20 text-red-400 rounded hover:bg-red-600/30 text-sm"
        >
          Retry
        </button>
      </div>
    );
  }

  const formatCurrency = (amount) => {
    return new Intl.NumberFormat("en-US", {
      style: "currency",
      currency: "USD",
    }).format(amount || 0);
  };

  // Check if there's no shipped orders yet (common for new installations)
  const hasNoShippedOrders = data?.revenue?.mtd_orders === 0 && data?.revenue?.ytd_orders === 0;
  const hasOutstandingOrders = data?.payments?.outstanding_orders > 0;

  return (
    <div className="space-y-6">
      {/* Helpful hint for new users */}
      {hasNoShippedOrders && hasOutstandingOrders && (
        <div className="bg-blue-500/10 border border-blue-500/30 rounded-xl p-4 flex items-start gap-3">
          <svg className="w-5 h-5 text-blue-400 mt-0.5 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
          </svg>
          <div>
            <p className="text-blue-400 font-medium text-sm">Revenue appears after shipping</p>
            <p className="text-gray-400 text-xs mt-1">
              You have {data?.payments?.outstanding_orders} orders awaiting fulfillment.
              Revenue is recognized when orders ship (accrual accounting per GAAP).
              Record payments via the order detail page.
            </p>
          </div>
        </div>
      )}

      {/* Revenue & Payments Row */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        <div className="bg-gray-900 border border-gray-800 rounded-xl p-5">
          <div className="text-gray-400 text-sm mb-1">
            Revenue MTD
            <span
              className="ml-1 text-xs"
              title="Revenue recognized at shipment per GAAP (excludes tax)"
            >
              ℹ️
            </span>
          </div>
          <div className="text-2xl font-bold text-white">
            {formatCurrency(data?.revenue?.mtd)}
          </div>
          <div className="text-xs text-gray-500 mt-1">
            {data?.revenue?.mtd_orders || 0} orders shipped
          </div>
        </div>

        <div className="bg-gray-900 border border-gray-800 rounded-xl p-5">
          <div className="text-gray-400 text-sm mb-1">
            Revenue YTD
            <span
              className="ml-1 text-xs"
              title="Year-to-date from fiscal year start"
            >
              ℹ️
            </span>
          </div>
          <div className="text-2xl font-bold text-white">
            {formatCurrency(data?.revenue?.ytd)}
          </div>
          <div className="text-xs text-gray-500 mt-1">
            {data?.revenue?.ytd_orders || 0} orders shipped
          </div>
        </div>

        <div className="bg-gray-900 border border-gray-800 rounded-xl p-5">
          <div className="text-gray-400 text-sm mb-1">
            Cash Received MTD
            <span
              className="ml-1 text-xs"
              title="Actual payments collected (cash basis)"
            >
              ℹ️
            </span>
          </div>
          <div className="text-2xl font-bold text-green-400">
            {formatCurrency(data?.payments?.mtd_received)}
          </div>
          <div className="text-xs text-gray-500 mt-1">
            YTD: {formatCurrency(data?.payments?.ytd_received)}
          </div>
        </div>

        <div className="bg-gray-900 border border-gray-800 rounded-xl p-5">
          <div className="text-gray-400 text-sm mb-1">
            Accounts Receivable
            <span
              className="ml-1 text-xs"
              title="Outstanding balance owed by customers"
            >
              ℹ️
            </span>
          </div>
          <div className="text-2xl font-bold text-yellow-400">
            {formatCurrency(data?.payments?.outstanding)}
          </div>
          <div className="text-xs text-gray-500 mt-1">
            {data?.payments?.outstanding_orders || 0} unpaid orders
          </div>
        </div>
      </div>

      {/* Tax & COGS Row */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <div className="bg-gray-900 border border-gray-800 rounded-xl p-5">
          <div className="text-gray-400 text-sm mb-1">
            Sales Tax Liability MTD
            <span
              className="ml-1 text-xs"
              title="Tax collected on behalf of government (not revenue)"
            >
              ℹ️
            </span>
          </div>
          <div className="text-2xl font-bold text-blue-400">
            {formatCurrency(data?.tax?.mtd_collected)}
          </div>
          <div className="text-xs text-gray-500 mt-1">
            YTD: {formatCurrency(data?.tax?.ytd_collected)}
          </div>
        </div>

        <div className="bg-gray-900 border border-gray-800 rounded-xl p-5">
          <div className="text-gray-400 text-sm mb-1">
            COGS MTD
            <span
              className="ml-1 text-xs"
              title="Direct material costs of shipped goods"
            >
              ℹ️
            </span>
          </div>
          <div className="text-2xl font-bold text-red-400">
            {formatCurrency(data?.cogs?.mtd)}
          </div>
          <div className="text-xs text-gray-500 mt-1">Cost of goods sold</div>
        </div>

        <div className="bg-gray-900 border border-gray-800 rounded-xl p-5">
          <div className="text-gray-400 text-sm mb-1">
            Gross Profit MTD
            <span
              className="ml-1 text-xs"
              title="Revenue - COGS (before operating expenses)"
            >
              ℹ️
            </span>
          </div>
          <div className="text-2xl font-bold text-green-400">
            {formatCurrency(data?.profit?.mtd_gross)}
          </div>
          <div className="text-xs text-gray-500 mt-1">
            {(data?.profit?.mtd_margin_pct || 0).toFixed(1)}% margin
          </div>
        </div>
      </div>
    </div>
  );
}
