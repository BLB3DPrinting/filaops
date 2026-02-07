import { useState, useEffect } from "react";
import { API_URL } from "../../config/api";
import { useToast } from "../../components/Toast";

// Location type options
const TYPE_OPTIONS = [
  { value: "warehouse", label: "Warehouse", color: "blue" },
  { value: "shelf", label: "Shelf", color: "green" },
  { value: "bin", label: "Bin", color: "yellow" },
  { value: "staging", label: "Staging Area", color: "purple" },
  { value: "quality", label: "Quality/QC", color: "orange" },
];

export default function AdminLocations() {
  const toast = useToast();
  const [locations, setLocations] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [showModal, setShowModal] = useState(false);
  const [editingLocation, setEditingLocation] = useState(null);
  const [includeInactive, setIncludeInactive] = useState(false);

  useEffect(() => {
    fetchLocations();
  }, [includeInactive]);

  const fetchLocations = async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams();
      if (includeInactive) params.set("include_inactive", "true");

      const res = await fetch(`${API_URL}/api/v1/admin/locations?${params}`, {
        credentials: "include",
      });
      if (!res.ok) throw new Error("Failed to fetch locations");
      const data = await res.json();
      setLocations(Array.isArray(data) ? data : []);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const getTypeStyle = (type) => {
    const found = TYPE_OPTIONS.find((t) => t.value === type);
    if (!found) return "bg-gray-500/20 text-gray-400";
    return {
      blue: "bg-blue-500/20 text-blue-400",
      green: "bg-green-500/20 text-green-400",
      yellow: "bg-yellow-500/20 text-yellow-400",
      purple: "bg-purple-500/20 text-purple-400",
      orange: "bg-orange-500/20 text-orange-400",
    }[found.color];
  };

  const handleSave = async (locationData) => {
    try {
      const url = editingLocation
        ? `${API_URL}/api/v1/admin/locations/${editingLocation.id}`
        : `${API_URL}/api/v1/admin/locations`;
      const method = editingLocation ? "PUT" : "POST";

      const res = await fetch(url, {
        method,
        credentials: "include",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify(locationData),
      });

      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || "Failed to save location");
      }

      toast.success(editingLocation ? "Location updated" : "Location created");
      setShowModal(false);
      setEditingLocation(null);
      fetchLocations();
    } catch (err) {
      toast.error(err.message);
    }
  };

  const handleDelete = async (location) => {
    if (location.code === "MAIN") {
      toast.error("Cannot delete the main warehouse");
      return;
    }
    if (!confirm(`Deactivate location "${location.name}"?`)) return;

    try {
      const res = await fetch(
        `${API_URL}/api/v1/admin/locations/${location.id}`,
        {
          method: "DELETE",
          credentials: "include",
        }
      );

      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || "Failed to deactivate location");
      }

      toast.success("Location deactivated");
      fetchLocations();
    } catch (err) {
      toast.error(err.message);
    }
  };

  const handleReactivate = async (location) => {
    try {
      const res = await fetch(
        `${API_URL}/api/v1/admin/locations/${location.id}`,
        {
          method: "PUT",
          credentials: "include",
          headers: {
            "Content-Type": "application/json",
          },
          body: JSON.stringify({ active: true }),
        }
      );

      if (!res.ok) throw new Error("Failed to reactivate location");

      toast.success("Location reactivated");
      fetchLocations();
    } catch (err) {
      toast.error(err.message);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-500"></div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="bg-red-500/10 border border-red-500/30 rounded-lg p-4 text-red-400">
        {error}
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white">Inventory Locations</h1>
          <p className="text-gray-400 mt-1">
            Manage warehouses, shelves, and storage locations
          </p>
        </div>
        <button
          onClick={() => {
            setEditingLocation(null);
            setShowModal(true);
          }}
          className="bg-blue-600 hover:bg-blue-700 text-white px-4 py-2 rounded-lg flex items-center gap-2 transition-colors"
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
          Add Location
        </button>
      </div>

      {/* Filters */}
      <div className="flex items-center gap-4">
        <label className="flex items-center gap-2 text-gray-400">
          <input
            type="checkbox"
            checked={includeInactive}
            onChange={(e) => setIncludeInactive(e.target.checked)}
            className="rounded bg-gray-800 border-gray-700 text-blue-500 focus:ring-blue-500"
          />
          Show inactive locations
        </label>
      </div>

      {/* Locations Table */}
      <div className="bg-gray-900 rounded-lg border border-gray-800 overflow-hidden">
        <table className="w-full">
          <thead className="bg-gray-800/50">
            <tr>
              <th className="px-4 py-3 text-left text-xs font-medium text-gray-400 uppercase tracking-wider">
                Code
              </th>
              <th className="px-4 py-3 text-left text-xs font-medium text-gray-400 uppercase tracking-wider">
                Name
              </th>
              <th className="px-4 py-3 text-left text-xs font-medium text-gray-400 uppercase tracking-wider">
                Type
              </th>
              <th className="px-4 py-3 text-left text-xs font-medium text-gray-400 uppercase tracking-wider">
                Parent
              </th>
              <th className="px-4 py-3 text-left text-xs font-medium text-gray-400 uppercase tracking-wider">
                Status
              </th>
              <th className="px-4 py-3 text-right text-xs font-medium text-gray-400 uppercase tracking-wider">
                Actions
              </th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-800">
            {locations.length === 0 ? (
              <tr>
                <td
                  colSpan="6"
                  className="px-4 py-8 text-center text-gray-500"
                >
                  No locations found. Click "Add Location" to create one.
                </td>
              </tr>
            ) : (
              locations.map((location) => {
                const parent = locations.find((l) => l.id === location.parent_id);
                return (
                <tr
                  key={location.id}
                  className={`hover:bg-gray-800/50 ${
                    !location.active ? "opacity-50" : ""
                  }`}
                >
                  <td className="px-4 py-3 text-white font-mono">
                    {location.code}
                  </td>
                  <td className="px-4 py-3 text-white">{location.name}</td>
                  <td className="px-4 py-3">
                    <span
                      className={`px-2 py-1 rounded text-xs font-medium ${getTypeStyle(
                        location.type
                      )}`}
                    >
                      {TYPE_OPTIONS.find((t) => t.value === location.type)
                        ?.label || location.type}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-gray-400">
                    {parent ? parent.code : "—"}
                  </td>
                  <td className="px-4 py-3">
                    <span
                      className={`px-2 py-1 rounded text-xs font-medium ${
                        location.active
                          ? "bg-green-500/20 text-green-400"
                          : "bg-gray-500/20 text-gray-400"
                      }`}
                    >
                      {location.active ? "Active" : "Inactive"}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-right">
                    <div className="flex items-center justify-end gap-2">
                      <button
                        onClick={() => {
                          setEditingLocation(location);
                          setShowModal(true);
                        }}
                        className="text-gray-400 hover:text-white p-1"
                        title="Edit"
                      >
                        <svg
                          className="w-4 h-4"
                          fill="none"
                          stroke="currentColor"
                          viewBox="0 0 24 24"
                        >
                          <path
                            strokeLinecap="round"
                            strokeLinejoin="round"
                            strokeWidth={2}
                            d="M15.232 5.232l3.536 3.536m-2.036-5.036a2.5 2.5 0 113.536 3.536L6.5 21.036H3v-3.572L16.732 3.732z"
                          />
                        </svg>
                      </button>
                      {location.active ? (
                        <button
                          onClick={() => handleDelete(location)}
                          className="text-gray-400 hover:text-red-400 p-1"
                          title="Deactivate"
                          disabled={location.code === "MAIN"}
                        >
                          <svg
                            className="w-4 h-4"
                            fill="none"
                            stroke="currentColor"
                            viewBox="0 0 24 24"
                          >
                            <path
                              strokeLinecap="round"
                              strokeLinejoin="round"
                              strokeWidth={2}
                              d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"
                            />
                          </svg>
                        </button>
                      ) : (
                        <button
                          onClick={() => handleReactivate(location)}
                          className="text-gray-400 hover:text-green-400 p-1"
                          title="Reactivate"
                        >
                          <svg
                            className="w-4 h-4"
                            fill="none"
                            stroke="currentColor"
                            viewBox="0 0 24 24"
                          >
                            <path
                              strokeLinecap="round"
                              strokeLinejoin="round"
                              strokeWidth={2}
                              d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"
                            />
                          </svg>
                        </button>
                      )}
                    </div>
                  </td>
                </tr>
              );
              })
            )}
          </tbody>
        </table>
      </div>

      {/* Modal */}
      {showModal && (
        <LocationModal
          location={editingLocation}
          locations={locations}
          onSave={handleSave}
          onClose={() => {
            setShowModal(false);
            setEditingLocation(null);
          }}
        />
      )}
    </div>
  );
}

