import { useState, useEffect, useCallback } from "react";
import ItemForm from "../../components/ItemForm";
import MaterialForm from "../../components/MaterialForm";
import RoutingEditor from "../../components/RoutingEditor";
import StatCard from "../../components/StatCard";
import { ItemCard } from "../../components/inventory/ItemCard";
import ConfirmDialog from "../../components/ConfirmDialog";
import { API_URL } from "../../config/api";
import { useToast } from "../../components/Toast";
import CategoryNode from "../../components/items/CategoryNode";
import CategoryModal from "../../components/items/CategoryModal";
import BulkUpdateModal from "../../components/items/BulkUpdateModal";
import ItemsTable from "../../components/items/ItemsTable";
import AdjustmentReasonModal from "../../components/items/AdjustmentReasonModal";

// Item type options
const ITEM_TYPES = [
  { value: "finished_good", label: "Finished Good", color: "blue" },
  { value: "component", label: "Component", color: "purple" },
  { value: "material", label: "Material", color: "orange" },
  { value: "filament", label: "Filament (Legacy)", color: "orange" },
  { value: "supply", label: "Supply", color: "yellow" },
  { value: "service", label: "Service", color: "green" },
];

export default function AdminItems() {
  const toast = useToast();
  const [items, setItems] = useState([]);
  const [categories, setCategories] = useState([]);
  const [categoryTree, setCategoryTree] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [selectedCategory, setSelectedCategory] = useState(null);
  const [expandedCategories, setExpandedCategories] = useState(new Set());
  const [viewMode, setViewMode] = useState("table"); // "table" | "cards"
  const [filters, setFilters] = useState({
    search: "",
    itemType: "all",
    activeOnly: true,
  });
  const [quickFilter, setQuickFilter] = useState(null); // null | "all" | "finished_good" | "component" | "material" | "supply" | "needs_reorder"

  // Sort state - default to stock status (shortage first)
  const [sortConfig, setSortConfig] = useState({ key: "stock_status", direction: "asc" });

  // Back to top visibility
  const [showBackToTop, setShowBackToTop] = useState(false);

  // Pagination state - use 200 as default to get all items for accurate stats
  const [pagination, setPagination] = useState({
    page: 1,
    pageSize: 200,
    total: 0,
  });

  // Stats state - stored separately to persist across filter changes
  const [allItemsStats, setAllItemsStats] = useState({
    total: 0,
    finishedGoods: 0,
    components: 0,
    supplies: 0,
    materials: 0,
    needsReorder: 0,
  });

  // Modal states
  const [showItemModal, setShowItemModal] = useState(false);
  const [showMaterialModal, setShowMaterialModal] = useState(false);
  const [showCategoryModal, setShowCategoryModal] = useState(false);
  const [showRoutingEditor, setShowRoutingEditor] = useState(false);
  const [selectedItemForRouting, setSelectedItemForRouting] = useState(null);
  const [editingItem, setEditingItem] = useState(null);
  const [editingCategory, setEditingCategory] = useState(null);

  // Recost states
  const [recosting, setRecosting] = useState(false);
  const [recostResult, setRecostResult] = useState(null);

  // Bulk selection states
  const [selectedItems, setSelectedItems] = useState(new Set());
  const [showBulkUpdateModal, setShowBulkUpdateModal] = useState(false);

  // Inventory adjustment states
  const [editingQtyItem, setEditingQtyItem] = useState(null);
  const [editingQtyValue, setEditingQtyValue] = useState("");
  const [adjustmentReason, setAdjustmentReason] = useState("");
  const [adjustmentNotes, setAdjustmentNotes] = useState("");
  const [adjustingQty, setAdjustingQty] = useState(false);
  const [showAdjustmentModal, setShowAdjustmentModal] = useState(false);

  // Confirm dialog states
  const [showDeleteCategoryConfirm, setShowDeleteCategoryConfirm] = useState(false);
  const [categoryToDelete, setCategoryToDelete] = useState(null);
  const [showRecostConfirm, setShowRecostConfirm] = useState(false);

  const token = localStorage.getItem("adminToken");

  const fetchCategories = useCallback(async () => {
    if (!token) return;
    try {
      // Fetch flat list
      const res = await fetch(
        `${API_URL}/api/v1/items/categories?include_inactive=true`,
        {
          headers: { Authorization: `Bearer ${token}` },
        }
      );
      if (!res.ok) throw new Error("Failed to fetch categories");
      const data = await res.json();
      setCategories(data);

      // Fetch tree structure
      const treeRes = await fetch(`${API_URL}/api/v1/items/categories/tree`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (treeRes.ok) {
        const treeData = await treeRes.json();
        setCategoryTree(treeData);
      }
    } catch {
      // Category fetch failure is non-critical - category tree will just be empty
    }
  }, [token]);

  useEffect(() => {
    fetchCategories();
  }, [fetchCategories]);

  const fetchItems = useCallback(async () => {
    if (!token) return;
    setLoading(true);
    try {
      const params = new URLSearchParams();
      params.set("limit", pagination.pageSize.toString());
      params.set(
        "offset",
        ((pagination.page - 1) * pagination.pageSize).toString()
      );
      params.set("active_only", filters.activeOnly.toString());
      if (selectedCategory)
        params.set("category_id", selectedCategory.toString());
      if (filters.itemType !== "all") params.set("item_type", filters.itemType);
      if (filters.search) params.set("search", filters.search);

      const res = await fetch(`${API_URL}/api/v1/items?${params}`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!res.ok) throw new Error("Failed to fetch items");
      const data = await res.json();
      setItems(data.items || []);
      setPagination((prev) => ({ ...prev, total: data.total || 0 }));
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, [
    token,
    pagination.pageSize,
    pagination.page,
    filters.activeOnly,
    filters.itemType,
    filters.search,
    selectedCategory,
  ]);

  useEffect(() => {
    fetchItems();
  }, [fetchItems]);

  // Reset to page 1 when filters change
  useEffect(() => {
    setPagination((prev) => ({ ...prev, page: 1 }));
  }, [selectedCategory, filters.itemType, filters.activeOnly]);

  // Calculate stats from items when viewing all items (no type filter, no search, page 1)
  useEffect(() => {
    if (filters.itemType === "all" && !filters.search && pagination.page === 1 && items.length > 0) {
      const useDirectCount = pagination.total <= pagination.pageSize;

      if (useDirectCount) {
        setAllItemsStats({
          total: items.length,
          finishedGoods: items.filter((i) => i.item_type === "finished_good").length,
          components: items.filter((i) => i.item_type === "component").length,
          supplies: items.filter((i) => i.item_type === "supply").length,
          materials: items.filter((i) => i.item_type === "material" || i.material_type_id).length,
          needsReorder: items.filter((i) => i.needs_reorder).length,
        });
      } else {
        setAllItemsStats({
          total: pagination.total,
          finishedGoods: items.filter((i) => i.item_type === "finished_good").length,
          components: items.filter((i) => i.item_type === "component").length,
          supplies: items.filter((i) => i.item_type === "supply").length,
          materials: items.filter((i) => i.item_type === "material" || i.material_type_id).length,
          needsReorder: items.filter((i) => i.needs_reorder).length,
        });
      }
    }
  }, [items, filters.itemType, filters.search, pagination.page, pagination.total, pagination.pageSize]);

  // Sort and filter helpers
  const getItemStockStatus = (item) => {
    const available = parseFloat(item.available_qty || 0);
    const onHand = parseFloat(item.on_hand_qty || 0);

    if (available < 0) return 0;  // Shortage (critical)
    if (available === 0) return 1; // Out of Stock (short)
    if (onHand > 0 && available < onHand * 0.2) return 2; // Low Stock (tight)
    return 3; // In Stock (healthy)
  };

  const sortItems = (itemsToSort) => {
    if (!sortConfig.key) return itemsToSort;

    return [...itemsToSort].sort((a, b) => {
      let aVal, bVal;

      if (sortConfig.key === "stock_status") {
        aVal = getItemStockStatus(a);
        bVal = getItemStockStatus(b);
      } else {
        aVal = a[sortConfig.key];
        bVal = b[sortConfig.key];

        if (aVal == null) aVal = "";
        if (bVal == null) bVal = "";

        const numericFields = ["on_hand_qty", "available_qty", "reorder_point", "standard_cost", "selling_price"];
        if (numericFields.includes(sortConfig.key)) {
          aVal = parseFloat(aVal) || 0;
          bVal = parseFloat(bVal) || 0;
        }

        if (sortConfig.key === "active" || sortConfig.key === "needs_reorder") {
          aVal = aVal ? 1 : 0;
          bVal = bVal ? 1 : 0;
        }
      }

      if (aVal < bVal) return sortConfig.direction === "asc" ? -1 : 1;
      if (aVal > bVal) return sortConfig.direction === "asc" ? 1 : -1;
      return 0;
    });
  };

  const handleSort = (key) => {
    setSortConfig((prev) => ({
      key,
      direction: prev.key === key && prev.direction === "asc" ? "desc" : "asc",
    }));
  };

  // Apply quick filter for needs_reorder (client-side since it's a flag)
  let baseItems = items;
  if (quickFilter === "needs_reorder") {
    baseItems = items.filter((item) => item.needs_reorder);
  }

  const filteredItems = viewMode === "cards"
    ? [...baseItems].sort((a, b) => getItemStockStatus(a) - getItemStockStatus(b))
    : sortItems(baseItems);

  // Back to top scroll handler
  useEffect(() => {
    const handleScroll = () => {
      setShowBackToTop(window.scrollY > 400);
    };
    window.addEventListener("scroll", handleScroll);
    return () => window.removeEventListener("scroll", handleScroll);
  }, []);

  const scrollToTop = () => {
    window.scrollTo({ top: 0, behavior: "smooth" });
  };

  // Debounced search
  useEffect(() => {
    const timer = setTimeout(() => {
      if (pagination.page === 1) {
        fetchItems();
      } else {
        setPagination((prev) => ({ ...prev, page: 1 }));
      }
    }, 300);
    return () => clearTimeout(timer);
  }, [filters.search, pagination.page, fetchItems]);

  // Pagination helpers
  const totalPages = Math.ceil(pagination.total / pagination.pageSize);
  const canGoPrev = pagination.page > 1;
  const canGoNext = pagination.page < totalPages;

  // Toggle category expand/collapse
  const toggleExpand = (categoryId) => {
    setExpandedCategories((prev) => {
      const next = new Set(prev);
      if (next.has(categoryId)) {
        next.delete(categoryId);
      } else {
        next.add(categoryId);
      }
      return next;
    });
  };

  // Delete category handler
  const handleDeleteCategory = (category) => {
    setCategoryToDelete(category);
    setShowDeleteCategoryConfirm(true);
  };

  const confirmDeleteCategory = async () => {
    if (!categoryToDelete) return;
    try {
      const res = await fetch(
        `${API_URL}/api/v1/items/categories/${categoryToDelete.id}`,
        {
          method: "DELETE",
          headers: { Authorization: `Bearer ${token}` },
        }
      );
      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || "Failed to delete category");
      }
      toast.success("Category deleted");
      fetchCategories();
    } catch (err) {
      toast.error(err.message);
    } finally {
      setShowDeleteCategoryConfirm(false);
      setCategoryToDelete(null);
    }
  };

  const stats = allItemsStats;

  // Save category
  const handleSaveCategory = async (catData) => {
    try {
      const url = editingCategory
        ? `${API_URL}/api/v1/items/categories/${editingCategory.id}`
        : `${API_URL}/api/v1/items/categories`;
      const method = editingCategory ? "PATCH" : "POST";

      const res = await fetch(url, {
        method,
        headers: {
          Authorization: `Bearer ${token}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify(catData),
      });

      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || "Failed to save category");
      }

      toast.success(editingCategory ? "Category updated" : "Category created");
      setShowCategoryModal(false);
      setEditingCategory(null);
      fetchCategories();
    } catch (err) {
      toast.error(err.message);
    }
  };

  // Bulk selection handlers
  const handleSelectAll = (e) => {
    if (e.target.checked) {
      setSelectedItems(new Set(filteredItems.map((item) => item.id)));
    } else {
      setSelectedItems(new Set());
    }
  };

  const handleSelectItem = (itemId) => {
    const newSelected = new Set(selectedItems);
    if (newSelected.has(itemId)) {
      newSelected.delete(itemId);
    } else {
      newSelected.add(itemId);
    }
    setSelectedItems(newSelected);
  };

  const isAllSelected =
    filteredItems.length > 0 && selectedItems.size === filteredItems.length;
  const isIndeterminate =
    selectedItems.size > 0 && selectedItems.size < filteredItems.length;

  // Inventory quantity adjustment handler
  const handleSaveQtyAdjustment = async (item) => {
    const inputQty = parseFloat(editingQtyValue);
    if (isNaN(inputQty) || inputQty < 0) {
      toast.error("Please enter a valid quantity");
      return;
    }

    if (!adjustmentReason.trim()) {
      setShowAdjustmentModal(true);
      return;
    }

    let newQty = inputQty;
    let inputUnit = item.material_type_id ? "G" : (item.unit || "EA");

    setAdjustingQty(true);
    try {
      const finalReason = adjustmentReason === "Other" && adjustmentNotes.trim()
        ? adjustmentNotes.trim()
        : adjustmentReason.trim();

      const params = new URLSearchParams({
        product_id: item.id.toString(),
        location_id: "1",
        new_on_hand_quantity: newQty.toString(),
        adjustment_reason: finalReason,
        input_unit: inputUnit,
      });
      if (adjustmentReason !== "Other" && adjustmentNotes.trim()) {
        params.set("notes", adjustmentNotes.trim());
      }

      const res = await fetch(
        `${API_URL}/api/v1/inventory/adjust-quantity?${params}`,
        {
          method: "POST",
          headers: {
            Authorization: `Bearer ${token}`,
            "Content-Type": "application/json",
          },
        }
      );

      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || "Failed to adjust inventory");
      }

      const result = await res.json();
      const displayQty = item.material_type_id ? result.new_quantity.toFixed(0) : result.new_quantity.toFixed(0);
      const displayUnit = item.material_type_id ? "g" : (item.unit || "EA");
      const prevQty = item.material_type_id ? result.previous_quantity.toFixed(0) : result.previous_quantity.toFixed(0);
      toast.success(
        `Inventory adjusted: ${prevQty} → ${displayQty} ${displayUnit}`
      );

      setEditingQtyItem(null);
      setEditingQtyValue("");
      setAdjustmentReason("");
      setAdjustmentNotes("");
      setShowAdjustmentModal(false);

      fetchItems();
    } catch (err) {
      toast.error(err.message || "Failed to adjust inventory quantity");
    } finally {
      setAdjustingQty(false);
    }
  };

  const handleConfirmAdjustment = () => {
    if (!adjustmentReason.trim()) {
      toast.error("Please select an adjustment reason");
      return;
    }
    if (adjustmentReason === "Other" && !adjustmentNotes.trim()) {
      toast.error("Please specify the reason for 'Other'");
      return;
    }
    if (editingQtyItem) {
      handleSaveQtyAdjustment(editingQtyItem);
    }
  };

  // Bulk update handler
  const handleBulkUpdate = async (updateData) => {
    if (selectedItems.size === 0) {
      toast.warning("Please select at least one item");
      return;
    }

    try {
      const res = await fetch(`${API_URL}/api/v1/items/bulk-update`, {
        method: "POST",
        headers: {
          Authorization: `Bearer ${token}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          item_ids: Array.from(selectedItems),
          ...updateData,
        }),
      });

      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || "Failed to update items");
      }

      const data = await res.json();
      toast.success(`Successfully updated ${data.message}`);
      setSelectedItems(new Set());
      setShowBulkUpdateModal(false);
      fetchItems();
    } catch (err) {
      toast.error(err.message);
    }
  };

  // Recost all items
  const handleRecostAll = () => {
    setShowRecostConfirm(true);
  };

  const confirmRecostAll = async () => {
    setShowRecostConfirm(false);
    setRecosting(true);
    setRecostResult(null);
    try {
      const params = new URLSearchParams();
      if (selectedCategory)
        params.set("category_id", selectedCategory.toString());
      if (filters.itemType !== "all") params.set("item_type", filters.itemType);

      const res = await fetch(`${API_URL}/api/v1/items/recost-all?${params}`, {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` },
      });

      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || "Failed to recost items");
      }

      const data = await res.json();
      setRecostResult(data);
      toast.success(`Recosted ${data.updated || 0} items`);
      fetchItems();
    } catch (err) {
      toast.error(err.message);
    } finally {
      setRecosting(false);
    }
  };

  return (
    <div data-testid="items-page" className="flex gap-6 h-full">
      {/* Left Sidebar - Categories */}
      <div className="w-64 flex-shrink-0">
        <div className="bg-gray-900 border border-gray-800 rounded-xl p-4">
          <div className="flex justify-between items-center mb-4">
            <h2 className="text-lg font-semibold text-white">Categories</h2>
            <button
              onClick={() => {
                setEditingCategory(null);
                setShowCategoryModal(true);
              }}
              className="text-blue-400 hover:text-blue-300 text-sm"
            >
              + Add
            </button>
          </div>

          <button
            onClick={() => setSelectedCategory(null)}
            className={`w-full text-left px-3 py-2 rounded-lg text-sm mb-2 transition-colors ${
              selectedCategory === null
                ? "bg-blue-600/20 text-blue-400 border border-blue-500/30"
                : "text-gray-400 hover:bg-gray-800 hover:text-white"
            }`}
          >
            All Items
          </button>

          <div className="space-y-1">
            {categoryTree.map((node) => (
              <CategoryNode
                key={node.id}
                node={node}
                expandedCategories={expandedCategories}
                selectedCategory={selectedCategory}
                toggleExpand={toggleExpand}
                setSelectedCategory={setSelectedCategory}
                setEditingCategory={setEditingCategory}
                setShowCategoryModal={setShowCategoryModal}
                handleDeleteCategory={handleDeleteCategory}
              />
            ))}
          </div>
        </div>
      </div>

      {/* Main Content */}
      <div className="flex-1 space-y-6">
        {/* Header */}
        <div className="flex justify-between items-center">
          <div>
            <h1 className="text-2xl font-bold text-white">Items</h1>
            <p className="text-gray-400 mt-1">
              Manage products, components, supplies, and services
            </p>
          </div>
          <div className="flex gap-2">
            {/* View Toggle */}
            <div className="flex bg-gray-800 rounded-lg p-1 border border-gray-700">
              <button
                data-testid="view-toggle-table"
                onClick={() => setViewMode("table")}
                className={`px-3 py-1 rounded text-sm font-medium transition-colors ${
                  viewMode === "table"
                    ? "bg-blue-600 text-white"
                    : "text-gray-400 hover:text-white"
                }`}
              >
                Table
              </button>
              <button
                data-testid="view-toggle-cards"
                onClick={() => setViewMode("cards")}
                className={`px-3 py-1 rounded text-sm font-medium transition-colors ${
                  viewMode === "cards"
                    ? "bg-blue-600 text-white"
                    : "text-gray-400 hover:text-white"
                }`}
              >
                Cards
              </button>
            </div>
            <button
              onClick={fetchItems}
              disabled={loading}
              className="px-4 py-2 bg-gray-700 text-white rounded-lg hover:bg-gray-600 disabled:opacity-50"
              title="Refresh items"
            >
              {loading ? "Loading..." : "↻ Refresh"}
            </button>
            <button
              onClick={handleRecostAll}
              disabled={recosting}
              className="px-4 py-2 bg-gray-800 border border-gray-700 text-gray-300 rounded-lg hover:bg-gray-700 hover:text-white disabled:opacity-50"
            >
              {recosting ? "Recosting..." : "Recost All"}
            </button>
            <button
              onClick={() => {
                setShowMaterialModal(true);
              }}
              className="px-4 py-2 bg-orange-600 hover:bg-orange-700 text-white rounded-lg font-medium transition-colors"
            >
              + New Material
            </button>
            <button
              onClick={() => {
                setEditingItem(null);
                setShowItemModal(true);
              }}
              className="px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-lg font-medium transition-colors"
            >
              + New Item
            </button>
          </div>
        </div>

        {/* Recost Result */}
        {recostResult && (
          <div className="bg-green-500/10 border border-green-500/30 rounded-xl p-4">
            <div className="flex justify-between items-start">
              <div>
                <p className="text-green-400 font-medium">
                  Recost complete: {recostResult.updated} items updated,{" "}
                  {recostResult.skipped} skipped
                </p>
                {recostResult.items?.length > 0 && (
                  <div className="mt-2 text-sm text-gray-400 max-h-32 overflow-auto">
                    {recostResult.items.slice(0, 10).map((item, i) => (
                      <div key={i}>
                        {item.sku}: ${item.old_cost.toFixed(2)} → $
                        {item.new_cost.toFixed(2)} ({item.cost_source})
                      </div>
                    ))}
                    {recostResult.items.length > 10 && (
                      <div className="text-gray-500">
                        ...and {recostResult.items.length - 10} more
                      </div>
                    )}
                  </div>
                )}
              </div>
              <button
                onClick={() => setRecostResult(null)}
                className="text-gray-500 hover:text-white"
              >
                x
              </button>
            </div>
          </div>
        )}

        {/* Filters */}
        <div className="flex gap-4 bg-gray-900 border border-gray-800 rounded-xl p-4">
          <div className="flex-1">
            <input
              type="text"
              placeholder="Search by SKU, name, or UPC..."
              value={filters.search}
              onChange={(e) =>
                setFilters({ ...filters, search: e.target.value })
              }
              className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-2 text-white placeholder-gray-500"
            />
          </div>
          <select
            value={filters.itemType}
            onChange={(e) => {
              setFilters({ ...filters, itemType: e.target.value });
              setQuickFilter(null);
            }}
            className="bg-gray-800 border border-gray-700 rounded-lg px-4 py-2 text-white"
          >
            <option value="all">All Types</option>
            {ITEM_TYPES.map((type) => (
              <option key={type.value} value={type.value}>
                {type.label}
              </option>
            ))}
          </select>
          <label className="flex items-center gap-2 text-gray-400">
            <input
              type="checkbox"
              checked={filters.activeOnly}
              onChange={(e) =>
                setFilters({ ...filters, activeOnly: e.target.checked })
              }
              className="rounded"
            />
            Active only
          </label>
        </div>

        {/* Stats - Clickable filters */}
        <div className="grid grid-cols-6 gap-4">
          <StatCard
            variant="simple"
            title="Total Items"
            value={stats.total}
            color="neutral"
            onClick={() => {
              setQuickFilter(quickFilter === "all" ? null : "all");
              setFilters({ ...filters, itemType: "all" });
            }}
            active={quickFilter === "all"}
          />
          <StatCard
            variant="simple"
            title="Finished Goods"
            value={stats.finishedGoods}
            color="primary"
            onClick={() => {
              const isActive = quickFilter === "finished_good";
              setQuickFilter(isActive ? null : "finished_good");
              setFilters({ ...filters, itemType: isActive ? "all" : "finished_good" });
            }}
            active={quickFilter === "finished_good"}
          />
          <StatCard
            variant="simple"
            title="Components"
            value={stats.components}
            color="secondary"
            onClick={() => {
              const isActive = quickFilter === "component";
              setQuickFilter(isActive ? null : "component");
              setFilters({ ...filters, itemType: isActive ? "all" : "component" });
            }}
            active={quickFilter === "component"}
          />
          <StatCard
            variant="simple"
            title="Materials"
            value={stats.materials}
            color="primary"
            onClick={() => {
              const isActive = quickFilter === "material";
              setQuickFilter(isActive ? null : "material");
              setFilters({ ...filters, itemType: isActive ? "all" : "material" });
            }}
            active={quickFilter === "material"}
          />
          <StatCard
            variant="simple"
            title="Supplies"
            value={stats.supplies}
            color="warning"
            onClick={() => {
              const isActive = quickFilter === "supply";
              setQuickFilter(isActive ? null : "supply");
              setFilters({ ...filters, itemType: isActive ? "all" : "supply" });
            }}
            active={quickFilter === "supply"}
          />
          <StatCard
            variant="simple"
            title="Needs Reorder"
            value={stats.needsReorder}
            color="danger"
            onClick={() => {
              const isActive = quickFilter === "needs_reorder";
              setQuickFilter(isActive ? null : "needs_reorder");
            }}
            active={quickFilter === "needs_reorder"}
          />
        </div>

        {/* Error */}
        {error && (
          <div className="bg-red-500/10 border border-red-500/30 rounded-xl p-4 text-red-400">
            {error}
          </div>
        )}

        {/* Loading overlay - shows spinner over content instead of replacing it */}
        {loading && items.length > 0 && (
          <div className="flex items-center justify-center py-2">
            <div className="animate-spin rounded-full h-5 w-5 border-b-2 border-blue-500 mr-2"></div>
            <span className="text-gray-400 text-sm">Refreshing...</span>
          </div>
        )}
        {/* Initial loading - only when no items yet */}
        {loading && items.length === 0 && (
          <div className="flex items-center justify-center h-32">
            <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-500"></div>
          </div>
        )}

        {/* Bulk Actions Toolbar */}
        {selectedItems.size > 0 && (
          <div className="bg-blue-600/20 border border-blue-500/30 rounded-xl p-4 mb-4 flex items-center justify-between">
            <div className="flex items-center gap-4">
              <span className="text-white font-medium">
                {selectedItems.size} item{selectedItems.size !== 1 ? "s" : ""}{" "}
                selected
              </span>
              <button
                onClick={() => setShowBulkUpdateModal(true)}
                className="px-4 py-2 bg-blue-600 hover:bg-blue-500 text-white rounded-lg text-sm font-medium"
              >
                Bulk Update
              </button>
              <button
                onClick={() => setSelectedItems(new Set())}
                className="px-4 py-2 text-gray-400 hover:text-white text-sm"
              >
                Clear Selection
              </button>
            </div>
          </div>
        )}

        {/* Items Card View */}
        {viewMode === "cards" && (
          <div className={`grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4 transition-opacity ${loading ? 'opacity-60' : ''}`}>
            {filteredItems.length === 0 ? (
              <div className="col-span-full py-12 text-center text-gray-500">
                No items found
              </div>
            ) : (
              filteredItems.map((item) => (
                <ItemCard
                  key={item.id}
                  itemId={item.id}
                  onClick={() => {
                    setEditingItem(item);
                    setShowItemModal(true);
                  }}
                />
              ))
            )}
          </div>
        )}

        {/* Items Table */}
        {viewMode === "table" && (
          <ItemsTable
            items={filteredItems}
            loading={loading}
            selectedItems={selectedItems}
            onSelectAll={handleSelectAll}
            onSelectItem={handleSelectItem}
            isAllSelected={isAllSelected}
            isIndeterminate={isIndeterminate}
            sortConfig={sortConfig}
            onSort={handleSort}
            editingQtyItem={editingQtyItem}
            editingQtyValue={editingQtyValue}
            onEditingQtyValueChange={setEditingQtyValue}
            adjustmentReason={adjustmentReason}
            adjustingQty={adjustingQty}
            onStartEditQty={(item) => {
              setEditingQtyItem(item);
              setEditingQtyValue(item.on_hand_qty != null ? parseFloat(item.on_hand_qty).toString() : "0");
              setAdjustmentReason("");
              setAdjustmentNotes("");
            }}
            onSaveQtyAdjustment={handleSaveQtyAdjustment}
            onCancelEditQty={() => {
              setEditingQtyItem(null);
              setEditingQtyValue("");
              setAdjustmentReason("");
              setAdjustmentNotes("");
              setShowAdjustmentModal(false);
            }}
            onShowAdjustmentModal={() => setShowAdjustmentModal(true)}
            pagination={pagination}
            onPageChange={(page) => setPagination((prev) => ({ ...prev, page }))}
            onPageSizeChange={(pageSize) => setPagination((prev) => ({ ...prev, pageSize, page: 1 }))}
            totalPages={totalPages}
            canGoPrev={canGoPrev}
            canGoNext={canGoNext}
            onEditItem={(item) => {
              setEditingItem(item);
              setShowItemModal(true);
            }}
            onEditRouting={(item) => {
              setSelectedItemForRouting(item);
              setShowRoutingEditor(true);
            }}
          />
        )}
      </div>

      {/* Item Form */}
      <ItemForm
        isOpen={showItemModal}
        onClose={() => {
          setShowItemModal(false);
          setEditingItem(null);
        }}
        onSuccess={() => {
          setShowItemModal(false);
          setEditingItem(null);
          fetchItems();
        }}
        editingItem={editingItem}
      />

      {/* Material Form */}
      <MaterialForm
        isOpen={showMaterialModal}
        onClose={() => {
          setShowMaterialModal(false);
        }}
        onSuccess={(newItem) => {
          setShowMaterialModal(false);
          toast.success(`Material created: ${newItem?.sku || "Success"}`);
          if (newItem?.sku) {
            setFilters((prev) => ({
              ...prev,
              search: newItem.sku,
              itemType: "all",
            }));
            setSelectedCategory(null);
          } else {
            fetchItems();
          }
        }}
      />

      {/* Routing Editor */}
      <RoutingEditor
        isOpen={showRoutingEditor}
        onClose={() => {
          setShowRoutingEditor(false);
          setSelectedItemForRouting(null);
        }}
        productId={selectedItemForRouting?.id}
        onSuccess={() => {
          setShowRoutingEditor(false);
          setSelectedItemForRouting(null);
          fetchItems();
        }}
      />

      {/* Category Modal */}
      {showCategoryModal && (
        <CategoryModal
          category={editingCategory}
          categories={categories}
          onSave={handleSaveCategory}
          onClose={() => {
            setShowCategoryModal(false);
            setEditingCategory(null);
          }}
        />
      )}

      {/* Bulk Update Modal */}
      {showBulkUpdateModal && (
        <BulkUpdateModal
          categories={categories}
          selectedCount={selectedItems.size}
          onSave={handleBulkUpdate}
          onClose={() => {
            setShowBulkUpdateModal(false);
            setSelectedItems(new Set());
          }}
        />
      )}

      {/* Adjustment Reason Modal */}
      <AdjustmentReasonModal
        isOpen={showAdjustmentModal && !!editingQtyItem}
        adjustmentReason={adjustmentReason}
        adjustmentNotes={adjustmentNotes}
        adjustingQty={adjustingQty}
        onReasonChange={setAdjustmentReason}
        onNotesChange={setAdjustmentNotes}
        onConfirm={handleConfirmAdjustment}
        onClose={() => {
          setShowAdjustmentModal(false);
          setAdjustmentReason("");
          setAdjustmentNotes("");
        }}
      />

      {/* Delete Category Confirm Dialog */}
      <ConfirmDialog
        isOpen={showDeleteCategoryConfirm}
        title="Delete Category"
        message={`Delete category "${categoryToDelete?.name}"? Items in this category will become uncategorized.`}
        confirmLabel="Delete"
        confirmVariant="danger"
        onConfirm={confirmDeleteCategory}
        onCancel={() => {
          setShowDeleteCategoryConfirm(false);
          setCategoryToDelete(null);
        }}
      />

      {/* Recost All Confirm Dialog */}
      <ConfirmDialog
        isOpen={showRecostConfirm}
        title="Recost All Items"
        message="This will update standard costs from BOM/Routing (manufactured) or average cost (purchased). This action may take a moment."
        confirmLabel="Recost All"
        confirmVariant="warning"
        onConfirm={confirmRecostAll}
        onCancel={() => setShowRecostConfirm(false)}
      />

      {/* Back to Top Button */}
      {showBackToTop && (
        <button
          onClick={scrollToTop}
          className="fixed bottom-6 right-6 z-50 bg-blue-600 hover:bg-blue-500 text-white p-3 rounded-full shadow-lg transition-all hover:scale-110"
          title="Back to top"
        >
          <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 10l7-7m0 0l7 7m-7-7v18" />
          </svg>
        </button>
      )}
    </div>
  );
}
