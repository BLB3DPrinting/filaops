/**
 * ProductionOrderDetail - Production Order Command Center
 *
 * Detailed view for managing a single production order:
 * - Order status and progress
 * - Material requirements and availability
 * - Blocking issues analysis
 * - Action buttons (Release, Start, Complete, etc.)
 */
import { useState, useEffect } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { useApi } from "../../hooks/useApi";
import { useToast } from "../../components/Toast";
import BlockingIssuesPanel from "../../components/orders/BlockingIssuesPanel";
import {
  OperationsPanel,
  OperationSchedulerModal,
  OperationsTimeline,
} from "../../components/production";
import {
  PRODUCTION_ORDER_COLORS,
  getStatusColor,
} from "../../lib/statusColors.js";

/**
 * Wrapper to fetch operations for timeline
 */
function OperationsTimelineWrapper({ productionOrderId }) {
  const [operations, setOperations] = useState([]);
  const api = useApi();

  useEffect(() => {
    const fetchOps = async () => {
      if (!productionOrderId) return;
      try {
        const data = await api.get(
          `/api/v1/production-orders/${productionOrderId}/operations`,
        );
        setOperations(Array.isArray(data) ? data : data.operations || []);
      } catch (err) {
        console.error("Failed to fetch operations for timeline:", err);
      }
    };
    fetchOps();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [productionOrderId]);

  if (operations.length === 0) return null;

  return <OperationsTimeline operations={operations} />;
}

export default function ProductionOrderDetail() {
  const { orderId } = useParams();
  const navigate = useNavigate();
  const toast = useToast();
  const api = useApi();

  const [order, setOrder] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [updating, setUpdating] = useState(false);
  const [schedulerOpen, setSchedulerOpen] = useState(false);
  const [selectedOperation, setSelectedOperation] = useState(null);

  useEffect(() => {
    if (orderId) {
      fetchOrder();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [orderId]);

  const fetchOrder = async ({ silent = false } = {}) => {
    if (!silent) {
      setLoading(true);
      setError(null);
    }

    try {
      const data = await api.get(`/api/v1/production-orders/${orderId}`);
      setOrder(data);
    } catch (err) {
      console.error("fetchOrder failed:", err);
      setError(err.message);
      // For terminal errors on background refreshes, clear stale order data
      const status = err.response?.status;
      if (silent && status && (status === 401 || status >= 500)) {
        setOrder(null);
      }
    } finally {
      if (!silent) setLoading(false);
    }
  };

  const handleStatusUpdate = async (action) => {
    setUpdating(true);
    try {
      await api.post(`/api/v1/production-orders/${orderId}/${action}`);

      toast.success(`Order ${action} successfully`);
      fetchOrder();
    } catch (err) {
      toast.error(err.message);
    } finally {
      setUpdating(false);
    }
  };

  const getProductionStatusColor = (status) =>
    getStatusColor(PRODUCTION_ORDER_COLORS, status);

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-500"></div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="p-6">
        <div className="bg-red-500/10 border border-red-500/30 rounded-xl p-6 text-center">
          <p className="text-red-400 mb-4">{error}</p>
          <button
            onClick={() => navigate("/admin/production")}
            className="px-4 py-2 bg-gray-700 text-white rounded-lg hover:bg-gray-600"
          >
            Back to Production
          </button>
        </div>
      </div>
    );
  }

  if (!order) {
    return (
      <div className="p-6">
        <div className="bg-gray-900 border border-gray-800 rounded-xl p-6 text-center">
          <p className="text-gray-400 mb-4">Production order not found</p>
          <button
            onClick={() => navigate("/admin/production")}
            className="px-4 py-2 bg-gray-700 text-white rounded-lg hover:bg-gray-600"
          >
            Back to Production
          </button>
        </div>
      </div>
    );
  }

  const progress =
    order.quantity_ordered > 0
      ? Math.round((order.quantity_completed / order.quantity_ordered) * 100)
      : 0;

  return (
    <div className="space-y-6 p-6">
      {/* Header */}
      <div className="flex justify-between items-center">
        <div>
          <button
            onClick={() => navigate("/admin/production")}
            className="text-gray-400 hover:text-white mb-2"
          >
            ← Back to Production
          </button>
          <h1 className="text-2xl font-bold text-white">
            Production Order: {order.code}
          </h1>
          <p className="text-gray-400 mt-1">Production Command Center</p>
        </div>
        <div className="flex gap-2">
          <button
            onClick={fetchOrder}
            className="px-4 py-2 bg-gray-700 text-white rounded-lg hover:bg-gray-600"
          >
            ↻ Refresh
          </button>
          {order.status === "draft" && (
            <button
              onClick={() => handleStatusUpdate("release")}
              disabled={updating}
              className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50"
            >
              Release
            </button>
          )}
          {order.status === "released" && (
            <button
              onClick={() => handleStatusUpdate("start")}
              disabled={updating}
              className="px-4 py-2 bg-purple-600 text-white rounded-lg hover:bg-purple-700 disabled:opacity-50"
            >
              Start Production
            </button>
          )}
          {order.status === "in_progress" && (
            <button
              onClick={() => handleStatusUpdate("complete")}
              disabled={updating}
              className="px-4 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700 disabled:opacity-50"
            >
              Complete
            </button>
          )}
        </div>
      </div>

      {/* Order Summary */}
      <div className="bg-gray-900 border border-gray-800 rounded-xl p-6">
        <h2 className="text-lg font-semibold text-white mb-4">Order Summary</h2>
        <div className="grid grid-cols-5 gap-4">
          <div>
            <div className="text-sm text-gray-400">Product</div>
            <div className="text-white font-medium">
              {order.product_name || order.product_sku || "N/A"}
            </div>
          </div>
          <div>
            <div className="text-sm text-gray-400">Quantity</div>
            <div className="text-white font-medium">
              {order.quantity_completed || 0} / {order.quantity_ordered}
            </div>
          </div>
          <div>
            <div className="text-sm text-gray-400">Status</div>
            <span
              className={`inline-block px-2 py-1 rounded-full text-sm ${getProductionStatusColor(order.status)}`}
            >
              {order.status}
            </span>
          </div>
          <div>
            <div className="text-sm text-gray-400">Priority</div>
            <div className="text-white font-medium">
              {order.priority || "Normal"}
            </div>
          </div>
          <div>
            <div className="text-sm text-gray-400">Due Date</div>
            <div className="text-white font-medium">
              {order.due_date
                ? new Date(order.due_date).toLocaleDateString()
                : "Not set"}
            </div>
          </div>
        </div>

        {/* Progress Bar */}
        <div className="mt-4">
          <div className="flex justify-between text-sm mb-1">
            <span className="text-gray-400">Progress</span>
            <span className="text-white">{progress}%</span>
          </div>
          <div className="w-full bg-gray-800 rounded-full h-2">
            <div
              className="bg-gradient-to-r from-blue-600 to-purple-600 h-2 rounded-full transition-all"
              style={{ width: `${progress}%` }}
            ></div>
          </div>
        </div>
      </div>

      {/* Operations Timeline (visual overview) */}
      {order.status !== "draft" && (
        <OperationsTimelineWrapper productionOrderId={order.id} />
      )}

      {/* Operations Panel */}
      <OperationsPanel
        productionOrderId={order.id}
        productionOrder={order}
        orderStatus={order.status}
        onOperationClick={(operation) => {
          if (operation.status === "pending") {
            setSelectedOperation(operation);
            setSchedulerOpen(true);
          }
        }}
      />

      {/* Blocking Issues Panel */}
      <BlockingIssuesPanel
        orderType="production"
        orderId={order.id}
        onActionClick={(action) => {
          // Navigate based on action reference type
          if (action.reference_type === "purchase_order") {
            navigate(`/admin/purchasing?po_id=${action.reference_id}`);
          } else if (action.reference_type === "product") {
            // Navigate to purchasing with product pre-selected for new PO
            // Extract quantity from action impact (e.g., "Need 7 units")
            const quantityMatch = action.impact?.match(/Need\s+([\d.]+)/);
            const quantity = quantityMatch ? quantityMatch[1] : "";
            navigate(
              `/admin/purchasing?create_po=true&product_id=${action.reference_id}${quantity ? `&quantity=${quantity}` : ""}`,
            );
          } else if (action.reference_type === "production_order") {
            navigate(`/admin/production/${action.reference_id}`);
          }
        }}
      />

      {/* Order Lineage - Show if this is a remake */}
      {order.remake_of_id && (
        <div className="bg-gray-900 border border-yellow-600/30 rounded-xl p-6">
          <div className="flex items-center gap-2 mb-4">
            <svg
              className="w-5 h-5 text-yellow-500"
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
            <h2 className="text-lg font-semibold text-yellow-400">
              Remake Order
            </h2>
          </div>
          <div className="flex items-center justify-between">
            <div>
              <p className="text-gray-400 text-sm mb-1">
                This order is a remake of:
              </p>
              <p className="text-white font-medium">
                {order.remake_of_code || `PO-${order.remake_of_id}`}
              </p>
              {order.remake_reason && (
                <p className="text-yellow-400/80 text-sm mt-1">
                  Reason: {order.remake_reason}
                </p>
              )}
            </div>
            <button
              onClick={() =>
                navigate(`/admin/production/${order.remake_of_id}`)
              }
              className="px-4 py-2 bg-yellow-600/20 text-yellow-400 rounded-lg hover:bg-yellow-600/30"
            >
              View Original
            </button>
          </div>
        </div>
      )}

      {/* Linked Sales Order */}
      {order.sales_order_id && (
        <div className="bg-gray-900 border border-gray-800 rounded-xl p-6">
          <h2 className="text-lg font-semibold text-white mb-4">
            Linked Sales Order
          </h2>
          <div className="flex items-center justify-between">
            <div>
              <p className="text-white font-medium">
                {order.sales_order_code || `SO-${order.sales_order_id}`}
              </p>
              <p className="text-gray-400 text-sm">
                {order.customer_name || "Customer"}
              </p>
            </div>
            <button
              onClick={() => navigate(`/admin/orders/${order.sales_order_id}`)}
              className="px-4 py-2 bg-blue-600/20 text-blue-400 rounded-lg hover:bg-blue-600/30"
            >
              View Sales Order
            </button>
          </div>
        </div>
      )}

      {/* Notes */}
      {order.notes && (
        <div className="bg-gray-900 border border-gray-800 rounded-xl p-6">
          <h2 className="text-lg font-semibold text-white mb-4">Notes</h2>
          <p className="text-gray-300">{order.notes}</p>
        </div>
      )}

      {/* Operation Scheduler Modal */}
      <OperationSchedulerModal
        isOpen={schedulerOpen}
        onClose={() => {
          setSchedulerOpen(false);
          setSelectedOperation(null);
        }}
        operation={selectedOperation}
        productionOrder={order}
        onScheduled={() => {
          toast.success("Operation scheduled successfully");
          fetchOrder({ silent: true });
        }}
      />
    </div>
  );
}
