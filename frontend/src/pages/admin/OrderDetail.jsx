/**
 * OrderDetail - Order Command Center
 *
 * Comprehensive view for managing order fulfillment:
 * - Order header and line items
 * - Material requirements (BOM explosion)
 * - Capacity requirements (routing explosion)
 * - Action buttons (Create WO, Create PO, Schedule)
 */
import { useState, useEffect } from "react";
import { useParams, useNavigate } from "react-router-dom";
import {
  AlertTriangle,
  CheckCircle2,
  Circle,
  CreditCard,
  Factory,
  FileText,
  Truck,
} from "lucide-react";
import { useApi } from "../../hooks/useApi";
import { useToast } from "../../components/Toast";
import { API_URL } from "../../config/api";
import RecordPaymentModal from "../../components/payments/RecordPaymentModal";
import ActivityTimeline from "../../components/ActivityTimeline";
import ShippingTimeline from "../../components/ShippingTimeline";
import BlockingIssuesPanel from "../../components/orders/BlockingIssuesPanel";
import FulfillmentProgress from "../../components/orders/FulfillmentProgress";
import { useFulfillmentStatus } from "../../hooks/useFulfillmentStatus";
import { ProductionProgressSummary, ProductionOrderStatusCard } from "../../components/orders/ProductionStatusCards";
import MaterialRequirementsSection from "../../components/orders/MaterialRequirementsSection";
import CapacityRequirementsSection from "../../components/orders/CapacityRequirementsSection";
import PaymentsSection from "../../components/orders/PaymentsSection";
import ShippingAddressSection from "../../components/orders/ShippingAddressSection";
import { CancelOrderModal, DeleteOrderModal } from "../../components/orders/OrderModals";
import ReleaseScheduleWizard from "../../components/production/ReleaseScheduleWizard";

const getInvoiceBalanceDue = (invoice) =>
  invoice?.balance_due ?? invoice?.amount_due ?? 0;

const formatMoney = (value) => `$${parseFloat(value || 0).toFixed(2)}`;

const COMPLETE_PRODUCTION_STATUSES = new Set(["complete", "completed", "closed"]);
const SHIPPED_ORDER_STATUSES = new Set(["shipped", "delivered", "completed"]);
const UNCONFIRMED_ORDER_STATUSES = new Set(["draft", "pending", "pending_confirmation"]);
// LEGACY-1: order-level fulfillment_status values that count as shipment
// evidence (order_status.py sets "shipped"/"delivered"; "fulfilled" is
// accepted defensively for older data).
const SHIPMENT_EVIDENCE_FULFILLMENT_STATUSES = new Set([
  "fulfilled",
  "shipped",
  "delivered",
]);

