/**
 * ReservationReconciliationReport — HARD-5
 *
 * Collapsible admin section showing:
 *   1. Allocation drift table — stored allocated_quantity vs ledger-derived sum.
 *   2. Stranded allocations — production orders in a terminal state or deleted
 *      that still hold positive net reservations.
 *   3. Per-PO repair button with confirmation dialog.
 *
 * Mounted alongside ReconciliationReport in AdminInventoryTransactions.jsx.
 * Staff-gated at the API level; this component assumes auth is already checked.
 */
import { useState, useEffect } from "react";
import { useApi } from "../../hooks/useApi";

const API_BASE = "/api/v1/admin/inventory/reservations";

// ---------------------------------------------------------------------------
// Small utilities
// ---------------------------------------------------------------------------

function formatQty(val) {
  if (val == null) return "—";
  return Number(val).toLocaleString(undefined, { maximumFractionDigits: 4 });
}

function driftColor(drift) {
  if (drift === 0) return "text-gray-400";
  return drift > 0 ? "text-yellow-400" : "text-red-400";
}

function StatusBadge({ status }) {
  const map = {
    complete: "bg-green-500/20 text-green-400",
    completed: "bg-green-500/20 text-green-400",
    cancelled: "bg-gray-500/20 text-gray-400",
    closed: "bg-blue-500/20 text-blue-400",
    deleted: "bg-red-500/20 text-red-400",
  };
  const cls = map[status] || "bg-gray-700 text-gray-300";
  return (
    <span className={`px-2 py-0.5 rounded-full text-xs ${cls}`}>{status}</span>
  );
}

// ---------------------------------------------------------------------------
// Repair confirmation dialog
// ---------------------------------------------------------------------------

