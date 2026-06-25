import { useState, useEffect } from "react";
import { useNavigate, useLocation, useSearchParams } from "react-router-dom";
import SalesOrderWizard from "../../components/SalesOrderWizard";
import { useApi } from "../../hooks/useApi";
import { useToast } from "../../components/Toast";
import EmptyState from "../../components/EmptyState";
import { SalesOrderCard } from "../../components/orders";
import OrderFilters from "../../components/orders/OrderFilters";
import { normalizeList } from "../../lib/normalizeList";

export default function AdminOrders() {
  const navigate = useNavigate();
  const location = useLocation();
  const api = useApi();
  const toast = useToast();
  const [searchParams, setSearchParams] = useSearchParams();

  // URL-based filter/sort state (UI-303)
  const fulfillmentFilter = searchParams.get("filter") || "";
  const sortValue = searchParams.get("sort") || "fulfillment_priority:asc";
  const searchQuery = searchParams.get("search") || "";

  const [orders, setOrders] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  // Create order modal state
  const [showCreateModal, setShowCreateModal] = useState(false);


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
      if (fulfillmentFilter === "pending_review") {
        // Special filter: show orders awaiting admin confirmation
        params.set("status", "pending_confirmation");
      } else if (fulfillmentFilter) {
        params.set("fulfillment_state", fulfillmentFilter);
      }

      // Sort by field:order (UI-303)
      const [sortBy, sortOrder] = sortValue.split(":");
      if (sortBy) params.set("sort_by", sortBy);
      if (sortOrder) params.set("sort_order", sortOrder);

      const data = await api.get(`/api/v1/sales-orders/?${params}`);
      setOrders(normalizeList(data).items);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
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

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row items-start sm:items-center sm:justify-between gap-4">
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
            orders.length === 0 && !fulfillmentFilter ? (
              <EmptyState
                icon="orders"
                title="No orders yet"
                description="Create your first sales order to get started."
                actionLabel="New Order"
                onAction={() => setShowCreateModal(true)}
              />
            ) : (
              <EmptyState
                icon="filter"
                title="No orders match your filters"
                onClearFilters={() => {
                  setSearchParams({});
                }}
              />
            )
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

    </div>
  );
}
