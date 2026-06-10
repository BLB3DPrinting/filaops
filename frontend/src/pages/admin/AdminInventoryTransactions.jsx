import { useState, useEffect } from "react";
import { Link } from "react-router-dom";
import { useApi } from "../../hooks/useApi";
import { useFormatCurrency } from "../../hooks/useFormatCurrency";

// ---------------------------------------------------------------------------
// CountModal — inline count-entry form for a single reconciliation row
// ---------------------------------------------------------------------------

function CountModal({ item, onClose, onSuccess }) {
  const api = useApi();
  const [countedQty, setCountedQty] = useState(
    item.stored_on_hand != null ? String(item.stored_on_hand) : ""
  );
  const [notes, setNotes] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState(null);

  const handleSubmit = async (e) => {
    e.preventDefault();
    const qty = parseFloat(countedQty);
    if (isNaN(qty) || qty < 0) {
      setError("Counted quantity must be a number >= 0");
      return;
    }
    try {
      setSubmitting(true);
      setError(null);
      await api.post("/api/v1/admin/inventory/reconciliation/count", {
        product_id: item.product_id,
        location_id: item.location_id,
        counted_qty: qty,
        notes: notes || null,
      });
      onSuccess();
    } catch (err) {
      setError(err.message || "Failed to post count");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60">
      <div className="bg-gray-900 border border-gray-700 rounded-xl shadow-2xl w-full max-w-md mx-4">
        <div className="flex items-center justify-between px-5 py-4 border-b border-gray-800">
          <div>
            <h3 className="text-white font-semibold">Record physical count</h3>
            <p className="text-gray-400 text-xs mt-0.5">
              {item.sku} — {item.name}
              {item.location_name ? ` @ ${item.location_name}` : ""}
            </p>
          </div>
          <button
            onClick={onClose}
            className="text-gray-500 hover:text-gray-300 text-xl leading-none"
            aria-label="Close"
          >
            &times;
          </button>
        </div>
        <form onSubmit={handleSubmit} className="px-5 py-4 space-y-4">
          <div className="flex gap-4 text-sm bg-gray-800/60 rounded-lg px-3 py-2">
            <span className="text-gray-400">Stored:</span>
            <span className="text-white tabular-nums">
              {item.stored_on_hand != null
                ? Number(item.stored_on_hand).toLocaleString(undefined, { maximumFractionDigits: 4 })
                : "—"}
            </span>
            <span className="text-gray-500 ml-auto text-xs">
              (delta = counted − stored)
            </span>
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-300 mb-1">
              Counted quantity <span className="text-red-400">*</span>
            </label>
            <input
              type="number"
              step="0.0001"
              min="0"
              required
              value={countedQty}
              onChange={(e) => setCountedQty(e.target.value)}
              className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-white focus:outline-none focus:border-blue-500"
              autoFocus
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-300 mb-1">
              Notes (optional)
            </label>
            <input
              type="text"
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              placeholder="e.g. shelf count, bin A3"
              maxLength={500}
              className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-white focus:outline-none focus:border-blue-500"
            />
          </div>

          {error && (
            <div className="bg-red-500/10 border border-red-500/30 rounded-lg p-3 text-red-400 text-sm">
              {error}
            </div>
          )}

          <div className="flex gap-3 pt-1">
            <button
              type="submit"
              disabled={submitting}
              className="flex-1 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50 font-medium"
            >
              {submitting ? "Posting…" : "Post count"}
            </button>
            <button
              type="button"
              onClick={onClose}
              disabled={submitting}
              className="px-4 py-2 bg-gray-700 text-gray-200 rounded-lg hover:bg-gray-600 disabled:opacity-50"
            >
              Cancel
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// FallbackModal — "Baseline to stored" confirm dialog
// ---------------------------------------------------------------------------

function FallbackModal({ onClose, onSuccess }) {
  const api = useApi();
  const [confirmText, setConfirmText] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState(null);

  const REQUIRED_CONFIRM = "BASELINE_TO_STORED";
  const isReady = confirmText === REQUIRED_CONFIRM;

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!isReady) return;
    try {
      setSubmitting(true);
      setError(null);
      const result = await api.post(
        "/api/v1/admin/inventory/reconciliation/count/all-to-stored",
        { confirm: REQUIRED_CONFIRM }
      );
      onSuccess(result);
    } catch (err) {
      setError(err.message || "Failed to run fallback");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70">
      <div className="bg-gray-900 border border-orange-500/40 rounded-xl shadow-2xl w-full max-w-lg mx-4">
        <div className="px-5 py-4 border-b border-gray-800 flex items-start gap-3">
          <div className="mt-0.5 text-orange-400">
            <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                d="M12 9v2m0 4h.01M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0z" />
            </svg>
          </div>
          <div>
            <h3 className="text-white font-semibold">Baseline to stored — dev/test only</h3>
            <p className="text-gray-400 text-sm mt-1">
              Stamps <code className="text-orange-300 text-xs">baseline_timestamp = NOW</code> for
              ALL inventory rows using the current stored on-hand as the physical baseline.
              No ledger rows are written.
            </p>
            <p className="text-orange-400 text-sm mt-2 font-medium">
              Do NOT run this on a production database without explicit owner approval.
              This permanently discards pre-existing transaction history from future
              drift calculations.
            </p>
          </div>
        </div>

        <form onSubmit={handleSubmit} className="px-5 py-4 space-y-4">
          <div>
            <label className="block text-sm text-gray-300 mb-1.5">
              Type <span className="font-mono text-orange-300 select-all">{REQUIRED_CONFIRM}</span> to confirm:
            </label>
            <input
              type="text"
              value={confirmText}
              onChange={(e) => setConfirmText(e.target.value)}
              placeholder={REQUIRED_CONFIRM}
              className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-white font-mono focus:outline-none focus:border-orange-500"
              autoFocus
              autoComplete="off"
            />
          </div>

          {error && (
            <div className="bg-red-500/10 border border-red-500/30 rounded-lg p-3 text-red-400 text-sm">
              {error}
            </div>
          )}

          <div className="flex gap-3 pt-1">
            <button
              type="submit"
              disabled={!isReady || submitting}
              className="flex-1 px-4 py-2 bg-orange-600 text-white rounded-lg hover:bg-orange-700 disabled:opacity-40 font-medium"
            >
              {submitting ? "Running…" : "Run fallback"}
            </button>
            <button
              type="button"
              onClick={onClose}
              disabled={submitting}
              className="px-4 py-2 bg-gray-700 text-gray-200 rounded-lg hover:bg-gray-600 disabled:opacity-50"
            >
              Cancel
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Reconciliation report — counting work queue (HARD-4b + HARD-4c)
// ---------------------------------------------------------------------------

function ReconciliationReport() {
  const api = useApi();
  const [report, setReport] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [driftedOnly, setDriftedOnly] = useState(false);
  const [expanded, setExpanded] = useState(false);

  // Count modal state
  const [countingItem, setCountingItem] = useState(null);
  // Fallback modal state
  const [showFallback, setShowFallback] = useState(false);
  const [fallbackResult, setFallbackResult] = useState(null);

  const fetchReport = async () => {
    try {
      setLoading(true);
      setError(null);
      const params = driftedOnly ? "?drifted_only=true" : "";
      const data = await api.get(`/api/v1/admin/inventory/reconciliation${params}`);
      setReport(data);
    } catch (err) {
      setError(err.message || "Failed to load reconciliation report");
    } finally {
      setLoading(false);
    }
  };

  // Fetch whenever the filter or expanded state changes
  useEffect(() => {
    if (expanded) {
      fetchReport();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [expanded, driftedOnly]);

  const formatQty = (val) =>
    val == null ? "—" : Number(val).toLocaleString(undefined, { maximumFractionDigits: 4 });

  const driftColor = (drift) => {
    if (drift === 0) return "text-gray-400";
    return drift > 0 ? "text-yellow-400" : "text-red-400";
  };

  const handleCountSuccess = () => {
    setCountingItem(null);
    fetchReport();
  };

  const handleFallbackSuccess = (result) => {
    setShowFallback(false);
    setFallbackResult(result);
    fetchReport();
  };

  return (
    <>
      {/* Count entry modal */}
      {countingItem && (
        <CountModal
          item={countingItem}
          onClose={() => setCountingItem(null)}
          onSuccess={handleCountSuccess}
        />
      )}

      {/* Fallback modal */}
      {showFallback && (
        <FallbackModal
          onClose={() => setShowFallback(false)}
          onSuccess={handleFallbackSuccess}
        />
      )}

      <div className="bg-gray-900 border border-gray-800 rounded-xl overflow-hidden">
        {/* Collapsible header */}
        <button
          className="w-full flex items-center justify-between px-6 py-4 text-left hover:bg-gray-800/40 transition-colors"
          onClick={() => setExpanded((v) => !v)}
        >
          <div>
            <h2 className="text-lg font-semibold text-white">
              Reconciliation — items needing a count
            </h2>
            <p className="text-gray-400 text-sm mt-0.5">
              Compares stored on-hand against the transaction ledger to identify
              drift. Items without a baseline have never been physically counted.
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
            {/* Controls */}
            <div className="flex items-center gap-4 px-6 py-3 bg-gray-900/60">
              <label className="flex items-center gap-2 text-sm text-gray-300 cursor-pointer select-none">
                <input
                  type="checkbox"
                  checked={driftedOnly}
                  onChange={(e) => setDriftedOnly(e.target.checked)}
                  className="rounded border-gray-600 bg-gray-800 text-blue-500"
                />
                Show drifted items only
              </label>
              <button
                onClick={fetchReport}
                disabled={loading}
                className="ml-auto px-3 py-1.5 text-xs bg-gray-700 text-gray-200 rounded hover:bg-gray-600 disabled:opacity-50"
              >
                {loading ? "Loading…" : "Refresh"}
              </button>
              {/* Fallback button — clearly labeled as dev/test only */}
              <button
                onClick={() => { setFallbackResult(null); setShowFallback(true); }}
                className="px-3 py-1.5 text-xs bg-orange-900/60 border border-orange-700/50 text-orange-300 rounded hover:bg-orange-900/80"
                title="Stamp baseline_timestamp = NOW for all rows using current stored on-hand. Dev/test/first-install only."
              >
                Baseline to stored — dev/test only
              </button>
            </div>

            {/* Fallback success banner */}
            {fallbackResult && (
              <div className="mx-6 mt-3 bg-orange-500/10 border border-orange-500/30 rounded-lg px-4 py-2 text-orange-300 text-sm flex items-center justify-between">
                <span>{fallbackResult.message}</span>
                <button
                  onClick={() => setFallbackResult(null)}
                  className="text-orange-400 hover:text-orange-200 ml-4 text-lg leading-none"
                >
                  &times;
                </button>
              </div>
            )}

            {/* Summary badges */}
            {report && !loading && (
              <div className="flex gap-4 px-6 py-3 border-b border-gray-800">
                <div className="text-sm text-gray-400">
                  <span className="font-medium text-white">{report.total_items}</span> total items
                </div>
                <div className="text-sm text-gray-400">
                  <span className={`font-medium ${report.drifted_items > 0 ? "text-yellow-400" : "text-green-400"}`}>
                    {report.drifted_items}
                  </span> drifted
                </div>
                <div className="text-sm text-gray-400">
                  <span className={`font-medium ${report.uncounted_items > 0 ? "text-orange-400" : "text-gray-300"}`}>
                    {report.uncounted_items}
                  </span> uncounted
                </div>
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

            {/* Table */}
            {!loading && report && (
              <div className="overflow-x-auto">
                <table className="w-full">
                  <thead className="bg-gray-800/50">
                    <tr>
                      <th className="text-left py-2 px-4 text-xs font-medium text-gray-400 uppercase">SKU</th>
                      <th className="text-left py-2 px-4 text-xs font-medium text-gray-400 uppercase">Name</th>
                      <th className="text-left py-2 px-4 text-xs font-medium text-gray-400 uppercase">Location</th>
                      <th className="text-right py-2 px-4 text-xs font-medium text-gray-400 uppercase">Stored</th>
                      <th className="text-right py-2 px-4 text-xs font-medium text-gray-400 uppercase">Ledger Sum</th>
                      <th className="text-right py-2 px-4 text-xs font-medium text-gray-400 uppercase">Drift</th>
                      <th className="text-left py-2 px-4 text-xs font-medium text-gray-400 uppercase">Baseline</th>
                      <th className="text-left py-2 px-4 text-xs font-medium text-gray-400 uppercase">Status</th>
                      <th className="text-left py-2 px-4 text-xs font-medium text-gray-400 uppercase">Action</th>
                    </tr>
                  </thead>
                  <tbody>
                    {report.items.length === 0 ? (
                      <tr>
                        <td colSpan={9} className="py-8 text-center text-gray-500 text-sm">
                          {driftedOnly ? "No drifted items — all balanced." : "No inventory rows found."}
                        </td>
                      </tr>
                    ) : (
                      report.items.map((item) => (
                        <tr
                          key={`${item.product_id}-${item.location_id}`}
                          className={`border-b border-gray-800 hover:bg-gray-800/30 ${
                            item.has_drift ? "bg-yellow-500/5" : ""
                          }`}
                        >
                          <td className="py-2.5 px-4 font-mono text-sm text-white">{item.sku}</td>
                          <td className="py-2.5 px-4 text-gray-300 text-sm max-w-xs truncate">{item.name}</td>
                          <td className="py-2.5 px-4 text-gray-400 text-sm">{item.location_name || "—"}</td>
                          <td className="py-2.5 px-4 text-right text-white tabular-nums">{formatQty(item.stored_on_hand)}</td>
                          <td className="py-2.5 px-4 text-right text-gray-300 tabular-nums">{formatQty(item.ledger_sum)}</td>
                          <td className={`py-2.5 px-4 text-right font-semibold tabular-nums ${driftColor(item.drift)}`}>
                            {item.drift > 0 ? "+" : ""}{formatQty(item.drift)}
                          </td>
                          <td className="py-2.5 px-4 text-gray-500 text-xs">
                            {item.baseline_timestamp
                              ? new Date(item.baseline_timestamp).toLocaleDateString()
                              : "—"}
                          </td>
                          <td className="py-2.5 px-4">
                            {item.is_counted ? (
                              item.has_drift ? (
                                <span className="px-2 py-0.5 rounded-full text-xs bg-yellow-500/20 text-yellow-400">
                                  drifted
                                </span>
                              ) : (
                                <span className="px-2 py-0.5 rounded-full text-xs bg-green-500/20 text-green-400">
                                  clean
                                </span>
                              )
                            ) : (
                              <span className="px-2 py-0.5 rounded-full text-xs bg-orange-500/20 text-orange-400">
                                uncounted
                              </span>
                            )}
                          </td>
                          <td className="py-2.5 px-4">
                            {/* Count action — available for drifted or uncounted items */}
                            {(item.has_drift || !item.is_counted) && (
                              <button
                                onClick={() => setCountingItem(item)}
                                className="px-2.5 py-1 text-xs bg-blue-600/20 border border-blue-600/40 text-blue-400 rounded hover:bg-blue-600/30 hover:text-blue-300 transition-colors"
                                title="Enter physical count to post a reconciliation_baseline transaction"
                              >
                                Count
                              </button>
                            )}
                          </td>
                        </tr>
                      ))
                    )}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        )}
      </div>
    </>
  );
}

// ---------------------------------------------------------------------------
// Main page
// ---------------------------------------------------------------------------

export default function AdminInventoryTransactions() {
  const api = useApi();
  const formatCurrency = useFormatCurrency();
  const [transactions, setTransactions] = useState([]);
  const [products, setProducts] = useState([]);
  const [locations, setLocations] = useState([]);
  const [adjustmentReasons, setAdjustmentReasons] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [showForm, setShowForm] = useState(false);
  const [formData, setFormData] = useState({
    product_id: "",
    location_id: "",
    transaction_type: "receipt",
    quantity: "",
    cost_per_unit: "",
    reference_type: "",
    reference_id: "",
    lot_number: "",
    serial_number: "",
    notes: "",
    to_location_id: "",
    reason_code: "",
  });
  const [filters, setFilters] = useState({
    product_id: "",
    transaction_type: "",
    location_id: "",
  });

  useEffect(() => {
    fetchTransactions();
    fetchProducts();
    fetchLocations();
  }, [filters]);

  // Fetch adjustment reasons for dropdown
  useEffect(() => {
    api.get("/api/v1/admin/inventory/transactions/adjustment-reasons")
      .then(data => setAdjustmentReasons(data))
      .catch(() => {}); // Non-critical, will fallback to empty dropdown
  }, []);

  const fetchTransactions = async () => {
    try {
      setLoading(true);
      const params = new URLSearchParams();
      if (filters.product_id) params.append("product_id", filters.product_id);
      if (filters.transaction_type)
        params.append("transaction_type", filters.transaction_type);
      if (filters.location_id)
        params.append("location_id", filters.location_id);

      const data = await api.get(`/api/v1/admin/inventory/transactions?${params.toString()}`);
      setTransactions(data);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const fetchProducts = async () => {
    try {
      const data = await api.get(`/api/v1/items?limit=2000`);
      setProducts(data.items || []);
    } catch {
      // Non-critical: Products fetch failure - dropdown will be empty but page still works
    }
  };

  const fetchLocations = async () => {
    try {
      const data = await api.get(`/api/v1/admin/inventory/transactions/locations`);
      setLocations(data);
    } catch {
      // Locations fetch failure is non-critical - location selector will be empty
    }
  };

  const handleSubmit = async (e) => {
    e.preventDefault();

    try {
      const payload = {
        ...formData,
        product_id: parseInt(formData.product_id),
        location_id: formData.location_id
          ? parseInt(formData.location_id)
          : null,
        quantity: parseFloat(formData.quantity),
        cost_per_unit: formData.cost_per_unit
          ? parseFloat(formData.cost_per_unit)
          : null,
        reference_id: formData.reference_id
          ? parseInt(formData.reference_id)
          : null,
        to_location_id:
          formData.transaction_type === "transfer" && formData.to_location_id
            ? parseInt(formData.to_location_id)
            : null,
        ...(formData.reason_code && { reason_code: formData.reason_code }),
      };

      await api.post(`/api/v1/admin/inventory/transactions`, payload);

      // Reset form and refresh
      setFormData({
        product_id: "",
        location_id: "",
        transaction_type: "receipt",
        quantity: "",
        cost_per_unit: "",
        reference_type: "",
        reference_id: "",
        lot_number: "",
        serial_number: "",
        notes: "",
        to_location_id: "",
        reason_code: "",
      });
      setShowForm(false);
      fetchTransactions();
    } catch (err) {
      setError(err.message);
    }
  };

  const getTransactionTypeColor = (type) => {
    const colors = {
      receipt: "bg-green-500/20 text-green-400",
      issue: "bg-red-500/20 text-red-400",
      transfer: "bg-blue-500/20 text-blue-400",
      adjustment: "bg-yellow-500/20 text-yellow-400",
      consumption: "bg-orange-500/20 text-orange-400",
      scrap: "bg-gray-500/20 text-gray-400",
    };
    return colors[type] || "bg-gray-500/20 text-gray-400";
  };

  if (loading && transactions.length === 0) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-500"></div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex justify-between items-center">
        <div>
          <h1 className="text-2xl font-bold text-white">
            Inventory Transactions
          </h1>
          <p className="text-gray-400 mt-1">
            Manage receipts, issues, transfers, and adjustments
          </p>
        </div>
        <button
          onClick={() => setShowForm(!showForm)}
          className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700"
        >
          {showForm ? "Cancel" : "+ New Transaction"}
        </button>
      </div>

      {/* Reconciliation Report — counting work queue */}
      <ReconciliationReport />

      {/* Error Message */}
      {error && (
        <div className="bg-red-500/10 border border-red-500/30 rounded-xl p-4 text-red-400">
          {error}
        </div>
      )}

      {/* Transaction Form */}
      {showForm && (
        <div className="bg-gray-900 border border-gray-800 rounded-xl p-6">
          <h2 className="text-lg font-semibold text-white mb-4">
            Create Transaction
          </h2>
          <form onSubmit={handleSubmit} className="space-y-4">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div>
                <label className="block text-sm font-medium text-gray-400 mb-1">
                  Product *
                </label>
                <select
                  required
                  value={formData.product_id}
                  onChange={(e) =>
                    setFormData({ ...formData, product_id: e.target.value })
                  }
                  className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-white"
                >
                  <option value="">Select product</option>
                  {products.map((p) => (
                    <option key={p.id} value={p.id}>
                      {p.sku} - {p.name}
                    </option>
                  ))}
                </select>
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-400 mb-1">
                  Transaction Type *
                </label>
                <select
                  required
                  value={formData.transaction_type}
                  onChange={(e) =>
                    setFormData({
                      ...formData,
                      transaction_type: e.target.value,
                    })
                  }
                  className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-white"
                >
                  <option value="receipt">Receipt</option>
                  <option value="issue">Issue</option>
                  <option value="transfer">Transfer</option>
                  <option value="adjustment">Adjustment</option>
                  <option value="consumption">Consumption</option>
                  <option value="scrap">Scrap</option>
                </select>
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-400 mb-1">
                  Location
                </label>
                <select
                  value={formData.location_id}
                  onChange={(e) =>
                    setFormData({ ...formData, location_id: e.target.value })
                  }
                  className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-white"
                >
                  <option value="">Default (Main Warehouse)</option>
                  {locations.map((loc) => (
                    <option key={loc.id} value={loc.id}>
                      {loc.name} ({loc.code})
                    </option>
                  ))}
                </select>
              </div>

              {formData.transaction_type === "transfer" && (
                <div>
                  <label className="block text-sm font-medium text-gray-400 mb-1">
                    To Location *
                  </label>
                  <select
                    required={formData.transaction_type === "transfer"}
                    value={formData.to_location_id}
                    onChange={(e) =>
                      setFormData({
                        ...formData,
                        to_location_id: e.target.value,
                      })
                    }
                    className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-white"
                  >
                    <option value="">Select destination</option>
                    {locations.map((loc) => (
                      <option key={loc.id} value={loc.id}>
                        {loc.name} ({loc.code})
                      </option>
                    ))}
                  </select>
                </div>
              )}

              <div>
                <label className="block text-sm font-medium text-gray-400 mb-1">
                  Quantity *
                </label>
                <input
                  type="number"
                  step="0.01"
                  required
                  value={formData.quantity}
                  onChange={(e) =>
                    setFormData({ ...formData, quantity: e.target.value })
                  }
                  className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-white"
                />
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-400 mb-1">
                  Cost per Unit
                </label>
                <input
                  type="number"
                  step="0.01"
                  value={formData.cost_per_unit}
                  onChange={(e) =>
                    setFormData({ ...formData, cost_per_unit: e.target.value })
                  }
                  className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-white"
                />
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-400 mb-1">
                  Reference Type
                </label>
                <select
                  value={formData.reference_type}
                  onChange={(e) =>
                    setFormData({ ...formData, reference_type: e.target.value })
                  }
                  className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-white"
                >
                  <option value="">None</option>
                  <option value="purchase_order">Purchase Order</option>
                  <option value="production_order">Production Order</option>
                  <option value="sales_order">Sales Order</option>
                  <option value="adjustment">Adjustment</option>
                </select>
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-400 mb-1">
                  Reference ID
                </label>
                <input
                  type="number"
                  value={formData.reference_id}
                  onChange={(e) =>
                    setFormData({ ...formData, reference_id: e.target.value })
                  }
                  className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-white"
                />
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-400 mb-1">
                  Lot Number
                </label>
                <input
                  type="text"
                  value={formData.lot_number}
                  onChange={(e) =>
                    setFormData({ ...formData, lot_number: e.target.value })
                  }
                  className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-white"
                />
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-400 mb-1">
                  Serial Number
                </label>
                <input
                  type="text"
                  value={formData.serial_number}
                  onChange={(e) =>
                    setFormData({ ...formData, serial_number: e.target.value })
                  }
                  className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-white"
                />
              </div>
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-400 mb-1">
                Notes
              </label>
              <textarea
                value={formData.notes}
                onChange={(e) =>
                  setFormData({ ...formData, notes: e.target.value })
                }
                rows={3}
                className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-white"
              />
            </div>

            {formData.transaction_type === "adjustment" && (
              <div>
                <label className="block text-sm font-medium text-gray-400 mb-1">
                  Adjustment Reason
                </label>
                <select
                  value={formData.reason_code}
                  onChange={(e) =>
                    setFormData({ ...formData, reason_code: e.target.value })
                  }
                  className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-white"
                >
                  <option value="">Select reason...</option>
                  {adjustmentReasons.map((r) => (
                    <option key={r.code} value={r.code}>
                      {r.name}
                    </option>
                  ))}
                </select>
              </div>
            )}

            <div className="flex gap-4">
              <button
                type="submit"
                className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700"
              >
                Create Transaction
              </button>
              <button
                type="button"
                onClick={() => setShowForm(false)}
                className="px-4 py-2 bg-gray-700 text-white rounded-lg hover:bg-gray-600"
              >
                Cancel
              </button>
            </div>
          </form>
        </div>
      )}

      {/* Filters */}
      <div className="bg-gray-900 border border-gray-800 rounded-xl p-4">
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <div>
            <label className="block text-sm font-medium text-gray-400 mb-1">
              Product
            </label>
            <select
              value={filters.product_id}
              onChange={(e) =>
                setFilters({ ...filters, product_id: e.target.value })
              }
              className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-white"
            >
              <option value="">All Products</option>
              {products.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.sku} - {p.name}
                </option>
              ))}
            </select>
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-400 mb-1">
              Type
            </label>
            <select
              value={filters.transaction_type}
              onChange={(e) =>
                setFilters({ ...filters, transaction_type: e.target.value })
              }
              className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-white"
            >
              <option value="">All Types</option>
              <option value="receipt">Receipt</option>
              <option value="issue">Issue</option>
              <option value="transfer">Transfer</option>
              <option value="adjustment">Adjustment</option>
              <option value="consumption">Consumption</option>
              <option value="scrap">Scrap</option>
            </select>
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-400 mb-1">
              Location
            </label>
            <select
              value={filters.location_id}
              onChange={(e) =>
                setFilters({ ...filters, location_id: e.target.value })
              }
              className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-white"
            >
              <option value="">All Locations</option>
              {locations.map((loc) => (
                <option key={loc.id} value={loc.id}>
                  {loc.name}
                </option>
              ))}
            </select>
          </div>
        </div>
      </div>

      {/* Transactions Table */}
      <div className="bg-gray-900 border border-gray-800 rounded-xl overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full">
            <thead className="bg-gray-800/50">
              <tr>
                <th className="text-left py-3 px-4 text-xs font-medium text-gray-400 uppercase">
                  Date
                </th>
                <th className="text-left py-3 px-4 text-xs font-medium text-gray-400 uppercase">
                  Product
                </th>
                <th className="text-left py-3 px-4 text-xs font-medium text-gray-400 uppercase">
                  Type
                </th>
                <th className="text-left py-3 px-4 text-xs font-medium text-gray-400 uppercase">
                  Quantity
                </th>
                <th className="text-left py-3 px-4 text-xs font-medium text-gray-400 uppercase">
                  Location
                </th>
                <th className="text-left py-3 px-4 text-xs font-medium text-gray-400 uppercase">
                  Reference
                </th>
                <th className="text-left py-3 px-4 text-xs font-medium text-gray-400 uppercase">
                  Cost/Unit
                </th>
                <th className="text-left py-3 px-4 text-xs font-medium text-gray-400 uppercase">
                  Total Cost
                </th>
                <th className="text-left py-3 px-4 text-xs font-medium text-gray-400 uppercase">
                  Unit
                </th>
                <th className="text-left py-3 px-4 text-xs font-medium text-gray-400 uppercase">
                  Notes
                </th>
                <th className="text-left py-3 px-4 text-xs font-medium text-gray-400 uppercase">
                  Reason
                </th>
              </tr>
            </thead>
            <tbody>
              {transactions.length > 0 ? (
                transactions.map((txn) => (
                  <tr
                    key={txn.id}
                    className="border-b border-gray-800 hover:bg-gray-800/50"
                  >
                    <td className="py-3 px-4 text-gray-400 text-sm">
                      {new Date(txn.created_at).toLocaleDateString()}
                    </td>
                    <td className="py-3 px-4">
                      <div className="text-white font-medium">
                        {txn.product_sku}
                      </div>
                      <div className="text-gray-500 text-xs">
                        {txn.product_name}
                      </div>
                    </td>
                    <td className="py-3 px-4">
                      <span
                        className={`px-2 py-1 rounded-full text-xs ${getTransactionTypeColor(
                          txn.transaction_type
                        )}`}
                      >
                        {txn.transaction_type}
                      </span>
                      {txn.to_location_name && (
                        <div className="text-gray-500 text-xs mt-1">
                          &rarr; {txn.to_location_name}
                        </div>
                      )}
                    </td>
                    <td className="py-3 px-4 text-white">
                      {/* SINGLE SOURCE OF TRUTH: Display stored quantity and unit directly */}
                      {parseFloat(txn.quantity).toLocaleString(undefined, { maximumFractionDigits: 4 })}
                      {txn.unit && (
                        <span className="text-gray-500 text-xs ml-1">{txn.unit}</span>
                      )}
                    </td>
                    <td className="py-3 px-4 text-gray-400">
                      {txn.location_name || "N/A"}
                    </td>
                    <td className="py-3 px-4 text-gray-400 text-sm">
                      {txn.reference_type && txn.reference_id
                        ? `${txn.reference_type} #${txn.reference_id}`
                        : "-"}
                    </td>
                    <td className="py-3 px-4 text-gray-400">
                      {/* SINGLE SOURCE OF TRUTH: Display stored cost_per_unit with unit */}
                      {txn.cost_per_unit
                        ? formatCurrency(parseFloat(txn.cost_per_unit)) + "/" + (txn.unit || "EA")
                        : "-"}
                    </td>
                    <td className="py-3 px-4 text-white font-medium">
                      {/* SINGLE SOURCE OF TRUTH: Display stored total_cost directly - NO client-side math */}
                      {txn.total_cost != null
                        ? formatCurrency(parseFloat(txn.total_cost))
                        : "-"}
                    </td>
                    <td className="py-3 px-4 text-gray-500 text-xs">
                      {/* SINGLE SOURCE OF TRUTH: Display stored unit directly */}
                      {txn.unit || "-"}
                    </td>
                    <td className="py-3 px-4 text-gray-500 text-sm max-w-xs truncate">
                      {txn.notes || "-"}
                    </td>
                    <td className="py-3 px-4 text-gray-500 text-sm">
                      {txn.reason_code || "-"}
                    </td>
                  </tr>
                ))
              ) : (
                <tr>
                  <td colSpan={11} className="py-8 text-center text-gray-500">
                    No transactions found
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
