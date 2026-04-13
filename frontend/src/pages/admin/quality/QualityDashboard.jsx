import { useState, useEffect } from "react";
import { Link } from "react-router-dom";
import { useApi } from "../../../hooks/useApi";
import StatCard from "../../../components/StatCard";

/**
 * QualityDashboard — Overview of quality management metrics.
 *
 * Shows:
 * - Stat cards: first-pass yield, pending inspections, scrap rate, total inspections
 * - Inspection queue (orders awaiting QC)
 * - Recent inspections with pass/fail badges
 * - Scrap summary by reason
 */
export default function QualityDashboard() {
  const api = useApi();
  const [metrics, setMetrics] = useState(null);
  const [queue, setQueue] = useState({ items: [], total: 0 });
  const [recentInspections, setRecentInspections] = useState([]);
  const [scrapSummary, setScrapSummary] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    fetchAll();
  }, []);

  const fetchAll = async () => {
    try {
      setLoading(true);
      setError(null);

      const results = await Promise.allSettled([
          api.get("/api/v1/quality/metrics?days=30"),
          api.get("/api/v1/quality/inspection-queue?limit=10"),
          api.get("/api/v1/quality/recent-inspections?limit=10"),
          api.get("/api/v1/quality/scrap-summary?days=30"),
        ]);

      const [metricsRes, queueRes, recentRes, scrapRes] = results;

      if (metricsRes.status === "fulfilled") setMetrics(metricsRes.value);
      if (queueRes.status === "fulfilled") setQueue(queueRes.value);
      if (recentRes.status === "fulfilled")
        setRecentInspections(recentRes.value);
      if (scrapRes.status === "fulfilled") setScrapSummary(scrapRes.value);

      const rejected = results.filter((r) => r.status === "rejected");
      if (rejected.length === results.length) {
        setError("Failed to load quality data");
      } else if (rejected.length > 0) {
        setError(
          "Some quality data could not be loaded. Displayed information may be incomplete."
        );
      }
    } catch (err) {
      setError("Failed to load quality data");
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  const qcBadge = (status) => {
    const styles = {
      passed: "bg-green-500/20 text-green-400 border border-green-500/30",
      failed: "bg-red-500/20 text-red-400 border border-red-500/30",
      waived: "bg-amber-500/20 text-amber-400 border border-amber-500/30",
      pending: "bg-blue-500/20 text-blue-400 border border-blue-500/30",
      in_progress: "bg-cyan-500/20 text-cyan-400 border border-cyan-500/30",
    };
    return (
      <span
        className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium ${styles[status] || "bg-gray-500/20 text-gray-400"}`}
      >
        {status?.replace("_", " ")}
      </span>
    );
  };

  if (loading) {
    return (
      <div className="p-6 space-y-6">
        <h1 className="text-2xl font-bold text-[var(--text-primary)]">
          Quality Dashboard
        </h1>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
          {[...Array(4)].map((_, i) => (
            <div
              key={i}
              className="h-24 animate-pulse bg-[var(--bg-card)] rounded-lg border border-[var(--border-subtle)]"
            />
          ))}
        </div>
      </div>
    );
  }

  if (error && !metrics && queue.items.length === 0) {
    return (
      <div className="p-6">
        <div className="bg-red-500/10 border border-red-500/30 rounded-lg p-4 text-red-400">
          {error}
        </div>
      </div>
    );
  }

  return (
    <div className="p-6 space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold text-[var(--text-primary)]">
          Quality Dashboard
        </h1>
        <span className="text-sm text-[var(--text-muted)]">Last 30 days</span>
      </div>

      {/* Partial error banner */}
      {error && (
        <div className="bg-amber-500/10 border border-amber-500/30 rounded-lg p-3 text-amber-400 text-sm">
          {error}
        </div>
      )}

      {/* Stat Cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard
          variant="gradient"
          title="First-Pass Yield"
          value={
            metrics?.first_pass_yield != null
              ? `${metrics.first_pass_yield}%`
              : "—"
          }
          color={
            metrics?.first_pass_yield == null
              ? "neutral"
              : metrics.first_pass_yield >= 90
                ? "success"
                : metrics.first_pass_yield >= 75
                  ? "warning"
                  : "danger"
          }
        />
        <StatCard
          variant="gradient"
          title="Pending Inspections"
          value={metrics?.pending_inspections ?? 0}
          color={metrics?.pending_inspections > 5 ? "warning" : "primary"}
        />
        <StatCard
          variant="gradient"
          title="Scrap Rate"
          value={metrics?.scrap_rate != null ? `${metrics.scrap_rate}%` : "—"}
          color={
            metrics?.scrap_rate == null
              ? "neutral"
              : metrics.scrap_rate > 5
                ? "danger"
                : "success"
          }
        />
        <StatCard
          variant="gradient"
          title="Total Inspections"
          value={metrics?.total_inspections ?? 0}
          color="neutral"
        />
      </div>

      {/* Two-Column Layout: Inspection Queue + Recent Inspections */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Inspection Queue */}
        <div className="bg-[var(--bg-card)] rounded-lg border border-[var(--border-subtle)] overflow-hidden">
          <div className="px-4 py-3 border-b border-[var(--border-subtle)] flex items-center justify-between">
            <h2 className="text-sm font-semibold text-[var(--text-primary)] uppercase tracking-wider">
              Inspection Queue
            </h2>
            <span className="text-xs text-[var(--text-muted)]">
              {queue.total} pending
            </span>
          </div>
          {queue.items.length === 0 ? (
            <div className="p-8 text-center text-[var(--text-muted)] text-sm">
              No orders awaiting inspection
            </div>
          ) : (
            <div className="divide-y divide-[var(--border-subtle)]">
              {queue.items.map((item) => (
                <Link
                  key={item.id}
                  to={`/admin/production/${item.id}`}
                  className="flex items-center justify-between px-4 py-3 hover:bg-[var(--bg-secondary)] transition-colors"
                >
                  <div className="min-w-0 flex-1">
                    <div className="text-sm font-medium text-[var(--text-primary)] truncate">
                      {item.code}
                    </div>
                    <div className="text-xs text-[var(--text-muted)] truncate">
                      {item.product_name || "Unknown product"}
                    </div>
                  </div>
                  <div className="flex items-center gap-3 ml-4">
                    <span className="text-xs text-[var(--text-secondary)]">
                      {item.quantity_completed}/{item.quantity_ordered}
                    </span>
                    {qcBadge(item.qc_status)}
                  </div>
                </Link>
              ))}
            </div>
          )}
        </div>

        {/* Recent Inspections */}
        <div className="bg-[var(--bg-card)] rounded-lg border border-[var(--border-subtle)] overflow-hidden">
          <div className="px-4 py-3 border-b border-[var(--border-subtle)]">
            <h2 className="text-sm font-semibold text-[var(--text-primary)] uppercase tracking-wider">
              Recent Inspections
            </h2>
          </div>
          {recentInspections.length === 0 ? (
            <div className="p-8 text-center text-[var(--text-muted)] text-sm">
              No inspections recorded yet
            </div>
          ) : (
            <div className="divide-y divide-[var(--border-subtle)]">
              {recentInspections.map((item) => (
                <div
                  key={item.id}
                  className="flex items-center justify-between px-4 py-3"
                >
                  <div className="min-w-0 flex-1">
                    <div className="text-sm font-medium text-[var(--text-primary)] truncate">
                      {item.code}
                    </div>
                    <div className="text-xs text-[var(--text-muted)] truncate">
                      {item.product_name || "Unknown"} — by{" "}
                      {item.qc_inspected_by || "—"}
                    </div>
                  </div>
                  <div className="flex items-center gap-3 ml-4">
                    {qcBadge(item.qc_status)}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Scrap Summary */}
      {scrapSummary.length > 0 && (
        <div className="bg-[var(--bg-card)] rounded-lg border border-[var(--border-subtle)] overflow-hidden">
          <div className="px-4 py-3 border-b border-[var(--border-subtle)]">
            <h2 className="text-sm font-semibold text-[var(--text-primary)] uppercase tracking-wider">
              Scrap by Reason (30 days)
            </h2>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-[var(--border-subtle)]">
                  <th className="text-left px-4 py-2 text-[var(--text-muted)] font-medium">
                    Reason
                  </th>
                  <th className="text-right px-4 py-2 text-[var(--text-muted)] font-medium">
                    Count
                  </th>
                  <th className="text-right px-4 py-2 text-[var(--text-muted)] font-medium">
                    Qty
                  </th>
                  <th className="text-right px-4 py-2 text-[var(--text-muted)] font-medium">
                    Cost
                  </th>
                </tr>
              </thead>
              <tbody className="divide-y divide-[var(--border-subtle)]">
                {scrapSummary.map((row) => (
                  <tr key={row.reason_code}>
                    <td className="px-4 py-2 text-[var(--text-primary)]">
                      <span className="font-medium">{row.reason_name}</span>
                      <span className="ml-2 text-xs text-[var(--text-muted)]">
                        {row.reason_code}
                      </span>
                    </td>
                    <td className="text-right px-4 py-2 text-[var(--text-secondary)]">
                      {row.count}
                    </td>
                    <td className="text-right px-4 py-2 text-[var(--text-secondary)]">
                      {row.total_quantity}
                    </td>
                    <td className="text-right px-4 py-2 text-red-400 font-medium">
                      ${row.total_cost.toFixed(2)}
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
