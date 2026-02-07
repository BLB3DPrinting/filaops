/**
 * PeriodsTab - Fiscal period management with close/reopen actions.
 */
/* eslint-disable react-hooks/exhaustive-deps */
import { useState, useEffect } from "react";
import { API_URL } from "../../config/api";
import { useToast } from "../Toast";
import { ErrorAlert, Skeleton, TableSkeleton, HelpIcon } from "./AccountingShared";

export default function PeriodsTab() {
  const [periods, setPeriods] = useState([]);
  const [currentPeriod, setCurrentPeriod] = useState(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState(null);
  const [actionLoading, setActionLoading] = useState(null);
  const [lastUpdated, setLastUpdated] = useState(null);
  const toast = useToast();

  useEffect(() => {
    fetchPeriods();
  }, []);

  const fetchPeriods = async () => {
    if (!loading) setRefreshing(true);
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(`${API_URL}/api/v1/accounting/periods`, {
        credentials: "include",
      });
      if (res.ok) {
        const data = await res.json();
        setPeriods(data.periods || []);
        setCurrentPeriod(data.current_period);
        setLastUpdated(new Date());
      } else {
        setError(`Failed to load periods: ${res.status}`);
      }
    } catch (err) {
      setError(`Network error: ${err.message}`);
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  };

  const formatLastUpdated = (date) => {
    if (!date) return "";
    return date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  };

  const closePeriod = async (periodId) => {
    if (!confirm("Are you sure you want to close this period? No further entries can be made.")) return;
    setActionLoading(periodId);
    try {
      const res = await fetch(`${API_URL}/api/v1/accounting/periods/${periodId}/close`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify({ confirm: true }),
      });
      if (res.ok) {
        const result = await res.json();
        toast.success(result.message || "Period closed successfully");
        fetchPeriods();
      } else {
        const data = await res.json();
        toast.error(data.detail || "Failed to close period");
      }
    } catch (err) {
      toast.error(`Error closing period: ${err.message}`);
    } finally {
      setActionLoading(null);
    }
  };

  const reopenPeriod = async (periodId) => {
    if (!confirm("Are you sure? This will allow modifications to historical data.")) return;
    setActionLoading(periodId);
    try {
      const res = await fetch(`${API_URL}/api/v1/accounting/periods/${periodId}/reopen`, {
        method: "POST",
        credentials: "include",
      });
      if (res.ok) {
        const result = await res.json();
        toast.warning(result.message || "Period reopened - historical data can now be modified");
        fetchPeriods();
      } else {
        const data = await res.json();
        toast.error(data.detail || "Failed to reopen period");
      }
    } catch (err) {
      toast.error(`Error reopening period: ${err.message}`);
    } finally {
      setActionLoading(null);
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
      <div className="space-y-4">
        {/* Skeleton for current period */}
        <div className="bg-blue-500/10 border border-blue-500/30 rounded-xl p-4">
          <div className="flex items-center gap-2">
            <Skeleton variant="circle" className="w-3 h-3" />
            <Skeleton className="h-4 w-32" />
            <Skeleton className="h-4 w-20" />
          </div>
        </div>
        {/* Skeleton for periods table */}
        <TableSkeleton rows={6} cols={7} />
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {error && <ErrorAlert message={error} onRetry={fetchPeriods} />}

      {/* Current Period Highlight */}
      {currentPeriod && (
        <div className="bg-blue-500/10 border border-blue-500/30 rounded-xl p-4">
          <div className="flex items-center gap-2">
            <div className="w-3 h-3 bg-blue-500 rounded-full animate-pulse"></div>
            <span className="text-blue-400 font-medium">Current Period:</span>
            <span className="text-white">{currentPeriod.year}-{String(currentPeriod.period).padStart(2, '0')}</span>
            <span className={`ml-2 px-2 py-0.5 rounded text-xs ${
              currentPeriod.status === "open"
                ? "bg-green-500/20 text-green-400"
                : "bg-gray-500/20 text-gray-400"
            }`}>
              {currentPeriod.status}
            </span>
          </div>
        </div>
      )}

      {/* Periods Table */}
      <div className="bg-gray-900 border border-gray-800 rounded-xl overflow-hidden">
        <div className="p-4 border-b border-gray-800 flex justify-between items-center">
          <div className="flex items-center gap-2">
            <h3 className="text-lg font-semibold text-white">Fiscal Periods</h3>
            <HelpIcon label="Manage accounting periods. Closing a period prevents entries from being backdated. Reopen with caution - allows modifications to historical data." />
          </div>
          <div className="flex items-center gap-3">
            {lastUpdated && (
              <span className="text-xs text-gray-500">
                Updated {formatLastUpdated(lastUpdated)}
              </span>
            )}
            <button
              onClick={fetchPeriods}
              disabled={refreshing}
              className="p-2 rounded-lg text-gray-400 hover:text-white hover:bg-gray-800 disabled:opacity-50 disabled:cursor-not-allowed"
              title="Refresh data"
            >
              <svg
                className={`w-4 h-4 ${refreshing ? "animate-spin" : ""}`}
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"
                />
              </svg>
            </button>
          </div>
        </div>
        <table className="w-full">
          <thead className="bg-gray-800/50">
            <tr>
              <th className="text-left py-3 px-4 text-xs font-medium text-gray-400 uppercase">Period</th>
              <th className="text-left py-3 px-4 text-xs font-medium text-gray-400 uppercase">Date Range</th>
              <th className="text-center py-3 px-4 text-xs font-medium text-gray-400 uppercase">Status</th>
              <th className="text-right py-3 px-4 text-xs font-medium text-gray-400 uppercase">Entries</th>
              <th className="text-right py-3 px-4 text-xs font-medium text-gray-400 uppercase">Total DR</th>
              <th className="text-right py-3 px-4 text-xs font-medium text-gray-400 uppercase">Total CR</th>
              <th className="text-center py-3 px-4 text-xs font-medium text-gray-400 uppercase">Actions</th>
            </tr>
          </thead>
          <tbody>
            {periods.length === 0 ? (
              <tr>
                <td colSpan={7} className="py-8 text-center text-gray-500">
                  No fiscal periods found
                </td>
              </tr>
            ) : (
              periods.map((period) => (
                <tr key={period.id} className="border-t border-gray-800">
                  <td className="py-3 px-4 text-white font-medium">
                    {period.year}-{String(period.period).padStart(2, '0')}
                  </td>
                  <td className="py-3 px-4 text-gray-400 text-sm">
                    {period.start_date} to {period.end_date}
                  </td>
                  <td className="py-3 px-4 text-center">
                    <span className={`px-2 py-1 rounded-full text-xs ${
                      period.status === "open"
                        ? "bg-green-500/20 text-green-400"
                        : "bg-gray-500/20 text-gray-400"
                    }`}>
                      {period.status}
                    </span>
                  </td>
                  <td className="py-3 px-4 text-right text-gray-400">{period.journal_entry_count}</td>
                  <td className="py-3 px-4 text-right text-white">{formatCurrency(period.total_debits)}</td>
                  <td className="py-3 px-4 text-right text-white">{formatCurrency(period.total_credits)}</td>
                  <td className="py-3 px-4 text-center">
                    {period.status === "open" ? (
                      <button
                        onClick={() => closePeriod(period.id)}
                        disabled={actionLoading === period.id}
                        className="px-3 py-1 bg-yellow-600 hover:bg-yellow-700 text-white rounded text-sm disabled:opacity-50"
                      >
                        {actionLoading === period.id ? "..." : "Close"}
                      </button>
                    ) : (
                      <button
                        onClick={() => reopenPeriod(period.id)}
                        disabled={actionLoading === period.id}
                        className="px-3 py-1 bg-gray-600 hover:bg-gray-700 text-white rounded text-sm disabled:opacity-50"
                      >
                        {actionLoading === period.id ? "..." : "Reopen"}
                      </button>
                    )}
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