export default function OrderDetail() {
  const { orderId } = useParams();
  const navigate = useNavigate();
  const toast = useToast();
  const api = useApi();

  const [order, setOrder] = useState(null);
  const [materialRequirements, setMaterialRequirements] = useState([]);
  const [capacityRequirements, setCapacityRequirements] = useState([]);
  const [productionOrders, setProductionOrders] = useState([]);
  const [loading, setLoading] = useState(true);

  const hasOrderProduct = () => {
    return Boolean(
      order?.product_id ||
        order?.lines?.some((line) => Boolean(line.product_id))
    );
  };

  const hasMainProductWO = () => {
    // Cancelled WOs are not coverage — mirrored in
    // generate_production_orders() (backend) — keep in sync.
    const activePOs = productionOrders.filter(
      (po) => po.status !== "cancelled"
    );
    const productLines = order?.lines?.filter((line) => line.product_id) || [];
    if (productLines.length > 0) {
      const woLineIds = new Set(
        activePOs
          .map((po) => po.sales_order_line_id)
          .filter((lineId) => lineId !== null && lineId !== undefined)
      );
      // LEGACY-1 fallback: WOs created before line-level linkage existed
      // have sales_order_line_id = null. Treat such a WO as covering every
      // line with the same product_id (coverage check, not assignment).
      // Mirrored in generate_production_orders() in
      // backend/app/services/sales_order_service.py — keep in sync.
      const legacyCoveredProductIds = new Set(
        activePOs
          .filter(
            (po) =>
              po.sales_order_line_id === null ||
              po.sales_order_line_id === undefined
          )
          .map((po) => po.product_id)
      );
      return productLines.every(
        (line) =>
          woLineIds.has(line.id) || legacyCoveredProductIds.has(line.product_id)
      );
    }
    if (order?.product_id) {
      return activePOs.some((po) => po.product_id === order.product_id);
    }
    return false;
  };

  // LEGACY-1: shipment evidence — did anything actually ship?
  const hasShipmentEvidence = () => {
    if (!order) return false;
    if (order.shipped_at) return true;
    if (SHIPMENT_EVIDENCE_FULFILLMENT_STATUSES.has(order.fulfillment_status)) {
      return true;
    }
    return (order.lines || []).some(
      (line) => parseFloat(line.shipped_quantity || 0) > 0
    );
  };

  // Mismatch: status claims shipped/delivered/completed, but no shipment
  // was ever recorded — legacy data from an older FilaOps version.
  const isLegacyFulfillmentMismatch = () =>
    Boolean(order) &&
    SHIPPED_ORDER_STATUSES.has(order.status) &&
    !hasShipmentEvidence();

  const [error, setError] = useState(null);
  const [exploding, setExploding] = useState(false);
  const [paymentSummary, setPaymentSummary] = useState(null);
  const [payments, setPayments] = useState([]);
  const [showPaymentModal, setShowPaymentModal] = useState(false);
  const [isRefund, setIsRefund] = useState(false);

  // Cancel/Delete modal state
  const [showCancelModal, setShowCancelModal] = useState(false);
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);

  // Confirm/Reject external order state
  const [showRejectModal, setShowRejectModal] = useState(false);
  const [rejectReason, setRejectReason] = useState("");
  const [confirmingOrder, setConfirmingOrder] = useState(false);

  // Invoice generation state
  const [generatingInvoice, setGeneratingInvoice] = useState(false);
  const [orderInvoice, setOrderInvoice] = useState(null);
  const [invoiceLoading, setInvoiceLoading] = useState(false);
  const [sendingInvoice, setSendingInvoice] = useState(false);

  const isBillingReleaseSatisfied = () => {
    const invoiceStatus = orderInvoice?.status || "";
    const totalPaid = Number(paymentSummary?.total_paid || 0);
    return (
      order?.payment_status === "paid" ||
      totalPaid > 0 ||
      ["sent", "partially_paid", "paid"].includes(invoiceStatus)
    );
  };

  const getProductionReleaseBlockReason = () => {
    if (!order) return "Order is still loading";
    if (!hasOrderProduct()) return "Order must have a product line";
    if (hasMainProductWO()) return "Production order already exists";
    // Mirror the backend rule exactly: status must be "confirmed" (not merely past-unconfirmed)
    if (order.status !== "confirmed") {
      if (UNCONFIRMED_ORDER_STATUSES.has(order.status)) {
        return "Order must be confirmed before production release";
      }
      return `Work orders can only be created while the order is in Confirmed status; this order is ${order.status.replace(/_/g, " ")}.`;
    }
    if (!isBillingReleaseSatisfied()) {
      return "Create/send an invoice or record payment before production release";
    }
    return "";
  };

  const canGenerateProductionOrder = () => !getProductionReleaseBlockReason();

  // Line editing state
  const [editingLineId, setEditingLineId] = useState(null);
  const [editQty, setEditQty] = useState("");
  const [editPrice, setEditPrice] = useState("");
  const [editReason, setEditReason] = useState("");
  const [savingLineEdit, setSavingLineEdit] = useState(false);
  const [removingLineId, setRemovingLineId] = useState(null);

  // Close short state
  const [showCloseShortModal, setShowCloseShortModal] = useState(false);
  const [closeShortReason, setCloseShortReason] = useState("");
  const [closingShort, setClosingShort] = useState(false);
  const [closeShortPreview, setCloseShortPreview] = useState(null);
  const [loadingPreview, setLoadingPreview] = useState(false);

  // Refresh state
  const [refreshing, setRefreshing] = useState(false);

  // LEGACY-1: legacy fulfillment resolution state
  // legacyResolveAction is "close_out" | "reopen" | null (null = modal closed)
  const [legacyResolveAction, setLegacyResolveAction] = useState(null);
  const [resolvingLegacy, setResolvingLegacy] = useState(false);

  // SCHED-3b: guided schedule wizard state
  // wizardPending=true means we're waiting for fetchProductionOrders to
  // resolve so we can hand the new PO to the wizard.
  const [wizardPending, setWizardPending] = useState(false);
  const [wizardOpen, setWizardOpen] = useState(false);
  const [wizardProductionOrder, setWizardProductionOrder] = useState(null);
  // Codes returned by generate-production-orders — the wizard must target
  // one of THESE, not whatever sorts first in productionOrders.
  const [wizardTargetCodes, setWizardTargetCodes] = useState([]);

  // Collapsible sections state
  const [expandedSections, setExpandedSections] = useState({
    materialRequirements: true,
    capacityRequirements: true,
    productionOrders: true,
    payments: true,
  });

  // Material availability check state
  const [checkingAvailability, setCheckingAvailability] = useState(false);
  const [materialAvailability, setMaterialAvailability] = useState(null);

  // Fulfillment status hook (UI-302)
  const {
    data: fulfillmentStatus,
    loading: fulfillmentLoading,
    error: fulfillmentError,
    refetch: refetchFulfillment,
  } = useFulfillmentStatus(orderId);

  const explodeBOM = async (productId, quantity) => {
    setExploding(true);
    try {
      // PRIMARY: Use the new material-requirements endpoint (routing-first approach)
      try {
        const matReqData = await api.get(
          `/api/v1/sales-orders/${orderId}/material-requirements`
        );

        const requirements = (matReqData.requirements || []).map((req) => ({
          product_id: req.product_id,
          product_sku: req.product_sku || "",
          product_name: req.product_name || "",
          gross_quantity: parseFloat(req.quantity_required || 0),
          net_shortage: parseFloat(req.quantity_short || 0),
          on_hand_quantity: parseFloat(req.quantity_available || 0),
          available_quantity: parseFloat(req.quantity_available || 0),
          unit_cost: 0,
          has_bom: req.has_bom || false,
          operation_code: req.operation_code || null,
          material_source: req.material_source || "bom",
          has_incoming_supply: req.has_incoming_supply || false,
          incoming_supply_details: req.incoming_supply_details || null,
        }));
        setMaterialRequirements(requirements);
        setMaterialAvailability(matReqData.summary);
      } catch {
        // FALLBACK: Use the MRP requirements endpoint
        try {
          const data = await api.get(
            `/api/v1/mrp/requirements?product_id=${productId}`
          );

          const scaled = (data.requirements || []).map((req) => {
            const gross_qty = parseFloat(req.gross_quantity || 0) * quantity;
            const available_qty = parseFloat(req.available_quantity || 0);
            const incoming_qty = parseFloat(req.incoming_quantity || 0) || 0;
            const safety_stock = parseFloat(req.safety_stock || 0) || 0;

            const available_supply = available_qty + incoming_qty;
            let net_shortage = gross_qty - available_supply + safety_stock;

            if (net_shortage < 0) {
              net_shortage = 0;
            }

            return {
              product_id: req.product_id,
              product_sku: req.product_sku || "",
              product_name: req.product_name || "",
              gross_quantity: gross_qty,
              net_shortage: net_shortage,
              on_hand_quantity: parseFloat(req.on_hand_quantity || 0),
              available_quantity: available_qty,
              unit_cost: parseFloat(req.unit_cost || 0),
              has_bom: req.has_bom || false,
              operation_code: null,
              material_source: "bom",
            };
          });
          setMaterialRequirements(scaled);
        } catch {
          // If MRP endpoint fails, try BOM explosion directly
          try {
            const bomData = await api.get(
              `/api/v1/mrp/explode-bom/${productId}?quantity=${quantity}`
            );

            const requirements = (bomData.components || []).map((comp) => ({
              product_id: comp.product_id,
              product_sku: comp.product_sku,
              product_name: comp.product_name,
              gross_quantity: parseFloat(comp.gross_quantity || 0),
              net_shortage: parseFloat(comp.gross_quantity || 0),
              on_hand_quantity: 0,
              available_quantity: 0,
              unit_cost: 0,
              has_bom: comp.has_bom || false,
              operation_code: null,
              material_source: "bom",
            }));
            setMaterialRequirements(requirements);
          } catch {
            // All BOM endpoints failed - material requirements section will be empty
          }
        }
      }

      // Get routing for capacity requirements (optional)
      try {
        const routing = await api.get(
          `/api/v1/routings/product/${productId}`
        );

        if (routing.operations && routing.operations.length > 0) {
          const capacity = routing.operations.map((op) => {
            const setupTime = parseFloat(op.setup_time_minutes) || 0;
            const runTime = parseFloat(op.run_time_minutes) || 0;
            return {
              ...op,
              setup_time_minutes: setupTime,
              run_time_minutes: runTime,
              total_time_minutes: setupTime + runTime * quantity,
              work_center_name:
                op.work_center?.name || op.work_center_name || "N/A",
              operation_name:
                op.operation_name || op.operation_code || "Operation",
            };
          });
          setCapacityRequirements(capacity);
        }
      } catch {
        // Routing is optional - don't fail
      }
    } catch {
      // BOM explosion failure - material requirements section will be empty
    } finally {
      setExploding(false);
    }
  };

  const fetchOrder = async () => {
    setLoading(true);
    setError(null);

    try {
      const data = await api.get(`/api/v1/sales-orders/${orderId}`);
      setOrder(data);

      // Explode BOM for material requirements
      if (
        data.order_type === "line_item" &&
        data.lines &&
        data.lines.length > 0
      ) {
        const firstLine = data.lines[0];
        if (firstLine.product_id) {
          await explodeBOM(firstLine.product_id, firstLine.quantity);
        }
      } else if (data.product_id) {
        await explodeBOM(data.product_id, data.quantity);
      } else if (data.quote_id) {
        try {
          const quoteData = await api.get(`/api/v1/quotes/${data.quote_id}`);
          if (quoteData.product_id) {
            await explodeBOM(quoteData.product_id, data.quantity);
          }
        } catch {
          // Quote fetch failure is non-critical
        }
      }
    } catch (err) {
      setError(err.message || "Failed to fetch order");
      throw err;
    } finally {
      setLoading(false);
    }
  };

  const fetchProductionOrders = async () => {
    if (!orderId) return;
    try {
      const data = await api.get(
        `/api/v1/production-orders?sales_order_id=${orderId}`
      );
      setProductionOrders(data.items || data || []);
    } catch {
      // Production orders fetch failure is non-critical
    }
  };

  const fetchPaymentData = async () => {
    if (!orderId) return;
    try {
      const summary = await api.get(
        `/api/v1/payments/order/${orderId}/summary`
      );
      setPaymentSummary(summary);
    } catch {
      // Payment summary fetch failure is non-critical
    }
    try {
      const data = await api.get(`/api/v1/payments?order_id=${orderId}`);
      setPayments(data.items || []);
    } catch {
      // Payment list fetch failure is non-critical
    }
  };

  const fetchOrderInvoice = async ({ shouldApply = () => true } = {}) => {
    if (!orderId) return null;
    if (shouldApply()) {
      setInvoiceLoading(true);
    }
    try {
      const data = await api.get(
        `/api/v1/invoices?sales_order_id=${orderId}&limit=1`
      );
      const invoices = data.items || data || [];
      const invoice = invoices.length > 0 ? invoices[0] : null;
      if (shouldApply()) {
        setOrderInvoice(invoice);
      }
      return invoice;
    } catch {
      if (shouldApply()) {
        setOrderInvoice(null);
      }
      return null;
    } finally {
      if (shouldApply()) {
        setInvoiceLoading(false);
      }
    }
  };

  useEffect(() => {
    if (!orderId) return undefined;
    let cancelled = false;
    const shouldApply = () => !cancelled;

    void (async () => {
      try {
        await Promise.all([
          fetchOrder(),
          fetchProductionOrders(),
          fetchPaymentData(),
          fetchOrderInvoice({ shouldApply }),
        ]);
      } catch {
        // Individual fetchers own user-visible error state.
      }
    })();

    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [orderId]);

  // SCHED-3b: open the wizard once productionOrders is populated after release
  useEffect(() => {
    if (!wizardPending || productionOrders.length === 0) return;
    // Target a WO created by THIS generate call (matched by code). If codes
    // are unavailable (older API shape), fall back to the newest WO for this
    // order rather than index 0.
    const target = wizardTargetCodes.length
      ? productionOrders.find((po) => wizardTargetCodes.includes(po.code))
      : [...productionOrders].sort(
          (a, b) => new Date(b.created_at || 0) - new Date(a.created_at || 0)
        )[0];
    if (!target) return; // refetch hasn't caught up with the new WO yet
    setWizardPending(false);
    setWizardTargetCodes([]);
    setWizardProductionOrder(target);
    setWizardOpen(true);
  }, [wizardPending, wizardTargetCodes, productionOrders]);

  const handlePaymentRecorded = () => {
    setShowPaymentModal(false);
    setIsRefund(false);
    fetchPaymentData();
    fetchOrder();
    fetchOrderInvoice();
    toast.success(isRefund ? "Refund recorded" : "Payment recorded");
  };

  const handleRefresh = async () => {
    setRefreshing(true);
    try {
      await Promise.all([
        fetchOrder(),
        fetchProductionOrders(),
        fetchPaymentData(),
        fetchOrderInvoice(),
      ]);
      toast.success("Data refreshed");
    } catch {
      toast.error("Failed to refresh");
    } finally {
      setRefreshing(false);
    }
  };

  const handleCreateProductionOrder = async () => {
    const blockReason = getProductionReleaseBlockReason();
    if (blockReason) {
      toast.error(blockReason);
      return;
    }

    try {
      const result = await api.post(
        `/api/v1/sales-orders/${orderId}/generate-production-orders`
      );

      toast.success("Production order created successfully!");
      fetchProductionOrders();
      fetchOrder();

      // SCHED-3b: offer the guided schedule wizard after release.
      // Remember WHICH orders this call created (by code) so the wizard
      // targets a newly created WO, not whatever happens to sort first.
      setWizardTargetCodes(result?.created_orders || []);
      setWizardPending(true);
    } catch (err) {
      toast.error(err.message);
    }
  };

  const handleCreatePurchaseOrder = async (materialReq) => {
    navigate(
      `/admin/purchasing?material_id=${materialReq.product_id}&qty=${materialReq.net_shortage}`
    );
  };

  const handleCreateWorkOrder = async (materialReq) => {
    try {
      await api.post(`/api/v1/production-orders`, {
        product_id: materialReq.product_id,
        quantity_ordered: Math.ceil(materialReq.net_shortage || 1),
        sales_order_id: parseInt(orderId),
        notes: `Created from SO ${order.order_number} for sub-assembly`,
      });

      toast.success(`Work order created for ${materialReq.product_name}`);
      fetchOrder();
      fetchProductionOrders();
    } catch (err) {
      toast.error(err.message);
    }
  };

  const canCancelOrder = () => {
    return order && ["pending", "confirmed", "on_hold"].includes(order.status);
  };

  const handleCancelOrder = async (cancellationReason) => {
    try {
      await api.post(`/api/v1/sales-orders/${orderId}/cancel`, {
        cancellation_reason: cancellationReason,
      });

      toast.success(`Order ${order.order_number} cancelled`);
      setShowCancelModal(false);
      fetchOrder();
    } catch (err) {
      toast.error(err.message || "Failed to cancel order");
    }
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

  const openCloseShortModal = async () => {
    setLoadingPreview(true);
    try {
      const preview = await api.get(`/api/v1/sales-orders/${orderId}/close-short-preview`);
      setCloseShortPreview(preview);
      setShowCloseShortModal(true);
    } catch (err) {
      toast.error(err.message || "Failed to load close-short preview");
    } finally {
      setLoadingPreview(false);
    }
  };

  const handleCloseShort = async () => {
    if (!closeShortReason.trim()) return;
    setClosingShort(true);
    try {
      await api.post(`/api/v1/sales-orders/${orderId}/close-short`, {
        reason: closeShortReason,
      });
      toast.success(`Order ${order.order_number} closed short → Ready to Ship`);
      setShowCloseShortModal(false);
      setCloseShortReason("");
      setCloseShortPreview(null);
      fetchOrder();
      fetchProductionOrders();
      refetchFulfillment();
    } catch (err) {
      toast.error(err.message || "Failed to close order short");
    } finally {
      setClosingShort(false);
    }
  };

  // LEGACY-1: resolve a legacy fulfillment mismatch (close_out | reopen)
  const handleResolveLegacyFulfillment = async () => {
    if (!legacyResolveAction) return;
    setResolvingLegacy(true);
    try {
      await api.post(
        `/api/v1/sales-orders/${orderId}/resolve-legacy-fulfillment`,
        { action: legacyResolveAction }
      );
      toast.success(
        legacyResolveAction === "close_out"
          ? `Order ${order.order_number} closed out — fulfillment recorded`
          : `Order ${order.order_number} reopened — ready to ship`
      );
      setLegacyResolveAction(null);
      fetchOrder();
      fetchProductionOrders();
      refetchFulfillment();
    } catch (err) {
      toast.error(err.message || "Failed to resolve legacy fulfillment");
    } finally {
      setResolvingLegacy(false);
    }
  };

  const handleSaveLineEdit = async (lineId) => {
    if ((editQty === "" && editPrice === "") || !editReason.trim()) return;
    setSavingLineEdit(true);
    try {
      await api.patch(`/api/v1/sales-orders/${orderId}/lines`, {
        lines: [{
          line_id: lineId,
          new_quantity: editQty !== "" ? parseFloat(editQty) : undefined,
          new_unit_price: editPrice !== "" ? parseFloat(editPrice) : undefined,
          reason: editReason,
        }],
      });
      toast.success("Line updated");
      setEditingLineId(null);
      setEditQty("");
      setEditPrice("");
      setEditReason("");
      fetchOrder();
    } catch (err) {
      toast.error(err.message || "Failed to update line");
    } finally {
      setSavingLineEdit(false);
    }
  };

  const handleRemoveLine = async (line) => {
    const label = line.product_name || line.material_name || line.description || `Line ${line.id}`;
    if (!window.confirm(`Remove "${label}" from this order? This cannot be undone.`)) return;
    setRemovingLineId(line.id);
    try {
      await api.del(`/api/v1/sales-orders/${orderId}/lines/${line.id}`);
      toast.success(`${label} removed from order`);
      fetchOrder();
    } catch (err) {
      toast.error(err.message || "Failed to remove line");
    } finally {
      setRemovingLineId(null);
    }
  };

  const canEditLines = () => {
    return order && ["pending", "confirmed", "in_production", "on_hold"].includes(order.status);
  };

  const handleConfirmOrder = async () => {
    setConfirmingOrder(true);
    try {
      if (order.status === "pending_confirmation") {
        await api.post(`/api/v1/sales-orders/${orderId}/confirm`);
      } else {
        await api.patch(`/api/v1/sales-orders/${orderId}/status`, {
          status: "confirmed",
        });
      }
      toast.success(`Order ${order.order_number} confirmed`);
      const refreshResults = await Promise.allSettled([
        fetchOrder(),
        fetchOrderInvoice(),
        fetchPaymentData(),
        fetchProductionOrders(),
        refetchFulfillment(),
      ]);
      if (refreshResults.some((result) => result.status === "rejected")) {
        toast.error("Order confirmed, but some related data failed to refresh");
      }
    } catch (err) {
      toast.error(err.message || "Failed to confirm order");
    } finally {
      setConfirmingOrder(false);
    }
  };

  const handleAcceptShortPO = async (po) => {
    if (!confirm(`Accept short on ${po.code || `WO-${po.id}`}? This will complete it with ${po.quantity_completed}/${po.quantity_ordered} units.`)) return;
    try {
      await api.post(`/api/v1/production-orders/${po.id}/accept-short`);
      toast.success(`${po.code || `WO-${po.id}`} accepted short (${po.quantity_completed}/${po.quantity_ordered})`);
      fetchOrder();
      fetchProductionOrders();
      refetchFulfillment();
    } catch (err) {
      toast.error(err.message || "Failed to accept short");
    }
  };

  const [rejectingOrder, setRejectingOrder] = useState(false);

  const handleRejectOrder = async () => {
    if (!rejectReason.trim()) return;
    setRejectingOrder(true);
    try {
      await api.post(`/api/v1/sales-orders/${orderId}/reject`, {
        reason: rejectReason,
      });
      toast.success(`Order ${order.order_number} rejected`);
      setShowRejectModal(false);
      setRejectReason("");
      fetchOrder();
    } catch (err) {
      toast.error(err.message || "Failed to reject order");
    } finally {
      setRejectingOrder(false);
    }
  };

  const handleDeleteOrder = async () => {
    try {
      await api.del(`/api/v1/sales-orders/${orderId}`);

      toast.success(`Order ${order.order_number} deleted`);
      navigate("/admin/orders");
    } catch (err) {
      toast.error(err.message || "Failed to delete order");
    }
  };

  const handleGenerateInvoice = async () => {
    setGeneratingInvoice(true);
    try {
      const invoice = await api.post("/api/v1/invoices", {
        sales_order_id: order.id,
      });
      setOrderInvoice(invoice);
      toast.success(`Invoice ${invoice.invoice_number} created`);
      await Promise.all([fetchOrder(), fetchOrderInvoice(), fetchPaymentData()]);
    } catch (err) {
      toast.error(err.response?.data?.detail || err.message || "Failed to generate invoice");
    } finally {
      setGeneratingInvoice(false);
    }
  };

  const handleSendOrderInvoice = async () => {
    if (!orderInvoice) return;
    setSendingInvoice(true);
    try {
      const invoice = await api.post(`/api/v1/invoices/${orderInvoice.id}/send`);
      setOrderInvoice(invoice);
      toast.success(`Invoice ${invoice.invoice_number} marked as sent`);
    } catch (err) {
      toast.error(err.response?.data?.detail || err.message || "Failed to mark invoice sent");
    } finally {
      setSendingInvoice(false);
    }
  };

  const handleDownloadOrderInvoice = async () => {
    if (!orderInvoice) return;
    try {
      const response = await fetch(
        `${API_URL}/api/v1/invoices/${orderInvoice.id}/pdf`,
        { credentials: "include" }
      );
      if (!response.ok) throw new Error("Failed to download invoice PDF");
      const blob = await response.blob();
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `${orderInvoice.invoice_number || "invoice"}.pdf`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      window.URL.revokeObjectURL(url);
    } catch (err) {
      toast.error(err.message || "Failed to download invoice PDF");
    }
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

  const getProductionComplete = () => {
    return (
      productionOrders.length > 0 &&
      productionOrders.every((po) => COMPLETE_PRODUCTION_STATUSES.has(po.status))
    );
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
        panel: "border-emerald-500/40 bg-emerald-950/20",
        icon: "bg-emerald-500/20 text-emerald-300",
        label: "text-emerald-300",
      };
    }
    if (state === "active") {
      return {
        panel: "border-blue-500/50 bg-blue-950/30",
        icon: "bg-blue-500/20 text-blue-300",
        label: "text-blue-300",
      };
    }
    if (state === "blocked") {
      return {
        panel: "border-amber-500/40 bg-amber-950/20",
        icon: "bg-amber-500/20 text-amber-300",
        label: "text-amber-300",
      };
    }
    return {
      panel: "border-gray-700 bg-gray-900/60",
      icon: "bg-gray-800 text-gray-400",
      label: "text-gray-400",
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
          onClick: handleGenerateInvoice,
          disabled: generatingInvoice,
        };
      }
      if (orderInvoice?.status === "draft") {
        return {
          label: sendingInvoice ? "Marking..." : "Mark Sent",
          onClick: handleSendOrderInvoice,
          disabled: sendingInvoice,
        };
      }
      if (!billingReleased && orderConfirmed) {
        return {
          label: "Record Payment",
          onClick: () => {
            setIsRefund(false);
            setShowPaymentModal(true);
          },
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
              onClick: handleConfirmOrder,
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
              onClick: handleCreateProductionOrder,
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

  if (loading) {
    return (
      <div className="flex items-center justify-center h-screen">
        <div className="text-white">Loading order...</div>
      </div>
    );
  }

  if (error || !order) {
    return (
      <div className="flex items-center justify-center h-screen">
        <div className="text-red-400">Error: {error || "Order not found"}</div>
      </div>
    );
  }

  const handleCheckAvailability = async () => {
    if (!hasOrderProduct()) {
      toast.error("Order must have a product to check availability");
      return;
    }

    setCheckingAvailability(true);
    try {
      if (productionOrders.length > 0) {
        const availabilityChecks = await Promise.all(
          productionOrders.map(async (po) => {
            try {
              return await api.get(
                `/api/v1/production-orders/${po.id}/material-availability`
              );
            } catch {
              return null;
            }
          })
        );
        setMaterialAvailability(availabilityChecks.filter(Boolean));
      } else {
        toast.info("Create a production order first to check material availability");
      }
    } catch {
      toast.error("Failed to check availability");
    } finally {
      setCheckingAvailability(false);
    }
  };

  const toggleSection = (section) => {
    setExpandedSections((prev) => ({
      ...prev,
      [section]: !prev[section],
    }));
  };

  return (
    <div className="space-y-6 p-6">
      {/* Header */}
      <div className="flex justify-between items-center">
        <div>
          <button
            onClick={() => navigate("/admin/orders")}
            className="text-gray-400 hover:text-white mb-2"
          >
            &larr; Back to Orders
          </button>
          <h1 className="text-2xl font-bold text-white">
            Order: {order.order_number}
          </h1>
          <p className="text-gray-400 mt-1">Order Command Center</p>
        </div>
        <div className="flex gap-2">
          <button
            onClick={handleRefresh}
            disabled={refreshing}
            className="px-4 py-2 bg-gray-700 text-white rounded-lg hover:bg-gray-600 disabled:opacity-50"
            title="Refresh order data"
          >
            {refreshing ? "Refreshing..." : "\u21BB Refresh"}
          </button>
          <button
            onClick={() =>
              window.open(
                `${API_URL}/api/v1/sales-orders/${order.id}/packing-slip/pdf`,
                "_blank"
              )
            }
            className="px-4 py-2 bg-gray-700 text-white rounded-lg hover:bg-gray-600"
            title="Print packing slip PDF"
          >
            Print Packing Slip
          </button>
        </div>
      </div>

      {/* LEGACY-1: data-health banner for legacy fulfillment mismatch */}
      {isLegacyFulfillmentMismatch() && (
        <div className="rounded-xl border border-amber-500/40 bg-amber-950/20 p-4">
          <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
            <div className="flex items-start gap-3">
              <AlertTriangle className="h-5 w-5 shrink-0 text-amber-400 mt-0.5" />
              <div>
                <p className="text-sm font-semibold text-amber-300">
                  Legacy data issue: no shipment on record
                </p>
                <p className="mt-1 text-sm text-amber-200/80">
                  This order&apos;s status says{" "}
                  <span className="font-medium capitalize">
                    {order.status.replace(/_/g, " ")}
                  </span>
                  , but no shipment was ever recorded — likely data from an
                  older FilaOps version.
                </p>
              </div>
            </div>
            <div className="flex shrink-0 flex-wrap gap-2">
              <button
                onClick={() => setLegacyResolveAction("close_out")}
                className="rounded-lg bg-amber-600 px-3 py-2 text-sm font-medium text-white hover:bg-amber-500"
              >
                Close Out as Fulfilled
              </button>
              <button
                onClick={() => setLegacyResolveAction("reopen")}
                className="rounded-lg border border-amber-500/40 bg-gray-800 px-3 py-2 text-sm font-medium text-amber-200 hover:bg-gray-700"
              >
                Reopen for Shipping
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Order Workflow */}
      <div className="rounded-xl border border-gray-700 bg-gray-900/60 p-5">
        <div className="mb-4 flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <h2 className="text-lg font-semibold text-white">Order Workflow</h2>
            <p className="text-sm text-gray-400">
              Confirm, bill, release production, then fulfill.
            </p>
          </div>
          <span className="w-fit rounded-full bg-gray-800 px-3 py-1 text-xs font-medium text-gray-300">
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
                      <div className="text-xs font-semibold uppercase tracking-wide text-gray-500">
                        Step {index + 1}
                      </div>
                      <h3 className="text-sm font-semibold text-white">
                        {step.title}
                      </h3>
                    </div>
                  </div>
                  <span className={`rounded-full bg-gray-950/50 px-2 py-1 text-xs font-medium capitalize ${classes.label}`}>
                    {step.state}
                  </span>
                </div>

                <div className="mt-4 flex-1">
                  <div className={`text-sm font-medium capitalize ${classes.label}`}>
                    {step.meta || "Waiting"}
                  </div>
                  <p className="mt-2 text-sm leading-5 text-gray-300">
                    {step.detail}
                  </p>
                </div>

                {step.action && (
                  <button
                    onClick={step.action.onClick}
                    disabled={step.action.disabled}
                    className="mt-4 w-full rounded-lg bg-blue-600 px-3 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-50"
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
          <div className="mt-4 flex flex-wrap items-center gap-3 border-t border-gray-700/50 pt-4">
            <span className="text-xs font-medium uppercase tracking-wide text-gray-500">
              Order actions:
            </span>
            {(order.status === "pending" || order.status === "pending_confirmation") && (
              <>
                <button
                  onClick={handleConfirmOrder}
                  disabled={confirmingOrder}
                  className="rounded-lg bg-green-700 px-3 py-1.5 text-sm text-white hover:bg-green-600 disabled:opacity-50"
                >
                  {confirmingOrder ? "Confirming..." : "Confirm Order"}
                </button>
                {order.status === "pending_confirmation" && (
                  <button
                    onClick={() => setShowRejectModal(true)}
                    className="rounded-lg bg-red-700 px-3 py-1.5 text-sm text-white hover:bg-red-600"
                  >
                    Reject Order
                  </button>
                )}
              </>
            )}
            {canCancelOrder() && (
              <button
                onClick={() => setShowCancelModal(true)}
                className="rounded-lg bg-yellow-700 px-3 py-1.5 text-sm text-white hover:bg-yellow-600"
              >
                Cancel Order
              </button>
            )}
            {canCloseShort() && (
              <button
                onClick={openCloseShortModal}
                className="rounded-lg bg-amber-700 px-3 py-1.5 text-sm text-white hover:bg-amber-600"
              >
                Close Short
              </button>
            )}
            {canDeleteOrder() && (
              <button
                onClick={() => setShowDeleteConfirm(true)}
                className="rounded-lg bg-red-900 px-3 py-1.5 text-sm text-white hover:bg-red-800 border border-red-700"
              >
                Delete Order
              </button>
            )}
          </div>
        )}
      </div>

      {/* Quick Actions \u2014 idempotent tools only (links + checks) */}
      <div className="bg-gradient-to-r from-blue-900/20 to-cyan-900/20 border border-blue-500/30 rounded-xl p-6">
        <h2 className="text-lg font-semibold text-white mb-4 flex items-center gap-2">
          <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" />
          </svg>
          Quick Actions
        </h2>
        {invoiceLoading && !orderInvoice && (
          <div className="mb-4 rounded-lg border border-gray-700 bg-gray-900/70 px-4 py-3 text-sm text-gray-400">
            Checking invoice status...
          </div>
        )}
        {orderInvoice && (
          <div className="mb-4 rounded-lg border border-emerald-500/30 bg-emerald-950/20 px-4 py-3">
            <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
              <div>
                <div className="text-xs uppercase tracking-wide text-emerald-300">
                  Invoice on this order
                </div>
                <div className="mt-1 flex flex-wrap items-center gap-3">
                  <span className="font-mono text-sm font-semibold text-white">
                    {orderInvoice.invoice_number}
                  </span>
                  <span className="rounded-full bg-gray-900 px-2 py-1 text-xs text-gray-300">
                    {orderInvoice.status?.replace(/_/g, " ") || "draft"}
                  </span>
                  <span className="text-sm text-gray-300">
                    Balance {formatMoney(getInvoiceBalanceDue(orderInvoice))}
                  </span>
                </div>
              </div>
              <div className="flex flex-wrap gap-2">
                <button
                  onClick={() => navigate(`/admin/invoices?invoice=${orderInvoice.id}`)}
                  className="rounded-lg bg-gray-700 px-3 py-2 text-sm text-white hover:bg-gray-600"
                >
                  Open Invoice
                </button>
                <button
                  onClick={handleDownloadOrderInvoice}
                  className="rounded-lg bg-gray-700 px-3 py-2 text-sm text-white hover:bg-gray-600"
                >
                  Download PDF
                </button>
              </div>
            </div>
          </div>
        )}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          <button
            onClick={handleCheckAvailability}
            disabled={checkingAvailability || productionOrders.length === 0}
            className="px-4 py-3 bg-green-600 text-white rounded-lg hover:bg-green-700 disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2 transition-colors"
          >
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
            {checkingAvailability ? "Checking..." : "Check Material Availability"}
          </button>
          {productionOrders.length > 0 && (
            <button
              onClick={() => navigate(`/admin/production/${productionOrders[0].id}`)}
              className="px-4 py-3 bg-purple-600 text-white rounded-lg hover:bg-purple-700 flex items-center justify-center gap-2 transition-colors"
            >
              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z" />
              </svg>
              View in Production
            </button>
          )}
        </div>
        {materialAvailability && materialAvailability.length > 0 && (
          <div className="mt-4 space-y-2">
            {materialAvailability.map((avail, idx) => (
              <div
                key={idx}
                className={`p-3 rounded-lg ${
                  avail.can_release
                    ? "bg-green-900/20 border border-green-500/30"
                    : "bg-red-900/20 border border-red-500/30"
                }`}
              >
                <div className="flex items-center justify-between">
                  <span className="text-white font-medium">{avail.order_code}</span>
                  <span className={`text-sm ${avail.can_release ? "text-green-400" : "text-red-400"}`}>
                    {avail.can_release ? "\u2713 Materials Available" : `\u26A0 ${avail.shortage_count} Shortage${avail.shortage_count !== 1 ? "s" : ""}`}
                  </span>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Fulfillment Progress (UI-302) */}
      <FulfillmentProgress
        fulfillmentStatus={fulfillmentStatus}
        loading={fulfillmentLoading}
        error={fulfillmentError}
        onRefresh={refetchFulfillment}
        onShip={(type) => navigate(`/admin/shipping?orderId=${order.id}&mode=${type}`)}
        closedShort={order?.closed_short === true}
      />

      {/* Blocking Issues Panel */}
      <BlockingIssuesPanel
        orderType="sales"
        orderId={order.id}
        onActionClick={(action) => {
          if (action.reference_type === 'purchase_order') {
            navigate(`/admin/purchasing?po_id=${action.reference_id}`);
          } else if (action.reference_type === 'make_product') {
            const qty = parseFloat(action.impact?.match(/Need\s+([\d.]+)/)?.[1] || 0);
            handleCreateWorkOrder({
              product_id: action.reference_id,
              product_name: action.action.replace('Create production order for ', ''),
              net_shortage: qty
            });
          } else if (action.reference_type === 'product') {
            const quantityMatch = action.impact?.match(/Need\s+([\d.]+)/);
            const quantity = quantityMatch ? quantityMatch[1] : '';
            navigate(`/admin/purchasing?create_po=true&product_id=${action.reference_id}${quantity ? `&quantity=${quantity}` : ''}`);
          } else if (action.reference_type === 'production_order') {
            navigate(`/admin/production/${action.reference_id}`);
          }
        }}
      />

      {/* Order Summary */}
      <div className="bg-gray-900 border border-gray-800 rounded-xl p-6">
        <h2 className="text-lg font-semibold text-white mb-4">Order Summary</h2>
        <div className="grid grid-cols-4 gap-4">
          <div>
            <div className="text-sm text-gray-400">Product</div>
            <div className="text-white font-medium">
              {order.lines?.length > 1
                ? `${order.lines.length} line items`
                : order.product_name || order.lines?.[0]?.product_name || "N/A"}
            </div>
          </div>
          <div>
            <div className="text-sm text-gray-400">
              {order.lines?.length > 1 ? "Lines" : "Quantity"}
            </div>
            <div className="text-white font-medium">
              {order.lines?.length > 1 ? order.lines.length : order.quantity}
            </div>
          </div>
          <div>
            <div className="text-sm text-gray-400">Status</div>
            <div className="text-white font-medium flex items-center gap-2 capitalize">
              {order.status?.replace(/_/g, " ") || "unknown"}
              {order.closed_short && (
                getProductionComplete() ? (
                  <span className="px-2 py-0.5 text-xs rounded-full bg-emerald-500/20 text-emerald-400 border border-emerald-500/30">
                    Previously Closed Short — Fulfilled
                  </span>
                ) : (
                  <span className="px-2 py-0.5 text-xs rounded-full bg-amber-500/20 text-amber-400 border border-amber-500/30">
                    Closed Short
                  </span>
                )
              )}
            </div>
          </div>
          <div>
            <div className="text-sm text-gray-400">Total</div>
            <div className="text-white font-medium">
              ${parseFloat(order.total_price || 0).toFixed(2)}
            </div>
          </div>
        </div>
      </div>

      {/* Line Items */}
      {order.lines && order.lines.length > 0 && (
        <div className="bg-gray-900 border border-gray-800 rounded-xl p-6">
          <h2 className="text-lg font-semibold text-white mb-4">Line Items</h2>
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-gray-700 text-gray-400">
                <th className="text-left py-2 px-3">Product</th>
                <th className="text-left py-2 px-3">SKU</th>
                <th className="text-right py-2 px-3">Qty</th>
                <th className="text-right py-2 px-3">Shipped</th>
                <th className="text-right py-2 px-3">Unit Price</th>
                <th className="text-right py-2 px-3">Total</th>
                {canEditLines() && <th className="text-center py-2 px-3 w-16"></th>}
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-800">
              {order.lines.map((line, idx) => {
                const isEditing = editingLineId === line.id;
                const shipped = parseFloat(line.shipped_quantity || 0);
                const lineLabel = line.product_name || line.material_name || line.description || "One-time line";
                const lineCode = line.product_sku || line.material_sku || line.sku || (line.line_type === "service" ? "FEE" : "\u2014");
                return (
                  <tr key={line.id || idx}>
                    <td className="py-2 px-3 text-white">
                      {lineLabel}
                    </td>
                    <td className="py-2 px-3 text-gray-400 font-mono text-xs">
                      {lineCode}
                    </td>
                    <td className="py-2 px-3 text-right text-white">
                      {isEditing ? (
                        <input
                          type="number"
                          value={editQty}
                          onChange={(e) => setEditQty(e.target.value)}
                          min={shipped}
                          step="1"
                          className="w-20 bg-gray-800 border border-blue-500 rounded px-2 py-1 text-right text-white text-sm"
                          autoFocus
                        />
                      ) : (
                        <span className="flex items-center justify-end gap-1">
                          {line.original_quantity && parseFloat(line.original_quantity) !== parseFloat(line.quantity) && (
                            <span className="text-gray-500 line-through text-xs">{line.original_quantity}</span>
                          )}
                          {line.quantity}
                        </span>
                      )}
                    </td>
                    <td className="py-2 px-3 text-right text-gray-400">
                      {shipped > 0 ? shipped : "\u2014"}
                    </td>
                    <td className="py-2 px-3 text-right text-gray-300">
                      {isEditing ? (
                        <input
                          type="number"
                          value={editPrice}
                          onChange={(e) => setEditPrice(e.target.value)}
                          min="0"
                          step="0.01"
                          className="w-24 bg-gray-800 border border-blue-500 rounded px-2 py-1 text-right text-white text-sm"
                        />
                      ) : (
                        `$${parseFloat(line.unit_price || 0).toFixed(2)}`
                      )}
                    </td>
                    <td className="py-2 px-3 text-right text-green-400 font-medium">
                      ${parseFloat(line.total || 0).toFixed(2)}
                    </td>
                    {canEditLines() && (
                      <td className="py-2 px-3 text-center">
                        {isEditing ? (
                          <div className="flex gap-1 justify-center">
                            <button
                              onClick={() => handleSaveLineEdit(line.id)}
                              disabled={savingLineEdit || (editQty === "" && editPrice === "") || !editReason.trim()}
                              className="text-green-400 hover:text-green-300 disabled:opacity-50 text-xs"
                              title="Save"
                            >
                              {savingLineEdit ? "..." : "\u2713"}
                            </button>
                            <button
                              onClick={() => { setEditingLineId(null); setEditQty(""); setEditPrice(""); setEditReason(""); }}
                              className="text-gray-400 hover:text-white text-xs"
                              title="Cancel"
                            >
                              \u2717
                            </button>
                          </div>
                        ) : (
                          <div className="flex gap-2 justify-center">
                            <button
                              onClick={() => {
                                setEditingLineId(line.id);
                                setEditQty(String(line.quantity));
                                setEditPrice(String(line.unit_price || 0));
                                setEditReason("");
                              }}
                              className="text-gray-500 hover:text-blue-400 text-xs"
                              title="Edit line"
                            >
                              Edit
                            </button>
                            {order.lines.length > 1 && parseFloat(line.shipped_quantity || 0) === 0 && (
                              <button
                                onClick={() => handleRemoveLine(line)}
                                disabled={removingLineId === line.id}
                                className="text-gray-600 hover:text-red-400 disabled:opacity-50 text-xs"
                                title="Remove line"
                              >
                                {removingLineId === line.id ? "…" : "✕"}
                              </button>
                            )}
                          </div>
                        )}
                      </td>
                    )}
                  </tr>
                );
              })}
              {editingLineId && (
                <tr>
                  <td colSpan={canEditLines() ? 7 : 6} className="py-2 px-3">
                    <input
                      type="text"
                      value={editReason}
                      onChange={(e) => setEditReason(e.target.value)}
                      placeholder="Reason for change (required)..."
                      className="w-full bg-gray-800 border border-gray-700 rounded px-3 py-1.5 text-white text-sm placeholder-gray-500 focus:border-blue-500"
                    />
                  </td>
                </tr>
              )}
            </tbody>
            <tfoot>
              <tr className="border-t border-gray-700">
                <td colSpan={canEditLines() ? 6 : 5} className="py-3 px-3 text-right text-white font-medium">
                  Order Total
                </td>
                <td className="py-3 px-3 text-right text-green-400 font-bold">
                  ${parseFloat(order.total_price || 0).toFixed(2)}
                </td>
              </tr>
            </tfoot>
          </table>
        </div>
      )}

      {/* Customer Information */}
      <div className="bg-gray-900 border border-gray-800 rounded-xl p-6">
        <h2 className="text-lg font-semibold text-white mb-4">Customer</h2>
        {order.customer_name || order.customer_email ? (
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <div>
              <div className="text-sm text-gray-400">Name</div>
              <div className="text-white font-medium">
                {order.customer_name || "\u2014"}
              </div>
            </div>
            <div>
              <div className="text-sm text-gray-400">Email</div>
              <div className="text-white font-medium">
                {order.customer_email ? (
                  <a href={`mailto:${order.customer_email}`} className="text-blue-400 hover:underline">
                    {order.customer_email}
                  </a>
                ) : "\u2014"}
              </div>
            </div>
            <div>
              <div className="text-sm text-gray-400">Phone</div>
              <div className="text-white font-medium">
                {order.customer_phone || "\u2014"}
              </div>
            </div>
            {order.customer_id && (
              <div>
                <div className="text-sm text-gray-400">Customer ID</div>
                <div className="text-white font-medium">
                  <button
                    onClick={() => navigate(`/admin/customers/${order.customer_id}`)}
                    className="text-blue-400 hover:underline"
                  >
                    #{order.customer_id}
                  </button>
                </div>
              </div>
            )}
          </div>
        ) : order.quote_id ? (
          <div className="text-gray-400">
            Customer info available in linked quote.
            <button
              onClick={() => navigate(`/admin/quotes`)}
              className="text-blue-400 hover:underline ml-2"
            >
              View Quote
            </button>
          </div>
        ) : (
          <div className="text-gray-400">No customer information on file.</div>
        )}
      </div>

      {/* Shipping Address */}
      <ShippingAddressSection order={order} onOrderUpdated={fetchOrder} />

      {/* Material Requirements */}
      <MaterialRequirementsSection
        materialRequirements={materialRequirements}
        materialAvailability={materialAvailability}
        expandedSections={expandedSections}
        onToggle={toggleSection}
        exploding={exploding}
        order={order}
        onCreateWorkOrder={handleCreateWorkOrder}
        onCreatePurchaseOrder={handleCreatePurchaseOrder}
      />

      {/* Capacity Requirements */}
      <CapacityRequirementsSection
        capacityRequirements={capacityRequirements}
        expandedSections={expandedSections}
        onToggle={toggleSection}
        orderQuantity={order.quantity}
      />

      {/* Production Orders - Status Display */}
      {productionOrders.length > 0 && (
        <div className="bg-gray-900 border border-gray-800 rounded-xl p-6">
          <button
            onClick={() => toggleSection("productionOrders")}
            className="flex items-center gap-2 text-lg font-semibold text-white hover:text-gray-300 mb-4"
          >
            <svg
              className={`w-5 h-5 transition-transform ${expandedSections.productionOrders ? "rotate-90" : ""}`}
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
            </svg>
            Production Status ({productionOrders.length})
          </button>
          {expandedSections.productionOrders && (
            <div className="space-y-3">
              <ProductionProgressSummary orders={productionOrders} />
              {productionOrders.map((po) => (
                <ProductionOrderStatusCard
                  key={po.id}
                  order={po}
                  onViewInProduction={() =>
                    navigate(`/admin/production/${po.id}`)
                  }
                  onAcceptShort={handleAcceptShortPO}
                />
              ))}
            </div>
          )}
        </div>
      )}

      {/* Payments */}
      <PaymentsSection
        payments={payments}
        paymentSummary={paymentSummary}
        onRecordPayment={() => {
          setIsRefund(false);
          setShowPaymentModal(true);
        }}
        onRefund={() => {
          setIsRefund(true);
          setShowPaymentModal(true);
        }}
      />

      {/* Activity Timeline */}
      <div className="bg-gray-900 border border-gray-800 rounded-xl p-6">
        <h2 className="text-lg font-semibold text-white mb-4">Activity</h2>
        <ActivityTimeline orderId={parseInt(orderId)} />
      </div>

      {/* Shipping Timeline - Show if order has been shipped */}
      {order?.tracking_number && (
        <div className="bg-gray-900 border border-gray-800 rounded-xl p-6">
          <div className="flex items-center gap-2 mb-4">
            <svg className="w-5 h-5 text-cyan-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 16V6a1 1 0 00-1-1H4a1 1 0 00-1 1v10a1 1 0 001 1h1m8-1a1 1 0 01-1 1H9m4-1V8a1 1 0 011-1h2.586a1 1 0 01.707.293l3.414 3.414a1 1 0 01.293.707V16a1 1 0 01-1 1h-1m-6-1a1 1 0 001 1h1M5 17a2 2 0 104 0m-4 0a2 2 0 114 0m6 0a2 2 0 104 0m-4 0a2 2 0 114 0" />
            </svg>
            <h2 className="text-lg font-semibold text-white">Shipping Tracking</h2>
          </div>
          <ShippingTimeline orderId={parseInt(orderId)} />
        </div>
      )}

      {/* Record Payment Modal */}
      {showPaymentModal && (
        <RecordPaymentModal
          orderId={parseInt(orderId)}
          isRefund={isRefund}
          onClose={() => {
            setShowPaymentModal(false);
            setIsRefund(false);
          }}
          onSuccess={handlePaymentRecorded}
        />
      )}

      {/* SCHED-3b: Guided initial-schedule wizard (shown after production release) */}
      {wizardOpen && wizardProductionOrder && (
        <ReleaseScheduleWizard
          isOpen={wizardOpen}
          productionOrder={wizardProductionOrder}
          onClose={() => {
            setWizardOpen(false);
            setWizardProductionOrder(null);
          }}
          onOpenScheduler={() => {
            setWizardOpen(false);
            navigate(`/admin/production/${wizardProductionOrder.id}`);
          }}
          onRefresh={() => {
            fetchProductionOrders();
          }}
        />
      )}

      {/* Cancel Order Modal */}
      {showCancelModal && (
        <CancelOrderModal
          orderNumber={order.order_number}
          onCancel={handleCancelOrder}
          onClose={() => setShowCancelModal(false)}
        />
      )}

      {/* Delete Order Confirmation Modal */}
      {showDeleteConfirm && (
        <DeleteOrderModal
          orderNumber={order.order_number}
          onDelete={handleDeleteOrder}
          onClose={() => setShowDeleteConfirm(false)}
        />
      )}

      {/* Close Short Modal */}
      {showCloseShortModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60" onClick={() => { setShowCloseShortModal(false); setCloseShortPreview(null); setCloseShortReason(""); }}>
          <div className="bg-gray-900 border border-gray-700 rounded-xl p-6 max-w-2xl w-full mx-4 max-h-[80vh] overflow-y-auto" onClick={(e) => e.stopPropagation()}>
            <h3 className="text-lg font-semibold text-white mb-2">
              Close Order Short
            </h3>
            <p className="text-gray-400 text-sm mb-4">
              This will adjust line quantities to match actual produced amounts and set the order to Ready to Ship.
            </p>

            {/* Unresolved PO warning */}
            {closeShortPreview && !closeShortPreview.all_pos_resolved && (
              <div className="bg-red-500/10 border border-red-500/30 rounded-lg p-3 mb-4">
                <p className="text-red-400 text-sm font-medium mb-1">Production orders still unresolved</p>
                <p className="text-red-400/80 text-xs">
                  Accept short on these POs first: {closeShortPreview.unresolved_pos.join(", ")}
                </p>
              </div>
            )}

            {/* Preview table from backend */}
            {loadingPreview ? (
              <div className="bg-gray-800 rounded-lg p-4 mb-4 text-center text-gray-400 text-sm">Loading preview...</div>
            ) : closeShortPreview?.lines ? (
              <div className="bg-gray-800 rounded-lg p-3 mb-4">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="text-gray-400 text-xs">
                      <th className="text-left py-1">Product</th>
                      <th className="text-right py-1">Ordered</th>
                      <th className="text-right py-1">Adjusted</th>
                      <th className="text-left py-1 pl-3">Reason</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-700">
                    {closeShortPreview.lines.map((line) => (
                      <tr key={line.line_id}>
                        <td className="py-1.5 text-white text-xs">{line.product_name || line.product_sku || "N/A"}</td>
                        <td className="py-1.5 text-right text-white">{line.ordered_qty}</td>
                        <td className={`py-1.5 text-right font-medium ${line.will_adjust ? "text-amber-400" : "text-green-400"}`}>
                          {line.achievable_qty}
                        </td>
                        <td className="py-1.5 text-left pl-3 text-gray-400 text-xs max-w-[200px] truncate">{line.reason}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>

                {/* PO summary */}
                {closeShortPreview.lines.some(l => l.linked_po_summary?.length > 0) && (
                  <div className="mt-3 pt-3 border-t border-gray-700">
                    <p className="text-xs text-gray-500 mb-1">Linked Production Orders:</p>
                    <div className="flex flex-wrap gap-2">
                      {[...new Map(closeShortPreview.lines.flatMap(l => l.linked_po_summary || []).map(po => [po.po_number, po])).values()].map(po => (
                        <span key={po.po_number} className={`px-2 py-0.5 rounded text-xs ${["complete", "completed", "closed", "cancelled"].includes(po.status) ? "bg-green-500/20 text-green-400" : "bg-amber-500/20 text-amber-400"}`}>
                          {po.po_number}: {po.completed}/{po.ordered} ({po.status})
                        </span>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            ) : null}

            <div className="bg-amber-500/10 border border-amber-500/30 rounded-lg p-3 mb-4">
              <p className="text-amber-400 text-sm">
                This will adjust quantities and set the order to Ready to Ship. Ship through the normal flow after.
              </p>
            </div>

            <textarea
              value={closeShortReason}
              onChange={(e) => setCloseShortReason(e.target.value)}
              placeholder="Reason for closing short (required)..."
              className="w-full bg-gray-800 border border-gray-700 rounded-lg p-3 text-white placeholder-gray-500 focus:border-amber-500 focus:ring-1 focus:ring-amber-500 mb-4"
              rows={2}
            />
            <div className="flex justify-end gap-3">
              <button
                onClick={() => { setShowCloseShortModal(false); setCloseShortReason(""); setCloseShortPreview(null); }}
                className="px-4 py-2 bg-gray-700 text-white rounded-lg hover:bg-gray-600"
              >
                Cancel
              </button>
              <button
                onClick={handleCloseShort}
                disabled={!closeShortReason.trim() || closingShort || (closeShortPreview && !closeShortPreview.all_pos_resolved)}
                className="px-4 py-2 bg-amber-600 text-white rounded-lg hover:bg-amber-500 disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {closingShort ? "Closing..." : "Close Order Short"}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* LEGACY-1: confirm dialog for legacy fulfillment resolution */}
      {legacyResolveAction && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/60"
          onClick={() => !resolvingLegacy && setLegacyResolveAction(null)}
        >
          <div
            className="bg-gray-900 border border-gray-700 rounded-xl p-6 max-w-md w-full mx-4"
            onClick={(e) => e.stopPropagation()}
          >
            <h3 className="text-lg font-semibold text-white mb-2">
              {legacyResolveAction === "close_out"
                ? "Close Out as Fulfilled"
                : "Reopen for Shipping"}
            </h3>
            {legacyResolveAction === "close_out" ? (
              <p className="text-gray-400 text-sm mb-4">
                This records the order as fully shipped (paperwork only). No
                inventory movements or accounting entries are created — the
                goods already left under an older FilaOps version. An audit
                note is added to the order.
              </p>
            ) : (
              <p className="text-gray-400 text-sm mb-4">
                This sets the order back to Ready to Ship so you can ship it
                through the normal flow (which records inventory and
                accounting). Invoice and payment are left untouched. An audit
                note is added to the order.
              </p>
            )}
            <div className="flex justify-end gap-3">
              <button
                onClick={() => setLegacyResolveAction(null)}
                disabled={resolvingLegacy}
                className="px-4 py-2 bg-gray-700 text-white rounded-lg hover:bg-gray-600 disabled:opacity-50"
              >
                Cancel
              </button>
              <button
                onClick={handleResolveLegacyFulfillment}
                disabled={resolvingLegacy}
                className="px-4 py-2 bg-amber-600 text-white rounded-lg hover:bg-amber-500 disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {resolvingLegacy
                  ? "Working..."
                  : legacyResolveAction === "close_out"
                  ? "Close Out"
                  : "Reopen Order"}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Reject Order Modal */}
      {showRejectModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60">
          <div className="bg-gray-900 border border-gray-700 rounded-xl p-6 max-w-md w-full mx-4">
            <h3 className="text-lg font-semibold text-white mb-4">
              Reject Order {order.order_number}
            </h3>
            <p className="text-gray-400 text-sm mb-4">
              This will cancel the order and notify the source system.
            </p>
            <textarea
              value={rejectReason}
              onChange={(e) => setRejectReason(e.target.value)}
              placeholder="Reason for rejection..."
              className="w-full bg-gray-800 border border-gray-700 rounded-lg p-3 text-white placeholder-gray-500 focus:border-red-500 focus:ring-1 focus:ring-red-500 mb-4"
              rows={3}
            />
            <div className="flex justify-end gap-3">
              <button
                onClick={() => {
                  setShowRejectModal(false);
                  setRejectReason("");
                }}
                className="px-4 py-2 bg-gray-700 text-white rounded-lg hover:bg-gray-600"
              >
                Cancel
              </button>
              <button
                onClick={handleRejectOrder}
                disabled={!rejectReason.trim() || rejectingOrder}
                className="px-4 py-2 bg-red-600 text-white rounded-lg hover:bg-red-700 disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {rejectingOrder ? "Rejecting..." : "Reject Order"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
