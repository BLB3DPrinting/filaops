import { useState, useEffect } from "react";
import { API_URL } from "../../../config/api";
import { useToast } from "../../../components/Toast";

/**
 * MaterialTraceability - Quality traceability system
 * 
 * Features:
 * - Forward traceability (spool → products → customers)
 * - Backward traceability (product → materials → vendors)
 * - DHR export
 */
export default function MaterialTraceability() {
  const [activeTab, setActiveTab] = useState("forward");
  const [spools, setSpools] = useState([]);
  const [loadingSpools, setLoadingSpools] = useState(false);

  // Fetch spools for forward trace
  useEffect(() => {
    if (activeTab === "forward" && spools.length === 0) {
      const fetchSpools = async () => {
        setLoadingSpools(true);
        try {
          const res = await fetch(`${API_URL}/api/v1/spools?limit=200`, {
            credentials: "include",
          });
          const data = await res.json();
          // Handle error responses and ensure we always set an array
          if (data.detail || data.error) {
            console.error("API error:", data.detail || data.error);
            setSpools([]);
          } else {
            setSpools(Array.isArray(data) ? data : (data.items || []));
          }
        } catch (err) {
          console.error("Failed to fetch spools:", err);
          setSpools([]);
        } finally {
          setLoadingSpools(false);
        }
      };
      fetchSpools();
    }
  }, [activeTab, spools.length]);

  return (
    <div className="space-y-6 p-6">
      <div>
        <h1 className="text-2xl font-bold text-white">Material Traceability</h1>
        <p className="text-gray-400 mt-1">Track materials from spool to customer and back</p>
      </div>

      {/* Tabs */}
      <div className="flex gap-1 border-b border-gray-800">
        <button
          onClick={() => setActiveTab("forward")}
          className={`px-4 py-2 text-sm font-medium transition-colors ${
            activeTab === "forward"
              ? "text-white border-b-2 border-blue-500"
              : "text-gray-400 hover:text-gray-300"
          }`}
        >
          Forward Trace
        </button>
        <button
          onClick={() => setActiveTab("backward")}
          className={`px-4 py-2 text-sm font-medium transition-colors ${
            activeTab === "backward"
              ? "text-white border-b-2 border-blue-500"
              : "text-gray-400 hover:text-gray-300"
          }`}
        >
          Backward Trace
        </button>
      </div>

      {/* Content */}
      {activeTab === "forward" && (
        <ForwardTrace spools={spools} loadingSpools={loadingSpools} />
      )}
      {activeTab === "backward" && <BackwardTrace />}
    </div>
  );
}

/**
 * Forward Trace - Spool → Products → Customers
 */
