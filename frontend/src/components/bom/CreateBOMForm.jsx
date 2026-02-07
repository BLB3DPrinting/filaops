import { useState, useEffect, useCallback } from "react";
import { Link } from "react-router-dom";
import { API_URL } from "../../config/api";
import SearchableSelect from "../SearchableSelect";

export default function CreateBOMForm({ onClose, onCreate, existingBoms = [] }) {
  const [formData, setFormData] = useState({
    product_id: "",
    name: "",
    revision: "1.0",
  });
  const [products, setProducts] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [existingBomWarning, setExistingBomWarning] = useState(null);
  const [forceNewVersion, setForceNewVersion] = useState(false);

  const fetchProducts = useCallback(async () => {
    try {
      const res = await fetch(
        `${API_URL}/api/v1/products?limit=500&is_raw_material=false`,
        {
          credentials: "include",
        }
      );
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || "Failed to load products.");
      }
      const data = await res.json();
      setProducts(data.items || data);
    } catch (err) {
      setError(err.message || "Failed to load products. Please refresh the page.");
    }
  }, []);

  useEffect(() => {
    fetchProducts();
  }, [fetchProducts]);

  // Handle returning from product creation with polling retry logic
  useEffect(() => {
    const checkPendingCreation = async () => {
      const bomPending = sessionStorage.getItem("bom_creation_pending");
      if (!bomPending) return;

      sessionStorage.removeItem("bom_creation_pending");

      // Implement polling with retries to handle slow networks
      const maxRetries = 3;
      const retryDelays = [0, 1000, 2000]; // 0ms, 1s, 2s

      for (let i = 0; i < maxRetries; i++) {
        if (i > 0) {
          await new Promise((resolve) => setTimeout(resolve, retryDelays[i]));
        }
        await fetchProducts();
        // After final retry, stop regardless of result
        if (i === maxRetries - 1) break;
      }
    };

    // Check on mount
    checkPendingCreation();

    // Also check when window regains focus (user returns from another tab/window)
    const handleFocus = async () => {
      const bomPending = sessionStorage.getItem("bom_creation_pending");
      if (bomPending) {
        sessionStorage.removeItem("bom_creation_pending");
        await fetchProducts();
      }
    };

    window.addEventListener("focus", handleFocus);
    return () => window.removeEventListener("focus", handleFocus);
  }, [fetchProducts]);

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!formData.product_id) {
      setError("Please select a product");
      return;
    }

    // If product has existing BOM and user didn't check "force new version", block
    if (existingBomWarning && !forceNewVersion) {
      setError(
        "Please select 'Create a new version' or click 'View' on the existing BOM instead."
      );
      return;
    }

    setLoading(true);
    setError(null);

    try {
      // Add force_new parameter if creating a new version
      const url = forceNewVersion
        ? `${API_URL}/api/v1/admin/bom?force_new=true`
        : `${API_URL}/api/v1/admin/bom`;

      const res = await fetch(url, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify({
          product_id: parseInt(formData.product_id),
          name: formData.name || null,
          revision: formData.revision,
        }),
      });

      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || "Failed to create BOM");
      }

      const newBom = await res.json();
      onCreate(newBom);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      {error && (
        <div className="bg-red-500/10 border border-red-500/30 rounded-lg p-3 text-red-400 text-sm">
          {error}
        </div>
      )}

      <div>
        <div className="flex justify-between items-center mb-1">
          <label className="block text-sm text-gray-400">Product *</label>
          <Link
            to="/admin/items?action=new"
            className="text-xs text-blue-400 hover:text-blue-300 underline"
            onClick={() => {
              // Store that we're coming from BOM creation
              sessionStorage.setItem("bom_creation_pending", "true");
            }}
          >
            + Create New Item
          </Link>
        </div>
        <SearchableSelect
          options={products}
          value={formData.product_id}
          onChange={(val) => {
            setFormData({ ...formData, product_id: val });
            // Check if product already has a BOM
            const existingBom = existingBoms.find(
              (b) => b.product_id === parseInt(val) && b.active
            );
            if (existingBom) {
              setExistingBomWarning(existingBom);
              setForceNewVersion(false);
            } else {
              setExistingBomWarning(null);
              setForceNewVersion(false);
            }
          }}
          placeholder="Select a product..."
          displayKey="name"
          valueKey="id"
        />
        <p className="text-xs text-gray-500 mt-1">
          Don't see the product?{" "}
          <Link
            to="/admin/items?action=new"
            className="text-blue-400 hover:text-blue-300 underline"
            onClick={() =>
              sessionStorage.setItem("bom_creation_pending", "true")
            }
          >
            Create it first
          </Link>
          , then return here.
        </p>
      </div>

      {/* Existing BOM Warning */}
      {existingBomWarning && (
        <div className="bg-yellow-500/10 border border-yellow-500/30 rounded-lg p-4 text-yellow-200">
          <div className="font-semibold mb-2">
            This product already has an active BOM
          </div>
          <p className="text-sm text-yellow-300 mb-3">
            BOM: {existingBomWarning.code || existingBomWarning.name} (v
            {existingBomWarning.version}) with {existingBomWarning.line_count}{" "}
            component(s)
          </p>
          <div className="flex items-center gap-2">
            <input
              type="checkbox"
              id="forceNewVersion"
              checked={forceNewVersion}
              onChange={(e) => setForceNewVersion(e.target.checked)}
              className="w-4 h-4 rounded border-gray-600 bg-gray-700 text-yellow-600 focus:ring-yellow-500"
            />
            <label htmlFor="forceNewVersion" className="text-sm">
              Create a new version (deactivates current BOM)
            </label>
          </div>
          {!forceNewVersion && (
            <p className="text-xs text-gray-400 mt-2">
              Tip: To add components to the existing BOM, click "View" on the
              BOM in the list instead.
            </p>
          )}
        </div>
      )}

      <div>
        <label className="block text-sm text-gray-400 mb-1">
          BOM Name (optional)
        </label>
        <input
          type="text"
          value={formData.name}
          onChange={(e) => setFormData({ ...formData, name: e.target.value })}
          placeholder="Auto-generated if empty"
          className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-white"
        />
      </div>

      <div>
        <label className="block text-sm text-gray-400 mb-1">Revision</label>
        <input
          type="text"
          value={formData.revision}
          onChange={(e) =>
            setFormData({ ...formData, revision: e.target.value })
          }
          className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-white"
        />
      </div>

      <div className="flex gap-2 pt-4">
        <button
          type="submit"
          disabled={loading || (existingBomWarning && !forceNewVersion)}
          className="flex-1 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50"
        >
          {loading
            ? "Creating..."
            : forceNewVersion
            ? "Create New Version"
            : "Create BOM"}
        </button>
        <button
          type="button"
          onClick={onClose}
          className="px-4 py-2 bg-gray-700 text-white rounded-lg hover:bg-gray-600"
        >
          Cancel
        </button>
      </div>
    </form>
  );
}
