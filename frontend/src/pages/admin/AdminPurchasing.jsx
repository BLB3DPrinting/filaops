import { useState, useEffect, useRef, useMemo } from "react";
import { useSearchParams } from "react-router-dom";
import { API_URL } from "../../config/api";
import { useToast } from "../../components/Toast";
import PurchasingChart from "../../components/purchasing/PurchasingChart";
import VendorModal from "../../components/purchasing/VendorModal";
import VendorDetailPanel from "../../components/purchasing/VendorDetailPanel";
import POCreateModal from "../../components/purchasing/POCreateModal";
import PODetailModal from "../../components/purchasing/PODetailModal";
import ReceiveModal from "../../components/purchasing/ReceiveModal";
import PurchaseOrdersTab from "../../components/purchasing/PurchaseOrdersTab";
import VendorsTab from "../../components/purchasing/VendorsTab";
import LowStockTab from "../../components/purchasing/LowStockTab";

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
    setTrendLoading(true);
    try {
      const res = await fetch(
        `${API_URL}/api/v1/admin/dashboard/purchasing-trend?period=${period}`,
        { credentials: "include" }
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
    // Products are lazy-loaded when PO modal opens (not on every tab change)
  }, [activeTab, filters.status]);

  // Lazy-load products when PO modal opens (avoids 8k+ item fetch on page load)
  useEffect(() => {
    if (showPOModal && products.length === 0) {
      fetchProducts();
    }
  }, [showPOModal]);

  // Also fetch products when create_po URL param is present
  useEffect(() => {
    if (searchParams.get("create_po") === "true" && products.length === 0) {
      fetchProducts();
    }
  }, [searchParams]);

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
        credentials: "include",
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
        credentials: "include",
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
        credentials: "include",
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
        credentials: "include",
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
        credentials: "include",
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
        credentials: "include",
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
        credentials: "include",
        headers: {
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
        credentials: "include",
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
        credentials: "include",
        headers: {
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
          credentials: "include",
          headers: {
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
          credentials: "include",
          headers: {
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
        credentials: "include",
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
          credentials: "include",
          headers: {
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

  // Handle "Create PO" from individual low-stock row
  const handleCreatePOFromLowStockItem = async () => {
    setSelectedPO(null);
    if (!companySettings) {
      await fetchCompanySettings();
    }
    setShowPOModal(true);
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
        <PurchaseOrdersTab
          filteredOrders={filteredOrders}
          onViewPO={fetchPODetails}
          onStatusChange={handleStatusChange}
          onReceivePO={async (poId) => {
            await fetchPODetails(poId);
            setShowReceiveModal(true);
          }}
          onDeletePO={handleDeletePO}
          onCancelPO={handleCancelPO}
        />
      )}

      {/* Vendors Table */}
      {!loading && activeTab === "vendors" && (
        <VendorsTab
          filteredVendors={filteredVendors}
          onViewVendor={(vendor) => {
            setSelectedVendor(vendor);
            setShowVendorDetail(true);
          }}
          onEditVendor={(vendor) => {
            setSelectedVendor(vendor);
            setShowVendorModal(true);
          }}
          onDeleteVendor={handleDeleteVendor}
        />
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
        <LowStockTab
          lowStockItems={lowStockItems}
          lowStockSummary={lowStockSummary}
          lowStockLoading={lowStockLoading}
          selectedLowStockIds={selectedLowStockIds}
          selectedItemsByVendor={selectedItemsByVendor}
          toggleLowStockItem={toggleLowStockItem}
          toggleAllLowStock={toggleAllLowStock}
          clearLowStockSelection={clearLowStockSelection}
          fetchLowStock={fetchLowStock}
          onCreatePO={handleCreatePOFromLowStockItem}
          onCreatePOFromSelection={handleCreatePOFromSelection}
        />
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