function ForwardTrace({ spools, loadingSpools }) {
  const toast = useToast();
  const [spoolId, setSpoolId] = useState("");
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);

  const handleTrace = async (e) => {
    e.preventDefault();
    if (!spoolId) {
      toast.error("Please select a spool");
      return;
    }

    setLoading(true);
    setError(null);
    try {
      const res = await fetch(
        `${API_URL}/api/v1/traceability/forward/spool/${spoolId}`,
        {
          credentials: "include",
        }
      );

      if (res.ok) {
        const data = await res.json();
        setResult(data);
      } else {
        const errorData = await res.json();
        setError(errorData.detail || "Failed to trace spool");
        toast.error(errorData.detail || "Failed to trace spool");
      }
    } catch (err) {
      setError(err.message);
      toast.error(`Error: ${err.message}`);
    } finally {
      setLoading(false);
    }
  };

  const exportDHR = () => {
    if (!result) return;
    const dataStr = JSON.stringify(result, null, 2);
    const dataBlob = new Blob([dataStr], { type: "application/json" });
    const url = URL.createObjectURL(dataBlob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `DHR-${result.spool?.spool_number || "trace"}-${new Date().toISOString().split("T")[0]}.json`;
    link.click();
    URL.revokeObjectURL(url);
    toast.success("DHR exported");
  };

  return (
    <div className="space-y-4">
      {/* Search Form */}
      <div className="bg-gray-800 rounded-lg p-4">
        <form onSubmit={handleTrace} className="space-y-4">
          <div>
            <label className="block text-sm text-gray-400 mb-2">
              Select Spool to Trace Forward
            </label>
            <select
              value={spoolId}
              onChange={(e) => setSpoolId(e.target.value)}
              className="w-full bg-gray-700 border border-gray-600 rounded-lg px-3 py-2 text-white"
              disabled={loadingSpools}
            >
              <option value="">Select spool...</option>
              {spools.map((spool) => (
                <option key={spool.id} value={spool.id}>
                  {spool.spool_number} - {spool.product_name || spool.product_sku}
                </option>
              ))}
            </select>
          </div>
          <button
            type="submit"
            disabled={loading || !spoolId}
            className="px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-lg disabled:opacity-50"
          >
            {loading ? "Tracing..." : "Trace Forward"}
          </button>
        </form>
      </div>

      {/* Error */}
      {error && (
        <div className="bg-red-900/20 border border-red-500/30 rounded-lg p-4 text-red-400">
          {error}
        </div>
      )}

      {/* Results */}
      {result && (
        <div className="space-y-4">
          {/* Summary Cards */}
          <div className="grid grid-cols-4 gap-4">
            <div className="bg-gray-800 rounded-lg p-4">
              <div className="text-sm text-gray-400">Production Orders</div>
              <div className="text-2xl font-bold text-white">
                {result.summary?.total_production_orders || 0}
              </div>
            </div>
            <div className="bg-gray-800 rounded-lg p-4">
              <div className="text-sm text-gray-400">Units Produced</div>
              <div className="text-2xl font-bold text-white">
                {result.summary?.total_units_produced || 0}
              </div>
            </div>
            <div className="bg-gray-800 rounded-lg p-4">
              <div className="text-sm text-gray-400">Sales Orders</div>
              <div className="text-2xl font-bold text-white">
                {result.summary?.affected_sales_orders || 0}
              </div>
            </div>
            <div className="bg-gray-800 rounded-lg p-4">
              <div className="text-sm text-gray-400">Customers</div>
              <div className="text-2xl font-bold text-white">
                {result.summary?.affected_customers || 0}
              </div>
            </div>
          </div>

          {/* Spool Info */}
          {result.spool && (
            <div className="bg-gray-800 rounded-lg p-4">
              <h3 className="text-lg font-semibold text-white mb-3">Spool Information</h3>
              <div className="grid grid-cols-2 gap-4 text-sm">
                <div>
                  <span className="text-gray-400">Spool Number:</span>
                  <span className="text-white ml-2">{result.spool.spool_number}</span>
                </div>
                <div>
                  <span className="text-gray-400">Material:</span>
                  <span className="text-white ml-2">
                    {result.spool.material_name || result.spool.product_name}
                  </span>
                </div>
                <div>
                  <span className="text-gray-400">Weight:</span>
                  <span className="text-white ml-2">
                    {result.spool.current_weight_g || result.spool.current_weight_kg}g /{" "}
                    {result.spool.initial_weight_g || result.spool.initial_weight_kg}g
                  </span>
                </div>
                {result.spool.supplier_lot_number && (
                  <div>
                    <span className="text-gray-400">Lot Number:</span>
                    <span className="text-white ml-2">{result.spool.supplier_lot_number}</span>
                  </div>
                )}
              </div>
            </div>
          )}

          {/* Usage Tree */}
          {result.usage && result.usage.length > 0 && (
            <div className="bg-gray-800 rounded-lg p-4">
              <div className="flex justify-between items-center mb-3">
                <h3 className="text-lg font-semibold text-white">Usage Details</h3>
                <button
                  onClick={exportDHR}
                  className="px-3 py-1 bg-green-600 hover:bg-green-700 text-white text-sm rounded"
                >
                  Export DHR
                </button>
              </div>
              <div className="space-y-3">
                {result.usage.map((usage, idx) => (
                  <div key={idx} className="bg-gray-700/50 rounded-lg p-3">
                    <div className="flex items-center justify-between mb-2">
                      <div className="font-medium text-white">
                        {usage.production_order?.code || "Production Order"}
                      </div>
                      <div className="text-sm text-gray-400">
                        {usage.material_consumed_g || usage.material_consumed_kg}g consumed
                      </div>
                    </div>
                    <div className="text-sm text-gray-400">
                      Product: {usage.production_order?.product_name || "N/A"}
                    </div>
                    {usage.sales_order && (
                      <div className="text-sm text-gray-400 mt-1">
                        Sales Order: {usage.sales_order.order_number} →{" "}
                        {usage.sales_order.customer_name || "Customer"}
                      </div>
                    )}
                    {usage.serial_numbers && usage.serial_numbers.length > 0 && (
                      <div className="text-sm text-gray-400 mt-1">
                        Serial Numbers: {usage.serial_numbers.map((s) => s.serial_number).join(", ")}
                      </div>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

/**
 * Backward Trace - Product → Materials → Vendors
 */
function BackwardTrace() {
  const toast = useToast();
  const [traceType, setTraceType] = useState("serial");
  const [searchValue, setSearchValue] = useState("");
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);

  const handleTrace = async (e) => {
    e.preventDefault();
    if (!searchValue) {
      toast.error("Please enter a search value");
      return;
    }

    setLoading(true);
    setError(null);
    try {
      const endpoint =
        traceType === "serial"
          ? `/api/v1/traceability/backward/serial/${encodeURIComponent(searchValue)}`
          : `/api/v1/traceability/backward/sales-order/${searchValue}`;

      const res = await fetch(`${API_URL}${endpoint}`, {
        credentials: "include",
      });

      if (res.ok) {
        const data = await res.json();
        setResult(data);
      } else {
        const errorData = await res.json();
        setError(errorData.detail || "Failed to trace");
        toast.error(errorData.detail || "Failed to trace");
      }
    } catch (err) {
      setError(err.message);
      toast.error(`Error: ${err.message}`);
    } finally {
      setLoading(false);
    }
  };

  const exportDHR = () => {
    if (!result) return;
    const dataStr = JSON.stringify(result, null, 2);
    const dataBlob = new Blob([dataStr], { type: "application/json" });
    const url = URL.createObjectURL(dataBlob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `DHR-backward-${traceType}-${searchValue}-${new Date().toISOString().split("T")[0]}.json`;
    link.click();
    URL.revokeObjectURL(url);
    toast.success("DHR exported");
  };

  return (
    <div className="space-y-4">
      {/* Search Form */}
      <div className="bg-gray-800 rounded-lg p-4">
        <form onSubmit={handleTrace} className="space-y-4">
          <div>
            <label className="block text-sm text-gray-400 mb-2">Trace Type</label>
            <select
              value={traceType}
              onChange={(e) => {
                setTraceType(e.target.value);
                setSearchValue("");
                setResult(null);
              }}
              className="w-full bg-gray-700 border border-gray-600 rounded-lg px-3 py-2 text-white"
            >
              <option value="serial">Serial Number</option>
              <option value="sales_order">Sales Order</option>
            </select>
          </div>
          <div>
            <label className="block text-sm text-gray-400 mb-2">
              {traceType === "serial" ? "Serial Number" : "Sales Order ID"}
            </label>
            <input
              type="text"
              value={searchValue}
              onChange={(e) => setSearchValue(e.target.value)}
              placeholder={
                traceType === "serial"
                  ? "e.g., BLB-20250120-001"
                  : "Enter sales order ID"
              }
              className="w-full bg-gray-700 border border-gray-600 rounded-lg px-3 py-2 text-white"
            />
          </div>
          <button
            type="submit"
            disabled={loading || !searchValue}
            className="px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-lg disabled:opacity-50"
          >
            {loading ? "Tracing..." : "Trace Backward"}
          </button>
        </form>
      </div>

      {/* Error */}
      {error && (
        <div className="bg-red-900/20 border border-red-500/30 rounded-lg p-4 text-red-400">
          {error}
        </div>
      )}

      {/* Results */}
      {result && (
        <div className="space-y-4">
          {/* Product Info */}
          {result.product && (
            <div className="bg-gray-800 rounded-lg p-4">
              <h3 className="text-lg font-semibold text-white mb-3">Product Information</h3>
              <div className="grid grid-cols-2 gap-4 text-sm">
                <div>
                  <span className="text-gray-400">Product:</span>
                  <span className="text-white ml-2">{result.product.name || result.product.sku}</span>
                </div>
                {result.serial_number && (
                  <div>
                    <span className="text-gray-400">Serial Number:</span>
                    <span className="text-white ml-2">{result.serial_number.serial_number}</span>
                  </div>
                )}
                {result.production_order && (
                  <div>
                    <span className="text-gray-400">Production Order:</span>
                    <span className="text-white ml-2">
                      {result.production_order.code || result.production_order.id}
                    </span>
                  </div>
                )}
              </div>
            </div>
          )}

          {/* Material Lineage */}
          {result.material_lineage && result.material_lineage.length > 0 && (
            <div className="bg-gray-800 rounded-lg p-4">
              <div className="flex justify-between items-center mb-3">
                <h3 className="text-lg font-semibold text-white">Material Lineage</h3>
                <button
                  onClick={exportDHR}
                  className="px-3 py-1 bg-green-600 hover:bg-green-700 text-white text-sm rounded"
                >
                  Export DHR
                </button>
              </div>
              <div className="space-y-3">
                {result.material_lineage.map((material, idx) => (
                  <div key={idx} className="bg-gray-700/50 rounded-lg p-3">
                    <div className="font-medium text-white mb-2">
                      {material.spool?.spool_number || `Spool ${material.spool_id}`}
                    </div>
                    <div className="text-sm text-gray-400 space-y-1">
                      <div>
                        Material: {material.material_name || material.product_name || "N/A"}
                      </div>
                      <div>Weight Used: {material.weight_consumed_g || material.weight_consumed_kg}g</div>
                      {material.supplier_lot_number && (
                        <div>Lot Number: {material.supplier_lot_number}</div>
                      )}
                      {material.vendor && (
                        <div>Vendor: {material.vendor.name || material.vendor_name}</div>
                      )}
                      {material.purchase_order && (
                        <div>PO: {material.purchase_order.po_number || material.po_number}</div>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {(!result.material_lineage || result.material_lineage.length === 0) && (
            <div className="bg-gray-800 rounded-lg p-4 text-center text-gray-400">
              No material lineage found
            </div>
          )}
        </div>
      )}
    </div>
  );
}

