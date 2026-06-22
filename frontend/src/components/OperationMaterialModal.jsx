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
  operation: _operation = null, // Operation context (for title/label)
  defaultTypeFilter = 'all', // Smart default computed by parent from operation name
  material = null,           // If provided, editing existing material
  onSave,
}) {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [products, setProducts] = useState([]);
  const [searchTerm, setSearchTerm] = useState('');
  const [typeFilter, setTypeFilter] = useState('all');

  // Form state — field names match backend RoutingOperationMaterialCreate schema
  const [formData, setFormData] = useState({
    component_id: '',
    quantity: 1,
    quantity_per: 'unit', // QuantityPer enum: unit, batch, order
    unit: 'EA',
    scrap_factor: 0,
    is_cost_only: false,
    is_optional: false,
    is_variable: false,
    notes: '',
  });

  const isEditing = !!material;

  // Reset / populate form whenever the modal opens or the target material changes
  useEffect(() => {
    if (!isOpen) return;
    if (material) {
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setFormData({
        component_id: material.component_id || '',
        quantity: material.quantity || 1,
        quantity_per: material.quantity_per || 'unit',
        unit: material.unit || 'EA',
        scrap_factor: material.scrap_factor || 0,
        is_cost_only: material.is_cost_only || false,
        is_optional: material.is_optional || false,
        is_variable: material.is_variable ?? false,
        notes: material.notes || '',
      });
      // Show all types when editing so the selected component is always visible
      setTypeFilter('all');
    } else {
      setFormData({
        component_id: '',
        quantity: 1,
        quantity_per: 'unit',
        unit: 'EA',
        scrap_factor: 0,
        is_cost_only: false,
        is_optional: false,
        is_variable: false,
        notes: '',
      });
      setSearchTerm('');
      setTypeFilter(defaultTypeFilter);
    }
  }, [isOpen, material, defaultTypeFilter]);

  // Fetch products for component selection
  useEffect(() => {
    if (!isOpen) return;

    const fetchProducts = async () => {
      try {
        const params = new URLSearchParams({
          offset: '0',
          limit: '500',
          active_only: 'true',
          exclude_variants: 'true',
        });
        if (searchTerm) {
          params.append('search', searchTerm);
        }

        const res = await fetch(`${API_URL}/api/v1/items?${params}`, {
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

    if (formData.quantity <= 0) {
      setError('Quantity must be greater than 0');
      return;
    }

    setError(null);

    try {
      const payload = {
        component_id: parseInt(formData.component_id),
        quantity: parseFloat(formData.quantity),
        quantity_per: formData.quantity_per,
        unit: formData.unit,
        scrap_factor: parseFloat(formData.scrap_factor) || 0,
        is_cost_only: formData.is_cost_only,
        is_optional: formData.is_optional,
        is_variable: formData.is_variable,
        notes: formData.notes || null,
      };

      // Wizard/local mode: no operationId yet — return the material to the parent
      // instead of POSTing. Include the picked product's sku/name for display.
      if (!operationId) {
        const sp = products.find((p) => p.id === parseInt(formData.component_id));
        onSave?.({ ...payload, component_sku: sp?.sku, component_name: sp?.name });
        onClose();
        return;
      }

      // Network path only — wizard mode returns above without touching loading
      setLoading(true);
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

  const TYPE_LABELS = {
    finished_good: 'FG',
    component: 'COMP',
    material: 'MAT',
    supply: 'SUPPLY',
  };

  const filteredProducts = typeFilter === 'all'
    ? products
    : products.filter((p) => p.item_type === typeFilter);

  const availableTypes = [...new Set(products.map((p) => p.item_type).filter(Boolean))];

  // Context-aware label: "Add Component" for assemblies, "Add Material" default
  const addLabel = defaultTypeFilter === 'component' ? 'Component'
    : defaultTypeFilter === 'supply' ? 'Supply'
    : 'Material';
  const modalTitle = isEditing ? `Edit ${addLabel}` : `Add ${addLabel}`;

  return (
    <Modal isOpen={isOpen} onClose={onClose} title={modalTitle} disableClose={loading} className="w-full max-w-lg">
        <div className="p-6">
          {/* Header */}
          <div className="flex justify-between items-center mb-6">
            <h2 className="text-xl font-bold text-white">
              {modalTitle}
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
              {/* Type filter chips */}
              <div className="flex flex-wrap gap-1 mb-2">
                <button
                  type="button"
                  onClick={() => setTypeFilter('all')}
                  className={`px-2 py-0.5 rounded text-xs font-medium transition-colors ${typeFilter === 'all' ? 'bg-blue-600 text-white' : 'bg-gray-700 text-gray-400 hover:bg-gray-600'}`}
                >
                  All
                </button>
                {availableTypes.map((t) => (
                  <button
                    key={t}
                    type="button"
                    onClick={() => setTypeFilter(t)}
                    className={`px-2 py-0.5 rounded text-xs font-medium transition-colors ${typeFilter === t ? 'bg-blue-600 text-white' : 'bg-gray-700 text-gray-400 hover:bg-gray-600'}`}
                  >
                    {TYPE_LABELS[t] || t}
                  </button>
                ))}
              </div>
              <input
                type="text"
                placeholder="Search by SKU or name..."
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
                    unit: product?.unit || 'EA',
                  });
                }}
                className="w-full bg-gray-800 border border-gray-700 rounded px-3 py-2 text-white"
              >
                <option value="">Select component...</option>
                {filteredProducts.map((p) => (
                  <option key={p.id} value={p.id}>
                    [{TYPE_LABELS[p.item_type] || p.item_type || '?'}] {p.sku} — {p.name}
                  </option>
                ))}
              </select>
              {selectedProduct && (
                <p className="text-xs text-gray-500 mt-1">
                  Type: {selectedProduct.item_type} | Unit: {selectedProduct.unit}
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
                  value={formData.quantity}
                  onChange={(e) => setFormData({ ...formData, quantity: e.target.value })}
                  className="w-full bg-gray-800 border border-gray-700 rounded px-3 py-2 text-white"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-300 mb-2">
                  Per
                </label>
                <select
                  value={formData.quantity_per}
                  onChange={(e) => setFormData({ ...formData, quantity_per: e.target.value })}
                  className="w-full bg-gray-800 border border-gray-700 rounded px-3 py-2 text-white"
                >
                  <option value="unit">Per Unit</option>
                  <option value="batch">Per Batch</option>
                  <option value="order">Per Order</option>
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
                  value={formData.scrap_factor}
                  onChange={(e) => setFormData({ ...formData, scrap_factor: e.target.value })}
                  className="w-full bg-gray-800 border border-gray-700 rounded px-3 py-2 text-white"
                />
              </div>
            </div>

            {/* Options */}
            <div className="flex flex-wrap gap-6">
              <label className="flex items-center gap-2 cursor-pointer">
                <input
                  type="checkbox"
                  checked={formData.is_cost_only}
                  onChange={(e) => setFormData({ ...formData, is_cost_only: e.target.checked })}
                  className="w-4 h-4 rounded bg-gray-700 border-gray-600 text-blue-500"
                />
                <span className="text-sm text-gray-300">Cost Only</span>
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
              <label className="flex items-center gap-2 cursor-pointer">
                <input
                  type="checkbox"
                  checked={formData.is_variable}
                  onChange={(e) => setFormData({ ...formData, is_variable: e.target.checked })}
                  className="rounded border-gray-600 bg-gray-800 text-blue-500 focus:ring-blue-500"
                />
                <span className="text-sm text-gray-300">Variable</span>
                <span className="text-xs text-gray-500">(swap this material per variant)</span>
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
                {loading ? 'Saving...' : isEditing ? 'Update' : `Add ${addLabel}`}
              </button>
            </div>
          </div>
        </div>
    </Modal>
  );
}
