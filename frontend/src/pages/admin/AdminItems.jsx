import { useState, useEffect, useCallback } from "react";
import ItemForm from "../../components/ItemForm";
import MaterialForm from "../../components/MaterialForm";
import RoutingEditor from "../../components/RoutingEditor";
import { ItemCard } from "../../components/inventory/ItemCard";
import ConfirmDialog from "../../components/ConfirmDialog";
import { useApi } from "../../hooks/useApi";
import { useToast } from "../../components/Toast";
import CategorySidebar from "../../components/items/CategorySidebar";
import CategoryModal from "../../components/items/CategoryModal";
import BulkUpdateModal from "../../components/items/BulkUpdateModal";
import ItemsTable from "../../components/items/ItemsTable";
import ItemsPageHeader from "../../components/items/ItemsPageHeader";
import ItemsFilterBar from "../../components/items/ItemsFilterBar";
import AdjustmentReasonModal from "../../components/items/AdjustmentReasonModal";
import DuplicateItemModal from "../../components/items/DuplicateItemModal";
import SuggestPricesModal from "../../components/items/SuggestPricesModal";

export default function AdminItems() {
  const api = useApi();
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

  // Pagination state
  const [pagination, setPagination] = useState({
    page: 1,
    pageSize: 50,
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
  const [duplicatingItem, setDuplicatingItem] = useState(null);
  const [showSuggestPrices, setShowSuggestPrices] = useState(false);
  const [suggestPricesResult, setSuggestPricesResult] = useState(null);

  // Confirm dialog states
  const [showDeleteCategoryConfirm, setShowDeleteCategoryConfirm] = useState(false);
  const [categoryToDelete, setCategoryToDelete] = useState(null);
  const [showRecostConfirm, setShowRecostConfirm] = useState(false);

  const fetchCategories = useCallback(async () => {
    try {
      const data = await api.get(`/api/v1/items/categories?include_inactive=true`);
      setCategories(data);

      try {
        const treeData = await api.get(`/api/v1/items/categories/tree`);
        setCategoryTree(treeData);
      } catch {
        // Tree fetch failure is non-critical
      }
    } catch {
      // Category fetch failure is non-critical - category tree will just be empty
    }
  }, [api]);

  useEffect(() => {
    fetchCategories();
  }, [fetchCategories]);

  const fetchItems = useCallback(async () => {
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

      const data = await api.get(`/api/v1/items?${params}`);
      setItems(data.items || []);
      setPagination((prev) => ({ ...prev, total: data.total || 0 }));
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, [
    api,
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

  // Fetch stats from dedicated lightweight endpoint
  const fetchStats = useCallback(async () => {
    try {
      const data = await api.get("/api/v1/items/stats");
      setAllItemsStats({
        total: data.total || 0,
        finishedGoods: data.finished_goods || 0,
        components: data.components || 0,
        supplies: data.supplies || 0,
        materials: data.materials || 0,
        needsReorder: data.needs_reorder || 0,
      });
    } catch {
      // Stats fetch failure is non-critical
    }
  }, [api]);

  useEffect(() => {
    fetchStats();
  }, [fetchStats]);

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
      await api.del(`/api/v1/items/categories/${categoryToDelete.id}`);
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
      if (editingCategory) {
        await api.patch(`/api/v1/items/categories/${editingCategory.id}`, catData);
      } else {
        await api.post(`/api/v1/items/categories`, catData);
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

      const result = await api.post(`/api/v1/inventory/adjust-quantity?${params}`);
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
      const data = await api.post(`/api/v1/items/bulk-update`, {
        item_ids: Array.from(selectedItems),
        ...updateData,
      });
      toast.success(`Successfully updated ${data.message}`);
      setSelectedItems(new Set());
      setShowBulkUpdateModal(false);
      fetchItems();
      fetchStats();
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

      const data = await api.post(`/api/v1/items/recost-all?${params}`);
      setRecostResult(data);
      toast.success(`Recosted ${data.updated || 0} items`);
      fetchItems();
    } catch (err) {
      toast.error(err.message);
    } finally {
      setRecosting(false);
    }
  };

  const handleSuggestPricesSuccess = (result) => {
    setShowSuggestPrices(false);
    setSuggestPricesResult(result);
    fetchItems();
  };

  return (
    <div data-testid="items-page" className="flex gap-6 h-full">
      {/* Left Sidebar - Categories */}
      <CategorySidebar
        categoryTree={categoryTree}
        expandedCategories={expandedCategories}
        selectedCategory={selectedCategory}
        onToggleExpand={toggleExpand}
        onSelectCategory={setSelectedCategory}
        onEditCategory={setEditingCategory}
        onShowCategoryModal={setShowCategoryModal}
        onAddCategory={() => {
          setEditingCategory(null);
          setShowCategoryModal(true);
        }}
        onDeleteCategory={handleDeleteCategory}
      />

      {/* Main Content */}
      <div className="flex-1 space-y-6">
        <ItemsPageHeader
          viewMode={viewMode}
          onViewModeChange={setViewMode}
          loading={loading}
          recosting={recosting}
          recostResult={recostResult}
          onRefresh={fetchItems}
          onRecostAll={handleRecostAll}
          onClearRecostResult={() => setRecostResult(null)}
          onSuggestPrices={() => setShowSuggestPrices(true)}
          suggestPricesResult={suggestPricesResult}
          onClearSuggestPricesResult={() => setSuggestPricesResult(null)}
          onNewMaterial={() => setShowMaterialModal(true)}
          onNewItem={() => {
            setEditingItem(null);
            setShowItemModal(true);
          }}
        />

        <ItemsFilterBar
          filters={filters}
          onFiltersChange={setFilters}
          quickFilter={quickFilter}
          onQuickFilterChange={setQuickFilter}
          stats={stats}
        />

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
            onDuplicateItem={(item) => setDuplicatingItem(item)}
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
          fetchStats();
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

      {/* Duplicate Item Modal */}
      <DuplicateItemModal
        isOpen={!!duplicatingItem}
        onClose={() => setDuplicatingItem(null)}
        onSuccess={() => {
          setDuplicatingItem(null);
          fetchItems();
          fetchStats();
        }}
        sourceItem={duplicatingItem}
      />

      <SuggestPricesModal
        isOpen={showSuggestPrices}
        onClose={() => setShowSuggestPrices(false)}
        onSuccess={handleSuggestPricesSuccess}
        selectedCategory={selectedCategory}
        filters={filters}
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
