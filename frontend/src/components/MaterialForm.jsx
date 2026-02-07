/**
 * MaterialForm - Simple form for creating material items (filament)
 *
 * Uses the new POST /api/v1/items/material endpoint.
 * Pre-filled for material creation with material type and color selection.
 * Allows creating new colors on-the-fly if none exist for the material type.
 */
import { useState, useEffect, useCallback } from "react";
import { API_URL } from "../config/api";
import Modal from "./Modal";

export default function MaterialForm({ isOpen, onClose, onSuccess }) {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const [materialTypes, setMaterialTypes] = useState([]);
  const [colors, setColors] = useState([]);
  const [selectedMaterialType, setSelectedMaterialType] = useState("");

  // Color creation state
  const [showColorForm, setShowColorForm] = useState(false);
  const [newColorName, setNewColorName] = useState("");
  const [newColorHex, setNewColorHex] = useState("#000000");
  const [creatingColor, setCreatingColor] = useState(false);

  const [formData, setFormData] = useState({
    material_type_code: "",
    color_code: "",
    initial_qty_kg: 0,
    cost_per_kg: "",
    selling_price: "",
  });

  const fetchMaterialTypes = useCallback(async () => {
    try {
      const res = await fetch(
        `${API_URL}/api/v1/materials/types?customer_visible_only=false`,
        {
          credentials: "include",
        }
      );
      if (res.ok) {
        const data = await res.json();
        setMaterialTypes(data.materials || []);
      }
    } catch {
      // Material types fetch failure is non-critical
    }
  }, []);

  const fetchColors = useCallback(
    async (materialTypeCode) => {
      try {
        const res = await fetch(
          `${API_URL}/api/v1/materials/types/${materialTypeCode}/colors?in_stock_only=false&customer_visible_only=false`,
          {
            credentials: "include",
          }
        );
        if (res.ok) {
          const data = await res.json();
          setColors(data.colors || []);
        }
      } catch {
        setColors([]);
      }
    },
    []
  );

  useEffect(() => {
    if (isOpen) {
      fetchMaterialTypes();
      setFormData({
        material_type_code: "",
        color_code: "",
        initial_qty_kg: 0,
        cost_per_kg: "",
        selling_price: "",
      });
      setSelectedMaterialType("");
      setError(null);
      setShowColorForm(false);
      setNewColorName("");
      setNewColorHex("#000000");
    }
  }, [isOpen, fetchMaterialTypes]);

  useEffect(() => {
    if (selectedMaterialType) {
      fetchColors(selectedMaterialType);
    } else {
      setColors([]);
    }
  }, [selectedMaterialType, fetchColors]);

  const handleCreateColor = async () => {
    if (!newColorName.trim()) {
      setError("Color name is required");
      return;
    }

    setCreatingColor(true);
    setError(null);

    try {
      const res = await fetch(
        `${API_URL}/api/v1/materials/types/${selectedMaterialType}/colors`,
        {
          method: "POST",
          credentials: "include",
          headers: {
            "Content-Type": "application/json",
          },
          body: JSON.stringify({
            name: newColorName.trim(),
            hex_code: newColorHex || null,
          }),
        }
      );

      if (!res.ok) {
        const errorData = await res.json();
        throw new Error(errorData.detail || "Failed to create color");
      }

      const data = await res.json();

      // Refresh colors list and select the new color
      await fetchColors(selectedMaterialType);
      setFormData({ ...formData, color_code: data.code });
      setShowColorForm(false);
      setNewColorName("");
      setNewColorHex("#000000");
    } catch (err) {
      setError(err.message);
    } finally {
      setCreatingColor(false);
    }
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setLoading(true);
    setError(null);

    try {
      const payload = {
        material_type_code: formData.material_type_code,
        color_code: formData.color_code,
        initial_qty_kg: parseFloat(formData.initial_qty_kg) || 0,
        cost_per_kg: formData.cost_per_kg
          ? parseFloat(formData.cost_per_kg)
          : null,
        selling_price: formData.selling_price
          ? parseFloat(formData.selling_price)
          : null,
      };

      const res = await fetch(`${API_URL}/api/v1/items/material`, {
        method: "POST",
        credentials: "include",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify(payload),
      });

      if (!res.ok) {
        const errorData = await res.json();
        throw new Error(errorData.detail || "Failed to create material");
      }

      const data = await res.json();
      onSuccess?.(data);
      onClose();
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const selectedMaterial = materialTypes.find(
    (m) => m.code === formData.material_type_code
  );

  return (
    <Modal isOpen={isOpen} onClose={onClose} title="Create New Material" disableClose={loading}>
      <div className="p-6">
          <div className="flex justify-between items-center mb-6">
            <h2 className="text-2xl font-bold text-white">
              Create New Material
            </h2>
            <button
              onClick={onClose}
              className="text-gray-400 hover:text-white"
            >
              ✕
            </button>
          </div>

          {error && (
            <div className="mb-4 p-3 bg-red-500/10 border border-red-500/30 text-red-400 rounded-xl">
              {error}
            </div>
          )}

          <form onSubmit={handleSubmit} className="space-y-4">
            {/* Material Type */}
            <div>
              <label className="block text-sm font-medium text-gray-300 mb-1">
                Material Type <span className="text-red-400">*</span>
              </label>
              <select
                required
                value={formData.material_type_code}
                onChange={(e) => {
                  setFormData({
                    ...formData,
                    material_type_code: e.target.value,
                    color_code: "",
                  });
                  setSelectedMaterialType(e.target.value);
                }}
                className="w-full px-4 py-2 bg-gray-800 border border-gray-700 rounded-lg text-white focus:border-blue-500 focus:outline-none"
              >
                <option value="">Select material type...</option>
                {materialTypes.map((mt) => (
                  <option key={mt.code} value={mt.code}>
                    {mt.name} ({mt.base_material})
                  </option>
                ))}
              </select>
              {selectedMaterial && (
                <p className="mt-1 text-sm text-gray-400">
                  {selectedMaterial.description}
                </p>
              )}
            </div>

            {/* Color */}
            <div>
              <label className="block text-sm font-medium text-gray-300 mb-1">
                Color <span className="text-red-400">*</span>
              </label>

              {!showColorForm ? (
                <>
                  <select
                    required={!showColorForm}
                    value={formData.color_code}
                    onChange={(e) =>
                      setFormData({ ...formData, color_code: e.target.value })
                    }
                    className="w-full px-4 py-2 bg-gray-800 border border-gray-700 rounded-lg text-white focus:border-blue-500 focus:outline-none"
                    disabled={!formData.material_type_code}
                  >
                    <option value="">
                      {formData.material_type_code
                        ? colors.length === 0
                          ? "No colors available - create one below"
                          : "Select color..."
                        : "Select material type first"}
                    </option>
                    {colors.map((color) => (
                      <option key={color.code} value={color.code}>
                        {color.name} {color.hex && `(${color.hex})`}
                      </option>
                    ))}
                  </select>

                  {formData.material_type_code && (
                    <button
                      type="button"
                      onClick={() => setShowColorForm(true)}
                      className="mt-2 text-sm text-blue-400 hover:text-blue-300 flex items-center gap-1"
                    >
                      <span>+</span> Create new color for this material
                    </button>
                  )}
                </>
              ) : (
                <div className="border border-gray-700 rounded-xl p-3 bg-gray-800 space-y-3">
                  <div className="flex justify-between items-center">
                    <span className="text-sm font-medium text-gray-300">
                      New Color
                    </span>
                    <button
                      type="button"
                      onClick={() => {
                        setShowColorForm(false);
                        setNewColorName("");
                        setNewColorHex("#000000");
                      }}
                      className="text-gray-400 hover:text-white text-sm"
                    >
                      Cancel
                    </button>
                  </div>

                  <div>
                    <label className="block text-xs text-gray-400 mb-1">
                      Color Name *
                    </label>
                    <input
                      type="text"
                      value={newColorName}
                      onChange={(e) => setNewColorName(e.target.value)}
                      placeholder="e.g., Mystic Blue"
                      className="w-full px-4 py-2 bg-gray-700 border border-gray-600 rounded-lg text-white placeholder-gray-500 text-sm focus:border-blue-500 focus:outline-none"
                    />
                  </div>

                  <div>
                    <label className="block text-xs text-gray-400 mb-1">
                      Hex Color (optional)
                    </label>
                    <div className="flex gap-2 items-center">
                      <input
                        type="color"
                        value={newColorHex}
                        onChange={(e) => setNewColorHex(e.target.value)}
                        className="w-10 h-10 border border-gray-600 rounded cursor-pointer bg-gray-700"
                      />
                      <input
                        type="text"
                        value={newColorHex}
                        onChange={(e) => setNewColorHex(e.target.value)}
                        placeholder="#000000"
                        className="flex-1 px-4 py-2 bg-gray-700 border border-gray-600 rounded-lg text-white text-sm focus:border-blue-500 focus:outline-none"
                      />
                    </div>
                  </div>

                  <button
                    type="button"
                    onClick={handleCreateColor}
                    disabled={creatingColor || !newColorName.trim()}
                    className="w-full px-3 py-2 bg-green-600 text-white rounded-lg font-medium hover:bg-green-700 disabled:opacity-50 text-sm"
                  >
                    {creatingColor ? "Creating..." : "Create Color"}
                  </button>
                </div>
              )}
            </div>

            {/* Initial Quantity */}
            <div>
              <label className="block text-sm font-medium text-gray-300 mb-1">
                Initial Quantity (kg)
              </label>
              <input
                type="number"
                step="0.001"
                min="0"
                value={formData.initial_qty_kg}
                onChange={(e) =>
                  setFormData({ ...formData, initial_qty_kg: e.target.value })
                }
                className="w-full px-4 py-2 bg-gray-800 border border-gray-700 rounded-lg text-white placeholder-gray-500 focus:border-blue-500 focus:outline-none"
                placeholder="0.000"
              />
            </div>

            {/* Pricing */}
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-sm font-medium text-gray-300 mb-1">
                  Cost per kg
                </label>
                <input
                  type="number"
                  step="0.01"
                  min="0"
                  value={formData.cost_per_kg}
                  onChange={(e) =>
                    setFormData({ ...formData, cost_per_kg: e.target.value })
                  }
                  className="w-full px-4 py-2 bg-gray-800 border border-gray-700 rounded-lg text-white placeholder-gray-500 focus:border-blue-500 focus:outline-none"
                  placeholder="0.00"
                />
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-300 mb-1">
                  Selling Price per kg
                </label>
                <input
                  type="number"
                  step="0.01"
                  min="0"
                  value={formData.selling_price}
                  onChange={(e) =>
                    setFormData({ ...formData, selling_price: e.target.value })
                  }
                  className="w-full px-4 py-2 bg-gray-800 border border-gray-700 rounded-lg text-white placeholder-gray-500 focus:border-blue-500 focus:outline-none"
                  placeholder="0.00"
                />
              </div>
            </div>

            {/* Actions */}
            <div className="flex justify-end gap-3 pt-4 border-t border-gray-700">
              <button
                type="button"
                onClick={onClose}
                className="px-4 py-2 bg-gray-800 border border-gray-700 rounded-lg text-gray-300 hover:bg-gray-700"
                disabled={loading}
              >
                Cancel
              </button>
              <button
                type="submit"
                className="px-4 py-2 bg-blue-600 text-white rounded-lg font-medium hover:bg-blue-700 disabled:opacity-50"
                disabled={
                  loading ||
                  !formData.material_type_code ||
                  !formData.color_code
                }
              >
                {loading ? "Creating..." : "Create Material"}
              </button>
            </div>
          </form>

          <div className="mt-4 p-3 bg-blue-500/10 border border-blue-500/30 rounded-xl text-sm text-blue-300">
            <strong>Note:</strong> This will create a Product with SKU format:
            MAT-{formData.material_type_code || "TYPE"}-
            {formData.color_code || "COLOR"}
          </div>
        </div>
    </Modal>
  );
}
