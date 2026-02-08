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

  const hasMainProductWO = () => {
    if (!order?.lines || order.lines.length === 0) {
      return productionOrders.some((po) => po.product_id === order?.product_id);
    }
    const lineProductIds = order.lines.map((line) => line.product_id);
    const woProductIds = productionOrders
      .filter((po) => po.sales_order_line_id)
      .map((po) => po.product_id);
    return lineProductIds.every((pid) => woProductIds.includes(pid));
  };

  const [error, setError] = useState(null);
  const [exploding, setExploding] = useState(false);
  const [paymentSummary, setPaymentSummary] = useState(null);
  const [payments, setPayments] = useState([]);
  const [showPaymentModal, setShowPaymentModal] = useState(false);
  const [isRefund, setIsRefund] = useState(false);

  // Cancel/Delete modal state
  const [showCancelModal, setShowCancelModal] = useState(false);
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);

  // Refresh state
  const [refreshing, setRefreshing] = useState(false);

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

  useEffect(() => {
    if (orderId) {
      fetchOrder();
      fetchProductionOrders();
      fetchPaymentData();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [orderId]);

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

  const handlePaymentRecorded = () => {
    setShowPaymentModal(false);
    setIsRefund(false);
    fetchPaymentData();
    fetchOrder();
    toast.success(isRefund ? "Refund recorded" : "Payment recorded");
  };

  const handleRefresh = async () => {
    setRefreshing(true);
    try {
      await Promise.all([
        fetchOrder(),
        fetchProductionOrders(),
        fetchPaymentData(),
      ]);
      toast.success("Data refreshed");
    } catch {
      toast.error("Failed to refresh");
    } finally {
      setRefreshing(false);
    }
  };

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

  const handleCreateProductionOrder = async () => {
    const hasProduct =
      order?.product_id ||
      (order?.lines && order.lines.length > 0 && order.lines[0].product_id);
    if (!order || !hasProduct) {
      toast.error("Order must have a product to create production order");
      return;
    }

    try {
      await api.post(
        `/api/v1/sales-orders/${orderId}/generate-production-orders`
      );

      toast.success("Production order created successfully!");
      fetchProductionOrders();
      fetchOrder();
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

  const handleDeleteOrder = async () => {
    try {
      await api.del(`/api/v1/sales-orders/${orderId}`);

      toast.success(`Order ${order.order_number} deleted`);
      navigate("/admin/orders");
    } catch (err) {
      toast.error(err.message || "Failed to delete order");
    }
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
    if (!order.product_id && !(order.lines?.length > 0 && order.lines[0].product_id)) {
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
          {order.status !== "shipped" && order.status !== "delivered" && (
            <button
              onClick={() => navigate(`/admin/shipping?orderId=${order.id}`)}
              disabled={
                productionOrders.length === 0 ||
                !productionOrders.every((po) => po.status === "complete") ||
                materialRequirements.some((req) => req.net_shortage > 0)
              }
              className="px-4 py-2 bg-green-600 hover:bg-green-700 text-white rounded-lg disabled:opacity-50 disabled:cursor-not-allowed"
              title={
                productionOrders.length === 0
                  ? "Create work order first"
                  : !productionOrders.every((po) => po.status === "complete")
                  ? "Production must be complete"
                  : materialRequirements.some((req) => req.net_shortage > 0)
                  ? "Material shortages must be resolved"
                  : "Ship order"
              }
            >
              Ship Order
            </button>
          )}
          {canCancelOrder() && (
            <button
              onClick={() => setShowCancelModal(true)}
              className="px-4 py-2 bg-yellow-600 hover:bg-yellow-500 text-white rounded-lg"
            >
              Cancel Order
            </button>
          )}
        </div>
      </div>

      {/* Quick Actions Panel */}
      <div className="bg-gradient-to-r from-blue-900/20 to-cyan-900/20 border border-blue-500/30 rounded-xl p-6">
        <h2 className="text-lg font-semibold text-white mb-4 flex items-center gap-2">
          <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" />
          </svg>
          Quick Actions
        </h2>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
          <button
            onClick={handleCreateProductionOrder}
            disabled={
              (!order.product_id &&
                !(order.lines?.length > 0 && order.lines[0].product_id)) ||
              hasMainProductWO()
            }
            className="px-4 py-3 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2 transition-colors"
          >
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 6v6m0 0v6m0-6h6m-6 0H6" />
            </svg>
            {hasMainProductWO() ? "WO Exists" : "Generate Production Order"}
          </button>
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
              onClick={() => navigate(`/admin/production?order=${productionOrders[0].id}`)}
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
              {order.product_name || "N/A"}
            </div>
          </div>
          <div>
            <div className="text-sm text-gray-400">Quantity</div>
            <div className="text-white font-medium">{order.quantity}</div>
          </div>
          <div>
            <div className="text-sm text-gray-400">Status</div>
            <div className="text-white font-medium">{order.status}</div>
          </div>
          <div>
            <div className="text-sm text-gray-400">Total</div>
            <div className="text-white font-medium">
              ${parseFloat(order.total_price || 0).toFixed(2)}
            </div>
          </div>
        </div>
      </div>

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

      {/* Production Orders - Read-Only Status Display */}
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
                    navigate(`/admin/production?search=${encodeURIComponent(po.code || `WO-${po.id}`)}`)
                  }
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
    </div>
  );
}
