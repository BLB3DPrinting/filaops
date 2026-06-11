/**
 * ProductionOrderDetail - Production Order Command Center
 *
 * Detailed view for managing a single production order:
 * - Order status and progress
 * - Material requirements and availability
 * - Blocking issues analysis
 * - Action buttons (Release, Start, Complete, etc.)
 */
import { useState, useEffect, useCallback } from "react";
import { useParams, useNavigate } from "react-router-dom";
import {
  ArrowLeft,
  CheckCircle2,
  Circle,
  Clock3,
  Factory,
  FileText,
  PackageCheck,
  PlayCircle,
  RefreshCw,
} from "lucide-react";
import { useApi } from "../../hooks/useApi";
import { useToast } from "../../components/Toast";
import BlockingIssuesPanel from "../../components/orders/BlockingIssuesPanel";
import {
  OperationsPanel,
  OperationSchedulerModal,
  OperationsTimeline,
} from "../../components/production";
import ReleaseScheduleWizard from "../../components/production/ReleaseScheduleWizard";
import {
  PRODUCTION_ORDER_COLORS,
  getStatusColor,
} from "../../lib/statusColors.js";

const DONE_STATUSES = new Set(["complete", "completed", "closed"]);
const ACTIVE_STATUSES = new Set(["in_progress", "scheduled"]);

const formatStatusLabel = (status) =>
  (status || "unknown").replace(/_/g, " ");

function buildProductionWorkflowSteps(order) {
  const status = order?.status || "draft";
  const isReleased = status === "released";
  const isActive = ACTIVE_STATUSES.has(status);
  const isDone = DONE_STATUSES.has(status);

  return [
    {
      key: "draft",
      step: "Step 1",
      title: "Work Order",
      status: status === "draft" ? "current" : "done",
      headline: status === "draft" ? "Draft" : "Created",
      detail: order?.sales_order_id
        ? "Created from the sales order and waiting for shop release."
        : "Created for stock or internal production.",
      icon: FileText,
    },
    {
      key: "release",
      step: "Step 2",
      title: "Release",
      status: status === "draft" ? "waiting" : isReleased ? "current" : "done",
      headline:
        status === "draft"
          ? "Not Released"
          : isReleased
            ? "Released"
            : "Released",
      detail:
        status === "draft"
          ? "Release when material and commercial checks are satisfied."
          : "This order is released to production.",
      action: status === "draft" ? "release" : null,
      actionLabel: "Release to Floor",
      icon: CheckCircle2,
    },
    {
      key: "build",
      step: "Step 3",
      title: "Build",
      status: isDone
        ? "done"
        : isActive
          ? "current"
          : isReleased
            ? "waiting"
            : "blocked",
      headline: isActive
        ? "In Production"
        : isDone
          ? "Production Done"
          : isReleased
            ? "Ready to Start"
            : "Waiting",
      detail: isReleased
        ? "Start production when the operator is ready to run."
        : isActive
          ? "Operations are being worked on the floor."
          : isDone
            ? "Finished goods are ready for fulfillment."
            : "Release the work order before starting production.",
      action: isReleased ? "start" : null,
      actionLabel: "Start Production",
      icon: PlayCircle,
    },
    {
      key: "complete",
      step: "Step 4",
      title: "Complete",
      status: isDone ? "done" : isActive ? "waiting" : "blocked",
      headline: isDone ? "Complete" : isActive ? "Ready to Complete" : "Waiting",
      detail: isActive
        ? "Complete after the accepted quantity is produced."
        : isDone
          ? "Production is complete for this work order."
          : "Start production before completion.",
      action: isActive ? "complete" : null,
      actionLabel: "Complete Production",
      icon: PackageCheck,
    },
  ];
}

