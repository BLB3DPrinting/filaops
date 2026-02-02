import { useState, useEffect, useRef, useMemo } from "react";
import { useSearchParams } from "react-router-dom";
import { API_URL } from "../../config/api";
import { useToast } from "../../components/Toast";
import { statusColors } from "../../components/purchasing/constants";
import PurchasingChart from "../../components/purchasing/PurchasingChart";
import VendorModal from "../../components/purchasing/VendorModal";
import VendorDetailPanel from "../../components/purchasing/VendorDetailPanel";
import POCreateModal from "../../components/purchasing/POCreateModal";
import PODetailModal from "../../components/purchasing/PODetailModal";
import ReceiveModal from "../../components/purchasing/ReceiveModal";

export default function AdminPurchasing() {
  const toast = useToast();
  const [searchParams, setSearchParams] = useSearchParams();
  const initialTab = searchParams.get("tab") || "orders";
  const [activeTab, setActiveTab] = useState(initialTab); // orders | vendors | import | low-stock

  // Initial items for PO modal (from URL params)
  const [initialItemsForPO, setInitialItemsForPO] = useState([]);

  // Track if we've already processed the create_po URL param
  const createPOProcessedRef = useRef(false);

  // Sync tab with URL
  useEffect(() => {
    const tabParam = searchParams.get("tab");
    if (tabParam && tabParam !== activeTab) {
      setActiveTab(tabParam);
    }
  }, [searchParams]);

  const [orders, setOrders] = useState([]);
  const [vendors, setVendors] = useState([]);
  const [products, setProducts] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [filters, setFilters] = useState({ status: "all", search: "" });

  // Low Stock State
  const [lowStockItems, setLowStockItems] = useState([]);
  const [lowStockSummary, setLowStockSummary] = useState(null);
  const [lowStockLoading, setLowStockLoading] = useState(false);
  const [selectedLowStockIds, setSelectedLowStockIds] = useState(new Set());

  // Company Settings (for auto-calc tax)
  const [companySettings, setCompanySettings] = useState(null);

  // Modals
  const [showVendorModal, setShowVendorModal] = useState(false);
  const [showVendorDetail, setShowVendorDetail] = useState(false);
  const [showPOModal, setShowPOModal] = useState(false);
  const [showReceiveModal, setShowReceiveModal] = useState(false);
  const [selectedPO, setSelectedPO] = useState(null);
  const [selectedVendor, setSelectedVendor] = useState(null);

  // Trend chart state
  const [purchasingTrend, setPurchasingTrend] = useState(null);
  const [trendPeriod, setTrendPeriod] = useState("MTD");
  const [trendLoading, setTrendLoading] = useState(false);

  const token = localStorage.getItem("adminToken");

  // Handle create_po URL param - auto-open PO modal with pre-filled item
  useEffect(() => {
    const createPO = searchParams.get("create_po");
    const productId = searchParams.get("product_id");
    const quantity = searchParams.get("quantity");

    // Only process if we have the create_po flag and product_id
    if (createPO !== "true" || !productId) {
      // Reset the ref when there's no create_po param
      createPOProcessedRef.current = false;
      return;
    }

    // Don't process again if we've already handled this
    if (createPOProcessedRef.current) {
      return;
    }

    // Wait for products to load
    if (products.length === 0) {
      console.log("[AdminPurchasing] Waiting for products to load...");
      return;
    }

    // Mark as processed BEFORE doing anything else
    createPOProcessedRef.current = true;

    console.log(`[AdminPurchasing] Looking for product ID: ${productId} in ${products.length} products`);

    // Find the product in the products list
    const product = products.find(p => String(p.id) === String(productId));

    if (product) {
      console.log(`[AdminPurchasing] Found product: ${product.sku}`);

      // Build initial items for the PO modal
      const initialItems = [{
        id: product.id,
        sku: product.sku,
        name: product.name,
        unit: product.unit || "EA",
        shortfall: quantity ? parseFloat(quantity) : 1,
        last_cost: product.last_cost || product.cost || 0,
      }];

      setInitialItemsForPO(initialItems);
      setSelectedPO(null);
      setShowPOModal(true);

      // Ensure we're on the orders tab
      setActiveTab("orders");

      toast.info(`Creating PO for ${product.sku}`);
    } else {
      console.warn(`[AdminPurchasing] Product ID ${productId} not found in products list`);
      toast.warning(`Product not found. Opening empty PO form.`);

      // Still open the modal but without pre-filled data
      setSelectedPO(null);
      setShowPOModal(true);
      setActiveTab("orders");
    }

    // Clear the URL params after processing
    const newParams = new URLSearchParams(searchParams);
    newParams.delete("create_po");
    newParams.delete("product_id");
    newParams.delete("quantity");
    setSearchParams(newParams, { replace: true });
  }, [searchParams, products, setSearchParams, toast]);

  // Build shortage map from lowStockItems for PO modal product enhancement
  // This includes both reorder point shortages and MRP-driven shortages
  const shortageMap = useMemo(() => {
    const map = {};
    lowStockItems.forEach(item => {
      map[item.id] = {
        needs_reorder: true,
        shortfall: item.shortfall,
        mrp_shortage: item.mrp_shortage,
        shortage_source: item.shortage_source, // "reorder_point", "mrp", or "both"
      };
    });
    return map;
  }, [lowStockItems]);

  // Enhanced products with shortage data merged in
  // This allows the PO modal to show MRP shortages, not just reorder point items
  const enhancedProducts = useMemo(() => {
    return products.map(product => {
      const shortage = shortageMap[product.id];
      if (shortage) {
        return { ...product, ...shortage };
      }
      return product;
    });
  }, [products, shortageMap]);

  // Group selected low-stock items by vendor for bulk PO creation
  const selectedItemsByVendor = useMemo(() => {
    const grouped = {};
    lowStockItems
      .filter(item => selectedLowStockIds.has(item.id))
      .forEach(item => {
        const vendorId = item.preferred_vendor_id || 'no_vendor';
        const vendorName = item.preferred_vendor_name || 'No Preferred Vendor';
        if (!grouped[vendorId]) {
          grouped[vendorId] = {
            vendorId: vendorId === 'no_vendor' ? null : vendorId,
            vendorName,
            items: [],
            totalValue: 0,
          };
        }
        grouped[vendorId].items.push(item);
        grouped[vendorId].totalValue += (item.shortfall || 0) * (item.last_cost || 0);
      });
    return Object.values(grouped);
  }, [lowStockItems, selectedLowStockIds]);

  // Low stock checkbox handlers
  const toggleLowStockItem = (itemId) => {
    setSelectedLowStockIds(prev => {
      const next = new Set(prev);
      if (next.has(itemId)) {
        next.delete(itemId);
      } else {
        next.add(itemId);
      }
      return next;
    });
  };

  const toggleAllLowStock = () => {
    if (selectedLowStockIds.size === lowStockItems.length) {
      setSelectedLowStockIds(new Set());
    } else {
      setSelectedLowStockIds(new Set(lowStockItems.map(i => i.id)));
    }
  };

  const clearLowStockSelection = () => {
    setSelectedLowStockIds(new Set());
  };

  const fetchPurchasingTrend = async (period) => {
    if (!token) return;
    setTrendLoading(true);
    try {
      const res = await fetch(
        `${API_URL}/api/v1/admin/dashboard/purchasing-trend?period=${period}`,
        { headers: { Authorization: `Bearer ${token}` } }
      );
      if (res.ok) {
        const data = await res.json();
        setPurchasingTrend(data);
      } else {
        console.error("Purchasing trend API error:", res.status);
      }
    } catch (err) {
      console.error("Failed to fetch purchasing trend:", err);
    } finally {
      setTrendLoading(false);
    }
  };

  useEffect(() => {
    fetchPurchasingTrend(trendPeriod);
  }, [trendPeriod]);

  useEffect(() => {
    if (activeTab === "orders") fetchOrders();
    else if (activeTab === "vendors") fetchVendors();
    else if (activeTab === "low-stock") fetchLowStock();
    // Import tab doesn't need data fetching on mount
    fetchProducts();
  }, [activeTab, filters.status]);

  // Fetch vendors, low stock count, and company settings on mount
  useEffect(() => {
    fetchVendors(false); // Silent fetch - don't show loading spinner
    fetchLowStock();
    fetchCompanySettings();
  }, []);

  // ============================================================================
  // Data Fetching
  // ============================================================================

  const fetchOrders = async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams();
      if (filters.status !== "all") params.set("status", filters.status);
      params.set("limit", "100");

      const res = await fetch(`${API_URL}/api/v1/purchase-orders?${params}`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!res.ok) throw new Error("Failed to fetch orders");
      const data = await res.json();
      // Handle both array and {items: [...]} responses, and error objects
      setOrders(Array.isArray(data) ? data : (data.items || []));
    } catch (err) {
      setError(err.message);
      setOrders([]);
    } finally {
      setLoading(false);
    }
  };

  const fetchVendors = async (showLoading = true) => {
    if (showLoading) setLoading(true);
    try {
      const res = await fetch(`${API_URL}/api/v1/vendors?active_only=false`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!res.ok) throw new Error("Failed to fetch vendors");
      const data = await res.json();
      // Handle both array and {items: [...]} responses, and error objects
      setVendors(Array.isArray(data) ? data : (data.items || []));
    } catch (err) {
      if (showLoading) setError(err.message);
      setVendors([]);
    } finally {
      if (showLoading) setLoading(false);
    }
  };

  const fetchProducts = async () => {
    try {
      const res = await fetch(`${API_URL}/api/v1/items?limit=2000`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (res.ok) {
        const data = await res.json();
        console.log(`[AdminPurchasing] Loaded ${data.items?.length || 0} products`);
        setProducts(data.items || []);
      } else {
        console.warn(`[AdminPurchasing] Failed to fetch products: ${res.status}`);
      }
    } catch (err) {
      // Products fetch failure is non-critical - product selector will just be empty
      console.error("[AdminPurchasing] Error fetching products:", err);
    }
  };

  const fetchLowStock = async () => {
    setLowStockLoading(true);
    try {
      const res = await fetch(`${API_URL}/api/v1/items/low-stock`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (res.ok) {
        const data = await res.json();
        setLowStockItems(data.items || []);
        setLowStockSummary(data.summary || null);
      }
    } catch {
      setError("Failed to load low stock items. Please refresh the page.");
    } finally {
      setLowStockLoading(false);
    }
  };

  const fetchCompanySettings = async () => {
    try {
      const res = await fetch(`${API_URL}/api/v1/settings/company`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (res.ok) {
        const data = await res.json();
        setCompanySettings(data);
      }
    } catch (err) {
      // Non-critical - auto-calc tax just won't work
      console.error("Failed to fetch company settings:", err);
    }
  };

  const fetchPODetails = async (poId) => {
    try {
      const res = await fetch(`${API_URL}/api/v1/purchase-orders/${poId}`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (res.ok) {
        const data = await res.json();
        setSelectedPO(data);
        return data;
      } else {
        setError("Failed to load purchase order details.");
      }
    } catch (err) {
      setError(`Failed to load purchase order: ${err.message || "Network error"}`);
    }
    return null;
  };

  // ============================================================================
  // Vendor CRUD
  // ============================================================================

  const handleSaveVendor = async (vendorData) => {
    try {
      const url = selectedVendor
        ? `${API_URL}/api/v1/vendors/${selectedVendor.id}`
        : `${API_URL}/api/v1/vendors`;
      const method = selectedVendor ? "PUT" : "POST";

      const res = await fetch(url, {
        method,
        headers: {
          Authorization: `Bearer ${token}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify(vendorData),
      });

      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || "Failed to save vendor");
      }

      toast.success(selectedVendor ? "Vendor updated" : "Vendor created");
      setShowVendorModal(false);
      setSelectedVendor(null);
      fetchVendors();
    } catch (err) {
      toast.error(err.message);
    }
  };

  const handleDeleteVendor = async (vendorId) => {
    if (!confirm("Are you sure you want to delete this vendor?")) return;
    try {
      const res = await fetch(`${API_URL}/api/v1/vendors/${vendorId}`, {
        method: "DELETE",
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!res.ok) throw new Error("Failed to delete vendor");
      toast.success("Vendor deleted");
      fetchVendors();
    } catch (err) {
      toast.error(err.message);
    }
  };

  // ============================================================================
  // Purchase Order CRUD
  // ============================================================================

  const handleSavePO = async (poData) => {
    try {
      const url = selectedPO
        ? `${API_URL}/api/v1/purchase-orders/${selectedPO.id}`
        : `${API_URL}/api/v1/purchase-orders`;
      const method = selectedPO ? "PUT" : "POST";

      const res = await fetch(url, {
        method,
        headers: {
          Authorization: `Bearer ${token}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify(poData),
      });

      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || "Failed to save PO");
      }

      toast.success(selectedPO ? "Purchase order updated" : "Purchase order created");
      setShowPOModal(false);
      setSelectedPO(null);
      fetchOrders();
    } catch (err) {
      toast.error(err.message);
    }
  };

  const handleStatusChange = async (poId, newStatus, extraData = {}) => {
    try {
      const res = await fetch(
        `${API_URL}/api/v1/purchase-orders/${poId}/status`,
        {
          method: "POST",
          headers: {
            Authorization: `Bearer ${token}`,
            "Content-Type": "application/json",
          },
          body: JSON.stringify({ status: newStatus, ...extraData }),
        }
      );

      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || "Failed to update status");
      }

      toast.success(`Status updated to ${newStatus}`);
      fetchOrders();
      if (selectedPO?.id === poId) {
        fetchPODetails(poId);
      }
    } catch (err) {
      toast.error(err.message);
    }
  };

  const handleReceive = async (receiveData) => {
    try {
      const res = await fetch(
        `${API_URL}/api/v1/purchase-orders/${selectedPO.id}/receive`,
        {
          method: "POST",
          headers: {
            Authorization: `Bearer ${token}`,
            "Content-Type": "application/json",
          },
          body: JSON.stringify(receiveData),
        }
      );

      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || "Failed to receive items");
      }

      const result = await res.json();
      toast.success(
        `Received ${result.total_quantity} items. ${result.transactions_created.length} inventory transactions created.`
      );
      setShowReceiveModal(false);
      fetchOrders();
      fetchPODetails(selectedPO.id);
      // Refresh products and low stock data to update inventory levels
      fetchProducts();
      fetchLowStock();
    } catch (err) {
      toast.error(err.message);
    }
  };

  // handleFileUpload removed - file uploads are now handled via DocumentUploadPanel

  const handleDeletePO = async (poId, poNumber) => {
    if (!confirm(`Delete PO ${poNumber}? This cannot be undone.`)) return;

    try {
      const res = await fetch(`${API_URL}/api/v1/purchase-orders/${poId}`, {
        method: "DELETE",
        headers: { Authorization: `Bearer ${token}` },
      });

      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || "Failed to delete PO");
      }

      toast.success("Purchase order deleted");
      fetchOrders();
      if (selectedPO?.id === poId) {
        setSelectedPO(null);
      }
    } catch (err) {
      toast.error(err.message);
    }
  };

  const handleCancelPO = async (poId, poNumber) => {
    if (!confirm(`Cancel PO ${poNumber}? This will mark it as cancelled.`))
      return;

    try {
      const res = await fetch(
        `${API_URL}/api/v1/purchase-orders/${poId}/status`,
        {
          method: "POST",
          headers: {
            Authorization: `Bearer ${token}`,
            "Content-Type": "application/json",
          },
          body: JSON.stringify({ status: "cancelled" }),
        }
      );

      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || "Failed to cancel PO");
      }

      toast.success("Purchase order cancelled");
      fetchOrders();
      if (selectedPO?.id === poId) {
        const updated = await res.json();
        setSelectedPO(updated);
      }
    } catch (err) {
      toast.error(err.message);
    }
  };

  // Create PO from selected low-stock items for a specific vendor
  const handleCreatePOFromSelection = async (vendorGroup) => {
    if (!vendorGroup.vendorId) {
      toast.warning("Items without a preferred vendor cannot be bulk-ordered. Please set preferred vendors first.");
      return;
    }

    // Build initial items for PO modal
    const initialItems = vendorGroup.items.map(item => ({
      id: item.id,
      sku: item.sku,
      name: item.name,
      unit: item.unit || "EA",
      shortfall: item.reorder_quantity || item.shortfall || 1,
      last_cost: item.last_cost || 0,
    }));

    // Set initial items and open PO modal
    setInitialItemsForPO(initialItems);
    setSelectedPO(null);

    // Ensure company settings are loaded
    if (!companySettings) {
      await fetchCompanySettings();
    }

    setShowPOModal(true);
    setActiveTab("orders");

    // Clear selection after creating PO
    clearLowStockSelection();

    toast.info(`Creating PO for ${vendorGroup.vendorName} with ${initialItems.length} items`);
  };

  // ============================================================================
  // Filters
  // ============================================================================

  const filteredOrders = orders.filter((o) => {
    if (!filters.search) return true;
    const search = filters.search.toLowerCase();
    return (
      o.po_number?.toLowerCase().includes(search) ||
      o.vendor_name?.toLowerCase().includes(search)
    );
  });

  const filteredVendors = vendors.filter((v) => {
    if (!filters.search) return true;
    const search = filters.search.toLowerCase();
    return (
      v.name?.toLowerCase().includes(search) ||
      v.code?.toLowerCase().includes(search) ||
      v.contact_name?.toLowerCase().includes(search)
    );
  });

  // ============================================================================
  // Render
  // ============================================================================

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex justify-between items-start">
        <div>
          <h1 className="text-2xl font-bold text-white">Purchasing</h1>
          <p className="text-gray-400 mt-1">
            Manage vendors and purchase orders
          </p>
        </div>
        <div className="flex gap-2">
          {activeTab === "vendors" && (
            <button
              onClick={() => {
                setSelectedVendor(null);
                setShowVendorModal(true);
              }}
              className="px-4 py-2 bg-blue-600 hover:bg-blue-700 rounded-lg text-white font-medium"
            >
              + New Vendor
            </button>
          )}
          {activeTab === "orders" && (
            <>
              <button
                onClick={async () => {
                  setSelectedPO(null);
                  // Ensure company settings are loaded for auto-calc tax
                  if (!companySettings) {
                    await fetchCompanySettings();
                  }
                  setShowPOModal(true);
                }}
                className="px-4 py-2 bg-blue-600 hover:bg-blue-700 rounded-lg text-white font-medium"
              >
                + New PO
              </button>
            </>
          )}
        </div>
      </div>

      {/* Purchasing Trend Chart */}
      <div className="bg-gray-900 border border-gray-800 rounded-xl p-4">
        <PurchasingChart
          data={purchasingTrend}
          period={trendPeriod}
          onPeriodChange={setTrendPeriod}
          loading={trendLoading}
        />
      </div>

      {/* Tabs */}
      <div className="flex gap-4 border-b border-gray-800">
        <button
          onClick={() => setActiveTab("orders")}
          className={`pb-2 px-1 text-sm font-medium transition-colors ${
            activeTab === "orders"
              ? "text-blue-400 border-b-2 border-blue-400"
              : "text-gray-400 hover:text-white"
          }`}
        >
          Purchase Orders
        </button>
        <button
          onClick={() => setActiveTab("vendors")}
          className={`pb-2 px-1 text-sm font-medium transition-colors ${
            activeTab === "vendors"
              ? "text-blue-400 border-b-2 border-blue-400"
              : "text-gray-400 hover:text-white"
          }`}
        >
          Vendors
        </button>
        <button
          onClick={() => setActiveTab("import")}
          className={`pb-2 px-1 text-sm font-medium transition-colors ${
            activeTab === "import"
              ? "text-blue-400 border-b-2 border-blue-400"
              : "text-gray-400 hover:text-white"
          }`}
        >
          Import
        </button>
        <button
          onClick={() => setActiveTab("low-stock")}
          className={`pb-2 px-1 text-sm font-medium transition-colors flex items-center gap-2 ${
            activeTab === "low-stock"
              ? "text-orange-400 border-b-2 border-orange-400"
              : "text-gray-400 hover:text-white"
          }`}
        >
          Low Stock
          {lowStockItems.length > 0 && (
            <span className="bg-orange-500/20 text-orange-400 px-1.5 py-0.5 text-xs rounded-full">
              {lowStockItems.length}
            </span>
          )}
        </button>
      </div>

      {/* Filters - hide on import and low-stock tabs */}
      {activeTab !== "import" && activeTab !== "low-stock" && (
        <div className="flex gap-4 bg-gray-900 border border-gray-800 rounded-xl p-4">
          <div className="flex-1">
            <input
              type="text"
              placeholder={
                activeTab === "orders"
                  ? "Search PO number or vendor..."
                  : "Search vendor name or code..."
              }
              value={filters.search}
              onChange={(e) =>
                setFilters({ ...filters, search: e.target.value })
              }
              className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-2 text-white placeholder-gray-500"
            />
          </div>
          {activeTab === "orders" && (
            <select
              value={filters.status}
              onChange={(e) =>
                setFilters({ ...filters, status: e.target.value })
              }
              className="bg-gray-800 border border-gray-700 rounded-lg px-4 py-2 text-white"
            >
              <option value="all">All Status</option>
              <option value="draft">Draft</option>
              <option value="ordered">Ordered</option>
              <option value="shipped">Shipped</option>
              <option value="received">Received</option>
              <option value="closed">Closed</option>
              <option value="cancelled">Cancelled</option>
            </select>
          )}
        </div>
      )}

      {/* Error */}
      {error && (
        <div className="bg-red-500/10 border border-red-500/30 rounded-xl p-4 text-red-400">
          {error}
        </div>
      )}

      {/* Loading - only show for orders and vendors tabs */}
      {loading && (activeTab === "orders" || activeTab === "vendors") && (
        <div className="flex items-center justify-center h-32">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-500"></div>
        </div>
      )}

      {/* Purchase Orders Table */}
      {!loading && activeTab === "orders" && (
        <div className="bg-gray-900 border border-gray-800 rounded-xl overflow-hidden">
          <table className="w-full">
            <thead className="bg-gray-800/50">
              <tr>
                <th className="text-left py-3 px-4 text-xs font-medium text-gray-400 uppercase">
                  PO #
                </th>
                <th className="text-left py-3 px-4 text-xs font-medium text-gray-400 uppercase">
                  Vendor
                </th>
                <th className="text-left py-3 px-4 text-xs font-medium text-gray-400 uppercase">
                  Status
                </th>
                <th className="text-left py-3 px-4 text-xs font-medium text-gray-400 uppercase">
                  Order Date
                </th>
                <th className="text-left py-3 px-4 text-xs font-medium text-gray-400 uppercase">
                  Expected
                </th>
                <th className="text-left py-3 px-4 text-xs font-medium text-gray-400 uppercase">
                  Received
                </th>
                <th className="text-right py-3 px-4 text-xs font-medium text-gray-400 uppercase">
                  Total
                </th>
                <th className="text-center py-3 px-4 text-xs font-medium text-gray-400 uppercase">
                  Lines
                </th>
                <th className="text-right py-3 px-4 text-xs font-medium text-gray-400 uppercase">
                  Actions
                </th>
              </tr>
            </thead>
            <tbody>
              {filteredOrders.map((po) => (
                <tr
                  key={po.id}
                  className="border-b border-gray-800 hover:bg-gray-800/50"
                >
                  <td className="py-3 px-4 text-white font-medium">
                    {po.po_number}
                  </td>
                  <td className="py-3 px-4 text-gray-300">{po.vendor_name}</td>
                  <td className="py-3 px-4">
                    <span
                      className={`px-2 py-1 rounded-full text-xs ${
                        statusColors[po.status]
                      }`}
                    >
                      {po.status}
                    </span>
                  </td>
                  <td className="py-3 px-4 text-gray-400">
                    {po.order_date
                      ? new Date(po.order_date + "T00:00:00").toLocaleDateString()
                      : "-"}
                  </td>
                  <td className="py-3 px-4 text-gray-400">
                    {po.expected_date
                      ? new Date(po.expected_date + "T00:00:00").toLocaleDateString()
                      : "-"}
                  </td>
                  <td className="py-3 px-4 text-gray-400">
                    {po.received_date
                      ? new Date(po.received_date + "T00:00:00").toLocaleDateString()
                      : "-"}
                  </td>
                  <td className="py-3 px-4 text-right text-green-400 font-medium">
                    ${parseFloat(po.total_amount || 0).toFixed(2)}
                  </td>
                  <td className="py-3 px-4 text-center text-gray-400">
                    {po.line_count}
                  </td>
                  <td className="py-3 px-4 text-right space-x-2">
                    <button
                      onClick={async () => {
                        await fetchPODetails(po.id);
                      }}
                      className="text-blue-400 hover:text-blue-300 text-sm"
                    >
                      View
                    </button>
                    {po.status === "draft" && (
                      <button
                        onClick={() => handleStatusChange(po.id, "ordered")}
                        className="text-green-400 hover:text-green-300 text-sm"
                      >
                        Order
                      </button>
                    )}
                    {(po.status === "ordered" || po.status === "shipped") && (
                      <button
                        onClick={async () => {
                          await fetchPODetails(po.id);
                          setShowReceiveModal(true);
                        }}
                        className="text-purple-400 hover:text-purple-300 text-sm"
                      >
                        Receive
                      </button>
                    )}
                    {po.status === "draft" && (
                      <button
                        onClick={() => handleDeletePO(po.id, po.po_number)}
                        className="text-red-400 hover:text-red-300 text-sm"
                      >
                        Delete
                      </button>
                    )}
                    {!["draft", "closed", "cancelled"].includes(po.status) && (
                      <button
                        onClick={() => handleCancelPO(po.id, po.po_number)}
                        className="text-orange-400 hover:text-orange-300 text-sm"
                      >
                        Cancel
                      </button>
                    )}
                  </td>
                </tr>
              ))}
              {filteredOrders.length === 0 && (
                <tr>
                  <td colSpan={9} className="py-12 text-center text-gray-500">
                    No purchase orders found
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      )}

      {/* Vendors Table */}
      {!loading && activeTab === "vendors" && (
        <div className="bg-gray-900 border border-gray-800 rounded-xl overflow-hidden">
          <table className="w-full">
            <thead className="bg-gray-800/50">
              <tr>
                <th className="text-left py-3 px-4 text-xs font-medium text-gray-400 uppercase">
                  Code
                </th>
                <th className="text-left py-3 px-4 text-xs font-medium text-gray-400 uppercase">
                  Name
                </th>
                <th className="text-left py-3 px-4 text-xs font-medium text-gray-400 uppercase">
                  Contact
                </th>
                <th className="text-left py-3 px-4 text-xs font-medium text-gray-400 uppercase">
                  Email
                </th>
                <th className="text-left py-3 px-4 text-xs font-medium text-gray-400 uppercase">
                  Phone
                </th>
                <th className="text-left py-3 px-4 text-xs font-medium text-gray-400 uppercase">
                  Location
                </th>
                <th className="text-center py-3 px-4 text-xs font-medium text-gray-400 uppercase">
                  POs
                </th>
                <th className="text-center py-3 px-4 text-xs font-medium text-gray-400 uppercase">
                  Active
                </th>
                <th className="text-right py-3 px-4 text-xs font-medium text-gray-400 uppercase">
                  Actions
                </th>
              </tr>
            </thead>
            <tbody>
              {filteredVendors.map((vendor) => (
                <tr
                  key={vendor.id}
                  className="border-b border-gray-800 hover:bg-gray-800/50 cursor-pointer"
                  onClick={() => {
                    setSelectedVendor(vendor);
                    setShowVendorDetail(true);
                  }}
                >
                  <td className="py-3 px-4 text-white font-medium">
                    {vendor.code}
                  </td>
                  <td className="py-3 px-4 text-blue-400 hover:text-blue-300">
                    {vendor.name}
                  </td>
                  <td className="py-3 px-4 text-gray-400">
                    {vendor.contact_name || "-"}
                  </td>
                  <td className="py-3 px-4 text-gray-400">
                    {vendor.email || "-"}
                  </td>
                  <td className="py-3 px-4 text-gray-400">
                    {vendor.phone || "-"}
                  </td>
                  <td className="py-3 px-4 text-gray-400">
                    {vendor.city && vendor.state
                      ? `${vendor.city}, ${vendor.state}`
                      : "-"}
                  </td>
                  <td className="py-3 px-4 text-center text-gray-400">
                    {vendor.po_count}
                  </td>
                  <td className="py-3 px-4 text-center">
                    <span
                      className={`px-2 py-1 rounded-full text-xs ${
                        vendor.is_active
                          ? "bg-green-500/20 text-green-400"
                          : "bg-red-500/20 text-red-400"
                      }`}
                    >
                      {vendor.is_active ? "Yes" : "No"}
                    </span>
                  </td>
                  <td className="py-3 px-4 text-right space-x-2" onClick={(e) => e.stopPropagation()}>
                    <button
                      onClick={() => {
                        setSelectedVendor(vendor);
                        setShowVendorDetail(true);
                      }}
                      className="text-gray-400 hover:text-white text-sm"
                    >
                      View
                    </button>
                    <button
                      onClick={() => {
                        setSelectedVendor(vendor);
                        setShowVendorModal(true);
                      }}
                      className="text-blue-400 hover:text-blue-300 text-sm"
                    >
                      Edit
                    </button>
                    <button
                      onClick={() => handleDeleteVendor(vendor.id)}
                      className="text-red-400 hover:text-red-300 text-sm"
                    >
                      Delete
                    </button>
                  </td>
                </tr>
              ))}
              {filteredVendors.length === 0 && (
                <tr>
                  <td colSpan={9} className="py-12 text-center text-gray-500">
                    No vendors found
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      )}

      {/* Import Tab — Amazon Business import is a PRO feature */}
      {activeTab === "import" && (
        <div className="bg-gray-900 border border-gray-800 rounded-xl p-8 text-center">
          <h3 className="text-lg font-semibold text-white mb-2">
            Amazon Business Import
          </h3>
          <p className="text-gray-400 text-sm mb-4">
            Import purchase orders directly from Amazon Business CSV exports.
            Available in FilaOps Pro.
          </p>
          <a
            href="https://filaops.com/pricing"
            target="_blank"
            rel="noopener noreferrer"
            className="inline-block px-4 py-2 bg-blue-600 hover:bg-blue-700 rounded-lg text-white font-medium"
          >
            Learn More
          </a>
        </div>
      )}

      {/* Low Stock Tab */}
      {activeTab === "low-stock" && (
        <div className="space-y-6">
          {/* Enhanced Summary Cards */}
          {lowStockSummary && (
            <div className="grid grid-cols-4 gap-4">
              <div className="bg-red-500/10 border border-red-500/30 rounded-xl p-4">
                <div className="text-3xl font-bold text-red-400">
                  {lowStockSummary.critical_count || 0}
                </div>
                <div className="text-sm text-gray-400">Critical (Out of Stock)</div>
              </div>
              <div className="bg-orange-500/10 border border-orange-500/30 rounded-xl p-4">
                <div className="text-3xl font-bold text-orange-400">
                  {lowStockSummary.urgent_count || 0}
                </div>
                <div className="text-sm text-gray-400">Urgent (&lt;50% Reorder)</div>
              </div>
              <div className="bg-yellow-500/10 border border-yellow-500/30 rounded-xl p-4">
                <div className="text-3xl font-bold text-yellow-400">
                  {lowStockSummary.low_count || 0}
                </div>
                <div className="text-sm text-gray-400">Low Stock</div>
              </div>
              <div className="bg-gray-700/30 border border-gray-600 rounded-xl p-4">
                <div className="text-3xl font-bold text-white">
                  ${lowStockSummary.total_shortfall_value?.toFixed(0) || "0"}
                </div>
                <div className="text-sm text-gray-400">Shortfall Value</div>
              </div>
            </div>
          )}

          {/* MRP Shortage Alert */}
          {lowStockSummary?.mrp_shortage_count > 0 && (
            <div className="bg-blue-500/10 border border-blue-500/30 rounded-xl p-4 flex items-center gap-3">
              <svg className="w-5 h-5 text-blue-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
              <span className="text-blue-300 text-sm">
                <strong>{lowStockSummary.mrp_shortage_count}</strong> items have MRP-driven shortages from active sales orders
              </span>
            </div>
          )}

          {/* Low Stock Table */}
          <div className="bg-gray-900 border border-gray-800 rounded-xl overflow-hidden">
            <div className="p-4 border-b border-gray-800 flex justify-between items-center">
              <div>
                <h3 className="text-lg font-semibold text-white">
                  Items Requiring Attention
                </h3>
                <p className="text-sm text-gray-400 mt-0.5">
                  {lowStockItems.length} items below reorder point or with MRP shortages
                  {selectedLowStockIds.size > 0 && (
                    <span className="ml-2 text-blue-400">({selectedLowStockIds.size} selected)</span>
                  )}
                </p>
              </div>
              <div className="flex items-center gap-2">
                {/* Create PO Dropdown - shows when items are selected */}
                {selectedLowStockIds.size > 0 && selectedItemsByVendor.length > 0 && (
                  <div className="relative group">
                    <button className="px-3 py-1.5 bg-blue-600 hover:bg-blue-700 rounded-lg text-sm text-white flex items-center gap-2">
                      <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 6v6m0 0v6m0-6h6m-6 0H6" />
                      </svg>
                      Create PO ({selectedLowStockIds.size})
                      <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
                      </svg>
                    </button>
                    <div className="absolute right-0 mt-1 w-64 bg-gray-800 border border-gray-700 rounded-lg shadow-xl opacity-0 invisible group-hover:opacity-100 group-hover:visible transition-all z-50">
                      {selectedItemsByVendor.map((group) => (
                        <button
                          key={group.vendorId || 'no_vendor'}
                          onClick={() => handleCreatePOFromSelection(group)}
                          disabled={!group.vendorId}
                          className={`w-full text-left px-4 py-2 text-sm hover:bg-gray-700 first:rounded-t-lg last:rounded-b-lg ${
                            !group.vendorId ? 'text-gray-500 cursor-not-allowed' : 'text-white'
                          }`}
                        >
                          <div className="font-medium">{group.vendorName}</div>
                          <div className="text-xs text-gray-400">
                            {group.items.length} items · ${group.totalValue.toFixed(2)}
                          </div>
                        </button>
                      ))}
                    </div>
                  </div>
                )}

                {/* Clear Selection */}
                {selectedLowStockIds.size > 0 && (
                  <button
                    onClick={clearLowStockSelection}
                    className="px-3 py-1.5 bg-gray-700 hover:bg-gray-600 rounded-lg text-sm text-gray-300"
                  >
                    Clear
                  </button>
                )}

                <button
                  onClick={fetchLowStock}
                  disabled={lowStockLoading}
                  className="px-3 py-1.5 bg-gray-800 hover:bg-gray-700 rounded-lg text-sm text-gray-300 flex items-center gap-2"
                >
                  <svg className={`w-4 h-4 ${lowStockLoading ? 'animate-spin' : ''}`} fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
                  </svg>
                  {lowStockLoading ? "Refreshing..." : "Refresh"}
                </button>
              </div>
            </div>

            {lowStockLoading ? (
              <div className="p-8 text-center text-gray-400">
                <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-500 mx-auto mb-3"></div>
                Loading low stock items...
              </div>
            ) : lowStockItems.length === 0 ? (
              <div className="p-12 text-center">
                <svg className="w-16 h-16 mx-auto text-green-400 mb-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
                </svg>
                <div className="text-green-400 text-lg font-medium mb-2">
                  All Stock Levels OK
                </div>
                <p className="text-gray-400 text-sm">
                  No items are currently below their reorder point.
                </p>
              </div>
            ) : (
              <table className="w-full">
                <thead className="bg-gray-800/50">
                  <tr>
                    <th className="text-center py-3 px-2 text-xs font-medium text-gray-400 uppercase w-10">
                      <input
                        type="checkbox"
                        checked={lowStockItems.length > 0 && selectedLowStockIds.size === lowStockItems.length}
                        onChange={toggleAllLowStock}
                        className="w-4 h-4 rounded border-gray-600 bg-gray-800 text-blue-600 focus:ring-blue-500 focus:ring-offset-gray-900"
                      />
                    </th>
                    <th className="text-left py-3 px-4 text-xs font-medium text-gray-400 uppercase">
                      Urgency
                    </th>
                    <th className="text-left py-3 px-4 text-xs font-medium text-gray-400 uppercase">
                      Item
                    </th>
                    <th className="text-left py-3 px-4 text-xs font-medium text-gray-400 uppercase">
                      Category
                    </th>
                    <th className="text-right py-3 px-4 text-xs font-medium text-gray-400 uppercase">
                      Available
                    </th>
                    <th className="text-right py-3 px-4 text-xs font-medium text-gray-400 uppercase">
                      Reorder Pt
                    </th>
                    <th className="text-right py-3 px-4 text-xs font-medium text-gray-400 uppercase">
                      Shortfall
                    </th>
                    <th className="text-right py-3 px-4 text-xs font-medium text-gray-400 uppercase">
                      Actions
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {lowStockItems.map((item) => {
                    // Determine urgency level
                    const isCritical = item.available_qty <= 0;
                    const isUrgent = !isCritical && item.reorder_point && item.available_qty <= item.reorder_point * 0.5;
                    const hasMrpShortage = item.mrp_shortage > 0;

                    return (
                      <tr
                        key={item.id}
                        className={`border-b border-gray-800 hover:bg-gray-800/30 ${
                          isCritical ? 'bg-red-500/5' : isUrgent ? 'bg-orange-500/5' : ''
                        } ${selectedLowStockIds.has(item.id) ? 'bg-blue-500/10' : ''}`}
                      >
                        <td className="py-3 px-2 text-center">
                          <input
                            type="checkbox"
                            checked={selectedLowStockIds.has(item.id)}
                            onChange={() => toggleLowStockItem(item.id)}
                            className="w-4 h-4 rounded border-gray-600 bg-gray-800 text-blue-600 focus:ring-blue-500 focus:ring-offset-gray-900"
                          />
                        </td>
                        <td className="py-3 px-4">
                          <div className="flex items-center gap-2">
                            {isCritical && (
                              <span className="px-2 py-0.5 bg-red-500/20 text-red-400 rounded text-xs font-medium">
                                CRITICAL
                              </span>
                            )}
                            {isUrgent && (
                              <span className="px-2 py-0.5 bg-orange-500/20 text-orange-400 rounded text-xs font-medium">
                                URGENT
                              </span>
                            )}
                            {!isCritical && !isUrgent && (
                              <span className="px-2 py-0.5 bg-yellow-500/20 text-yellow-400 rounded text-xs font-medium">
                                LOW
                              </span>
                            )}
                            {hasMrpShortage && (
                              <span className="px-1.5 py-0.5 bg-blue-500/20 text-blue-400 rounded text-xs" title="MRP shortage from active orders">
                                MRP
                              </span>
                            )}
                          </div>
                        </td>
                        <td className="py-3 px-4">
                          <div className="text-white font-medium">
                            {item.name}
                          </div>
                          <div className="text-gray-500 text-xs">{item.sku}</div>
                        </td>
                        <td className="py-3 px-4 text-gray-400 text-sm">
                          {item.category_name || "-"}
                        </td>
                        <td className="py-3 px-4 text-right">
                          <span
                            className={
                              isCritical
                                ? "text-red-400 font-medium"
                                : isUrgent
                                ? "text-orange-400"
                                : "text-yellow-400"
                            }
                          >
                            {item.available_qty?.toFixed(2)} {item.unit}
                          </span>
                        </td>
                        <td className="py-3 px-4 text-right text-gray-400">
                          {item.reorder_point?.toFixed(2) || "-"} {item.unit}
                        </td>
                        <td className="py-3 px-4 text-right">
                          <span className="text-red-400 font-medium">
                            -{item.shortfall?.toFixed(2)} {item.unit}
                          </span>
                          {item.mrp_shortage > 0 && item.shortage_source === "mrp" && (
                            <div className="text-xs text-blue-400 mt-1">
                              (MRP: {item.mrp_shortage.toFixed(2)})
                            </div>
                          )}
                          {item.mrp_shortage > 0 && item.shortage_source === "both" && (
                            <div className="text-xs text-purple-400 mt-1">
                              +MRP: {item.mrp_shortage.toFixed(2)}
                            </div>
                          )}
                        </td>
                        <td className="py-3 px-4 text-right">
                          <div className="flex gap-2 justify-end">
                            <button
                              onClick={async () => {
                                setSelectedPO(null);
                                if (!companySettings) {
                                  await fetchCompanySettings();
                                }
                                setShowPOModal(true);
                                // TODO: Pre-populate with this item
                              }}
                              className="px-3 py-1 bg-blue-600 hover:bg-blue-700 rounded text-xs text-white"
                            >
                              Create PO
                            </button>
                            <button
                              onClick={() =>
                                (window.location.href = `/admin?tab=items&edit=${item.id}`)
                              }
                              className="px-3 py-1 bg-gray-700 hover:bg-gray-600 rounded text-xs text-gray-300"
                            >
                              Edit Item
                            </button>
                          </div>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            )}
          </div>
        </div>
      )}

      {/* Vendor Modal */}
      {showVendorModal && (
        <VendorModal
          vendor={selectedVendor}
          onClose={() => {
            setShowVendorModal(false);
            setSelectedVendor(null);
          }}
          onSave={handleSaveVendor}
        />
      )}

      {/* Vendor Detail Panel */}
      {showVendorDetail && selectedVendor && (
        <VendorDetailPanel
          vendor={selectedVendor}
          onClose={() => {
            setShowVendorDetail(false);
            setSelectedVendor(null);
          }}
          onEdit={(vendor) => {
            setShowVendorDetail(false);
            setSelectedVendor(vendor);
            setShowVendorModal(true);
          }}
          onCreatePO={async () => {
            setShowVendorDetail(false);
            // Pre-select the vendor for the new PO
            setSelectedPO(null);
            if (!companySettings) {
              await fetchCompanySettings();
            }
            setShowPOModal(true);
            // TODO: POCreateModal could accept preselectedVendorId prop
          }}
          onViewPO={async (poId) => {
            setShowVendorDetail(false);
            await fetchPODetails(poId);
          }}
        />
      )}

      {/* PO Modal */}
      {showPOModal && (
        <POCreateModal
          po={selectedPO}
          vendors={vendors}
          products={enhancedProducts}
          companySettings={companySettings}
          initialItems={initialItemsForPO}
          onClose={() => {
            setShowPOModal(false);
            setSelectedPO(null);
            setInitialItemsForPO([]); // Clear initial items when closing
          }}
          onSave={handleSavePO}
          onProductsRefresh={fetchProducts}
        />
      )}

      {/* PO Detail Modal */}
      {selectedPO && !showPOModal && !showReceiveModal && (
        <PODetailModal
          po={selectedPO}
          onClose={() => setSelectedPO(null)}
          onStatusChange={handleStatusChange}
          onEdit={() => setShowPOModal(true)}
          onReceive={() => setShowReceiveModal(true)}
        />
      )}

      {/* Receive Modal */}
      {showReceiveModal && selectedPO && (
        <ReceiveModal
          po={selectedPO}
          onClose={() => setShowReceiveModal(false)}
          onReceive={handleReceive}
        />
      )}


    </div>
  );
}
