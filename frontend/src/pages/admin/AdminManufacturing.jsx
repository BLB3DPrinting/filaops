import { useState, useEffect } from "react";
import RoutingEditor from "../../components/RoutingEditor";
import { API_URL } from "../../config/api";
import { useToast } from "../../components/Toast";
import WorkCenterCard from "../../components/manufacturing/WorkCenterCard";
import WorkCenterModal from "../../components/manufacturing/WorkCenterModal";
import ResourceModal from "../../components/manufacturing/ResourceModal";
import PrinterSetupModal from "../../components/manufacturing/PrinterSetupModal";

export default function AdminManufacturing() {
  const toast = useToast();
  const [activeTab, setActiveTab] = useState("work-centers");
  const [workCenters, setWorkCenters] = useState([]);
  const [routings, setRoutings] = useState([]);
  const [products, setProducts] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  // Modal states
  const [showWorkCenterModal, setShowWorkCenterModal] = useState(false);
  const [showResourceModal, setShowResourceModal] = useState(false);
  const [showRoutingModal, setShowRoutingModal] = useState(false);
  const [showPrinterSetupModal, setShowPrinterSetupModal] = useState(false);
  const [editingWorkCenter, setEditingWorkCenter] = useState(null);
  const [editingResource, setEditingResource] = useState(null);
  const [editingRouting, setEditingRouting] = useState(null);
  const [routingProductId, setRoutingProductId] = useState(null);
  const [selectedWorkCenter, setSelectedWorkCenter] = useState(null);

  // Fetch both on initial mount so tab badges show correct counts
  useEffect(() => {
    fetchWorkCenters();
    fetchRoutings();
    fetchProducts();
  }, []);

  const fetchWorkCenters = async () => {
    setLoading(true);
    try {
      const res = await fetch(
        `${API_URL}/api/v1/work-centers/?active_only=false`,
        {
          credentials: "include",
        }
      );
      if (!res.ok) throw new Error("Failed to fetch work centers");
      const data = await res.json();
      setWorkCenters(data);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const fetchRoutings = async () => {
    setLoading(true);
    try {
      const res = await fetch(`${API_URL}/api/v1/routings/`, {
        credentials: "include",
      });
      if (!res.ok) throw new Error("Failed to fetch routings");
      const data = await res.json();
      setRoutings(data);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const fetchProducts = async () => {
    try {
      const res = await fetch(`${API_URL}/api/v1/products?limit=500`, {
        credentials: "include",
      });
      if (res.ok) {
        const data = await res.json();
        // Handle both array and {items: [...]} responses
        setProducts(Array.isArray(data) ? data : (data.items || data.products || []));
      }
    } catch {
      // Products fetch failure is non-critical - product selector will just be empty
      setProducts([]);
    }
  };

  const handleSaveWorkCenter = async (data) => {
    try {
      const url = editingWorkCenter
        ? `${API_URL}/api/v1/work-centers/${editingWorkCenter.id}`
        : `${API_URL}/api/v1/work-centers/`;

      const res = await fetch(url, {
        method: editingWorkCenter ? "PUT" : "POST",
        credentials: "include",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify(data),
      });

      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || "Failed to save work center");
      }

      toast.success(
        editingWorkCenter ? "Work center updated" : "Work center created"
      );
      setShowWorkCenterModal(false);
      setEditingWorkCenter(null);
      fetchWorkCenters();
    } catch (err) {
      toast.error(err.message);
    }
  };

  const handleDeleteWorkCenter = async (wc) => {
    if (!confirm(`Deactivate work center "${wc.name}"?`)) return;

    try {
      const res = await fetch(`${API_URL}/api/v1/work-centers/${wc.id}`, {
        method: "DELETE",
        credentials: "include",
      });

      if (!res.ok) throw new Error("Failed to delete");
      toast.success("Work center deactivated");
      fetchWorkCenters();
    } catch (err) {
      toast.error(err.message);
    }
  };

  const handleDeleteResource = async (resource) => {
    if (!confirm(`Delete resource "${resource.name}"? This cannot be undone.`))
      return;

    try {
      const res = await fetch(
        `${API_URL}/api/v1/work-centers/resources/${resource.id}`,
        {
          method: "DELETE",
          credentials: "include",
        }
      );

      if (!res.ok) throw new Error("Failed to delete resource");
      toast.success("Resource deleted");
      fetchWorkCenters(); // Refresh to update resource counts
    } catch (err) {
      toast.error(err.message);
    }
  };

  const handleSaveResource = async (data) => {
    try {
      const url = editingResource
        ? `${API_URL}/api/v1/work-centers/resources/${editingResource.id}`
        : `${API_URL}/api/v1/work-centers/${selectedWorkCenter.id}/resources`;

      const res = await fetch(url, {
        method: editingResource ? "PUT" : "POST",
        credentials: "include",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify(data),
      });

      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || "Failed to save resource");
      }

      toast.success(editingResource ? "Resource updated" : "Resource created");
      setShowResourceModal(false);
      setEditingResource(null);
      fetchWorkCenters();
    } catch (err) {
      toast.error(err.message);
    }
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex justify-between items-center">
        <div>
          <h1 className="text-2xl font-bold text-white">Manufacturing</h1>
          <p className="text-gray-400 mt-1">
            Work centers, resources, and production routings
          </p>
        </div>
      </div>

      {/* Tabs */}
      <div className="border-b border-gray-700">
        <nav className="flex space-x-8">
          <button
            onClick={() => setActiveTab("work-centers")}
            className={`py-3 px-1 border-b-2 font-medium text-sm transition-colors ${
              activeTab === "work-centers"
                ? "border-blue-500 text-blue-400"
                : "border-transparent text-gray-400 hover:text-white hover:border-gray-600"
            }`}
          >
            Work Centers
            <span className="ml-2 px-2 py-0.5 text-xs rounded-full bg-gray-700">
              {workCenters.length}
            </span>
          </button>
          <button
            onClick={() => setActiveTab("routings")}
            className={`py-3 px-1 border-b-2 font-medium text-sm transition-colors ${
              activeTab === "routings"
                ? "border-blue-500 text-blue-400"
                : "border-transparent text-gray-400 hover:text-white hover:border-gray-600"
            }`}
          >
            Routings
            <span className="ml-2 px-2 py-0.5 text-xs rounded-full bg-gray-700">
              {routings.length}
            </span>
          </button>
        </nav>
      </div>

      {error && (
        <div className="bg-red-900/20 border border-red-500/30 rounded-lg p-4 text-red-400">
          {error}
        </div>
      )}

      {/* Work Centers Tab */}
      {activeTab === "work-centers" && (
        <div className="space-y-4">
          <div className="flex justify-between items-center">
            <button
              onClick={() => setShowPrinterSetupModal(true)}
              className="bg-purple-600 hover:bg-purple-700 text-white px-4 py-2 rounded-lg transition-colors flex items-center gap-2"
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
                  d="M17 17h2a2 2 0 002-2v-4a2 2 0 00-2-2H5a2 2 0 00-2 2v4a2 2 0 002 2h2m2 4h6a2 2 0 002-2v-4a2 2 0 00-2-2H9a2 2 0 00-2 2v4a2 2 0 002 2zm8-12V5a2 2 0 00-2-2H9a2 2 0 00-2 2v4h10z"
                />
              </svg>
              Printer Setup
            </button>
            <button
              onClick={() => {
                setEditingWorkCenter(null);
                setShowWorkCenterModal(true);
              }}
              className="bg-blue-600 hover:bg-blue-700 text-white px-4 py-2 rounded-lg transition-colors flex items-center gap-2"
            >
              <span>+</span> Add Work Center
            </button>
          </div>

          {loading ? (
            <div className="text-center py-12 text-gray-400">Loading...</div>
          ) : (
            <div className="grid gap-4">
              {workCenters.map((wc) => (
                <WorkCenterCard
                  key={wc.id}
                  workCenter={wc}
                  onEdit={() => {
                    setEditingWorkCenter(wc);
                    setShowWorkCenterModal(true);
                  }}
                  onDelete={() => handleDeleteWorkCenter(wc)}
                  onAddResource={() => {
                    setSelectedWorkCenter(wc);
                    setEditingResource(null);
                    setShowResourceModal(true);
                  }}
                  onEditResource={(r) => {
                    setSelectedWorkCenter(wc);
                    setEditingResource(r);
                    setShowResourceModal(true);
                  }}
                  onDeleteResource={handleDeleteResource}
                />
              ))}
            </div>
          )}
        </div>
      )}

      {/* Routings Tab */}
      {activeTab === "routings" && (
        <div className="space-y-4">
          <div className="flex justify-end items-center">
            <button
              onClick={() => {
                setEditingRouting(null);
                setRoutingProductId(null);
                setShowRoutingModal(true);
              }}
              className="bg-blue-600 hover:bg-blue-700 text-white px-4 py-2 rounded-lg transition-colors flex items-center gap-2"
            >
              <span>+</span> Create Routing
            </button>
          </div>

          {loading ? (
            <div className="text-center py-12 text-gray-400">Loading...</div>
          ) : routings.length === 0 ? (
            <div className="text-center py-12">
              <div className="text-gray-400 mb-2">No routings defined yet</div>
              <p className="text-sm text-gray-500">
                Routings define HOW to make a product - the sequence of
                operations at each work center.
              </p>
            </div>
          ) : (
            <div className="bg-gray-900 rounded-lg border border-gray-800 overflow-hidden">
              <table className="w-full">
                <thead>
                  <tr className="border-b border-gray-800 text-left text-sm text-gray-400">
                    <th className="px-4 py-3">Code</th>
                    <th className="px-4 py-3">Product</th>
                    <th className="px-4 py-3">Version</th>
                    <th className="px-4 py-3">Operations</th>
                    <th className="px-4 py-3">Total Time</th>
                    <th className="px-4 py-3">Cost</th>
                    <th className="px-4 py-3">Status</th>
                    <th className="px-4 py-3"></th>
                  </tr>
                </thead>
                <tbody>
                  {routings.map((routing) => (
                    <tr
                      key={routing.id}
                      className={`border-b border-gray-800 hover:bg-gray-800/50 ${
                        routing.is_template ? "bg-green-900/10" : ""
                      }`}
                    >
                      <td className="px-4 py-3 font-mono text-blue-400">
                        {routing.code}
                        {routing.is_template && (
                          <span className="ml-2 px-2 py-0.5 rounded text-xs bg-green-900/30 text-green-400">
                            Template
                          </span>
                        )}
                      </td>
                      <td className="px-4 py-3 text-white">
                        {routing.is_template ? (
                          <span className="text-green-300">{routing.name}</span>
                        ) : (
                          routing.product_name ||
                          routing.product_sku ||
                          `Product #${routing.product_id}`
                        )}
                      </td>
                      <td className="px-4 py-3 text-gray-400">
                        v{routing.version} ({routing.revision})
                      </td>
                      <td className="px-4 py-3 text-gray-400">
                        {routing.operation_count || 0} steps
                      </td>
                      <td className="px-4 py-3 text-gray-400">
                        {routing.total_run_time_minutes
                          ? `${parseFloat(
                              routing.total_run_time_minutes
                            ).toFixed(0)} min`
                          : "-"}
                      </td>
                      <td className="px-4 py-3 text-green-400">
                        {routing.total_cost
                          ? `$${parseFloat(routing.total_cost).toFixed(2)}`
                          : "-"}
                      </td>
                      <td className="px-4 py-3">
                        <span
                          className={`px-2 py-1 rounded text-xs ${
                            routing.is_active
                              ? "bg-green-900/30 text-green-400"
                              : "bg-gray-700 text-gray-400"
                          }`}
                        >
                          {routing.is_active ? "Active" : "Inactive"}
                        </span>
                      </td>
                      <td className="px-4 py-3">
                        <button
                          onClick={() => {
                            setEditingRouting(routing);
                            setRoutingProductId(routing.product_id);
                            setShowRoutingModal(true);
                          }}
                          className="text-blue-400 hover:text-blue-300 text-sm"
                        >
                          Edit
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      {/* Work Center Modal */}
      {showWorkCenterModal && (
        <WorkCenterModal
          workCenter={editingWorkCenter}
          onClose={() => {
            setShowWorkCenterModal(false);
            setEditingWorkCenter(null);
          }}
          onSave={handleSaveWorkCenter}
        />
      )}

      {/* Resource Modal */}
      {showResourceModal && (
        <ResourceModal
          resource={editingResource}
          workCenter={selectedWorkCenter}
          onClose={() => {
            setShowResourceModal(false);
            setEditingResource(null);
          }}
          onSave={handleSaveResource}
        />
      )}

      {/* Printer Setup Modal */}
      {showPrinterSetupModal && (
        <PrinterSetupModal
          workCenters={workCenters}
          onClose={() => setShowPrinterSetupModal(false)}
          onAddPrinter={(wc) => {
            setShowPrinterSetupModal(false);
            setSelectedWorkCenter(wc);
            setEditingResource(null);
            setShowResourceModal(true);
          }}
        />
      )}

      {/* Routing Editor Modal */}
      {showRoutingModal && (
        <RoutingEditor
          isOpen={showRoutingModal}
          onClose={() => {
            setShowRoutingModal(false);
            setEditingRouting(null);
            setRoutingProductId(null);
          }}
          productId={routingProductId || editingRouting?.product_id || null}
          routingId={editingRouting?.id || null}
          products={products}
          onSuccess={() => {
            setShowRoutingModal(false);
            setEditingRouting(null);
            setRoutingProductId(null);
            fetchRoutings();
          }}
        />
      )}
    </div>
  );
}