function WorkflowStepCard({ step, onAction, updating }) {
  const Icon = step.icon || Circle;
  const statusStyles = {
    done: {
      container: "border-emerald-500/50 bg-emerald-950/20",
      icon: "bg-emerald-500/20 text-emerald-300",
      label: "text-emerald-300",
      badge: "bg-emerald-500/20 text-emerald-200",
      badgeText: "Done",
    },
    current: {
      container: "border-blue-500/60 bg-blue-950/20",
      icon: "bg-blue-500/20 text-blue-300",
      label: "text-blue-300",
      badge: "bg-blue-500/20 text-blue-200",
      badgeText: "Current",
    },
    waiting: {
      container: "border-yellow-500/60 bg-yellow-950/20",
      icon: "bg-yellow-500/20 text-yellow-300",
      label: "text-yellow-300",
      badge: "bg-yellow-500/20 text-yellow-200",
      badgeText: "Waiting",
    },
    blocked: {
      container: "border-gray-700 bg-gray-950/30",
      icon: "bg-gray-800 text-gray-400",
      label: "text-gray-400",
      badge: "bg-gray-800 text-gray-400",
      badgeText: "Blocked",
    },
  };
  const styles = statusStyles[step.status] || statusStyles.blocked;

  return (
    <div className={`rounded-lg border p-4 ${styles.container}`}>
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-start gap-3">
          <div className={`rounded-lg p-2 ${styles.icon}`}>
            <Icon className="h-5 w-5" aria-hidden="true" />
          </div>
          <div>
            <div className="text-xs uppercase text-gray-500">{step.step}</div>
            <div className="text-sm font-semibold text-white">{step.title}</div>
          </div>
        </div>
        <span className={`rounded-full px-2 py-1 text-xs ${styles.badge}`}>
          {styles.badgeText}
        </span>
      </div>
      <div className={`mt-4 text-sm font-semibold ${styles.label}`}>
        {step.headline}
      </div>
      <p className="mt-2 min-h-10 text-sm text-gray-300">{step.detail}</p>
      {step.action && (
        <button
          type="button"
          onClick={() => onAction(step.action)}
          disabled={updating}
          className="mt-4 w-full rounded-lg bg-blue-600 px-3 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50"
        >
          {step.actionLabel}
        </button>
      )}
    </div>
  );
}

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
  // SCHED-3b: guided initial-schedule wizard
  const [wizardOpen, setWizardOpen] = useState(false);

  const fetchOrder = useCallback(async ({ silent = false } = {}) => {
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
  }, [api, orderId]);

  useEffect(() => {
    if (orderId) {
      // Route-driven data fetch updates loading/error state.
      // eslint-disable-next-line react-hooks/set-state-in-effect
      fetchOrder();
    }
  }, [fetchOrder, orderId]);

  const handleStatusUpdate = async (action) => {
    setUpdating(true);
    try {
      await api.post(`/api/v1/production-orders/${orderId}/${action}`);

      toast.success(`Order ${action} successfully`);
      fetchOrder();

      // SCHED-3b: after a successful release, offer the guided schedule wizard
      if (action === "release") {
        setWizardOpen(true);
      }
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

  const workflowSteps = buildProductionWorkflowSteps(order);
  const hasLinkedSalesOrder = Boolean(order.sales_order_id);

  const progress =
    order.quantity_ordered > 0
      ? Math.round((order.quantity_completed / order.quantity_ordered) * 100)
      : 0;

  return (
    <div className="space-y-6 p-6">
      {/* Header */}
      <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
        <div>
          <button
            onClick={() => navigate("/admin/production")}
            className="mb-2 inline-flex items-center gap-2 text-gray-400 hover:text-white"
          >
            <ArrowLeft className="h-4 w-4" aria-hidden="true" />
            Back to Production
          </button>
          <h1 className="text-2xl font-bold text-white">
            Production Order: {order.code}
          </h1>
          <div className="mt-1 flex flex-wrap items-center gap-2 text-sm text-gray-400">
            <span>Production Command Center</span>
            {hasLinkedSalesOrder && (
              <>
                <span className="text-gray-600">-</span>
                <button
                  type="button"
                  onClick={() => navigate(`/admin/orders/${order.sales_order_id}`)}
                  className="inline-flex items-center gap-1 text-blue-300 hover:text-blue-200"
                >
                  <FileText className="h-4 w-4" aria-hidden="true" />
                  {order.sales_order_code || `SO-${order.sales_order_id}`}
                </button>
              </>
            )}
          </div>
        </div>
        <div className="flex flex-wrap gap-2">
          <button
            onClick={fetchOrder}
            className="inline-flex items-center gap-2 rounded-lg bg-gray-700 px-4 py-2 text-white hover:bg-gray-600"
          >
            <RefreshCw className="h-4 w-4" aria-hidden="true" />
            Refresh
          </button>
          {order.status === "draft" && (
            <button
              onClick={() => handleStatusUpdate("release")}
              disabled={updating}
              className="inline-flex items-center gap-2 rounded-lg bg-blue-600 px-4 py-2 text-white hover:bg-blue-700 disabled:opacity-50"
            >
              <CheckCircle2 className="h-4 w-4" aria-hidden="true" />
              Release to Floor
            </button>
          )}
          {order.status === "released" && (
            <button
              onClick={() => handleStatusUpdate("start")}
              disabled={updating}
              className="inline-flex items-center gap-2 rounded-lg bg-purple-600 px-4 py-2 text-white hover:bg-purple-700 disabled:opacity-50"
            >
              <PlayCircle className="h-4 w-4" aria-hidden="true" />
              Start Production
            </button>
          )}
          {ACTIVE_STATUSES.has(order.status) && (
            <button
              onClick={() => handleStatusUpdate("complete")}
              disabled={updating}
              className="inline-flex items-center gap-2 rounded-lg bg-green-600 px-4 py-2 text-white hover:bg-green-700 disabled:opacity-50"
            >
              <PackageCheck className="h-4 w-4" aria-hidden="true" />
              Complete Production
            </button>
          )}
        </div>
      </div>

      {/* Production Workflow */}
      <div className="rounded-xl border border-blue-700/40 bg-blue-950/20 p-6">
        <div className="mb-4 flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <h2 className="flex items-center gap-2 text-lg font-semibold text-white">
              <Factory className="h-5 w-5 text-blue-300" aria-hidden="true" />
              Production Workflow
            </h2>
            <p className="mt-1 text-sm text-gray-400">
              Draft, release, run, then complete the work order.
            </p>
          </div>
          <span className="inline-flex w-fit items-center gap-2 rounded-full bg-gray-800 px-3 py-1 text-sm text-gray-300">
            <Clock3 className="h-4 w-4" aria-hidden="true" />
            {formatStatusLabel(order.status)}
          </span>
        </div>
        <div className="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-4">
          {workflowSteps.map((step) => (
            <WorkflowStepCard
              key={step.key}
              step={step}
              onAction={handleStatusUpdate}
              updating={updating}
            />
          ))}
        </div>
      </div>

      {/* Order Summary */}
      <div className="bg-gray-900 border border-gray-800 rounded-xl p-6">
        <h2 className="text-lg font-semibold text-white mb-4">Order Summary</h2>
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-5">
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
              {formatStatusLabel(order.status)}
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
          <div className="mb-4 flex items-center gap-2">
            <FileText className="h-5 w-5 text-blue-300" aria-hidden="true" />
            <h2 className="text-lg font-semibold text-white">
              Linked Sales Order
            </h2>
          </div>
          <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
            <div>
              <p className="text-white font-medium">
                {order.sales_order_code || `SO-${order.sales_order_id}`}
              </p>
              <p className="text-gray-400 text-sm">
                {order.customer_name || "Customer"} - Open the sales order for
                invoice, payment, and shipment controls.
              </p>
            </div>
            <button
              onClick={() => navigate(`/admin/orders/${order.sales_order_id}`)}
              className="inline-flex items-center justify-center gap-2 rounded-lg bg-blue-600/20 px-4 py-2 text-blue-300 hover:bg-blue-600/30"
            >
              <ArrowLeft className="h-4 w-4 rotate-180" aria-hidden="true" />
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

      {/* SCHED-3b: Guided initial-schedule wizard (shown after release) */}
      <ReleaseScheduleWizard
        isOpen={wizardOpen}
        productionOrder={order}
        onClose={() => setWizardOpen(false)}
        onOpenScheduler={() => {
          setWizardOpen(false);
          // Open the scheduler for the first pending op, if any
          setSchedulerOpen(true);
        }}
        onRefresh={() => fetchOrder({ silent: true })}
      />

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
