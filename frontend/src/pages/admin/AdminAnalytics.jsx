import React, { useState, useEffect, useCallback } from "react";
import { useApi } from "../../hooks/useApi";
import { useFeatureFlags } from "../../hooks/useFeatureFlags";

const AdminAnalytics = () => {
  const api = useApi();
  const { hasFeature } = useFeatureFlags();
  const hasAnalytics = hasFeature("reports_advanced");
  const [analytics, setAnalytics] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [days, setDays] = useState(30);

  const fetchAnalytics = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await api.get(
        `/api/v1/admin/analytics/dashboard?days=${days}`
      );
      setAnalytics(data);
    } catch (err) {
      console.error("Analytics fetch error:", err);
      setError(err.message || "Failed to connect to analytics service");
    } finally {
      setLoading(false);
    }
  }, [api, days]);

  useEffect(() => {
    // Don't call the (now gated) endpoint without the feature — the locked
    // panel renders below regardless of loading state, so the request would
    // only 402. Skipping the fetch leaves loading truthy, but !hasAnalytics
    // is checked first so the locked panel wins.
    if (!hasAnalytics) return;
    // eslint-disable-next-line react-hooks/set-state-in-effect -- Fetch-on-mount updates state after the async API response.
    fetchAnalytics();
  }, [hasAnalytics, fetchAnalytics]);

  // PRO gate — Advanced Analytics (reports_advanced) is a wholly-PRO page.
  // The /admin/analytics route is already wrapped in <ProGate> (redirects a
  // non-PRO direct-URL visit to the License page), but we also lock the page
  // itself on the feature so a PRO tier without reports_advanced sees the
  // upsell rather than a 402-driven error. Locked-state shape mirrors
  // AdminIntakeStudio.
  if (!hasAnalytics) {
    return (
      <div className="space-y-6">
        <div>
          <h1 className="text-2xl font-bold text-white">Advanced Analytics</h1>
          <p className="text-gray-400 mt-1">
            Revenue, customer, product, and profit insights for your business
          </p>
        </div>
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
            Advanced Analytics gives you revenue metrics with growth tracking,
            top-customer and top-product analysis, profit margin calculations,
            and customizable date ranges — all in one dashboard.
          </p>
          <a
            href="/pricing"
            className="inline-block bg-blue-600 hover:bg-blue-700 text-white px-6 py-2 rounded-lg transition-colors"
          >
            Upgrade to PRO
          </a>
        </div>
      </div>
    );
  }

  if (loading) {
    return <div className="p-6 text-white">Loading analytics...</div>;
  }

  if (error) {
    return (
      <div className="p-6">
        <div className="bg-red-900/30 border border-red-500/50 rounded-lg p-6">
          <h2 className="text-xl font-bold text-red-400 mb-2">
            Analytics Error
          </h2>
          <p className="text-gray-300 mb-2">{error}</p>
          <p className="text-gray-400 text-sm">
            Check browser console for details. If problem persists, verify the backend is running.
          </p>
          <button
            onClick={() => fetchAnalytics()}
            className="mt-4 bg-red-600 hover:bg-red-700 text-white px-4 py-2 rounded transition-colors"
          >
            Retry
          </button>
        </div>
      </div>
    );
  }

  if (!analytics) {
    return (
      <div className="p-6">
        <div className="bg-yellow-900/20 border border-yellow-500/30 rounded-lg p-6">
          <h2 className="text-xl font-bold text-yellow-400 mb-2">
            No Analytics Data Available
          </h2>
          <p className="text-gray-300">
            There's no data to display yet. Analytics will appear once you have
            completed orders in the system.
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="p-6 space-y-6">
      <div className="flex justify-between items-center">
        <h1 className="text-3xl font-bold text-white">Analytics Dashboard</h1>
        <select
          value={days}
          onChange={(e) => setDays(Number(e.target.value))}
          className="bg-gray-800 text-white px-4 py-2 rounded border border-gray-700"
        >
          <option value={7}>Last 7 days</option>
          <option value={30}>Last 30 days</option>
          <option value={90}>Last 90 days</option>
          <option value={365}>Last year</option>
        </select>
      </div>

      {/* Revenue Section */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        <div className="bg-gray-800 p-4 rounded">
          <div className="text-gray-400 text-sm">Total Revenue</div>
          <div className="text-2xl font-bold text-white">
            ${parseFloat(analytics.revenue.total_revenue).toFixed(2)}
          </div>
        </div>
        <div className="bg-gray-800 p-4 rounded">
          <div className="text-gray-400 text-sm">30-Day Revenue</div>
          <div className="text-2xl font-bold text-green-400">
            ${parseFloat(analytics.revenue.revenue_30_days).toFixed(2)}
          </div>
          {analytics.revenue.revenue_growth !== null && (
            <div
              className={`text-sm ${
                analytics.revenue.revenue_growth > 0
                  ? "text-green-400"
                  : "text-red-400"
              }`}
            >
              {analytics.revenue.revenue_growth > 0 ? "↑" : "↓"}{" "}
              {Math.abs(analytics.revenue.revenue_growth).toFixed(1)}%
            </div>
          )}
        </div>
        <div className="bg-gray-800 p-4 rounded">
          <div className="text-gray-400 text-sm">Avg Order Value</div>
          <div className="text-2xl font-bold text-white">
            ${parseFloat(analytics.revenue.average_order_value).toFixed(2)}
          </div>
        </div>
        <div className="bg-gray-800 p-4 rounded">
          <div className="text-gray-400 text-sm">Gross Margin</div>
          <div className="text-2xl font-bold text-blue-400">
            {analytics.profit.gross_margin.toFixed(1)}%
          </div>
        </div>
      </div>

      {/* Top Products */}
      <div className="bg-gray-800 p-6 rounded">
        <h2 className="text-xl font-bold text-white mb-4">
          Top Selling Products
        </h2>
        <div className="overflow-x-auto">
          <table className="w-full text-left">
            <thead>
              <tr className="border-b border-gray-700">
                <th className="pb-2 text-gray-400">SKU</th>
                <th className="pb-2 text-gray-400">Name</th>
                <th className="pb-2 text-gray-400">Qty Sold</th>
                <th className="pb-2 text-gray-400">Revenue</th>
              </tr>
            </thead>
            <tbody>
              {analytics.products.top_selling_products.map((product, idx) => (
                <tr key={idx} className="border-b border-gray-700">
                  <td className="py-2 text-white">{product.sku}</td>
                  <td className="py-2 text-white">{product.name}</td>
                  <td className="py-2 text-white">{product.quantity_sold}</td>
                  <td className="py-2 text-green-400">
                    ${product.revenue.toFixed(2)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* Top Customers */}
      <div className="bg-gray-800 p-6 rounded">
        <h2 className="text-xl font-bold text-white mb-4">Top Customers</h2>
        <div className="overflow-x-auto">
          <table className="w-full text-left">
            <thead>
              <tr className="border-b border-gray-700">
                <th className="pb-2 text-gray-400">Company</th>
                <th className="pb-2 text-gray-400">Revenue</th>
              </tr>
            </thead>
            <tbody>
              {analytics.customers.top_customers.map((customer, idx) => (
                <tr key={idx} className="border-b border-gray-700">
                  <td className="py-2 text-white">{customer.company_name}</td>
                  <td className="py-2 text-green-400">
                    ${customer.revenue.toFixed(2)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
};

export default AdminAnalytics;
