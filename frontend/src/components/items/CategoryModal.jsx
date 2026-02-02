/**
 * CategoryModal - Form for creating/editing item categories with validation.
 */
import { useState, useEffect } from "react";
import Modal from "../Modal";
import {
  validateRequired,
  validateLength,
  validateNumber,
} from "../../utils/validation";
import { RequiredIndicator } from "../ErrorMessage";

export default function CategoryModal({ category, categories, onSave, onClose }) {
  const [formData, setFormData] = useState({
    code: "",
    name: "",
    description: "",
    parent_id: null,
    sort_order: 0,
    is_active: true,
  });
  const [errors, setErrors] = useState({});
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (category) {
      setFormData({
        code: category.code || "",
        name: category.name || "",
        description: category.description || "",
        parent_id: category.parent_id || null,
        sort_order: category.sort_order || 0,
        is_active: category.is_active !== false,
      });
    } else {
      setFormData({
        code: "",
        name: "",
        description: "",
        parent_id: null,
        sort_order: 0,
        is_active: true,
      });
    }
    setErrors({});
  }, [category]);

  const validate = () => {
    const newErrors = {};
    const codeErr =
      validateRequired(formData.code, "Code") ||
      validateLength(formData.code, "Code", 1, 10);
    if (codeErr) newErrors.code = codeErr;

    const nameErr =
      validateRequired(formData.name, "Name") ||
      validateLength(formData.name, "Name", 1, 100);
    if (nameErr) newErrors.name = nameErr;

    if (formData.description) {
      const descErr = validateLength(
        formData.description,
        "Description",
        0,
        500
      );
      if (descErr) newErrors.description = descErr;
    }

    const sortErr = validateNumber(formData.sort_order, "Sort Order", { min: 0, max: 9999 });
    if (sortErr) newErrors.sort_order = sortErr;

    setErrors(newErrors);
    return Object.keys(newErrors).length === 0;
  };

  const handleSubmit = async () => {
    if (!validate()) return;
    setSaving(true);
    try {
      await onSave(formData);
    } finally {
      setSaving(false);
    }
  };

  // Filter categories to exclude self and children (for parent dropdown)
  const availableParents = categories.filter((c) => {
    if (category && c.id === category.id) return false;
    return c.is_active;
  });

  return (
    <Modal
      isOpen={true}
      onClose={onClose}
      title={category ? "Edit Category" : "New Category"}
      className="w-full max-w-md"
    >
      <div className="p-6 space-y-4">
        <div>
          <label className="block text-sm text-gray-400 mb-1">
            Code <RequiredIndicator />
          </label>
          <input
            type="text"
            value={formData.code}
            onChange={(e) =>
              setFormData({
                ...formData,
                code: e.target.value.toUpperCase(),
              })
            }
            className={`w-full bg-gray-800 border ${
              errors.code ? "border-red-500" : "border-gray-700"
            } rounded-lg px-4 py-2 text-white`}
            placeholder="e.g. FG, COMP, MAT"
            maxLength={10}
          />
          {errors.code && (
            <p className="text-red-400 text-xs mt-1">{errors.code}</p>
          )}
        </div>

        <div>
          <label className="block text-sm text-gray-400 mb-1">
            Name <RequiredIndicator />
          </label>
          <input
            type="text"
            value={formData.name}
            onChange={(e) =>
              setFormData({ ...formData, name: e.target.value })
            }
            className={`w-full bg-gray-800 border ${
              errors.name ? "border-red-500" : "border-gray-700"
            } rounded-lg px-4 py-2 text-white`}
            placeholder="Category name"
            maxLength={100}
          />
          {errors.name && (
            <p className="text-red-400 text-xs mt-1">{errors.name}</p>
          )}
        </div>

        <div>
          <label className="block text-sm text-gray-400 mb-1">
            Parent Category
          </label>
          <select
            value={formData.parent_id || ""}
            onChange={(e) =>
              setFormData({
                ...formData,
                parent_id: e.target.value
                  ? parseInt(e.target.value)
                  : null,
              })
            }
            className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-2 text-white"
          >
            <option value="">None (Top-level)</option>
            {availableParents.map((c) => (
              <option key={c.id} value={c.id}>
                {c.code} - {c.name}
              </option>
            ))}
          </select>
        </div>

        <div>
          <label className="block text-sm text-gray-400 mb-1">
            Description
          </label>
          <textarea
            value={formData.description}
            onChange={(e) =>
              setFormData({
                ...formData,
                description: e.target.value,
              })
            }
            className={`w-full bg-gray-800 border ${
              errors.description ? "border-red-500" : "border-gray-700"
            } rounded-lg px-4 py-2 text-white resize-none`}
            rows={3}
            maxLength={500}
          />
          {errors.description && (
            <p className="text-red-400 text-xs mt-1">
              {errors.description}
            </p>
          )}
        </div>

        <div className="flex gap-4">
          <div className="flex-1">
            <label className="block text-sm text-gray-400 mb-1">
              Sort Order
            </label>
            <input
              type="number"
              value={formData.sort_order}
              onChange={(e) =>
                setFormData({
                  ...formData,
                  sort_order: parseInt(e.target.value) || 0,
                })
              }
              className={`w-full bg-gray-800 border ${
                errors.sort_order ? "border-red-500" : "border-gray-700"
              } rounded-lg px-4 py-2 text-white`}
              min={0}
              max={9999}
            />
            {errors.sort_order && (
              <p className="text-red-400 text-xs mt-1">
                {errors.sort_order}
              </p>
            )}
          </div>
          <div className="flex items-end pb-2">
            <label className="flex items-center gap-2 text-gray-400">
              <input
                type="checkbox"
                checked={formData.is_active}
                onChange={(e) =>
                  setFormData({
                    ...formData,
                    is_active: e.target.checked,
                  })
                }
                className="rounded"
              />
              Active
            </label>
          </div>
        </div>

        <div className="flex gap-3 pt-2">
          <button
            onClick={onClose}
            className="flex-1 px-4 py-2 bg-gray-700 text-white rounded-lg hover:bg-gray-600"
          >
            Cancel
          </button>
          <button
            onClick={handleSubmit}
            disabled={saving}
            className="flex-1 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-500 disabled:opacity-50"
          >
            {saving
              ? "Saving..."
              : category
              ? "Update Category"
              : "Create Category"}
          </button>
        </div>
      </div>
    </Modal>
  );
}
