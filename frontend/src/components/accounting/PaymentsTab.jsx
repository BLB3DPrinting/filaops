/**
 * PaymentsTab - Payments journal with date filtering, export, method breakdown, and entries table.
 */
/* eslint-disable react-hooks/exhaustive-deps */
import { useState, useEffect } from "react";
import { API_URL } from "../../config/api";

export default function PaymentsTab() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [fetchError, setFetchError] = useState(null);
  const [exportError, setExportError] = useState(null);
  const [startDate, setStartDate] = useState(() => {
    const d = new Date();
    d.setDate(d.getDate() - 30);
    return d.toISOString().split("T")[0];
  });
  const [endDate, setEndDate] = useState(() => {
    return new Date().toISOString().split("T")[0];
  });

  const fetchPayments = async () => {
    setLoading(true);
    setFetchError(null);
    try {
      const params = new URLSearchParams({
        start_date: new Date(startDate).toISOString(),
        end_date: new Date(endDate).toISOString(),
      });
      const res = await fetch(
        `${API_URL}/api/v1/admin/accounting/payments-journal?${params}`,
        {
          credentials: "include",
        }
      );
      if (res.ok) {
        setData(await res.json());
      } else {
        setFetchError(`Failed to load: ${res.status} ${res.statusText}`);
      }
    } catch (err) {
      console.error("Error fetching payments:", err);
      setFetchError(`Network error: ${err.message}`);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchPayments();
  }, [startDate, endDate]);

  const handleExport = async () => {
    setExportError(null); // Clear previous errors
    try {
      const params = new URLSearchParams({
        start_date: new Date(startDate).toISOString(),
        end_date: new Date(endDate).toISOString(),
      });

      const res = await fetch(
        `${API_URL}/api/v1/admin/accounting/payments-journal/export?${params}`,
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
      a.download = `payments-journal-${startDate}-to-${endDate}.csv`;
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

  return (
    <div className="space-y-4">
      {/* Filters & Export */}
      <div className="flex flex-wrap items-center gap-4 bg-gray-900 border border-gray-800 rounded-xl p-4">
        <div>
          <label className="block text-xs text-gray-400 mb-1">Start Date</label>
          <input
            type="date"
            value={startDate}
            onChange={(e) => setStartDate(e.target.value)}
            min="2000-01-01"
            max="2099-12-31"
            className="bg-gray-800 border border-gray-700 text-white rounded px-3 py-1.5 text-sm"
          />
        </div>
        <div>
          <label className="block text-xs text-gray-400 mb-1">End Date</label>
          <input
            type="date"
            value={endDate}
            onChange={(e) => setEndDate(e.target.value)}
            min="2000-01-01"
            max="2099-12-31"
            className="bg-gray-800 border border-gray-700 text-white rounded px-3 py-1.5 text-sm"
          />
        </div>
        <div className="flex-1"></div>
        <button
          onClick={handleExport}
          className="px-4 py-2 bg-gray-700 text-white rounded-lg hover:bg-gray-600 text-sm"
        >
          Export CSV
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

      {/* Fetch Error Message */}
      {fetchError && (
        <div className="bg-red-900/30 border border-red-700 rounded-xl p-4 flex items-center gap-3">
          <svg className="w-5 h-5 text-red-400 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
          </svg>
          <div className="flex-1">
            <p className="text-red-400 font-medium text-sm">{fetchError}</p>
            <p className="text-gray-500 text-xs mt-1">Check that the backend server is running.</p>
          </div>
          <button
            onClick={fetchPayments}
            className="px-3 py-1 bg-red-600/20 text-red-400 rounded hover:bg-red-600/30 text-sm"
          >
            Retry
          </button>
        </div>
      )}

      {/* Summary Cards */}
      {data?.totals && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <div className="bg-gray-800/50 rounded-lg p-3">
            <div className="text-xs text-gray-400">Payments</div>
            <div className="text-lg font-semibold text-green-400">
              {formatCurrency(data.totals.payments)}
            </div>
          </div>
          <div className="bg-gray-800/50 rounded-lg p-3">
            <div className="text-xs text-gray-400">Refunds</div>
            <div className="text-lg font-semibold text-red-400">
              {formatCurrency(data.totals.refunds)}
            </div>
          </div>
          <div className="bg-gray-800/50 rounded-lg p-3">
            <div className="text-xs text-gray-400">Net</div>
            <div className="text-lg font-semibold text-white">
              {formatCurrency(data.totals.net)}
            </div>
          </div>
          <div className="bg-gray-800/50 rounded-lg p-3">
            <div className="text-xs text-gray-400">Transactions</div>
            <div className="text-lg font-semibold text-white">
              {data.totals.count}
            </div>
          </div>
        </div>
      )}

      {/* By Method */}
      {data?.by_method && Object.keys(data.by_method).length > 0 && (
        <div className="bg-gray-900 border border-gray-800 rounded-xl p-4">
          <h3 className="text-sm font-medium text-gray-400 mb-3">
            By Payment Method
          </h3>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            {Object.entries(data.by_method).map(([method, amount]) => (
              <div key={method} className="bg-gray-800/50 rounded-lg p-3">
                <div className="text-xs text-gray-400 capitalize">{method}</div>
                <div className="text-lg font-semibold text-white">
                  {formatCurrency(amount)}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Payments Table */}
      <div className="bg-gray-900 border border-gray-800 rounded-xl overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full">
            <thead className="bg-gray-800/50">
              <tr>
                <th className="text-left py-3 px-4 text-xs font-medium text-gray-400 uppercase">
                  Date
                </th>
                <th className="text-left py-3 px-4 text-xs font-medium text-gray-400 uppercase">
                  Payment #
                </th>
                <th className="text-left py-3 px-4 text-xs font-medium text-gray-400 uppercase">
                  Order
                </th>
                <th className="text-left py-3 px-4 text-xs font-medium text-gray-400 uppercase">
                  Method
                </th>
                <th className="text-right py-3 px-4 text-xs font-medium text-gray-400 uppercase">
                  Amount
                </th>
                <th className="text-center py-3 px-4 text-xs font-medium text-gray-400 uppercase">
                  Type
                </th>
              </tr>
            </thead>
            <tbody>
              {loading ? (
                <tr>
                  <td colSpan={6} className="py-8 text-center text-gray-500">
                    Loading...
                  </td>
                </tr>
              ) : data?.entries?.length > 0 ? (
                data.entries.map((entry, idx) => (
                  <tr
                    key={idx}
                    className="border-t border-gray-800 hover:bg-gray-800/50"
                  >
                    <td className="py-3 px-4 text-gray-400 text-sm">
                      {entry.date
                        ? new Date(entry.date).toLocaleDateString()
                        : "-"}
                    </td>
                    <td className="py-3 px-4 text-white font-medium">
                      {entry.payment_number}
                    </td>
                    <td className="py-3 px-4 text-gray-400 text-sm">
                      {entry.order_number || "-"}
                    </td>
                    <td className="py-3 px-4 text-gray-400 text-sm capitalize">
                      {entry.payment_method}
                    </td>
                    <td
                      className={`py-3 px-4 text-right font-medium ${
                        entry.amount >= 0 ? "text-green-400" : "text-red-400"
                      }`}
                    >
                      {formatCurrency(entry.amount)}
                    </td>
                    <td className="py-3 px-4 text-center">
                      <span
                        className={`px-2 py-1 rounded-full text-xs ${
                          entry.payment_type === "payment"
                            ? "bg-green-500/20 text-green-400"
                            : "bg-red-500/20 text-red-400"
                        }`}
                      >
                        {entry.payment_type}
                      </span>
                    </td>
                  </tr>
                ))
              ) : (
                <tr>
                  <td colSpan={6} className="py-12 text-center">
                    <div className="text-gray-500 mb-2">No payments recorded in this period</div>
                    <p className="text-gray-600 text-xs max-w-md mx-auto">
                      Payments are recorded via the "Record Payment" button on order detail pages.
                      Go to Orders → select an order → click "Record Payment".
                    </p>
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
