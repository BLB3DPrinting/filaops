/**
 * ItemForm - Simple single-screen form for creating/editing items
 *
 * Replaces the complex ItemWizard with a clean, focused form.
 * BOM and Routing are managed separately via dedicated editors.
 */
import { useState, useEffect, useCallback, useRef } from "react";
import { API_URL } from "../config/api";
import {
  validateRequired,
  validatePrice,
  validateSKU,
  validateForm,
  hasErrors,
} from "../utils/validation";
import { FormErrorSummary, RequiredIndicator } from "./ErrorMessage";
import Modal from "./Modal";

const ITEM_TYPES = [
  { value: "finished_good", label: "Finished Good" },
  { value: "component", label: "Component" },
  { value: "supply", label: "Supply" },
  { value: "service", label: "Service" },
  { value: "material", label: "Material (Filament)" },
];

const PROCUREMENT_TYPES = [
  { value: "make", label: "Make (Manufactured)" },
  { value: "buy", label: "Buy (Purchased)" },
  { value: "make_or_buy", label: "Make or Buy" },
];

const STOCKING_POLICIES = [
  { value: "on_demand", label: "On-Demand (MRP-driven)" },
  { value: "stocked", label: "Stocked (Reorder Point)" },
];

export default function ItemForm({
  isOpen,
  onClose,
  onSuccess,
  editingItem = null,
}) {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [errors, setErrors] = useState({});
  const [categories, setCategories] = useState([]);
  const [uomClasses, setUomClasses] = useState([]);
  const [uploading, setUploading] = useState(false);
  const fileInputRef = useRef(null);

  const [formData, setFormData] = useState({
    sku: editingItem?.sku || "",
    name: editingItem?.name || "",
    description: editingItem?.description || "",
    item_type: editingItem?.item_type || "finished_good",
    procurement_type: editingItem?.procurement_type || "make",
    stocking_policy: editingItem?.stocking_policy || "on_demand",
    category_id: editingItem?.category_id || null,
    unit: editingItem?.unit || "EA",
    standard_cost: editingItem?.standard_cost || "",
    selling_price: editingItem?.selling_price || "",
    reorder_point: editingItem?.reorder_point || "",
    image_url: editingItem?.image_url || "",
  });

  const fetchCategories = useCallback(async () => {
    try {
      const res = await fetch(`${API_URL}/api/v1/items/categories`, {
        credentials: "include",
      });
      if (res.ok) {
        const data = await res.json();
        setCategories(data);
      }
    } catch (err) {
      if (import.meta.env.DEV) {
        console.error("ItemForm: fetchCategories failed", {
          endpoint: `${API_URL}/api/v1/items/categories`,
          message: err?.message,
          stack: err?.stack,
        });
      }
    }
  }, []);

  const fetchUomClasses = useCallback(async () => {
    try {
      const res = await fetch(`${API_URL}/api/v1/admin/uom/classes`, {
        credentials: "include",
      });
      if (res.ok) {
        const data = await res.json();
        setUomClasses(data);
      }
    } catch (err) {
      if (import.meta.env.DEV) {
        console.error("ItemForm: fetchUomClasses failed", {
          endpoint: `${API_URL}/api/v1/admin/uom/classes`,
          message: err?.message,
          stack: err?.stack,
        });
      }
      setUomClasses([]);
    }
  }, []);

  useEffect(() => {
    if (isOpen) {
      fetchCategories();
      fetchUomClasses();
      if (editingItem) {
        setFormData({
          sku: editingItem.sku || "",
          name: editingItem.name || "",
          description: editingItem.description || "",
          item_type: editingItem.item_type || "finished_good",
          procurement_type: editingItem.procurement_type || "make",
          stocking_policy: editingItem.stocking_policy || "on_demand",
          category_id: editingItem.category_id || null,
          unit: editingItem.unit || "EA",
          standard_cost: editingItem.standard_cost || "",
          selling_price: editingItem.selling_price || "",
          reorder_point: editingItem.reorder_point || "",
          image_url: editingItem.image_url || "",
        });
      } else {
        // Reset form for new item
        setFormData({
          sku: "",
          name: "",
          description: "",
          item_type: "finished_good",
          procurement_type: "make",
          stocking_policy: "on_demand",
          category_id: null,
          unit: "EA",
          standard_cost: "",
          selling_price: "",
          reorder_point: "",
          image_url: "",
        });
      }
      setError(null);
      setErrors({});
    }
  }, [isOpen, editingItem, fetchCategories, fetchUomClasses]);

  // Auto-configure material type settings
  useEffect(() => {
    if (formData.item_type === 'material' && !editingItem) {
      setFormData(prev => ({
        ...prev,
        unit: 'G',
        procurement_type: 'buy',
      }));
    }
  }, [formData.item_type, editingItem]);

  const validateFormData = () => {
    const validationRules = {
      name: [(v) => validateRequired(v, "Item name")],
      unit: [(v) => validateRequired(v, "Unit of measure")],
      item_type: [(v) => validateRequired(v, "Item type")],
      procurement_type: [(v) => validateRequired(v, "Procurement type")],
    };

    // Only validate SKU if it's provided (it's optional - can be auto-generated)
    if (formData.sku && formData.sku.trim()) {
      validationRules.sku = [(v) => validateSKU(v)];
    }

    // Validate numeric fields if they have values
    if (formData.standard_cost !== "" && formData.standard_cost !== null) {
      validationRules.standard_cost = [
        (v) => validatePrice(v, "Standard cost"),
      ];
    }

    if (formData.selling_price !== "" && formData.selling_price !== null) {
      validationRules.selling_price = [
        (v) => validatePrice(v, "Selling price"),
      ];
    }

    return validateForm(formData, validationRules);
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError(null);
    setErrors({});

    // Validate form
    const validationErrors = validateFormData();
    if (hasErrors(validationErrors)) {
      setErrors(validationErrors);
      return;
    }

    setLoading(true);

    try {
      const payload = {
        sku: formData.sku,
        name: formData.name,
        description: formData.description || null,
        item_type: formData.item_type,
        procurement_type: formData.procurement_type,
        stocking_policy: formData.stocking_policy,
        unit: formData.unit,
        standard_cost: formData.standard_cost
          ? parseFloat(formData.standard_cost)
          : null,
        selling_price: formData.selling_price
          ? parseFloat(formData.selling_price)
          : null,
        reorder_point: formData.stocking_policy === "stocked" && formData.reorder_point
          ? parseFloat(formData.reorder_point)
          : null,
        category_id: formData.category_id || null,
        image_url: formData.image_url || null,
      };

      const url = editingItem
        ? `${API_URL}/api/v1/items/${editingItem.id}`
        : `${API_URL}/api/v1/items`;

      const method = editingItem ? "PATCH" : "POST";

      const res = await fetch(url, {
        method,
        credentials: "include",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify(payload),
      });

      if (!res.ok) {
        const errorData = await res.json();
        throw new Error(errorData.detail || "Failed to save item");
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

  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      title={editingItem ? "Edit Item" : "Create New Item"}
      className="w-full max-w-2xl max-h-[90vh] overflow-y-auto"
      disableClose={loading}
    >
      <div className="p-6">
          <div className="flex justify-between items-center mb-6">
            <h2 className="text-2xl font-bold text-white">
              {editingItem ? "Edit Item" : "Create New Item"}
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

          <FormErrorSummary errors={errors} className="mb-4" />

          <form onSubmit={handleSubmit} className="space-y-4">
            {/* Basic Info */}
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label htmlFor="item-sku" className="block text-sm font-medium text-gray-300 mb-1">
                  SKU{" "}
                  <span className="text-gray-500 text-xs">
                    (auto-generated if empty)
                  </span>
                </label>
                <input
                  id="item-sku"
                  type="text"
                  value={formData.sku}
                  onChange={(e) =>
                    setFormData({
                      ...formData,
                      sku: e.target.value.toUpperCase(),
                    })
                  }
                  aria-invalid={!!errors.sku}
                  aria-describedby={errors.sku ? "item-sku-error" : undefined}
                  className={`w-full px-4 py-2 bg-gray-800 border rounded-lg text-white placeholder-gray-500 focus:outline-none ${
                    errors.sku
                      ? "border-red-500 focus:border-red-500"
                      : "border-gray-700 focus:border-blue-500"
                  }`}
                  placeholder="Leave empty for auto-generation"
                />
                {errors.sku && (
                  <p id="item-sku-error" role="alert" className="text-red-400 text-sm mt-1">{errors.sku}</p>
                )}
              </div>

              <div>
                <label htmlFor="item-unit" className="block text-sm font-medium text-gray-300 mb-1">
                  Unit <RequiredIndicator />
                </label>
                <select
                  id="item-unit"
                  value={formData.unit}
                  onChange={(e) =>
                    setFormData({ ...formData, unit: e.target.value })
                  }
                  aria-invalid={!!errors.unit}
                  aria-describedby={errors.unit ? "item-unit-error" : undefined}
                  className={`w-full px-4 py-2 bg-gray-800 border rounded-lg text-white focus:outline-none ${
                    errors.unit
                      ? "border-red-500 focus:border-red-500"
                      : "border-gray-700 focus:border-blue-500"
                  }`}
                >
                  {uomClasses.length > 0 ? (
                    uomClasses.map((cls) => (
                      <optgroup
                        key={cls.uom_class}
                        label={
                          cls.uom_class.charAt(0).toUpperCase() +
                          cls.uom_class.slice(1)
                        }
                      >
                        {cls.units.map((u) => (
                          <option key={u.code} value={u.code}>
                            {u.code} - {u.name}
                          </option>
                        ))}
                      </optgroup>
                    ))
                  ) : (
                    // Fallback if UOM API not available
                    <>
                      <option value="EA">EA - Each</option>
                      <option value="KG">KG - Kilogram</option>
                      <option value="G">G - Gram</option>
                      <option value="LB">LB - Pound</option>
                      <option value="M">M - Meter</option>
                      <option value="FT">FT - Foot</option>
                      <option value="HR">HR - Hour</option>
                    </>
                  )}
                </select>
                {errors.unit && (
                  <p id="item-unit-error" role="alert" className="text-red-400 text-sm mt-1">{errors.unit}</p>
                )}
              </div>
            </div>

            <div>
              <label htmlFor="item-name" className="block text-sm font-medium text-gray-300 mb-1">
                Name <RequiredIndicator />
              </label>
              <input
                id="item-name"
                type="text"
                value={formData.name}
                onChange={(e) =>
                  setFormData({ ...formData, name: e.target.value })
                }
                aria-invalid={!!errors.name}
                aria-describedby={errors.name ? "item-name-error" : undefined}
                className={`w-full px-4 py-2 bg-gray-800 border rounded-lg text-white placeholder-gray-500 focus:outline-none ${
                  errors.name
                    ? "border-red-500 focus:border-red-500"
                    : "border-gray-700 focus:border-blue-500"
                }`}
                placeholder="Item name"
              />
              {errors.name && (
                <p id="item-name-error" role="alert" className="text-red-400 text-sm mt-1">{errors.name}</p>
              )}
            </div>

            <div>
              <label htmlFor="item-description" className="block text-sm font-medium text-gray-300 mb-1">
                Description
              </label>
              <textarea
                id="item-description"
                value={formData.description}
                onChange={(e) =>
                  setFormData({ ...formData, description: e.target.value })
                }
                className="w-full px-4 py-2 bg-gray-800 border border-gray-700 rounded-lg text-white placeholder-gray-500 focus:border-blue-500 focus:outline-none"
                rows="3"
                placeholder="Item description"
              />
            </div>

            {/* Image URL / Upload */}
            <div>
              <label htmlFor="item-image-url" className="block text-sm font-medium text-gray-300 mb-1">
                Product Image
              </label>
              <div className="flex gap-3 items-start">
                <div className="flex-1">
                  <div className="flex gap-2">
                    <input
                      id="item-image-url"
                      type="text"
                      value={formData.image_url}
                      onChange={(e) =>
                        setFormData({ ...formData, image_url: e.target.value })
                      }
                      className="flex-1 px-4 py-2 bg-gray-800 border border-gray-700 rounded-lg text-white placeholder-gray-500 focus:border-blue-500 focus:outline-none"
                      placeholder="https://example.com/image.jpg"
                    />
                    <input
                      type="file"
                      ref={fileInputRef}
                      accept="image/jpeg,image/png,image/webp,image/gif,.jpg,.jpeg,.png,.webp,.gif"
                      className="hidden"
                      onChange={async (e) => {
                        const file = e.target.files?.[0];
                        if (!file) return;

                        // Validate file size (5MB max)
                        if (file.size > 5 * 1024 * 1024) {
                          setError("Image must be less than 5MB");
                          return;
                        }

                        setUploading(true);
                        setError(null);

                        try {
                          const uploadData = new FormData();
                          uploadData.append("file", file);

                          const res = await fetch(
                            `${API_URL}/api/v1/admin/uploads/product-image`,
                            {
                              method: "POST",
                              credentials: "include",
                              body: uploadData,
                            }
                          );

                          if (!res.ok) {
                            const err = await res.json();
                            throw new Error(err.detail || "Upload failed");
                          }

                          const data = await res.json();
                          // Always store the relative path — nginx/proxy handles routing
                          setFormData((prev) => ({ ...prev, image_url: data.url }));
                        } catch (err) {
                          setError("Image upload failed. Please try again or paste a URL instead.");
                        } finally {
                          setUploading(false);
                          // Reset file input
                          if (fileInputRef.current) {
                            fileInputRef.current.value = "";
                          }
                        }
                      }}
                    />
                    <button
                      type="button"
                      onClick={() => fileInputRef.current?.click()}
                      disabled={uploading}
                      className="px-4 py-2 bg-gray-700 border border-gray-600 rounded-lg text-gray-300 hover:bg-gray-600 disabled:opacity-50 whitespace-nowrap"
                    >
                      {uploading ? "Uploading..." : "Upload"}
                    </button>
                  </div>
                  <p className="text-xs text-gray-500 mt-1">
                    Paste a URL or upload an image (JPG, PNG, WebP, GIF - max 5MB)
                  </p>
                </div>
                {formData.image_url && (
                  <div className="flex-shrink-0">
                    <img
                      src={formData.image_url}
                      alt="Product preview"
                      className="h-16 w-16 object-cover rounded border border-gray-600"
                      onError={(e) => {
                        e.target.style.display = "none";
                      }}
                    />
                  </div>
                )}
              </div>
            </div>

            {/* Classification */}
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label htmlFor="item-type" className="block text-sm font-medium text-gray-300 mb-1">
                  Item Type <RequiredIndicator />
                </label>
                <select
                  id="item-type"
                  value={formData.item_type}
                  onChange={(e) =>
                    setFormData({ ...formData, item_type: e.target.value })
                  }
                  aria-invalid={!!errors.item_type}
                  aria-describedby={errors.item_type ? "item-type-error" : undefined}
                  className={`w-full px-4 py-2 bg-gray-800 border rounded-lg text-white focus:outline-none ${
                    errors.item_type
                      ? "border-red-500 focus:border-red-500"
                      : "border-gray-700 focus:border-blue-500"
                  }`}
                >
                  {ITEM_TYPES.map((type) => (
                    <option key={type.value} value={type.value}>
                      {type.label}
                    </option>
                  ))}
                </select>
                {formData.item_type === 'material' && (
                  <p className="text-xs text-blue-400 mt-1">
                    Materials use: Unit=G (grams), Purchase=KG (kilograms)
                  </p>
                )}
                {errors.item_type && (
                  <p id="item-type-error" role="alert" className="text-red-400 text-sm mt-1">
                    {errors.item_type}
                  </p>
                )}
              </div>

              <div>
                <label htmlFor="item-procurement-type" className="block text-sm font-medium text-gray-300 mb-1">
                  Procurement Type <RequiredIndicator />
                </label>
                <select
                  id="item-procurement-type"
                  value={formData.procurement_type}
                  onChange={(e) =>
                    setFormData({
                      ...formData,
                      procurement_type: e.target.value,
                    })
                  }
                  aria-invalid={!!errors.procurement_type}
                  aria-describedby={errors.procurement_type ? "item-procurement-type-error" : undefined}
                  className={`w-full px-4 py-2 bg-gray-800 border rounded-lg text-white focus:outline-none ${
                    errors.procurement_type
                      ? "border-red-500 focus:border-red-500"
                      : "border-gray-700 focus:border-blue-500"
                  }`}
                >
                  {PROCUREMENT_TYPES.map((type) => (
                    <option key={type.value} value={type.value}>
                      {type.label}
                    </option>
                  ))}
                </select>
                {errors.procurement_type && (
                  <p id="item-procurement-type-error" role="alert" className="text-red-400 text-sm mt-1">
                    {errors.procurement_type}
                  </p>
                )}
              </div>
            </div>

            {/* Stocking Policy */}
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label htmlFor="item-stocking-policy" className="block text-sm font-medium text-gray-300 mb-1">
                  Stocking Policy
                </label>
                <select
                  id="item-stocking-policy"
                  value={formData.stocking_policy}
                  onChange={(e) =>
                    setFormData({
                      ...formData,
                      stocking_policy: e.target.value,
                    })
                  }
                  className="w-full px-4 py-2 bg-gray-800 border border-gray-700 rounded-lg text-white focus:border-blue-500 focus:outline-none"
                >
                  {STOCKING_POLICIES.map((policy) => (
                    <option key={policy.value} value={policy.value}>
                      {policy.label}
                    </option>
                  ))}
                </select>
                <p className="text-xs text-gray-500 mt-1">
                  {formData.stocking_policy === "stocked"
                    ? "Item will show as low stock when below reorder point"
                    : "Item is only ordered when MRP shows demand"}
                </p>
              </div>

              {formData.stocking_policy === "stocked" && (
                <div>
                  <label htmlFor="item-reorder-point" className="block text-sm font-medium text-gray-300 mb-1">
                    Reorder Point
                  </label>
                  <input
                    id="item-reorder-point"
                    type="number"
                    step="1"
                    min="0"
                    value={formData.reorder_point}
                    onChange={(e) =>
                      setFormData({ ...formData, reorder_point: e.target.value })
                    }
                    className="w-full px-4 py-2 bg-gray-800 border border-gray-700 rounded-lg text-white placeholder-gray-500 focus:border-blue-500 focus:outline-none"
                    placeholder="Min quantity to keep on hand"
                  />
                </div>
              )}
            </div>

            <div>
              <label htmlFor="item-category" className="block text-sm font-medium text-gray-300 mb-1">
                Category
              </label>
              <select
                id="item-category"
                value={formData.category_id || ""}
                onChange={(e) =>
                  setFormData({
                    ...formData,
                    category_id: e.target.value
                      ? parseInt(e.target.value)
                      : null,
                  })
                }
                className="w-full px-4 py-2 bg-gray-800 border border-gray-700 rounded-lg text-white focus:border-blue-500 focus:outline-none"
              >
                <option value="">No category</option>
                {categories.map((cat) => (
                  <option key={cat.id} value={cat.id}>
                    {cat.name}
                  </option>
                ))}
              </select>
            </div>

            {/* Pricing */}
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label htmlFor="item-standard-cost" className="block text-sm font-medium text-gray-300 mb-1">
                  Standard Cost
                </label>
                <input
                  id="item-standard-cost"
                  type="number"
                  step="0.01"
                  value={formData.standard_cost}
                  onChange={(e) =>
                    setFormData({ ...formData, standard_cost: e.target.value })
                  }
                  aria-invalid={!!errors.standard_cost}
                  aria-describedby={errors.standard_cost ? "item-standard-cost-error" : undefined}
                  className={`w-full px-4 py-2 bg-gray-800 border rounded-lg text-white placeholder-gray-500 focus:outline-none ${
                    errors.standard_cost
                      ? "border-red-500 focus:border-red-500"
                      : "border-gray-700 focus:border-blue-500"
                  }`}
                  placeholder="0.00"
                />
                {errors.standard_cost && (
                  <p id="item-standard-cost-error" role="alert" className="text-red-400 text-sm mt-1">
                    {errors.standard_cost}
                  </p>
                )}
              </div>

              <div>
                <label htmlFor="item-selling-price" className="block text-sm font-medium text-gray-300 mb-1">
                  Selling Price
                </label>
                <input
                  id="item-selling-price"
                  type="number"
                  step="0.01"
                  value={formData.selling_price}
                  onChange={(e) =>
                    setFormData({ ...formData, selling_price: e.target.value })
                  }
                  aria-invalid={!!errors.selling_price}
                  aria-describedby={errors.selling_price ? "item-selling-price-error" : undefined}
                  className={`w-full px-4 py-2 bg-gray-800 border rounded-lg text-white placeholder-gray-500 focus:outline-none ${
                    errors.selling_price
                      ? "border-red-500 focus:border-red-500"
                      : "border-gray-700 focus:border-blue-500"
                  }`}
                  placeholder="0.00"
                />
                {errors.selling_price && (
                  <p id="item-selling-price-error" role="alert" className="text-red-400 text-sm mt-1">
                    {errors.selling_price}
                  </p>
                )}
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
                disabled={loading}
              >
                {loading
                  ? "Saving..."
                  : editingItem
                  ? "Update Item"
                  : "Create Item"}
              </button>
            </div>
          </form>

          {formData.procurement_type === "make" && (
            <div className="mt-4 p-3 bg-blue-500/10 border border-blue-500/30 rounded-xl text-sm text-blue-300">
              <strong>Note:</strong> This item requires a BOM and Routing.
              Create the item first, then add BOM and Routing from the item
              detail page.
            </div>
          )}
        </div>
    </Modal>
  );
}
