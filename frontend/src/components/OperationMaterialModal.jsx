/**
 * OperationMaterialModal - Add/Edit material for a routing operation
 *
 * Allows adding components to an operation's bill of materials.
 */
import { useState, useEffect } from 'react';
import { API_URL } from '../config/api';
import Modal from './Modal';

export default function OperationMaterialModal({
  isOpen,
  onClose,
  operationId,
  material = null, // If provided, editing existing material
  onSave,
}) {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [products, setProducts] = useState([]);
  const [searchTerm, setSearchTerm] = useState('');

  // Form state
  const [formData, setFormData] = useState({
    component_id: '',
    quantity_per: 1,
    quantity_type: 'per_unit', // per_unit, per_batch, per_order
    unit: 'EA',
    scrap_factor_percent: 0,
    is_critical: true,
    is_optional: false,
    notes: '',
  });

  const isEditing = !!material;

  // Load material data when editing
  useEffect(() => {
    if (material) {
      setFormData({
        component_id: material.component_id || '',
        quantity_per: material.quantity_per || 1,
        quantity_type: material.quantity_type || 'per_unit',
        unit: material.unit || 'EA',
        scrap_factor_percent: material.scrap_factor_percent || 0,
        is_critical: material.is_critical !== false,
        is_optional: material.is_optional || false,
        notes: material.notes || '',
      });
    } else {
      // Reset form for new material
      setFormData({
        component_id: '',
        quantity_per: 1,
        quantity_type: 'per_unit',
        unit: 'EA',
        scrap_factor_percent: 0,
        is_critical: true,
        is_optional: false,
        notes: '',
      });
    }
  }, [material, isOpen]);

  // Fetch products for component selection
  useEffect(() => {
    if (!isOpen) return;

    const fetchProducts = async () => {
      try {
        const params = new URLSearchParams({
          skip: '0',
          limit: '100',
          active_only: 'true',
        });
        if (searchTerm) {
          params.append('search', searchTerm);
        }

        const res = await fetch(`${API_URL}/api/v1/products?${params}`, {
          credentials: "include",
        });
        if (res.ok) {
          const data = await res.json();
          setProducts(data.items || data || []);
        }
      } catch (err) {
        console.error('Error fetching products:', err);
      }
    };

    const timer = setTimeout(fetchProducts, 300);
    return () => clearTimeout(timer);
  }, [isOpen, searchTerm]);

  const handleSubmit = async () => {
    if (!formData.component_id) {
      setError('Please select a component');
      return;
    }

    if (formData.quantity_per <= 0) {
      setError('Quantity must be greater than 0');
      return;
    }

    setLoading(true);
    setError(null);

    try {
      const payload = {
        component_id: parseInt(formData.component_id),
        quantity_per: parseFloat(formData.quantity_per),
        quantity_type: formData.quantity_type,
        unit: formData.unit,
        scrap_factor_percent: parseFloat(formData.scrap_factor_percent) || 0,
        is_critical: formData.is_critical,
        is_optional: formData.is_optional,
        notes: formData.notes || null,
      };

      let res;
      if (isEditing) {
        // Update existing material
        res = await fetch(`${API_URL}/api/v1/routings/materials/${material.id}`, {
          method: 'PUT',
          credentials: "include",
          headers: {
            'Content-Type': 'application/json',
          },
          body: JSON.stringify(payload),
        });
      } else {
        // Add new material
        res = await fetch(`${API_URL}/api/v1/routings/operations/${operationId}/materials`, {
          method: 'POST',
          credentials: "include",
          headers: {
            'Content-Type': 'application/json',
          },
          body: JSON.stringify(payload),
        });
      }

      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || 'Failed to save material');
      }

      const data = await res.json();
      onSave?.(data);
      onClose();
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const handleDelete = async () => {
    if (!material?.id) return;

    if (!window.confirm('Remove this material from the operation?')) {
      return;
    }

    setLoading(true);
    setError(null);

    try {
      const res = await fetch(`${API_URL}/api/v1/routings/materials/${material.id}`, {
        method: 'DELETE',
        credentials: "include",
      });

      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || 'Failed to delete material');
      }

      onSave?.(null); // Signal deletion
      onClose();
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const selectedProduct = products.find((p) => p.id === parseInt(formData.component_id));

  return (
    <Modal isOpen={isOpen} onClose={onClose} title={isEditing ? 'Edit Material' : 'Add Material'} disableClose={loading} className="w-full max-w-lg">
        <div className="p-6">
          {/* Header */}
          <div className="flex justify-between items-center mb-6">
            <h2 className="text-xl font-bold text-white">
              {isEditing ? 'Edit Material' : 'Add Material'}
            </h2>
            <button
              onClick={onClose}
              className="text-gray-400 hover:text-white"
            >
              <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          </div>

          {/* Error */}
          {error && (
            <div className="mb-4 p-3 bg-red-500/10 border border-red-500/30 text-red-400 rounded text-sm">
              {error}
            </div>
          )}

          {/* Form */}
          <div className="space-y-4">
            {/* Component Selection */}
            <div>
              <label className="block text-sm font-medium text-gray-300 mb-2">
                Component *
              </label>
              <input
                type="text"
                placeholder="Search products..."
                value={searchTerm}
                onChange={(e) => setSearchTerm(e.target.value)}
                className="w-full bg-gray-800 border border-gray-700 rounded px-3 py-2 text-white mb-2"
              />
              <select
                value={formData.component_id}
                onChange={(e) => {
                  const product = products.find((p) => p.id === parseInt(e.target.value));
                  setFormData({
                    ...formData,
                    component_id: e.target.value,
                    unit: product?.unit_of_measure || 'EA',
                  });
                }}
                className="w-full bg-gray-800 border border-gray-700 rounded px-3 py-2 text-white"
              >
                <option value="">Select component...</option>
                {products.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.sku} - {p.name}
                  </option>
                ))}
              </select>
              {selectedProduct && (
                <p className="text-xs text-gray-500 mt-1">
                  Type: {selectedProduct.product_type} | Unit: {selectedProduct.unit_of_measure}
                </p>
              )}
            </div>

            {/* Quantity */}
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-sm font-medium text-gray-300 mb-2">
                  Quantity *
                </label>
                <input
                  type="number"
                  step="0.001"
                  min="0"
                  value={formData.quantity_per}
                  onChange={(e) => setFormData({ ...formData, quantity_per: e.target.value })}
                  className="w-full bg-gray-800 border border-gray-700 rounded px-3 py-2 text-white"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-300 mb-2">
                  Per
                </label>
                <select
                  value={formData.quantity_type}
                  onChange={(e) => setFormData({ ...formData, quantity_type: e.target.value })}
                  className="w-full bg-gray-800 border border-gray-700 rounded px-3 py-2 text-white"
                >
                  <option value="per_unit">Per Unit</option>
                  <option value="per_batch">Per Batch</option>
                  <option value="per_order">Per Order</option>
                </select>
              </div>
            </div>

            {/* Unit and Scrap Factor */}
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-sm font-medium text-gray-300 mb-2">
                  Unit
                </label>
                <input
                  type="text"
                  value={formData.unit}
                  onChange={(e) => setFormData({ ...formData, unit: e.target.value })}
                  className="w-full bg-gray-800 border border-gray-700 rounded px-3 py-2 text-white"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-300 mb-2">
                  Scrap Factor %
                </label>
                <input
                  type="number"
                  step="0.1"
                  min="0"
                  max="100"
                  value={formData.scrap_factor_percent}
                  onChange={(e) => setFormData({ ...formData, scrap_factor_percent: e.target.value })}
                  className="w-full bg-gray-800 border border-gray-700 rounded px-3 py-2 text-white"
                />
              </div>
            </div>

            {/* Options */}
            <div className="flex gap-6">
              <label className="flex items-center gap-2 cursor-pointer">
                <input
                  type="checkbox"
                  checked={formData.is_critical}
                  onChange={(e) => setFormData({ ...formData, is_critical: e.target.checked })}
                  className="w-4 h-4 rounded bg-gray-700 border-gray-600 text-blue-500"
                />
                <span className="text-sm text-gray-300">Critical</span>
              </label>
              <label className="flex items-center gap-2 cursor-pointer">
                <input
                  type="checkbox"
                  checked={formData.is_optional}
                  onChange={(e) => setFormData({ ...formData, is_optional: e.target.checked })}
                  className="w-4 h-4 rounded bg-gray-700 border-gray-600 text-blue-500"
                />
                <span className="text-sm text-gray-300">Optional</span>
              </label>
            </div>

            {/* Notes */}
            <div>
              <label className="block text-sm font-medium text-gray-300 mb-2">
                Notes
              </label>
              <textarea
                value={formData.notes}
                onChange={(e) => setFormData({ ...formData, notes: e.target.value })}
                className="w-full bg-gray-800 border border-gray-700 rounded px-3 py-2 text-white h-16 resize-none"
                placeholder="Optional notes about this material..."
              />
            </div>
          </div>

          {/* Actions */}
          <div className="flex justify-between mt-6 pt-4 border-t border-gray-700">
            <div>
              {isEditing && (
                <button
                  onClick={handleDelete}
                  disabled={loading}
                  className="px-4 py-2 text-red-400 hover:text-red-300 disabled:opacity-50"
                >
                  Delete
                </button>
              )}
            </div>
            <div className="flex gap-3">
              <button
                onClick={onClose}
                className="px-4 py-2 bg-gray-700 text-white rounded hover:bg-gray-600"
                disabled={loading}
              >
                Cancel
              </button>
              <button
                onClick={handleSubmit}
                disabled={loading || !formData.component_id}
                className="px-4 py-2 bg-blue-600 text-white rounded hover:bg-blue-700 disabled:opacity-50"
              >
                {loading ? 'Saving...' : isEditing ? 'Update' : 'Add Material'}
              </button>
            </div>
          </div>
        </div>
    </Modal>
  );
}
