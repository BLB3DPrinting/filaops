import React, { useState, useEffect } from "react";
import { API_URL } from "../../config/api";

const AdminAnalytics = () => {
  const [analytics, setAnalytics] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [days, setDays] = useState(30);

  useEffect(() => {
    fetchAnalytics();
  }, [days]);

  const fetchAnalytics = async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await fetch(
        `${API_URL}/api/v1/admin/analytics/dashboard?days=${days}`,
        {
          credentials: "include",
        }
      );

      if (response.status === 402) {
        // Tier required - user will see the Pro announcement
        setLoading(false);
        return;
      }

      if (response.ok) {
        const data = await response.json();
        setAnalytics(data);
      } else {
        const errorText = await response.text();
        console.error("Analytics fetch failed:", response.status, errorText);
        setError(`Failed to load analytics (${response.status})`);
      }
    } catch (err) {
      console.error("Analytics fetch error:", err);
      setError(err.message || "Failed to connect to analytics service");
    } finally {
      setLoading(false);
    }
  };

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

  if (error?.includes("402") || error?.includes("tier")) {
    return (
      <div className="p-6 space-y-6">
        <div className="bg-gradient-to-r from-blue-600/20 to-purple-600/20 border border-blue-500/30 rounded-lg p-8 text-center">
          <h1 className="text-3xl font-bold text-white mb-2">
            Advanced Analytics
          </h1>
          <p className="text-gray-300 mb-6">
            Get comprehensive insights into your business with revenue,
            customer, product, and profit analytics.
          </p>
          <div className="bg-gray-800/50 rounded-lg p-6 mb-6">
            <h2 className="text-xl font-semibold text-white mb-4">
              Available in FilaOps Pro
            </h2>
            <ul className="text-left text-gray-300 space-y-2 max-w-md mx-auto">
              <li className="flex items-start">
                <span className="text-green-400 mr-2">+</span>
                <span>Revenue metrics with growth tracking</span>
              </li>
              <li className="flex items-start">
                <span className="text-green-400 mr-2">+</span>
                <span>Top customers and products analysis</span>
              </li>
              <li className="flex items-start">
                <span className="text-green-400 mr-2">+</span>
                <span>Profit margin calculations</span>
              </li>
              <li className="flex items-start">
                <span className="text-green-400 mr-2">+</span>
                <span>Customizable date ranges</span>
              </li>
            </ul>
          </div>
          <p className="text-sm text-gray-400">
            Learn more at{" "}
            <a href="/pricing" className="text-blue-400 hover:text-blue-300 underline">
              filaops.com/pricing
            </a>
          </p>
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
