/**
 * OrderWorkflowPanel - Order Workflow steps + secondary order actions row.
 *
 * Extracted from OrderDetail.jsx (DEBT-1 D1-C). Step logic, gating predicates
 * that only serve this panel, and markup moved verbatim. Shared order state
 * and shared predicates flow in via explicit props.
 */
import { useNavigate } from "react-router-dom";
import {
  AlertTriangle,
  CheckCircle2,
  Circle,
  CreditCard,
  Factory,
  FileText,
  Truck,
} from "lucide-react";
import {
  formatMoney,
  SHIPPED_ORDER_STATUSES,
  UNCONFIRMED_ORDER_STATUSES,
} from "./orderWorkflowUtils";

export default function OrderWorkflowPanel({
  order,
  orderInvoice,
  paymentSummary,
  productionOrders,
  materialRequirements,
  generatingInvoice,
  sendingInvoice,
  confirmingOrder,
  hasOrderProduct,
  hasMainProductWO,
  hasShipmentEvidence,
  isBillingReleaseSatisfied,
  getProductionComplete,
  getProductionReleaseBlockReason,
  onConfirmOrder,
  onCreateProductionOrder,
  onGenerateInvoice,
  onSendInvoice,
  onRecordPayment,
  onRejectOrder,
  onCancelOrder,
  onCloseShort,
  onDeleteOrder,
}) {
  const navigate = useNavigate();

  const canCancelOrder = () => {
    return order && ["pending", "confirmed", "on_hold"].includes(order.status);
  };

  const canCloseShort = () => {
    return (
      order &&
      !order.closed_short &&
      ["confirmed", "in_production", "ready_to_ship"].includes(order.status)
    );
  };

  const canDeleteOrder = () => {
    return order && ["cancelled", "pending"].includes(order.status);
  };

  const canGenerateInvoice = () => {
    const invoiceableStatuses = [
      "confirmed",
      "in_production",
      "ready_to_ship",
      "shipped",
      "delivered",
      "completed",
    ];
    return order && !orderInvoice && invoiceableStatuses.includes(order.status);
  };

  const getShipBlockReason = () => {
    if (!order) return "Order is still loading";
    if (SHIPPED_ORDER_STATUSES.has(order.status)) return "Order already shipped";
    if (productionOrders.length === 0) return "Create production order first";
    if (!getProductionComplete()) return "Production must be complete";
    if (materialRequirements.some((req) => req.net_shortage > 0)) {
      return "Material shortages must be resolved";
    }
    return "";
  };

  const canShipOrder = () => !getShipBlockReason();

  const getStepState = ({ done, active, blocked }) => {
    if (done) return "done";
    if (active) return "active";
    if (blocked) return "blocked";
    return "waiting";
  };

  const getStepClasses = (state) => {
    if (state === "done") {
      return {
        panel: "border-[var(--status-green)]/40 bg-[var(--status-green-tint)]",
        icon: "bg-[var(--status-green-tint)] text-[var(--status-green)]",
        label: "text-[var(--status-green)]",
      };
    }
    if (state === "active") {
      return {
        panel: "border-[var(--orange)]/50 bg-[var(--orange-tint)]",
        icon: "bg-[var(--orange-tint)] text-[var(--orange)]",
        label: "text-[var(--orange)]",
      };
    }
    if (state === "blocked") {
      return {
        panel: "border-[var(--status-amber)]/40 bg-[var(--status-amber-tint)]",
        icon: "bg-[var(--status-amber-tint)] text-[var(--status-amber)]",
        label: "text-[var(--status-amber)]",
      };
    }
    return {
      panel: "border-[var(--rule-hair)] bg-[var(--paper-sunk)]",
      icon: "bg-[var(--paper-sunk)] text-[var(--ink-3)]",
      label: "text-[var(--ink-3)]",
    };
  };

  const renderStepIcon = (step) => {
    if (step.state === "done") {
      return <CheckCircle2 className="h-5 w-5" />;
    }
    if (step.state === "blocked") {
      return <AlertTriangle className="h-5 w-5" />;
    }
    if (step.Icon) {
      return <step.Icon className="h-5 w-5" />;
    }
    return <Circle className="h-5 w-5" />;
  };

  const getOrderWorkflowSteps = () => {
    const status = order?.status || "";
    const orderConfirmed = !UNCONFIRMED_ORDER_STATUSES.has(status);
    const canConfirmOrder = ["pending", "pending_confirmation"].includes(status);
    const hasInvoice = Boolean(orderInvoice);
    const invoiceStatus = orderInvoice?.status || "";
    const hasPayment = Number(paymentSummary?.total_paid || 0) > 0;
    const billingReleased = isBillingReleaseSatisfied();
    const productionReleased = hasMainProductWO();
    const productionComplete = getProductionComplete();
    const shipped = SHIPPED_ORDER_STATUSES.has(status);
    // LEGACY-1: "done" requires evidence, not just a status claim.
    const shipmentEvidence = hasShipmentEvidence();
    const legacyMismatch = shipped && !shipmentEvidence;
    const noProductionNeeded = !hasOrderProduct();
    const releaseBlockReason = getProductionReleaseBlockReason();
    const shipBlockReason = getShipBlockReason();

    const billingAction = (() => {
      if (canGenerateInvoice()) {
        return {
          label: generatingInvoice ? "Creating..." : "Create Invoice",
          onClick: onGenerateInvoice,
          disabled: generatingInvoice,
        };
      }
      if (orderInvoice?.status === "draft") {
        return {
          label: sendingInvoice ? "Marking..." : "Mark Sent",
          onClick: onSendInvoice,
          disabled: sendingInvoice,
        };
      }
      if (!billingReleased && orderConfirmed) {
        return {
          label: "Record Payment",
          onClick: onRecordPayment,
        };
      }
      if (orderInvoice) {
        return {
          label: "Open Invoice",
          onClick: () => navigate(`/admin/invoices?invoice=${orderInvoice.id}`),
        };
      }
      return null;
    })();

    return [
      {
        id: "confirm",
        title: "Confirm Order",
        Icon: CheckCircle2,
        state: getStepState({
          done: orderConfirmed,
          active: canConfirmOrder,
          blocked: status === "draft",
        }),
        meta: canConfirmOrder ? "Needs review" : status.replace(/_/g, " "),
        detail: canConfirmOrder
          ? "Review customer, lines, pricing, shipping, and tax."
          : "Commercial order is ready for billing.",
        action: canConfirmOrder
          ? {
              label: confirmingOrder ? "Confirming..." : "Confirm",
              onClick: onConfirmOrder,
              disabled: confirmingOrder,
            }
          : null,
      },
      {
        id: "billing",
        title: "Invoice / Payment",
        Icon: hasInvoice ? FileText : CreditCard,
        state: getStepState({
          done: billingReleased,
          active: orderConfirmed && !billingReleased,
          blocked: !orderConfirmed,
        }),
        meta: hasInvoice
          ? `${orderInvoice.invoice_number} · ${invoiceStatus.replace(/_/g, " ")}`
          : hasPayment
          ? `${formatMoney(paymentSummary?.total_paid)} paid`
          : "Not released",
        detail: billingReleased
          ? "Billing requirement is satisfied for production release."
          : "Send an invoice or record payment before production.",
        action: billingAction,
      },
      {
        id: "production",
        title: "Production Orders",
        Icon: Factory,
        state: getStepState({
          done: productionReleased || noProductionNeeded,
          active: !productionReleased && !noProductionNeeded && !releaseBlockReason,
          blocked: Boolean(releaseBlockReason) && !productionReleased && !noProductionNeeded,
        }),
        meta: noProductionNeeded
          ? "No product line"
          : productionReleased
          ? `${productionOrders.length} work order${productionOrders.length === 1 ? "" : "s"}`
          : "Not released",
        detail: noProductionNeeded
          ? "No production release is required for service-only lines."
          : productionReleased
          ? "Work orders are created and linked. Open production to release, start, and complete them."
          : releaseBlockReason || "Ready to create work orders.",
        action: productionReleased && productionOrders.length > 0
          ? {
              label: "Open Work Order",
              onClick: () => navigate(`/admin/production/${productionOrders[0].id}`),
            }
          : !releaseBlockReason
          ? {
              label: "Create Work Orders",
              onClick: onCreateProductionOrder,
            }
          : null,
      },
      {
        id: "fulfillment",
        title: "Fulfillment",
        Icon: Truck,
        state: getStepState({
          done: shipped && shipmentEvidence,
          active: canShipOrder(),
          blocked: legacyMismatch || (!shipped && Boolean(shipBlockReason)),
        }),
        meta: legacyMismatch
          ? "Needs review"
          : shipped
          ? status.replace(/_/g, " ")
          : productionComplete
          ? "Ready to ship"
          : "Waiting",
        detail: legacyMismatch
          ? `Order status says ${status.replace(/_/g, " ")}, but no shipment was recorded.`
          : shipped
          ? "Shipment is already in progress or complete."
          : shipBlockReason || "Production is complete and materials are clear.",
        action: canShipOrder()
          ? {
              label: "Ship Order",
              onClick: () => navigate(`/admin/shipping?orderId=${order.id}`),
            }
          : null,
      },
    ];
  };

  return (
      <div className="rounded-xl border border-[var(--rule-hair)] bg-[var(--paper)] p-5 shadow-[var(--shadow-pop)]">
        <div className="mb-4 flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <h2 className="text-lg font-semibold text-[var(--ink)]">Order Workflow</h2>
            <p className="text-sm text-[var(--ink-3)]">
              Confirm, bill, release production, then fulfill.
            </p>
          </div>
          <span className="w-fit rounded-full bg-[var(--paper-sunk)] px-3 py-1 text-xs font-medium text-[var(--ink-2)]">
            {order.status?.replace(/_/g, " ") || "unknown"}
          </span>
        </div>
        <div className="grid grid-cols-1 gap-3 lg:grid-cols-4">
          {getOrderWorkflowSteps().map((step, index) => {
            const classes = getStepClasses(step.state);
            return (
              <div
                key={step.id}
                className={`flex min-h-[210px] flex-col rounded-lg border p-4 ${classes.panel}`}
              >
                <div className="flex items-start justify-between gap-3">
                  <div className="flex items-center gap-3">
                    <div className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-lg ${classes.icon}`}>
                      {renderStepIcon(step)}
                    </div>
                    <div>
                      <div className="text-xs font-semibold uppercase tracking-wide text-[var(--ink-4)]">
                        Step {index + 1}
                      </div>
                      <h3 className="text-sm font-semibold text-[var(--ink)]">
                        {step.title}
                      </h3>
                    </div>
                  </div>
                  <span className={`rounded-full bg-[var(--paper-sunk)] px-2 py-1 text-xs font-medium capitalize ${classes.label}`}>
                    {step.state}
                  </span>
                </div>

                <div className="mt-4 flex-1">
                  <div className={`text-sm font-medium capitalize ${classes.label}`}>
                    {step.meta || "Waiting"}
                  </div>
                  <p className="mt-2 text-sm leading-5 text-[var(--ink-2)]">
                    {step.detail}
                  </p>
                </div>

                {step.action && (
                  <button
                    onClick={step.action.onClick}
                    disabled={step.action.disabled}
                    className="mt-4 w-full rounded-lg bg-[var(--orange)] px-3 py-2 text-sm font-medium text-white hover:bg-[var(--orange-press)] disabled:cursor-not-allowed disabled:opacity-50"
                  >
                    {step.action.label}
                  </button>
                )}
              </div>
            );
          })}
        </div>

        {/* Secondary / destructive actions — below workflow steps */}
        {(order.status === "pending_confirmation" || canCancelOrder() || canCloseShort() || canDeleteOrder()) && (
          <div className="mt-4 flex flex-wrap items-center gap-3 border-t border-[var(--rule-hair)] pt-4">
            <span className="text-xs font-medium uppercase tracking-wide text-[var(--ink-4)]">
              Order actions:
            </span>
            {(order.status === "pending" || order.status === "pending_confirmation") && (
              <>
                <button
                  onClick={onConfirmOrder}
                  disabled={confirmingOrder}
                  className="rounded-lg bg-[var(--paper-sunk)] px-3 py-1.5 text-sm text-[var(--ink-2)] border border-[var(--rule-hair)] hover:bg-[var(--rule-hair)] disabled:opacity-50"
                >
                  {confirmingOrder ? "Confirming..." : "Confirm Order"}
                </button>
                {order.status === "pending_confirmation" && (
                  <button
                    onClick={onRejectOrder}
                    className="rounded-lg bg-[var(--status-red)] px-3 py-1.5 text-sm text-white hover:opacity-90"
                  >
                    Reject Order
                  </button>
                )}
              </>
            )}
            {canCancelOrder() && (
              <button
                onClick={onCancelOrder}
                className="rounded-lg bg-[var(--paper-sunk)] px-3 py-1.5 text-sm text-[var(--ink-2)] border border-[var(--rule-hair)] hover:bg-[var(--rule-hair)]"
              >
                Cancel Order
              </button>
            )}
            {canCloseShort() && (
              <button
                onClick={onCloseShort}
                className="rounded-lg bg-[var(--paper-sunk)] px-3 py-1.5 text-sm text-[var(--ink-2)] border border-[var(--rule-hair)] hover:bg-[var(--rule-hair)]"
              >
                Close Short
              </button>
            )}
            {canDeleteOrder() && (
              <button
                onClick={onDeleteOrder}
                className="rounded-lg bg-[var(--status-red)] px-3 py-1.5 text-sm text-white hover:opacity-90 border border-[var(--status-red)]"
              >
                Delete Order
              </button>
            )}
          </div>
        )}
      </div>
  );
}