function RepairConfirmDialog({ item, onConfirm, onCancel, loading }) {
  const [reason, setReason] = useState(
    `Staff-initiated stranded allocation release — PO ${item.production_order_code}`
  );
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60">
      <div className="bg-gray-900 border border-red-500/40 rounded-xl p-6 max-w-md w-full mx-4 shadow-2xl">
        <h3 className="text-lg font-semibold text-white mb-2">
          Release stranded allocation?
        </h3>
        <p className="text-sm text-gray-300 mb-4">
          This will release{" "}
          <span className="font-semibold text-white">
            {formatQty(item.net_reserved)}
          </span>{" "}
          units of{" "}
          <span className="font-mono text-white">{item.sku}</span>{" "}
          reserved by production order{" "}
          <span className="font-mono text-white">{item.production_order_code}</span>{" "}
          (<StatusBadge status={item.status} />
          ). This action is irreversible.
        </p>
        <div className="mb-4">
          <label className="block text-xs text-gray-400 mb-1">Reason (recorded in audit trail)</label>
          <textarea
            className="w-full bg-gray-800 border border-gray-700 rounded px-3 py-2 text-sm text-white resize-none"
            rows={2}
            value={reason}
            onChange={(e) => setReason(e.target.value)}
          />
        </div>
        <div className="flex gap-3 justify-end">
          <button
            onClick={onCancel}
            disabled={loading}
            className="px-4 py-2 text-sm text-gray-300 bg-gray-700 rounded hover:bg-gray-600 disabled:opacity-50"
          >
            Cancel
          </button>
          <button
            onClick={() => onConfirm(reason)}
            disabled={loading || !reason.trim()}
            className="px-4 py-2 text-sm text-white bg-red-600 rounded hover:bg-red-700 disabled:opacity-50 font-semibold"
          >
            {loading ? "Releasing…" : "Release Allocation"}
          </button>
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Drift table sub-section
// ---------------------------------------------------------------------------

function DriftTable({ items, driftedOnly, onToggleDriftedOnly, onRefresh, loading }) {
  return (
    <div>
      {/* Controls */}
      <div className="flex items-center gap-4 px-6 py-3 bg-gray-900/60 border-b border-gray-800">
        <span className="text-sm font-medium text-gray-300">Allocation drift</span>
        <label className="flex items-center gap-2 text-sm text-gray-400 cursor-pointer select-none ml-2">
          <input
            type="checkbox"
            checked={driftedOnly}
            onChange={(e) => onToggleDriftedOnly(e.target.checked)}
            className="rounded border-gray-600 bg-gray-800 text-blue-500"
          />
          Drifted only
        </label>
        <button
          onClick={onRefresh}
          disabled={loading}
          className="ml-auto px-3 py-1.5 text-xs bg-gray-700 text-gray-200 rounded hover:bg-gray-600 disabled:opacity-50"
        >
          {loading ? "Loading…" : "Refresh"}
        </button>
      </div>

      <div className="overflow-x-auto">
        <table className="w-full">
          <thead className="bg-gray-800/50">
            <tr>
              <th className="text-left py-2 px-4 text-xs font-medium text-gray-400 uppercase">SKU</th>
              <th className="text-left py-2 px-4 text-xs font-medium text-gray-400 uppercase">Name</th>
              <th className="text-left py-2 px-4 text-xs font-medium text-gray-400 uppercase">Location</th>
              <th className="text-right py-2 px-4 text-xs font-medium text-gray-400 uppercase">On Hand</th>
              <th className="text-right py-2 px-4 text-xs font-medium text-gray-400 uppercase">Stored Alloc</th>
              <th className="text-right py-2 px-4 text-xs font-medium text-gray-400 uppercase">Ledger Alloc</th>
              <th className="text-right py-2 px-4 text-xs font-medium text-gray-400 uppercase">Drift</th>
              <th className="text-right py-2 px-4 text-xs font-medium text-gray-400 uppercase">Avail (stored)</th>
            </tr>
          </thead>
          <tbody>
            {!items || items.length === 0 ? (
              <tr>
                <td colSpan={8} className="py-8 text-center text-gray-500 text-sm">
                  {driftedOnly
                    ? "No allocation drift detected — all inventory rows balanced."
                    : "No inventory rows found."}
                </td>
              </tr>
            ) : (
              items.map((item) => (
                <tr
                  key={`${item.product_id}-${item.location_id}`}
                  className={`border-b border-gray-800 hover:bg-gray-800/30 ${
                    item.has_drift ? "bg-yellow-500/5" : ""
                  }`}
                >
                  <td className="py-2.5 px-4 font-mono text-sm text-white">{item.sku}</td>
                  <td className="py-2.5 px-4 text-gray-300 text-sm max-w-xs truncate">{item.name}</td>
                  <td className="py-2.5 px-4 text-gray-400 text-sm">{item.location_name || "—"}</td>
                  <td className="py-2.5 px-4 text-right text-white tabular-nums">{formatQty(item.on_hand)}</td>
                  <td className="py-2.5 px-4 text-right text-gray-300 tabular-nums">{formatQty(item.stored_allocated)}</td>
                  <td className="py-2.5 px-4 text-right text-blue-300 tabular-nums">{formatQty(item.ledger_allocated)}</td>
                  <td className={`py-2.5 px-4 text-right font-semibold tabular-nums ${driftColor(item.drift)}`}>
                    {item.drift > 0 ? "+" : ""}{formatQty(item.drift)}
                  </td>
                  <td className={`py-2.5 px-4 text-right tabular-nums ${item.stored_available < 0 ? "text-red-400 font-semibold" : "text-gray-300"}`}>
                    {formatQty(item.stored_available)}
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

// ---------------------------------------------------------------------------
// Stranded allocations sub-section
// ---------------------------------------------------------------------------

function StrandedTable({ items, onRepair }) {
  if (!items) return null;

  return (
    <div>
      <div className="px-6 py-3 bg-gray-900/60 border-b border-gray-800">
        <span className="text-sm font-medium text-gray-300">Stranded allocations</span>
        <span className="ml-2 text-xs text-gray-500">
          — production orders in a terminal state still holding reservations
        </span>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full">
          <thead className="bg-gray-800/50">
            <tr>
              <th className="text-left py-2 px-4 text-xs font-medium text-gray-400 uppercase">PO</th>
              <th className="text-left py-2 px-4 text-xs font-medium text-gray-400 uppercase">Status</th>
              <th className="text-left py-2 px-4 text-xs font-medium text-gray-400 uppercase">SKU</th>
              <th className="text-left py-2 px-4 text-xs font-medium text-gray-400 uppercase">Name</th>
              <th className="text-right py-2 px-4 text-xs font-medium text-gray-400 uppercase">Net Reserved</th>
              <th className="text-left py-2 px-4 text-xs font-medium text-gray-400 uppercase">Reason</th>
              <th className="py-2 px-4 text-xs font-medium text-gray-400 uppercase">Action</th>
            </tr>
          </thead>
          <tbody>
            {items.length === 0 ? (
              <tr>
                <td colSpan={7} className="py-8 text-center text-gray-500 text-sm">
                  No stranded allocations found — all reservations belong to live orders.
                </td>
              </tr>
            ) : (
              items.map((item) => (
                <tr
                  key={`${item.production_order_id}-${item.product_id}-${item.location_id}`}
                  className="border-b border-gray-800 hover:bg-gray-800/30 bg-red-500/5"
                >
                  <td className="py-2.5 px-4 font-mono text-sm text-white">
                    {item.production_order_code}
                  </td>
                  <td className="py-2.5 px-4">
                    <StatusBadge status={item.status} />
                  </td>
                  <td className="py-2.5 px-4 font-mono text-sm text-white">{item.sku}</td>
                  <td className="py-2.5 px-4 text-gray-300 text-sm max-w-xs truncate">{item.name}</td>
                  <td className="py-2.5 px-4 text-right text-red-400 font-semibold tabular-nums">
                    {formatQty(item.net_reserved)}
                  </td>
                  <td className="py-2.5 px-4 text-xs text-gray-500">
                    {item.stranded_reason === "order_missing" ? "Order deleted" : "Terminal status"}
                  </td>
                  <td className="py-2.5 px-4 text-center">
                    <button
                      onClick={() => onRepair(item)}
                      className="px-3 py-1 text-xs text-red-300 border border-red-500/40 rounded hover:bg-red-500/20 transition-colors"
                    >
                      Release
                    </button>
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

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

export default function ReservationReconciliationReport() {
  const api = useApi();
  const [report, setReport] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [expanded, setExpanded] = useState(false);
  const [driftedOnly, setDriftedOnly] = useState(false);
  const [repairTarget, setRepairTarget] = useState(null);
  const [repairing, setRepairing] = useState(false);
  const [repairError, setRepairError] = useState(null);
  const [repairSuccess, setRepairSuccess] = useState(null);

  const fetchReport = async () => {
    try {
      setLoading(true);
      setError(null);
      const params = driftedOnly ? "?drifted_only=true" : "";
      const data = await api.get(`${API_BASE}/reconciliation${params}`);
      setReport(data);
    } catch (err) {
      setError(err.message || "Failed to load reservation reconciliation report");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (expanded) {
      fetchReport();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [expanded, driftedOnly]);

  const handleRepairConfirm = async (reason) => {
    if (!repairTarget) return;
    try {
      setRepairing(true);
      setRepairError(null);
      const result = await api.post(
        `${API_BASE}/repair/${repairTarget.production_order_id}`,
        { confirm: true, reason }
      );
      if (result.errors && result.errors.length > 0) {
        setRepairError(result.errors.join("; "));
      } else {
        setRepairSuccess(
          `Released ${result.total_released_items} allocation(s) for ${repairTarget.production_order_code}.`
        );
        // Refresh the report to reflect the repair
        await fetchReport();
      }
    } catch (err) {
      setRepairError(err.message || "Repair failed");
    } finally {
      setRepairing(false);
      setRepairTarget(null);
    }
  };

  const strandedCount = report?.stranded_po_count ?? 0;
  const driftedCount = report?.drifted_rows ?? 0;

  return (
    <>
      {repairTarget && (
        <RepairConfirmDialog
          item={repairTarget}
          onConfirm={handleRepairConfirm}
          onCancel={() => setRepairTarget(null)}
          loading={repairing}
        />
      )}

      <div className="bg-gray-900 border border-gray-800 rounded-xl overflow-hidden">
        {/* Collapsible header */}
        <button
          className="w-full flex items-center justify-between px-6 py-4 text-left hover:bg-gray-800/40 transition-colors"
          onClick={() => setExpanded((v) => !v)}
        >
          <div>
            <div className="flex items-center gap-3">
              <h2 className="text-lg font-semibold text-white">
                Reservation Reconciliation — stranded allocations
              </h2>
              {strandedCount > 0 && (
                <span className="px-2 py-0.5 rounded-full text-xs bg-red-500/20 text-red-400 font-semibold">
                  {strandedCount} stranded
                </span>
              )}
            </div>
            <p className="text-gray-400 text-sm mt-0.5">
              Compares stored allocated_quantity against the reservation ledger.
              Identifies allocations held by terminal or deleted production orders that
              permanently understate availability.
            </p>
          </div>
          <svg
            className={`w-5 h-5 text-gray-400 flex-shrink-0 ml-4 transition-transform ${expanded ? "rotate-180" : ""}`}
            fill="none" viewBox="0 0 24 24" stroke="currentColor"
          >
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
          </svg>
        </button>

        {expanded && (
          <div className="border-t border-gray-800">
            {/* Summary badges */}
            {report && !loading && (
              <div className="flex flex-wrap gap-4 px-6 py-3 border-b border-gray-800 bg-gray-900/60">
                <div className="text-sm text-gray-400">
                  <span className="font-medium text-white">{report.total_inventory_rows}</span> inventory rows
                </div>
                <div className="text-sm text-gray-400">
                  <span className={`font-medium ${driftedCount > 0 ? "text-yellow-400" : "text-green-400"}`}>
                    {driftedCount}
                  </span> allocation drift
                </div>
                <div className="text-sm text-gray-400">
                  <span className={`font-medium ${strandedCount > 0 ? "text-red-400" : "text-green-400"}`}>
                    {strandedCount}
                  </span> stranded POs
                </div>
                {report.total_stranded_quantity > 0 && (
                  <div className="text-sm text-gray-400">
                    <span className="font-medium text-red-300">
                      {formatQty(report.total_stranded_quantity)}
                    </span> total stranded qty
                  </div>
                )}
              </div>
            )}

            {/* Repair success/error toasts */}
            {repairSuccess && (
              <div className="mx-6 my-3 bg-green-500/10 border border-green-500/30 rounded-lg p-3 text-green-400 text-sm flex justify-between">
                <span>{repairSuccess}</span>
                <button onClick={() => setRepairSuccess(null)} className="text-green-500 hover:text-green-300 ml-3">✕</button>
              </div>
            )}
            {repairError && (
              <div className="mx-6 my-3 bg-red-500/10 border border-red-500/30 rounded-lg p-3 text-red-400 text-sm flex justify-between">
                <span>{repairError}</span>
                <button onClick={() => setRepairError(null)} className="text-red-500 hover:text-red-300 ml-3">✕</button>
              </div>
            )}

            {/* Error */}
            {error && (
              <div className="mx-6 my-3 bg-red-500/10 border border-red-500/30 rounded-lg p-3 text-red-400 text-sm">
                {error}
              </div>
            )}

            {/* Loading spinner */}
            {loading && (
              <div className="flex items-center justify-center py-12">
                <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-500" />
              </div>
            )}

            {/* Drift table */}
            {!loading && report && (
              <DriftTable
                items={report.drift_items}
                driftedOnly={driftedOnly}
                onToggleDriftedOnly={setDriftedOnly}
                onRefresh={fetchReport}
                loading={loading}
              />
            )}

            {/* Divider */}
            {!loading && report && <div className="border-t border-gray-800 my-0" />}

            {/* Stranded table */}
            {!loading && report && (
              <StrandedTable
                items={report.stranded_items}
                onRepair={setRepairTarget}
              />
            )}
          </div>
        )}
      </div>
    </>
  );
}
