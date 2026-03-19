/**
 * CopyBOMModal — Copy an existing BOM to a different product.
 *
 * Prompts the user to select a target product and optionally toggle
 * whether to include BOM lines, then POSTs the copy request.
 */
import { useState, useEffect } from "react";
import { useApi } from "../../hooks/useApi";
import { useToast } from "../Toast";
import SearchableSelect from "../SearchableSelect";
import Modal from "../Modal";

export default function CopyBOMModal({ isOpen, onClose, onSuccess, sourceBom }) {
  const api = useApi();
  const toast = useToast();

  const [targetProductId, setTargetProductId] = useState("");
  const [includeLines, setIncludeLines] = useState(true);
  const [products, setProducts] = useState([]);
  const [loadingProducts, setLoadingProducts] = useState(false);
  const [submitting, setSubmitting] = useState(false);

  // Reset state and fetch products when modal opens
  useEffect(() => {
    if (!isOpen) return;
    setTargetProductId("");
    setIncludeLines(true);
    setSubmitting(false);

    let cancelled = false;
    const fetchProducts = async () => {
      setLoadingProducts(true);
      try {
        const data = await api.get("/api/v1/items?limit=500&active_only=true");
        if (!cancelled) setProducts(data.items || []);
      } catch {
        if (!cancelled) toast.error("Failed to load products");
      } finally {
        if (!cancelled) setLoadingProducts(false);
      }
    };
    fetchProducts();
    return () => { cancelled = true; };
  }, [isOpen, api]);

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!targetProductId) {
      toast.error("Please select a target product");
      return;
    }

    setSubmitting(true);
    try {
      await api.post(`/api/v1/admin/bom/${sourceBom.id}/copy`, {
        target_product_id: parseInt(targetProductId, 10),
        include_lines: includeLines,
      });
      toast.success("BOM copied successfully");
      onSuccess?.();
    } catch (err) {
      toast.error(`Failed to copy BOM: ${err.message || "Network error"}`);
    } finally {
      setSubmitting(false);
    }
  };

  if (!sourceBom) return null;

  return (
    <Modal isOpen={isOpen} onClose={onClose} title="Copy BOM">
      {/* Header */}
      <div className="p-6 border-b border-gray-700">
        <h2 className="text-xl font-semibold text-white">Copy BOM</h2>
        <p className="text-sm text-gray-400 mt-1">
          Source: <span className="text-blue-400 font-mono">{sourceBom.code || sourceBom.name}</span>
          {sourceBom.product_name && (
            <span className="text-gray-500 ml-1">({sourceBom.product_name})</span>
          )}
        </p>
      </div>

      <form onSubmit={handleSubmit}>
        <div className="p-6 space-y-5">
          {/* Target Product */}
          <div>
            <label className="block text-sm font-medium text-gray-300 mb-2">
              Target Product <span className="text-red-400">*</span>
            </label>
            {loadingProducts ? (
              <div className="text-gray-500 text-sm py-2">Loading products...</div>
            ) : (
              <SearchableSelect
                options={products}
                value={targetProductId}
                onChange={(val) => setTargetProductId(val)}
                placeholder="Search by name or SKU..."
                displayKey="name"
                valueKey="id"
                formatOption={(opt) => `${opt.sku} — ${opt.name}`}
              />
            )}
            <p className="text-xs text-gray-500 mt-1">
              The product that will receive the copied BOM.
            </p>
          </div>

          {/* Include Lines Toggle */}
          <div className="flex items-center gap-3">
            <input
              type="checkbox"
              id="includeLines"
              checked={includeLines}
              onChange={(e) => setIncludeLines(e.target.checked)}
              className="w-4 h-4 rounded border-gray-600 bg-gray-700 text-blue-600 focus:ring-blue-500"
            />
            <label htmlFor="includeLines" className="text-sm text-gray-300">
              Include BOM lines (components)
            </label>
          </div>
        </div>

        {/* Footer */}
        <div className="flex justify-end gap-3 p-6 border-t border-gray-700">
          <button
            type="button"
            onClick={onClose}
            className="px-4 py-2 text-gray-400 hover:text-white border border-gray-600 rounded-lg text-sm"
          >
            Cancel
          </button>
          <button
            type="submit"
            disabled={submitting || !targetProductId}
            className="px-6 py-2 bg-purple-600 hover:bg-purple-500 disabled:bg-purple-600/50 disabled:cursor-not-allowed text-white rounded-lg text-sm font-medium"
          >
            {submitting ? "Copying..." : "Copy BOM"}
          </button>
        </div>
      </form>
    </Modal>
  );
}
