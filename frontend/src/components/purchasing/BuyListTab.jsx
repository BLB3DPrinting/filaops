import { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { useApi } from "../../hooks/useApi";

/**
 * BuyListTab — consolidated buy list (HARD-7, Layer 1 live view).
 *
 * Answers "across ALL open demand, what do I buy, how much, by when?"
 *
 * Per-row "Create PO" navigates to /admin/purchasing?create_po=true&product_id=X&quantity=Y
 * so the existing POCreateModal pre-fills vendor + suggested qty without
 * any modification to purchase_order_service (human commits the PO).
 */
export default function BuyListTab() {
  const api = useApi();
  const navigate = useNavigate();

  const [buyList, setBuyList] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [expandedRows, setExpandedRows] = useState(new Set());

  const fetchBuyList = async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await api.get("/api/v1/buy-list");
      setBuyList(data);
    } catch (err) {
      setError(err.message || "Failed to load buy list");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchBuyList();
  }, []);

  const toggleRow = (productId) => {
    setExpandedRows((prev) => {
      const next = new Set(prev);
      if (next.has(productId)) {
        next.delete(productId);
      } else {
        next.add(productId);
      }
      return next;
    });
  };

  const handleCreatePO = (item) => {
    // Navigate to the Purchasing page with URL params that pre-fill POCreateModal.
    // This reuses the existing create_po param flow already in AdminPurchasing.jsx.
    const params = new URLSearchParams({
      tab: "orders",
      create_po: "true",
      product_id: String(item.product_id),
      quantity: String(item.suggested_qty),
    });
    navigate(`/admin/purchasing?${params.toString()}`);
  };

  const formatQty = (qty) => {
    const n = parseFloat(qty);
    if (Number.isInteger(n)) return n.toLocaleString();
    return n.toLocaleString(undefined, { maximumFractionDigits: 2 });
  };

  const formatCurrency = (val) => {
    const n = parseFloat(val);
    return n.toLocaleString("en-US", { style: "currency", currency: "USD" });
  };

  const formatDate = (d) => {
    if (!d) return "—";
    return new Date(d).toLocaleDateString("en-US", {
      month: "short",
      day: "numeric",
    });
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-48">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-500" />
      </div>
    );
  }

  if (error) {
    return (
      <div className="bg-red-500/10 border border-red-500/30 rounded-xl p-6 text-red-400">
        <p className="font-semibold mb-1">Failed to load buy list</p>
        <p className="text-sm">{error}</p>
        <button
          onClick={fetchBuyList}
          className="mt-3 px-3 py-1.5 bg-red-600/20 hover:bg-red-600/40 rounded text-sm"
        >
          Retry
        </button>
      </div>
    );
  }

  if (!buyList) return null;

  const { summary, items } = buyList;

  return (
    <div className="space-y-6">
      {/* Summary cards */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
        <div className="bg-red-500/10 border border-red-500/30 rounded-xl p-4">
          <div className="text-3xl font-bold text-red-400">
            {summary.components_short}
          </div>
          <div className="text-sm text-gray-400 mt-1">Components Short</div>
        </div>
        <div className="bg-orange-500/10 border border-orange-500/30 rounded-xl p-4">
          <div className="text-2xl font-bold text-orange-400">
            {formatCurrency(summary.total_estimated_buy_value)}
          </div>
          <div className="text-sm text-gray-400 mt-1">Est. Buy Value</div>
        </div>
        <div className="bg-blue-500/10 border border-blue-500/30 rounded-xl p-4">
          <div className="text-3xl font-bold text-blue-400">
            {summary.open_sales_orders_included}
          </div>
          <div className="text-sm text-gray-400 mt-1">Open Sales Orders</div>
        </div>
        <div className="bg-purple-500/10 border border-purple-500/30 rounded-xl p-4">
          <div className="text-3xl font-bold text-purple-400">
            {summary.open_production_orders_included}
          </div>
          <div className="text-sm text-gray-400 mt-1">Open Work Orders</div>
        </div>
      </div>

      {/* Draft-supply transparency notice */}
      {summary.draft_incoming_qty > 0 && (
        <div className="bg-yellow-500/10 border border-yellow-500/30 rounded-xl p-4 flex items-start gap-3">
          <svg
            className="w-5 h-5 text-yellow-400 mt-0.5 shrink-0"
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={2}
              d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"
            />
          </svg>
          <p className="text-yellow-300 text-sm">
            <strong>
              {formatQty(summary.draft_incoming_qty)} units
            </strong>{" "}
            of incoming supply shown below are on <strong>draft</strong> POs
            — uncommitted. Rows marked "(draft)" in the Incoming column may
            still be short if those POs are not placed.
          </p>
        </div>
      )}

      {/* Empty state */}
      {items.length === 0 && (
        <div className="bg-gray-900 border border-gray-800 rounded-xl p-12 text-center">
          <svg
            className="w-12 h-12 text-green-400 mx-auto mb-4"
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={2}
              d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z"
            />
          </svg>
          <h3 className="text-lg font-semibold text-white mb-2">
            All components covered
          </h3>
          <p className="text-gray-400 text-sm">
            No shortages detected across open sales and production orders.
          </p>
          <button
            onClick={fetchBuyList}
            className="mt-4 px-3 py-1.5 bg-gray-700 hover:bg-gray-600 rounded text-sm text-gray-300"
          >
            Refresh
          </button>
        </div>
      )}

      {/* Buy list table */}
      {items.length > 0 && (
        <div className="bg-gray-900 border border-gray-800 rounded-xl overflow-hidden">
          <div className="flex items-center justify-between p-4 border-b border-gray-800">
            <h3 className="text-sm font-semibold text-white">
              Components to Buy ({items.length})
            </h3>
            <button
              onClick={fetchBuyList}
              className="text-xs text-gray-400 hover:text-white flex items-center gap-1"
            >
              <svg
                className="w-3.5 h-3.5"
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
              Refresh
            </button>
          </div>

          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-gray-400 border-b border-gray-800">
                  <th className="px-4 py-3 font-medium w-6" />
                  <th className="px-4 py-3 font-medium">Component</th>
                  <th className="px-4 py-3 font-medium text-right">
                    Gross Demand
                  </th>
                  <th className="px-4 py-3 font-medium text-right">
                    On Hand
                  </th>
                  <th className="px-4 py-3 font-medium text-right">
                    Incoming
                  </th>
                  <th className="px-4 py-3 font-medium text-right">
                    Net Short
                  </th>
                  <th className="px-4 py-3 font-medium text-right">
                    Suggest Qty
                  </th>
                  <th className="px-4 py-3 font-medium">Vendor</th>
                  <th className="px-4 py-3 font-medium text-right">
                    Est. Value
                  </th>
                  <th className="px-4 py-3 font-medium">Need By</th>
                  <th className="px-4 py-3 font-medium" />
                </tr>
              </thead>
              <tbody>
                {items.map((item) => {
                  const isExpanded = expandedRows.has(item.product_id);
                  const hasDraft = item.incoming_details?.some(
                    (d) => d.status === "draft"
                  );

                  return (
                    <>
                      <tr
                        key={item.product_id}
                        className="border-b border-gray-800/50 bg-red-500/5 hover:bg-red-500/10 transition-colors"
                      >
                        {/* Expand toggle */}
                        <td className="px-4 py-3">
                          {item.incoming_details?.length > 0 && (
                            <button
                              onClick={() => toggleRow(item.product_id)}
                              className="text-gray-500 hover:text-gray-300"
                            >
                              <svg
                                className={`w-4 h-4 transition-transform ${
                                  isExpanded ? "rotate-90" : ""
                                }`}
                                fill="none"
                                stroke="currentColor"
                                viewBox="0 0 24 24"
                              >
                                <path
                                  strokeLinecap="round"
                                  strokeLinejoin="round"
                                  strokeWidth={2}
                                  d="M9 5l7 7-7 7"
                                />
                              </svg>
                            </button>
                          )}
                        </td>

                        {/* SKU / name */}
                        <td className="px-4 py-3">
                          <div className="font-mono text-white text-xs">
                            {item.sku}
                          </div>
                          <div className="text-gray-400 text-xs mt-0.5 truncate max-w-[180px]">
                            {item.name}
                          </div>
                        </td>

                        {/* Gross demand */}
                        <td className="px-4 py-3 text-right text-gray-300">
                          {formatQty(item.gross_demand)}{" "}
                          <span className="text-gray-500 text-xs">
                            {item.unit}
                          </span>
                        </td>

                        {/* On hand */}
                        <td className="px-4 py-3 text-right text-gray-300">
                          {formatQty(item.on_hand)}
                        </td>

                        {/* Incoming */}
                        <td className="px-4 py-3 text-right">
                          <span
                            className={
                              hasDraft
                                ? "text-yellow-400"
                                : "text-blue-400"
                            }
                          >
                            {formatQty(item.incoming_qty)}
                          </span>
                          {hasDraft && (
                            <span className="ml-1 text-yellow-500 text-xs">
                              ⚠ draft
                            </span>
                          )}
                        </td>

                        {/* Net short — highlighted */}
                        <td className="px-4 py-3 text-right">
                          <span className="font-semibold text-red-400">
                            {formatQty(item.net_shortage)}{" "}
                            <span className="text-xs font-normal">
                              {item.unit}
                            </span>
                          </span>
                        </td>

                        {/* Suggested qty */}
                        <td className="px-4 py-3 text-right text-white font-medium">
                          {formatQty(item.suggested_qty)}{" "}
                          <span className="text-gray-500 text-xs font-normal">
                            {item.unit}
                          </span>
                        </td>

                        {/* Vendor */}
                        <td className="px-4 py-3">
                          {item.preferred_vendor_name ? (
                            <span className="text-gray-300">
                              {item.preferred_vendor_name}
                            </span>
                          ) : (
                            <span className="text-gray-600 italic text-xs">
                              No vendor
                            </span>
                          )}
                        </td>

                        {/* Estimated value */}
                        <td className="px-4 py-3 text-right text-gray-300">
                          {formatCurrency(item.estimated_buy_value)}
                        </td>

                        {/* Need by */}
                        <td className="px-4 py-3 text-gray-400">
                          {formatDate(item.earliest_need)}
                        </td>

                        {/* Create PO button */}
                        <td className="px-4 py-3">
                          <button
                            onClick={() => handleCreatePO(item)}
                            className="px-2.5 py-1 bg-blue-600/80 hover:bg-blue-600 rounded text-white text-xs font-medium whitespace-nowrap"
                            title={`Create PO for ${item.sku} — ${formatQty(item.suggested_qty)} ${item.unit}${item.preferred_vendor_name ? " from " + item.preferred_vendor_name : ""}`}
                          >
                            + Create PO
                          </button>
                        </td>
                      </tr>

                      {/* Expanded incoming PO detail */}
                      {isExpanded && item.incoming_details?.length > 0 && (
                        <tr
                          key={`${item.product_id}-detail`}
                          className="border-b border-gray-800/50 bg-gray-800/30"
                        >
                          <td colSpan={11} className="px-10 py-3">
                            <div className="text-xs text-gray-400 mb-2 font-medium uppercase tracking-wide">
                              Open PO Supply
                            </div>
                            <div className="space-y-1">
                              {item.incoming_details.map((d) => (
                                <div
                                  key={d.purchase_order_id}
                                  className="flex items-center gap-4 text-xs"
                                >
                                  <span className="font-mono text-blue-300">
                                    {d.po_number}
                                  </span>
                                  <span className="text-gray-300">
                                    {formatQty(d.quantity)} {item.unit}
                                  </span>
                                  <span
                                    className={`px-1.5 py-0.5 rounded text-xs ${
                                      d.status === "draft"
                                        ? "bg-yellow-500/20 text-yellow-400"
                                        : d.status === "shipped"
                                        ? "bg-green-500/20 text-green-400"
                                        : "bg-blue-500/20 text-blue-400"
                                    }`}
                                  >
                                    {d.status === "draft"
                                      ? "draft (uncommitted)"
                                      : d.status}
                                  </span>
                                  {d.expected_date && (
                                    <span className="text-gray-500">
                                      due {formatDate(d.expected_date)}
                                    </span>
                                  )}
                                </div>
                              ))}
                            </div>
                          </td>
                        </tr>
                      )}
                    </>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}
