import { useState, useEffect, useCallback, useRef } from "react";
import { API_URL } from "../../config/api";
import { useToast } from "../../components/Toast";

export default function AdminScrapReasons() {
  const toast = useToast();
  const [reasons, setReasons] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [showModal, setShowModal] = useState(false);
  const [editingReason, setEditingReason] = useState(null);

  const fetchReasons = useCallback(async () => {
    setLoading(true);
    try {
      const res = await fetch(
        `${API_URL}/api/v1/production-orders/scrap-reasons/all`,
        {
          credentials: "include",
        }
      );
      if (!res.ok) throw new Error("Failed to fetch scrap reasons");
      const data = await res.json();
      setReasons(Array.isArray(data) ? data : []);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchReasons();
  }, [fetchReasons]);

  const handleSave = async (reasonData) => {
    try {
      const requestBody = {
        code: reasonData.code,
        name: reasonData.name,
        sequence: parseInt(reasonData.sequence, 10),
      };
      if (reasonData.description) {
        requestBody.description = reasonData.description;
      }

      const url = editingReason
        ? `${API_URL}/api/v1/production-orders/scrap-reasons/${editingReason.id}`
        : `${API_URL}/api/v1/production-orders/scrap-reasons`;
      const method = editingReason ? "PUT" : "POST";

      const res = await fetch(url, {
        method,
        credentials: "include",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify(requestBody),
      });

      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || "Failed to save scrap reason");
      }

      toast.success(
        editingReason ? "Scrap reason updated" : "Scrap reason created"
      );
      setShowModal(false);
      setEditingReason(null);
      await fetchReasons();
    } catch (err) {
      toast.error(err.message);
      throw err; // Re-throw so modal knows save failed
    }
  };

  const handleToggleActive = async (reason) => {
    try {
      const params = new URLSearchParams({
        active: (!reason.active).toString(),
      });

      const res = await fetch(
        `${API_URL}/api/v1/production-orders/scrap-reasons/${reason.id}?${params}`,
        {
          method: "PUT",
          credentials: "include",
        }
      );

      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || "Failed to update scrap reason");
      }

      toast.success(
        reason.active ? "Scrap reason deactivated" : "Scrap reason activated"
      );
      await fetchReasons();
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
          <h1 className="text-2xl font-bold text-white">Scrap Reasons</h1>
          <p className="text-gray-400 mt-1">
            Configure failure modes for scrapping production orders
          </p>
        </div>
        <button
          onClick={() => {
            setEditingReason(null);
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
          Add Reason
        </button>
      </div>

      {/* Info Banner */}
      <div className="bg-blue-500/10 border border-blue-500/30 rounded-lg p-4">
        <div className="flex gap-3">
          <svg
            className="w-5 h-5 text-blue-400 flex-shrink-0 mt-0.5"
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={2}
              d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"
            />
          </svg>
          <div>
            <p className="text-blue-400 text-sm">
              Scrap reasons are used when a production order fails and needs to
              be remade. Define failure modes specific to your 3D printing
              processes to track quality issues.
            </p>
          </div>
        </div>
      </div>

      {/* Reasons Table */}
      <div className="bg-gray-900 rounded-lg border border-gray-800 overflow-hidden">
        <table className="w-full">
          <thead className="bg-gray-800/50">
            <tr>
              <th className="px-4 py-3 text-left text-xs font-medium text-gray-400 uppercase tracking-wider">
                Order
              </th>
              <th className="px-4 py-3 text-left text-xs font-medium text-gray-400 uppercase tracking-wider">
                Code
              </th>
              <th className="px-4 py-3 text-left text-xs font-medium text-gray-400 uppercase tracking-wider">
                Name
              </th>
              <th className="px-4 py-3 text-left text-xs font-medium text-gray-400 uppercase tracking-wider">
                Description
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
            {reasons.length === 0 ? (
              <tr>
                <td colSpan="6" className="px-4 py-8 text-center text-gray-500">
                  No scrap reasons found. Click "Add Reason" to create one.
                </td>
              </tr>
            ) : (
              reasons.map((reason) => (
                <tr
                  key={reason.id}
                  className={`hover:bg-gray-800/50 ${
                    !reason.active ? "opacity-50" : ""
                  }`}
                >
                  <td className="px-4 py-3 text-gray-500 text-sm">
                    {reason.sequence}
                  </td>
                  <td className="px-4 py-3 text-white font-mono">
                    {reason.code}
                  </td>
                  <td className="px-4 py-3 text-white">{reason.name}</td>
                  <td className="px-4 py-3 text-gray-400 text-sm max-w-xs truncate">
                    {reason.description || "—"}
                  </td>
                  <td className="px-4 py-3">
                    <span
                      className={`px-2 py-1 rounded text-xs font-medium ${
                        reason.active
                          ? "bg-green-500/20 text-green-400"
                          : "bg-gray-500/20 text-gray-400"
                      }`}
                    >
                      {reason.active ? "Active" : "Inactive"}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-right">
                    <div className="flex items-center justify-end gap-2">
                      <button
                        onClick={() => {
                          setEditingReason(reason);
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
                      <button
                        onClick={() => handleToggleActive(reason)}
                        className={`p-1 ${
                          reason.active
                            ? "text-gray-400 hover:text-red-400"
                            : "text-gray-400 hover:text-green-400"
                        }`}
                        title={reason.active ? "Deactivate" : "Activate"}
                      >
                        {reason.active ? (
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
                              d="M18.364 18.364A9 9 0 005.636 5.636m12.728 12.728A9 9 0 015.636 5.636m12.728 12.728L5.636 5.636"
                            />
                          </svg>
                        ) : (
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
                              d="M5 13l4 4L19 7"
                            />
                          </svg>
                        )}
                      </button>
                    </div>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      {/* Modal */}
      {showModal && (
        <ScrapReasonModal
          reason={editingReason}
          onSave={handleSave}
          onClose={() => {
            setShowModal(false);
            setEditingReason(null);
          }}
        />
      )}
    </div>
  );
}

function ScrapReasonModal({ reason, onSave, onClose }) {
  const firstInputRef = useRef(null);
  const [formData, setFormData] = useState({
    code: reason?.code || "",
    name: reason?.name || "",
    description: reason?.description || "",
    sequence: reason?.sequence || 0,
  });
  const [errors, setErrors] = useState({});
  const [isSubmitting, setIsSubmitting] = useState(false);

  useEffect(() => {
    // Focus first input on mount
    if (firstInputRef.current) {
      firstInputRef.current.focus();
    }
  }, []);

  useEffect(() => {
    const handleEsc = (e) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", handleEsc);
    return () => window.removeEventListener("keydown", handleEsc);
  }, [onClose]);

  const validate = () => {
    const newErrors = {};
    if (!formData.code.trim()) {
      newErrors.code = "Code is required";
    }
    if (!formData.name.trim()) {
      newErrors.name = "Name is required";
    }
    setErrors(newErrors);
    return Object.keys(newErrors).length === 0;
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!validate()) return;

    setIsSubmitting(true);
    try {
      await onSave(formData);
    } catch {
      // Error handled by parent
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleBackdropClick = (e) => {
    if (e.target === e.currentTarget) {
      onClose();
    }
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50"
      onClick={handleBackdropClick}
    >
      <div
        className="bg-gray-900 rounded-lg border border-gray-800 w-full max-w-md p-6"
        onClick={(e) => e.stopPropagation()}
        role="dialog"
        aria-modal="true"
        aria-labelledby="modal-title"
      >
        <h2 id="modal-title" className="text-xl font-bold text-white mb-4">
          {reason ? "Edit Scrap Reason" : "Add Scrap Reason"}
        </h2>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-gray-400 mb-1">
              Code *
            </label>
            <input
              ref={firstInputRef}
              type="text"
              value={formData.code}
              onChange={(e) => {
                setFormData({
                  ...formData,
                  code: e.target.value.toLowerCase().replace(/\s+/g, "_"),
                });
                if (errors.code) {
                  setErrors({ ...errors, code: undefined });
                }
              }}
              className={`w-full bg-gray-800 border rounded-lg px-3 py-2 text-white focus:outline-none ${
                errors.code
                  ? "border-red-500 focus:border-red-500"
                  : "border-gray-700 focus:border-blue-500"
              }`}
              placeholder="e.g., nozzle_clog"
              disabled={!!reason || isSubmitting}
            />
            {errors.code && (
              <p className="text-red-400 text-sm mt-1">{errors.code}</p>
            )}
            <p className="text-gray-500 text-xs mt-1">
              Unique identifier (lowercase, underscores)
            </p>
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-400 mb-1">
              Name *
            </label>
            <input
              type="text"
              value={formData.name}
              onChange={(e) => {
                setFormData({ ...formData, name: e.target.value });
                if (errors.name) {
                  setErrors({ ...errors, name: undefined });
                }
              }}
              className={`w-full bg-gray-800 border rounded-lg px-3 py-2 text-white focus:outline-none ${
                errors.name
                  ? "border-red-500 focus:border-red-500"
                  : "border-gray-700 focus:border-blue-500"
              }`}
              placeholder="e.g., Nozzle Clog"
              disabled={isSubmitting}
            />
            {errors.name && (
              <p className="text-red-400 text-sm mt-1">{errors.name}</p>
            )}
            <p className="text-gray-500 text-xs mt-1">
              Display name shown in dropdown
            </p>
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-400 mb-1">
              Description
            </label>
            <textarea
              value={formData.description}
              onChange={(e) =>
                setFormData({ ...formData, description: e.target.value })
              }
              className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-white focus:outline-none focus:border-blue-500 h-20 resize-none"
              disabled={isSubmitting}
              placeholder="e.g., Nozzle clogged mid-print causing under-extrusion or failure"
            />
            <p className="text-gray-500 text-xs mt-1">
              Helpful explanation shown when selected
            </p>
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-400 mb-1">
              Sort Order
            </label>
            <input
              type="number"
              value={formData.sequence}
              onChange={(e) =>
                setFormData({
                  ...formData,
                  sequence: parseInt(e.target.value, 10) || 0,
                })
              }
              className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-white focus:outline-none focus:border-blue-500"
              disabled={isSubmitting}
              min="0"
            />
            <p className="text-gray-500 text-xs mt-1">
              Lower numbers appear first in dropdown
            </p>
          </div>
          <div className="flex justify-end gap-3 pt-4">
            <button
              type="button"
              onClick={onClose}
              className="px-4 py-2 text-gray-400 hover:text-white transition-colors"
              disabled={isSubmitting}
            >
              Cancel
            </button>
            <button
              type="submit"
              className="bg-blue-600 hover:bg-blue-700 text-white px-4 py-2 rounded-lg transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
              disabled={isSubmitting}
            >
              {isSubmitting
                ? "Saving..."
                : reason
                ? "Save Changes"
                : "Create Reason"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
