/**
 * TaxCenterTab - Tax summary with period selector, export, rate breakdown, and monthly table.
 */
/* eslint-disable react-hooks/exhaustive-deps */
import { useState, useEffect } from "react";
import { API_URL } from "../../config/api";

export default function TaxCenterTab() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [exportError, setExportError] = useState(null);
  const [period, setPeriod] = useState("quarter");

  useEffect(() => {
    fetchTaxSummary();
  }, [period]);

  const fetchTaxSummary = async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(
        `${API_URL}/api/v1/admin/accounting/tax-summary?period=${period}`,
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
      console.error("Error fetching tax summary:", err);
      setError(`Network error: ${err.message}`);
    } finally {
      setLoading(false);
    }
  };

  const handleExport = async () => {
    setExportError(null); // Clear previous errors
    try {
      const res = await fetch(
        `${API_URL}/api/v1/admin/accounting/tax-summary/export?period=${period}`,
        {
          credentials: "include",
        }
      );

      if (!res.ok) {
        setExportError(`Export failed: ${res.statusText}`);
        console.error("Export failed:", res.statusText);
        return;
      }

      // Convert response to Blob and trigger download
      const blob = await res.blob();
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `tax-summary-${period}.csv`;
      document.body.appendChild(a);
      a.click();
      window.URL.revokeObjectURL(url);
      document.body.removeChild(a);
    } catch (err) {
      setExportError(`Export error: ${err.message}`);
      console.error("Export error:", err);
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
          onClick={fetchTaxSummary}
          className="px-3 py-1 bg-red-600/20 text-red-400 rounded hover:bg-red-600/30 text-sm"
        >
          Retry
        </button>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {/* Period Selector & Export */}
      <div className="flex flex-wrap items-center gap-4 bg-gray-900 border border-gray-800 rounded-xl p-4">
        <div>
          <label className="block text-xs text-gray-400 mb-1">Period</label>
          <select
            value={period}
            onChange={(e) => setPeriod(e.target.value)}
            className="bg-gray-800 border border-gray-700 text-white rounded px-3 py-1.5 text-sm"
          >
            <option value="month">This Month</option>
            <option value="quarter">This Quarter</option>
            <option value="year">This Year</option>
          </select>
        </div>
        <div className="flex-1"></div>
        <button
          onClick={handleExport}
          className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 text-sm"
        >
          Export for Filing
        </button>
      </div>

      {/* Export Error Message */}
      {exportError && (
        <div className="bg-red-900/30 border border-red-700 rounded-lg p-3 text-red-400 text-sm flex items-center gap-2">
          <span>⚠️</span>
          <span>{exportError}</span>
          <button
            onClick={() => setExportError(null)}
            className="ml-auto text-red-400 hover:text-red-300"
          >
            ✕
          </button>
        </div>
      )}

      {/* Pending Tax Hint */}
      {data?.pending?.order_count > 0 && data?.summary?.order_count === 0 && (
        <div className="bg-blue-500/10 border border-blue-500/30 rounded-xl p-4 flex items-start gap-3">
          <svg className="w-5 h-5 text-blue-400 mt-0.5 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
          </svg>
          <div>
            <p className="text-blue-400 font-medium text-sm">Tax is recognized when orders ship</p>
            <p className="text-gray-400 text-xs mt-1">
              You have {data.pending.order_count} pending order{data.pending.order_count > 1 ? "s" : ""} with{" "}
              {formatCurrency(data.pending.tax_amount)} in tax.
              This will appear here when those orders are shipped (accrual accounting per GAAP).
            </p>
          </div>
        </div>
      )}

      {/* Period Header */}
      <div className="bg-blue-500/10 border border-blue-500/30 rounded-xl p-4">
        <h3 className="text-lg font-semibold text-blue-400">{data?.period}</h3>
        <p className="text-sm text-gray-400 mt-1">
          {data?.period_start
            ? new Date(data.period_start).toLocaleDateString()
            : ""}{" "}
          -{" "}
          {data?.period_end
            ? new Date(data.period_end).toLocaleDateString()
            : ""}
        </p>
      </div>

      {/* Summary Cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        <div className="bg-gray-900 border border-gray-800 rounded-xl p-5">
          <div className="text-gray-400 text-sm mb-1">Total Sales</div>
          <div className="text-2xl font-bold text-white">
            {formatCurrency(data?.summary?.total_sales)}
          </div>
          <div className="text-xs text-gray-500 mt-1">
            {data?.summary?.order_count || 0} orders
          </div>
        </div>
        <div className="bg-gray-900 border border-gray-800 rounded-xl p-5">
          <div className="text-gray-400 text-sm mb-1">Taxable Sales</div>
          <div className="text-2xl font-bold text-white">
            {formatCurrency(data?.summary?.taxable_sales)}
          </div>
        </div>
        <div className="bg-gray-900 border border-gray-800 rounded-xl p-5">
          <div className="text-gray-400 text-sm mb-1">Non-Taxable Sales</div>
          <div className="text-2xl font-bold text-gray-400">
            {formatCurrency(data?.summary?.non_taxable_sales)}
          </div>
        </div>
        <div className="bg-gray-900 border border-blue-500/50 rounded-xl p-5">
          <div className="text-blue-400 text-sm mb-1">Tax Collected</div>
          <div className="text-2xl font-bold text-blue-400">
            {formatCurrency(data?.summary?.tax_collected)}
          </div>
          <div className="text-xs text-gray-500 mt-1">Amount to remit</div>
        </div>
        {data?.pending?.order_count > 0 && (
          <div className="bg-gray-900 border border-yellow-500/50 rounded-xl p-5">
            <div className="text-yellow-400 text-sm mb-1">Pending Tax</div>
            <div className="text-2xl font-bold text-yellow-400">
              {formatCurrency(data.pending.tax_amount)}
            </div>
            <div className="text-xs text-gray-500 mt-1">
              {data.pending.order_count} unshipped order{data.pending.order_count > 1 ? "s" : ""}
            </div>
          </div>
        )}
      </div>

      {/* Tax by Rate */}
      {data?.by_rate?.length > 0 && (
        <div className="bg-gray-900 border border-gray-800 rounded-xl p-5">
          <h3 className="text-lg font-semibold text-white mb-4">By Tax Rate</h3>
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead className="bg-gray-800/50">
                <tr>
                  <th className="text-left py-2 px-4 text-xs font-medium text-gray-400 uppercase">
                    Rate
                  </th>
                  <th className="text-right py-2 px-4 text-xs font-medium text-gray-400 uppercase">
                    Taxable Sales
                  </th>
                  <th className="text-right py-2 px-4 text-xs font-medium text-gray-400 uppercase">
                    Tax Collected
                  </th>
                  <th className="text-right py-2 px-4 text-xs font-medium text-gray-400 uppercase">
                    Orders
                  </th>
                </tr>
              </thead>
              <tbody>
                {data.by_rate.map((rate, idx) => (
                  <tr key={idx} className="border-t border-gray-800">
                    <td className="py-2 px-4 text-white">
                      {rate.rate_pct.toFixed(2)}%
                    </td>
                    <td className="py-2 px-4 text-right text-white">
                      {formatCurrency(rate.taxable_sales)}
                    </td>
                    <td className="py-2 px-4 text-right text-blue-400 font-medium">
                      {formatCurrency(rate.tax_collected)}
                    </td>
                    <td className="py-2 px-4 text-right text-gray-400">
                      {rate.order_count}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Monthly Breakdown */}
      {data?.monthly_breakdown?.length > 0 && (
        <div className="bg-gray-900 border border-gray-800 rounded-xl p-5">
          <h3 className="text-lg font-semibold text-white mb-4">
            Monthly Breakdown
          </h3>
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead className="bg-gray-800/50">
                <tr>
                  <th className="text-left py-2 px-4 text-xs font-medium text-gray-400 uppercase">
                    Month
                  </th>
                  <th className="text-right py-2 px-4 text-xs font-medium text-gray-400 uppercase">
                    Taxable Sales
                  </th>
                  <th className="text-right py-2 px-4 text-xs font-medium text-gray-400 uppercase">
                    Tax Collected
                  </th>
                  <th className="text-right py-2 px-4 text-xs font-medium text-gray-400 uppercase">
                    Orders
                  </th>
                </tr>
              </thead>
              <tbody>
                {data.monthly_breakdown.map((month, idx) => (
                  <tr key={idx} className="border-t border-gray-800">
                    <td className="py-2 px-4 text-white">{month.month}</td>
                    <td className="py-2 px-4 text-right text-white">
                      {formatCurrency(month.taxable_sales)}
                    </td>
                    <td className="py-2 px-4 text-right text-blue-400 font-medium">
                      {formatCurrency(month.tax_collected)}
                    </td>
                    <td className="py-2 px-4 text-right text-gray-400">
                      {month.order_count}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}
