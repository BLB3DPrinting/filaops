import React, { useState, useEffect, useCallback, useRef } from "react";
import { useSearchParams, useNavigate } from "react-router-dom";
import { useApi } from "../../hooks/useApi";
import { useToast } from "../../components/Toast";
import CreateBOMForm from "../../components/bom/CreateBOMForm";
import CreateProductionOrderModal from "../../components/bom/CreateProductionOrderModal";
import BOMDetailView from "../../components/bom/BOMDetailView";
import Modal from "../../components/Modal";

// Create BOM Form
export default function AdminBOM() {
  const [searchParams, setSearchParams] = useSearchParams();
  const navigate = useNavigate();
  const api = useApi();
  const toast = useToast();
  const [boms, setBoms] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [selectedBOM, setSelectedBOM] = useState(null);
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [showProductionModal, setShowProductionModal] = useState(false);
  const [productionBOM, setProductionBOM] = useState(null);
  const [filters, setFilters] = useState({
    search: searchParams.get("search") || "",
    active: searchParams.get("active") || "all",
  });

  const productId = searchParams.get("product");
  const quotedQuantity = searchParams.get("quantity");
  const quoteId = searchParams.get("quote_id");

  // Store quote context for production order creation
  const [quoteContext, setQuoteContext] = useState(null);

  const fetchBOMs = useCallback(async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams();
      if (filters.search) params.set("search", filters.search);
      if (filters.active !== "all")
        params.set("active", filters.active === "active");

      const data = await api.get(`/api/v1/admin/bom?${params}`);
      setBoms(data);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, [filters, api]);

  useEffect(() => {
    fetchBOMs();
  }, [fetchBOMs]);

  // Define handleViewBOM before useEffect that uses it
  const handleViewBOM = useCallback(
    async (bomId) => {
      try {
        const data = await api.get(`/api/v1/admin/bom/${bomId}`);
        setSelectedBOM(data);
      } catch (err) {
        setError(`Failed to load BOM: ${err.message || "Unknown error"}`);
      }
    },
    [api]
  );

  // Track whether URL-driven auto-open has been performed
  const autoOpenedRef = useRef(false);

  // Reset auto-open tracking when URL params change
  useEffect(() => {
    autoOpenedRef.current = false;
  }, [productId, quotedQuantity, quoteId]);

  // Auto-open BOM for a specific product if passed in URL
  useEffect(() => {
    if (productId && boms.length > 0 && !autoOpenedRef.current) {
      const matchingBOM = boms.find(
        (b) => b.product_id === parseInt(productId)
      );
      if (matchingBOM) {
        // Store quote context before clearing params
        if (quotedQuantity || quoteId) {
          setQuoteContext({
            quantity: parseInt(quotedQuantity) || 1,
            quoteId: quoteId ? parseInt(quoteId) : null,
          });
        }
        handleViewBOM(matchingBOM.id);
        // Clear the params after opening
        setSearchParams({});
        // Mark that auto-open has been performed
        autoOpenedRef.current = true;
      }
    }
  }, [
    productId,
    boms,
    quotedQuantity,
    quoteId,
    handleViewBOM,
    setSearchParams,
  ]);

  const handleDeleteBOM = async (bomId) => {
    if (!confirm("Are you sure you want to delete this BOM?")) return;

    try {
      await api.del(`/api/v1/admin/bom/${bomId}`);
      toast.success("BOM deleted");
      fetchBOMs();
    } catch (err) {
      toast.error(`Failed to delete BOM: ${err.message || "Network error"}`);
    }
  };

  const handleCopyBOM = async (bomId) => {
    try {
      await api.post(`/api/v1/admin/bom/${bomId}/copy`);
      toast.success("BOM copied");
      fetchBOMs();
    } catch (err) {
      toast.error(`Failed to copy BOM: ${err.message || "Network error"}`);
    }
  };

  const handleCreateProductionOrder = (bom) => {
    setProductionBOM(bom);
    setShowProductionModal(true);
  };

  const handleProductionOrderCreated = (newOrder) => {
    setShowProductionModal(false);
    setProductionBOM(null);
    setSelectedBOM(null);
    // Navigate to production orders page to see the new order
    navigate(`/admin/production?order=${newOrder.id}`);
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row items-start sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-white">Bill of Materials</h1>
          <p className="text-gray-400 mt-1">
            Manage product BOMs and components
          </p>
        </div>
        <button
          onClick={() => setShowCreateModal(true)}
          className="px-4 py-2 bg-gradient-to-r from-blue-600 to-purple-600 text-white rounded-lg hover:from-blue-500 hover:to-purple-500"
        >
          + Create BOM
        </button>
      </div>

      {/* Filters */}
      <div className="flex flex-col sm:flex-row gap-4 bg-gray-900 border border-gray-800 rounded-xl p-4">
        <div className="flex-1">
          <input
            type="text"
            placeholder="Search by code, name, or product..."
            value={filters.search}
            onChange={(e) => setFilters({ ...filters, search: e.target.value })}
            className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-2 text-white placeholder-gray-500"
          />
        </div>
        <select
          value={filters.active}
          onChange={(e) => setFilters({ ...filters, active: e.target.value })}
          className="bg-gray-800 border border-gray-700 rounded-lg px-4 py-2 text-white"
        >
          <option value="all">All Status</option>
          <option value="active">Active Only</option>
          <option value="inactive">Inactive Only</option>
        </select>
      </div>

      {/* Error */}
      {error && (
        <div className="bg-red-500/10 border border-red-500/30 rounded-xl p-4 text-red-400">
          {error}
        </div>
      )}

      {/* Loading */}
      {loading && (
        <div className="flex items-center justify-center h-32">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-500"></div>
        </div>
      )}

      {/* BOM List */}
      {!loading && (
        <div className="bg-gray-900 border border-gray-800 rounded-xl overflow-hidden">
          <div className="overflow-x-auto">
          <table className="w-full min-w-[640px]">
            <thead className="bg-gray-800/50">
              <tr>
                <th className="text-left py-3 px-4 text-xs font-medium text-gray-400 uppercase">
                  Code
                </th>
                <th className="text-left py-3 px-4 text-xs font-medium text-gray-400 uppercase">
                  Name
                </th>
                <th className="text-left py-3 px-4 text-xs font-medium text-gray-400 uppercase">
                  Product
                </th>
                <th className="text-left py-3 px-4 text-xs font-medium text-gray-400 uppercase">
                  Version
                </th>
                <th className="text-left py-3 px-4 text-xs font-medium text-gray-400 uppercase">
                  Components
                </th>
                <th className="text-left py-3 px-4 text-xs font-medium text-gray-400 uppercase">
                  Total Cost
                </th>
                <th className="text-left py-3 px-4 text-xs font-medium text-gray-400 uppercase">
                  Status
                </th>
                <th className="text-right py-3 px-4 text-xs font-medium text-gray-400 uppercase">
                  Actions
                </th>
              </tr>
            </thead>
            <tbody>
              {boms.map((bom) => (
                <tr
                  key={bom.id}
                  className="border-b border-gray-800 hover:bg-gray-800/50"
                >
                  <td className="py-3 px-4 text-white font-medium">
                    {bom.code}
                  </td>
                  <td className="py-3 px-4 text-gray-300">{bom.name}</td>
                  <td className="py-3 px-4 text-gray-400">
                    {bom.product?.name || `#${bom.product_id}`}
                  </td>
                  <td className="py-3 px-4 text-gray-400">
                    v{bom.version} ({bom.revision})
                  </td>
                  <td className="py-3 px-4 text-gray-400">
                    {bom.line_count || 0}
                  </td>
                  <td className="py-3 px-4 text-green-400 font-medium">
                    ${parseFloat(bom.total_cost || 0).toFixed(2)}
                  </td>
                  <td className="py-3 px-4">
                    <span
                      className={`px-2 py-1 rounded-full text-xs ${
                        bom.active
                          ? "bg-green-500/20 text-green-400"
                          : "bg-gray-500/20 text-gray-400"
                      }`}
                    >
                      {bom.active ? "Active" : "Inactive"}
                    </span>
                  </td>
                  <td className="py-3 px-4 text-right space-x-2">
                    <button
                      onClick={() => handleViewBOM(bom.id)}
                      className="text-blue-400 hover:text-blue-300 text-sm"
                    >
                      View
                    </button>
                    <button
                      onClick={() => handleCopyBOM(bom.id)}
                      className="text-purple-400 hover:text-purple-300 text-sm"
                    >
                      Copy
                    </button>
                    <button
                      onClick={() => handleDeleteBOM(bom.id)}
                      className="text-red-400 hover:text-red-300 text-sm"
                    >
                      Delete
                    </button>
                  </td>
                </tr>
              ))}
              {boms.length === 0 && (
                <tr>
                  <td colSpan={8} className="py-12 text-center text-gray-500">
                    No BOMs found. Create your first BOM to get started.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
          </div>
        </div>
      )}

      {/* BOM Detail Modal */}
      <Modal
        isOpen={!!selectedBOM}
        onClose={() => setSelectedBOM(null)}
        title={`BOM: ${selectedBOM?.code}`}
        className="w-full max-w-6xl"
      >
        <div className="p-6">
          <div className="flex justify-between items-center mb-4">
            <h2 className="text-lg font-semibold text-white">{`BOM: ${selectedBOM?.code}`}</h2>
            <button onClick={() => setSelectedBOM(null)} className="text-gray-400 hover:text-white p-1" aria-label="Close">
              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          </div>
          {selectedBOM && (
            <BOMDetailView
              bom={selectedBOM}
              onClose={() => setSelectedBOM(null)}
              onUpdate={() => {
                fetchBOMs();
                handleViewBOM(selectedBOM.id);
              }}
              onCreateProductionOrder={handleCreateProductionOrder}
            />
          )}
        </div>
      </Modal>

      {/* Production Order Modal */}
      <Modal
        isOpen={showProductionModal}
        onClose={() => {
          setShowProductionModal(false);
          setProductionBOM(null);
        }}
        title="Create Production Order"
        className="w-full max-w-2xl"
      >
        <div className="p-6">
          <div className="flex justify-between items-center mb-4">
            <h2 className="text-lg font-semibold text-white">Create Production Order</h2>
            <button onClick={() => {
              setShowProductionModal(false);
              setProductionBOM(null);
            }} className="text-gray-400 hover:text-white p-1" aria-label="Close">
              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          </div>
          {productionBOM && (
            <CreateProductionOrderModal
              bom={productionBOM}
              quoteContext={quoteContext}
              onClose={() => {
                setShowProductionModal(false);
                setProductionBOM(null);
                setQuoteContext(null);
              }}
              onSuccess={handleProductionOrderCreated}
            />
          )}
        </div>
      </Modal>

      {/* Create BOM Modal */}
      <Modal
        isOpen={showCreateModal}
        onClose={() => setShowCreateModal(false)}
        title="Create New BOM"
        className="w-full max-w-2xl"
      >
        <div className="p-6">
          <div className="flex justify-between items-center mb-4">
            <h2 className="text-lg font-semibold text-white">Create New BOM</h2>
            <button onClick={() => setShowCreateModal(false)} className="text-gray-400 hover:text-white p-1" aria-label="Close">
              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          </div>
          <CreateBOMForm
            onClose={() => setShowCreateModal(false)}
            onCreate={(newBom) => {
              setShowCreateModal(false);
              fetchBOMs();
              handleViewBOM(newBom.id);
            }}
            existingBoms={boms}
          />
        </div>
      </Modal>
    </div>
  );
}
