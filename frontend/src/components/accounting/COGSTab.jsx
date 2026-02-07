/**
 * COGSTab - Cost of Goods Sold summary with period selector, summary cards, and breakdown.
 */
/* eslint-disable react-hooks/exhaustive-deps */
import { useState, useEffect } from "react";
import { API_URL } from "../../config/api";

export default function COGSTab() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [days, setDays] = useState(30);

  useEffect(() => {
    fetchCOGS();
  }, [days]);

  const fetchCOGS = async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(
        `${API_URL}/api/v1/admin/accounting/cogs-summary?days=${days}`,
        {
          credentials: "include",
        }
      );
      if (res.ok) {
        setData(await res.json());
      } else {
        setError(`Failed to load: ${res.status} ${res.statusText}`);
      }
    } catch (err) {
      console.error("Error fetching COGS:", err);
      setError(`Network error: ${err.message}`);
    } finally {
      setLoading(false);
    }
  };

  const formatCurrency = (amount) => {
    return new Intl.NumberFormat("en-US", {
      style: "currency",
      currency: "USD",
    }).format(amount || 0);
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
          onClick={fetchCOGS}
          className="px-3 py-1 bg-red-600/20 text-red-400 rounded hover:bg-red-600/30 text-sm"
        >
          Retry
        </button>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {/* Period Selector */}
      <div className="bg-gray-900 border border-gray-800 rounded-xl p-4">
        <div className="flex items-center gap-4">
          <label className="text-sm text-gray-400">Period:</label>
          <select
            value={days}
            onChange={(e) => setDays(parseInt(e.target.value))}
            className="bg-gray-800 border border-gray-700 text-white rounded px-3 py-1.5 text-sm"
          >
            <option value={7}>Last 7 days</option>
            <option value={30}>Last 30 days</option>
            <option value={90}>Last 90 days</option>
            <option value={365}>Last 365 days</option>
          </select>
        </div>
      </div>

      {/* Summary Cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        <div className="bg-gray-900 border border-gray-800 rounded-xl p-5">
          <div className="text-gray-400 text-sm mb-1">Orders Shipped</div>
          <div className="text-2xl font-bold text-white">
            {data?.orders_shipped || 0}
          </div>
        </div>
        <div className="bg-gray-900 border border-gray-800 rounded-xl p-5">
          <div className="text-gray-400 text-sm mb-1">
            Revenue
            <span
              className="ml-1 text-xs"
              title="Revenue excludes tax (tax is a liability)"
            >
              ℹ️
            </span>
          </div>
          <div className="text-2xl font-bold text-green-400">
            {formatCurrency(data?.revenue)}
          </div>
        </div>
        <div className="bg-gray-900 border border-gray-800 rounded-xl p-5">
          <div className="text-gray-400 text-sm mb-1">
            Total COGS
            <span
              className="ml-1 text-xs"
              title="Production costs only (materials, labor, packaging)"
            >
              ℹ️
            </span>
          </div>
          <div className="text-2xl font-bold text-red-400">
            {formatCurrency(data?.cogs?.total)}
          </div>
        </div>
        <div className="bg-gray-900 border border-gray-800 rounded-xl p-5">
          <div className="text-gray-400 text-sm mb-1">
            Gross Profit
            <span
              className="ml-1 text-xs"
              title="Revenue - COGS (before operating expenses)"
            >
              ℹ️
            </span>
          </div>
          <div className="text-2xl font-bold text-green-400">
            {formatCurrency(data?.gross_profit)}
          </div>
          <div className="text-xs text-gray-500 mt-1">
            {(data?.gross_margin_pct || 0).toFixed(1)}% margin
          </div>
        </div>
      </div>

      {/* COGS Breakdown */}
      <div className="bg-gray-900 border border-gray-800 rounded-xl p-5">
        <h3 className="text-lg font-semibold text-white mb-4">
          COGS Breakdown
          <span className="ml-2 text-xs text-gray-400 font-normal">
            (Production costs only)
          </span>
        </h3>
        <div className="space-y-3">
          <div className="flex items-center justify-between">
            <span className="text-gray-400">Materials</span>
            <span className="text-white font-medium">
              {formatCurrency(data?.cogs?.materials)}
            </span>
          </div>
          <div className="flex items-center justify-between">
            <span className="text-gray-400">Labor</span>
            <span className="text-white font-medium">
              {formatCurrency(data?.cogs?.labor)}
            </span>
          </div>
          <div className="flex items-center justify-between">
            <span className="text-gray-400">Packaging</span>
            <span className="text-white font-medium">
              {formatCurrency(data?.cogs?.packaging)}
            </span>
          </div>
          <div className="border-t border-gray-700 pt-3 flex items-center justify-between">
            <span className="text-white font-semibold">Total COGS</span>
            <span className="text-red-400 font-bold">
              {formatCurrency(data?.cogs?.total)}
            </span>
          </div>
          {data?.shipping_expense > 0 && (
            <>
              <div className="border-t border-gray-700 pt-3 mt-3">
                <div className="text-xs text-gray-500 mb-2">
                  Operating Expenses (not in COGS)
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-gray-400">Shipping Expense</span>
                  <span className="text-gray-400 font-medium">
                    {formatCurrency(data?.shipping_expense)}
                  </span>
                </div>
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