function LocationModal({ location, locations, onSave, onClose }) {
  const [formData, setFormData] = useState({
    code: location?.code || "",
    name: location?.name || "",
    type: location?.type || "warehouse",
    parent_id: location?.parent_id || null,
  });

  const handleSubmit = (e) => {
    e.preventDefault();
    if (!formData.code.trim() || !formData.name.trim()) {
      return;
    }
    onSave(formData);
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
      <div className="bg-gray-900 rounded-lg border border-gray-800 w-full max-w-md p-6">
        <h2 className="text-xl font-bold text-white mb-4">
          {location ? "Edit Location" : "Add Location"}
        </h2>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-gray-400 mb-1">
              Code *
            </label>
            <input
              type="text"
              value={formData.code}
              onChange={(e) =>
                setFormData({ ...formData, code: e.target.value.toUpperCase() })
              }
              className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-white focus:outline-none focus:border-blue-500"
              placeholder="e.g., SHELF-A"
              required
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-400 mb-1">
              Name *
            </label>
            <input
              type="text"
              value={formData.name}
              onChange={(e) =>
                setFormData({ ...formData, name: e.target.value })
              }
              className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-white focus:outline-none focus:border-blue-500"
              placeholder="e.g., Shelf A - Filament Storage"
              required
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-400 mb-1">
              Type
            </label>
            <select
              value={formData.type}
              onChange={(e) =>
                setFormData({ ...formData, type: e.target.value })
              }
              className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-white focus:outline-none focus:border-blue-500"
            >
              {TYPE_OPTIONS.map((opt) => (
                <option key={opt.value} value={opt.value}>
                  {opt.label}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-400 mb-1">
              Parent Location
            </label>
            <select
              value={formData.parent_id || ""}
              onChange={(e) =>
                setFormData({
                  ...formData,
                  parent_id: e.target.value ? parseInt(e.target.value) : null,
                })
              }
              className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-white focus:outline-none focus:border-blue-500"
            >
              <option value="">None (Top Level)</option>
              {locations
                .filter((l) => l.id !== location?.id)
                .map((l) => (
                  <option key={l.id} value={l.id}>
                    {l.code} - {l.name}
                  </option>
                ))}
            </select>
          </div>
          <div className="flex justify-end gap-3 pt-4">
            <button
              type="button"
              onClick={onClose}
              className="px-4 py-2 text-gray-400 hover:text-white transition-colors"
            >
              Cancel
            </button>
            <button
              type="submit"
              className="bg-blue-600 hover:bg-blue-700 text-white px-4 py-2 rounded-lg transition-colors"
            >
              {location ? "Save Changes" : "Create Location"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
