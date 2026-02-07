import { useState, useEffect } from "react";
import { useNavigate, useLocation, useSearchParams } from "react-router-dom";
import SalesOrderWizard from "../../components/SalesOrderWizard";
import { API_URL } from "../../config/api";
import { useToast } from "../../components/Toast";
import { validateLength } from "../../utils/validation";
import { SalesOrderCard } from "../../components/orders";
import OrderFilters from "../../components/orders/OrderFilters";

export default function AdminOrders() {
  const navigate = useNavigate();
  const location = useLocation();
  const toast = useToast();
  const [searchParams, setSearchParams] = useSearchParams();

  // URL-based filter/sort state (UI-303)
  const fulfillmentFilter = searchParams.get("filter") || "";
  const sortValue = searchParams.get("sort") || "fulfillment_priority:asc";
  const searchQuery = searchParams.get("search") || "";

  const [orders, setOrders] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [selectedOrder, setSelectedOrder] = useState(null);

  // Create order modal state
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [generatingPO, setGeneratingPO] = useState(false);

  // Cancel/Delete modal state
  const [showCancelModal, setShowCancelModal] = useState(false);
  const [cancellingOrder, setCancellingOrder] = useState(null);
  const [cancellationReason, setCancellationReason] = useState("");
  const [cancellationError, setCancellationError] = useState("");
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);
  const [deletingOrder, setDeletingOrder] = useState(null);

  // Check if returning from customer/item creation
  useEffect(() => {
    const pendingData = sessionStorage.getItem("pendingOrderData");
    if (pendingData) {
      // Open the order modal if we have pending data
      setShowCreateModal(true);
    }
  }, []);

  // Fetch orders on mount, when filters change, or when navigating back to this page
  useEffect(() => {
    fetchOrders();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [fulfillmentFilter, sortValue, location.key]);

  const fetchOrders = async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams();
      // Include fulfillment status data (API-302)
      params.set("include_fulfillment", "true");
      params.set("limit", "100");

      // Fulfillment state filter (UI-303)
      if (fulfillmentFilter) {
        params.set("fulfillment_state", fulfillmentFilter);
      }

      // Sort by field:order (UI-303)
      const [sortBy, sortOrder] = sortValue.split(":");
      if (sortBy) params.set("sort_by", sortBy);
      if (sortOrder) params.set("sort_order", sortOrder);

      const res = await fetch(`${API_URL}/api/v1/sales-orders/?${params}`, {
        credentials: "include",
      });

      if (!res.ok) throw new Error("Failed to fetch orders");

      const data = await res.json();
      setOrders(data.items || data);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const handleStatusUpdate = async (orderId, newStatus) => {
    try {
      const res = await fetch(
        `${API_URL}/api/v1/sales-orders/${orderId}/status`,
        {
          method: "PATCH",
          credentials: "include",
          headers: {
            "Content-Type": "application/json",
          },
          body: JSON.stringify({ status: newStatus }),
        }
      );

      if (res.ok) {
        toast.success("Order status updated");
        fetchOrders();
        if (selectedOrder?.id === orderId) {
          const updated = await res.json();
          setSelectedOrder(updated);
        }
      } else {
        const errorData = await res.json();
        toast.error(
          `Failed to update order status: ${
            errorData.detail || "Unknown error"
          }`
        );
      }
    } catch (err) {
      toast.error(
        `Failed to update order status: ${err.message || "Network error"}`
      );
    }
  };

  const handleGenerateProductionOrder = async (orderId) => {
    setGeneratingPO(true);
    setError(null);

    try {
      const res = await fetch(
        `${API_URL}/api/v1/sales-orders/${orderId}/generate-production-orders`,
        {
          method: "POST",
          credentials: "include",
          headers: {
            "Content-Type": "application/json",
          },
        }
      );

      const data = await res.json();

      if (res.ok) {
        if (data.created_orders?.length > 0) {
          toast.success(
            `Production Order(s) created: ${data.created_orders.join(", ")}`
          );
        } else if (data.existing_orders?.length > 0) {
          toast.info(
            `Production Order(s) already exist: ${data.existing_orders.join(
              ", "
            )}`
          );
        }
        fetchOrders();
        setSelectedOrder(null);
      } else {
        setError(data.detail || "Failed to generate production order");
      }
    } catch (err) {
      setError(err.message);
    } finally {
      setGeneratingPO(false);
    }
  };

  // Client-side search filter (API handles fulfillment filter)
  const filteredOrders = orders.filter((o) => {
    if (!searchQuery) return true;
    const search = searchQuery.toLowerCase();
    return (
      o.order_number?.toLowerCase().includes(search) ||
      o.product_name?.toLowerCase().includes(search) ||
      o.customer_name?.toLowerCase().includes(search) ||
      o.user?.email?.toLowerCase().includes(search)
    );
  });

  // URL state handlers (UI-303)
  const handleFilterChange = (newFilter) => {
    const newParams = new URLSearchParams(searchParams);
    if (newFilter) {
      newParams.set("filter", newFilter);
    } else {
      newParams.delete("filter");
    }
    setSearchParams(newParams);
  };

  const handleSortChange = (newSort) => {
    const newParams = new URLSearchParams(searchParams);
    newParams.set("sort", newSort);
    setSearchParams(newParams);
  };

  const handleSearchChange = (newSearch) => {
    const newParams = new URLSearchParams(searchParams);
    if (newSearch) {
      newParams.set("search", newSearch);
    } else {
      newParams.delete("search");
    }
    setSearchParams(newParams);
  };

  const handleViewDetails = (orderId) => {
    navigate(`/admin/orders/${orderId}`);
  };

  const handleShip = (orderId) => {
    navigate(`/admin/shipping?orderId=${orderId}`);
  };

  // Handle cancel order
  const handleCancelOrder = async () => {
    if (!cancellingOrder) return;

    // Validate cancellation reason if provided
    setCancellationError("");
    if (cancellationReason && cancellationReason.trim()) {
      const lengthError = validateLength(
        cancellationReason.trim(),
        "Cancellation reason",
        { max: 500 }
      );
      if (lengthError) {
        setCancellationError(lengthError);
        return;
      }
    }

    try {
      const res = await fetch(
        `${API_URL}/api/v1/sales-orders/${cancellingOrder.id}/cancel`,
        {
          method: "POST",
          credentials: "include",
          headers: {
            "Content-Type": "application/json",
          },
          body: JSON.stringify({ cancellation_reason: cancellationReason }),
        }
      );

      if (res.ok) {
        toast.success(`Order ${cancellingOrder.order_number} cancelled`);
        setShowCancelModal(false);
        setCancellingOrder(null);
        setCancellationReason("");
        setCancellationError("");
        fetchOrders();
      } else {
        const errorData = await res.json();
        toast.error(errorData.detail || "Failed to cancel order");
      }
    } catch (err) {
      toast.error(err.message || "Failed to cancel order");
    }
  };

  // Handle delete order
  const handleDeleteOrder = async () => {
    if (!deletingOrder) return;

    try {
      const res = await fetch(
        `${API_URL}/api/v1/sales-orders/${deletingOrder.id}`,
        {
          method: "DELETE",
          credentials: "include",
        }
      );

      if (res.ok || res.status === 204) {
        toast.success(`Order ${deletingOrder.order_number} deleted`);
        setShowDeleteConfirm(false);
        setDeletingOrder(null);
        fetchOrders();
      } else {
        let errorMsg = "Failed to delete order";
        const contentType = res.headers.get("content-type") || "";
        const text = await res.text();
        if (text && contentType.includes("application/json")) {
          try {
            const errorData = JSON.parse(text);
            errorMsg = errorData.detail || errorMsg;
          } catch {
            // Ignore JSON parse error, fallback to generic message
          }
        }
        toast.error(errorMsg);
      }
    } catch (err) {
      toast.error(err.message || "Failed to delete order");
    }
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex justify-between items-center">
        <div>
          <h1 className="text-2xl font-bold text-white">Order Management</h1>
          <p className="text-gray-400 mt-1">View and manage sales orders</p>
        </div>
        <div className="flex gap-2">
          <button
            onClick={fetchOrders}
            disabled={loading}
            className="px-4 py-2 bg-gray-700 text-white rounded-lg hover:bg-gray-600 disabled:opacity-50"
            title="Refresh orders"
          >
            {loading ? "Loading..." : "↻ Refresh"}
          </button>
          <button
            onClick={() => setShowCreateModal(true)}
            className="px-4 py-2 bg-gradient-to-r from-blue-600 to-purple-600 text-white rounded-lg hover:from-blue-500 hover:to-purple-500 flex items-center gap-2"
          >
            <svg
              className="w-5 h-5"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M12 4v16m8-8H4"
              />
            </svg>
            Create Order
          </button>
        </div>
      </div>

      {/* Filters (UI-303) */}
      <OrderFilters
        selectedFilter={fulfillmentFilter}
        onFilterChange={handleFilterChange}
        selectedSort={sortValue}
        onSortChange={handleSortChange}
        search={searchQuery}
        onSearchChange={handleSearchChange}
      />

      {/* Error */}
      {error && (
        <div className="bg-red-500/10 border border-red-500/30 rounded-xl p-4 text-red-400">
          {error}
          <button
            onClick={() => setError(null)}
            className="ml-4 text-red-300 hover:text-white"
          >
            Dismiss
          </button>
        </div>
      )}

      {/* Loading */}
      {loading && (
        <div className="flex items-center justify-center h-32">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-500"></div>
        </div>
      )}

      {/* Orders Card Grid (UI-303) */}
      {!loading && (
        <>
          {filteredOrders.length === 0 ? (
            <div className="bg-gray-900 border border-gray-800 rounded-xl p-12 text-center">
              <svg
                className="w-12 h-12 mx-auto text-gray-600 mb-4"
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2"
                />
              </svg>
              <p className="text-gray-500 text-lg">No orders found</p>
              <p className="text-gray-600 text-sm mt-1">
                {fulfillmentFilter
                  ? "Try adjusting your filters"
                  : "Create a new order to get started"}
              </p>
            </div>
          ) : (
            <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
              {filteredOrders.map((order) => (
                <SalesOrderCard
                  key={order.id}
                  order={order}
                  onViewDetails={handleViewDetails}
                  onShip={handleShip}
                />
              ))}
            </div>
          )}
        </>
      )}

      {/* Create Order Wizard */}
      <SalesOrderWizard
        isOpen={showCreateModal}
        onClose={() => setShowCreateModal(false)}
        onSuccess={() => {
          setShowCreateModal(false);
          fetchOrders();
        }}
      />

      {/* Order Detail Modal */}
      {selectedOrder && (
        <div className="fixed inset-0 z-50 overflow-y-auto">
          <div className="flex items-center justify-center min-h-screen px-4 pt-4 pb-20">
            <div
              className="fixed inset-0 bg-black/70"
              onClick={() => setSelectedOrder(null)}
            />
            <div className="relative bg-gray-900 border border-gray-700 rounded-xl shadow-xl max-w-2xl w-full mx-auto p-6">
              <div className="flex justify-between items-center mb-6">
                <h3 className="text-lg font-semibold text-white">
                  Order: {selectedOrder.order_number}
                </h3>
                <button
                  onClick={() => setSelectedOrder(null)}
                  className="text-gray-400 hover:text-white p-1"
                >
                  <svg
                    className="w-5 h-5"
                    fill="none"
                    stroke="currentColor"
                    viewBox="0 0 24 24"
                  >
                    <path
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      strokeWidth={2}
                      d="M6 18L18 6M6 6l12 12"
                    />
                  </svg>
                </button>
              </div>

              <div className="space-y-4">
                <div className="grid grid-cols-2 gap-4 text-sm">
                  <div>
                    <span className="text-gray-400">Product:</span>
                    <p className="text-white">{selectedOrder.product_name}</p>
                  </div>
                  <div>
                    <span className="text-gray-400">Material:</span>
                    <p className="text-white">
                      {selectedOrder.material_type} /{" "}
                      {selectedOrder.color || "N/A"}
                    </p>
                  </div>
                  <div>
                    <span className="text-gray-400">Quantity:</span>
                    <p className="text-white">{selectedOrder.quantity}</p>
                  </div>
                  <div>
                    <span className="text-gray-400">Unit Price:</span>
                    <p className="text-white">
                      ${parseFloat(selectedOrder.unit_price || 0).toFixed(2)}
                    </p>
                  </div>
                  <div>
                    <span className="text-gray-400">Grand Total:</span>
                    <p className="text-green-400 font-semibold">
                      ${parseFloat(selectedOrder.grand_total || 0).toFixed(2)}
                    </p>
                  </div>
                  <div>
                    <span className="text-gray-400">Source:</span>
                    <p className="text-white">
                      {selectedOrder.source} ({selectedOrder.order_type})
                    </p>
                  </div>
                </div>

                {/* Shipping Info */}
                {selectedOrder.shipping_address && (
                  <div className="bg-gray-800 p-4 rounded-lg">
                    <h4 className="text-sm font-medium text-gray-300 mb-2">
                      Shipping Address
                    </h4>
                    <p className="text-white text-sm whitespace-pre-line">
                      {selectedOrder.shipping_address}
                    </p>
                  </div>
                )}

                {/* Actions */}
                <div className="flex flex-col gap-4 pt-4 border-t border-gray-800">
                  {/* Generate Production Order Button */}
                  {selectedOrder.status !== "cancelled" &&
                    selectedOrder.status !== "completed" && (
                      <button
                        onClick={() =>
                          handleGenerateProductionOrder(selectedOrder.id)
                        }
                        disabled={generatingPO}
                        className="w-full px-4 py-2 bg-gradient-to-r from-purple-600 to-indigo-600 text-white rounded-lg hover:from-purple-500 hover:to-indigo-500 disabled:opacity-50 flex items-center justify-center gap-2"
                      >
                        <svg
                          className="w-5 h-5"
                          fill="none"
                          stroke="currentColor"
                          viewBox="0 0 24 24"
                        >
                          <path
                            strokeLinecap="round"
                            strokeLinejoin="round"
                            strokeWidth={2}
                            d="M19.428 15.428a2 2 0 00-1.022-.547l-2.387-.477a6 6 0 00-3.86.517l-.318.158a6 6 0 01-3.86.517L6.05 15.21a2 2 0 00-1.806.547M8 4h8l-1 1v5.172a2 2 0 00.586 1.414l5 5c1.26 1.26.367 3.414-1.415 3.414H4.828c-1.782 0-2.674-2.154-1.414-3.414l5-5A2 2 0 009 10.172V5L8 4z"
                          />
                        </svg>
                        {generatingPO
                          ? "Generating..."
                          : "Generate Production Order"}
                      </button>
                    )}

                  {/* Status Flow */}
                  <div className="flex gap-2 flex-wrap">
                    {[
                      "confirmed",
                      "in_production",
                      "ready_to_ship",
                      "shipped",
                      "completed",
                    ].map((status) => (
                      <button
                        key={status}
                        onClick={() =>
                          handleStatusUpdate(selectedOrder.id, status)
                        }
                        disabled={selectedOrder.status === status}
                        className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-colors ${
                          selectedOrder.status === status
                            ? "bg-blue-600 text-white"
                            : "bg-gray-800 text-gray-400 hover:bg-gray-700 hover:text-white"
                        }`}
                      >
                        {status.replace(/_/g, " ")}
                      </button>
                    ))}
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Cancel Order Modal */}
      {showCancelModal && cancellingOrder && (
        <div className="fixed inset-0 z-50 overflow-y-auto">
          <div className="flex items-center justify-center min-h-screen px-4 pt-4 pb-20">
            <div
              className="fixed inset-0 bg-black/70"
              onClick={() => {
                setShowCancelModal(false);
                setCancellingOrder(null);
                setCancellationReason("");
              }}
            />
            <div className="relative bg-gray-900 border border-gray-700 rounded-xl shadow-xl max-w-md w-full mx-auto p-6">
              <h3 className="text-lg font-semibold text-white mb-4">
                Cancel Order {cancellingOrder.order_number}?
              </h3>
              <p className="text-gray-400 mb-4">
                This will cancel the order. The order can still be deleted after
                cancellation.
              </p>
              <div className="mb-4">
                <label className="block text-sm text-gray-400 mb-2">
                  Cancellation Reason (optional)
                </label>
                <textarea
                  value={cancellationReason}
                  onChange={(e) => {
                    setCancellationReason(e.target.value);
                    setCancellationError("");
                  }}
                  className={`w-full bg-gray-800 border rounded-lg px-4 py-2 text-white ${
                    cancellationError
                      ? "border-red-500 focus:border-red-500"
                      : "border-gray-700"
                  }`}
                  rows={3}
                  placeholder="Enter reason for cancellation..."
                  maxLength={500}
                />
                {cancellationError && (
                  <div className="text-red-400 text-sm mt-1">
                    {cancellationError}
                  </div>
                )}
                {cancellationReason && (
                  <div className="text-gray-500 text-xs mt-1">
                    {cancellationReason.length}/500 characters
                  </div>
                )}
              </div>
              <div className="flex justify-end gap-3">
                <button
                  onClick={() => {
                    setShowCancelModal(false);
                    setCancellingOrder(null);
                    setCancellationReason("");
                    setCancellationError("");
                  }}
                  className="px-4 py-2 bg-gray-700 text-white rounded-lg hover:bg-gray-600"
                >
                  Keep Order
                </button>
                <button
                  onClick={handleCancelOrder}
                  className="px-4 py-2 bg-yellow-600 text-white rounded-lg hover:bg-yellow-500"
                >
                  Cancel Order
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Delete Order Confirmation Modal */}
      {showDeleteConfirm && deletingOrder && (
        <div className="fixed inset-0 z-50 overflow-y-auto">
          <div className="flex items-center justify-center min-h-screen px-4 pt-4 pb-20">
            <div
              className="fixed inset-0 bg-black/70"
              onClick={() => {
                setShowDeleteConfirm(false);
                setDeletingOrder(null);
              }}
            />
            <div className="relative bg-gray-900 border border-gray-700 rounded-xl shadow-xl max-w-md w-full mx-auto p-6">
              <h3 className="text-lg font-semibold text-white mb-4">
                Delete Order {deletingOrder.order_number}?
              </h3>
              <p className="text-gray-400 mb-4">
                This action cannot be undone. All order data, including line
                items and payment records, will be permanently deleted.
              </p>
              <div className="flex justify-end gap-3">
                <button
                  onClick={() => {
                    setShowDeleteConfirm(false);
                    setDeletingOrder(null);
                  }}
                  className="px-4 py-2 bg-gray-700 text-white rounded-lg hover:bg-gray-600"
                >
                  Keep Order
                </button>
                <button
                  onClick={handleDeleteOrder}
                  className="px-4 py-2 bg-red-600 text-white rounded-lg hover:bg-red-500"
                >
                  Delete Permanently
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
