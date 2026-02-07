/**
 * ManufacturingBOMEditor - View and edit manufacturing BOM (routing + materials)
 *
 * Shows the complete manufacturing process for a product:
 * - Operations in a collapsible tree
 * - Materials nested under each operation
 * - Cost rollups (labor, material, total)
 */
import { useState, useEffect, useCallback } from "react";
import { API_URL } from "../config/api";
import { useToast } from "./Toast";
import Modal from "./Modal";

// Quantity Per options
const QUANTITY_PER_OPTIONS = [
  { value: "unit", label: "Per Unit", description: "Multiply by order quantity" },
  { value: "batch", label: "Per Batch", description: "Fixed per production batch" },
  { value: "order", label: "Per Order", description: "Fixed per production order" },
];

export default function ManufacturingBOMEditor({
  isOpen,
  onClose,
  productId,
  onSuccess,
}) {
  const toast = useToast();
  
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);
  const [bom, setBom] = useState(null);
  const [expandedOps, setExpandedOps] = useState({});
  const [components, setComponents] = useState([]);
  
  // Add/Edit material modal state
  const [showMaterialModal, setShowMaterialModal] = useState(false);
  const [editingMaterial, setEditingMaterial] = useState(null);
  const [selectedOperationId, setSelectedOperationId] = useState(null);
  const [materialForm, setMaterialForm] = useState({
    component_id: "",
    quantity: "",
    quantity_per: "unit",
    unit: "EA",
    scrap_factor: "0",
    is_cost_only: false,
    is_optional: false,
    notes: "",
  });

  // Fetch Manufacturing BOM
  const fetchBOM = useCallback(async () => {
    if (!productId) return;
    
    setLoading(true);
    setError(null);
    
    try {
      const res = await fetch(
        `${API_URL}/api/v1/routings/manufacturing-bom/${productId}`,
        { credentials: "include" }
      );
      
      if (res.status === 404) {
        setError("No routing found for this product. Create a routing first.");
        setBom(null);
        return;
      }
      
      if (!res.ok) throw new Error("Failed to fetch manufacturing BOM");
      
      const data = await res.json();
      setBom(data);
      
      // Auto-expand all operations initially
      const expanded = {};
      data.operations?.forEach(op => {
        expanded[op.id] = true;
      });
      setExpandedOps(expanded);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, [productId]);

  // Fetch components (for material selection)
  const fetchComponents = useCallback(async () => {
    try {
      const res = await fetch(
        `${API_URL}/api/v1/products?item_type=component,supply&limit=500`,
        { credentials: "include" }
      );
      if (res.ok) {
        const data = await res.json();
        setComponents(Array.isArray(data) ? data : (data.items || data.products || []));
      }
    } catch {
      // Non-critical - component selector will be empty
    }
  }, []);

  useEffect(() => {
    if (isOpen && productId) {
      fetchBOM();
      fetchComponents();
    }
  }, [isOpen, productId, fetchBOM, fetchComponents]);

  // Toggle operation expansion
  const toggleOperation = (opId) => {
    setExpandedOps(prev => ({
      ...prev,
      [opId]: !prev[opId]
    }));
  };

  // Open add material modal
  const handleAddMaterial = (operationId) => {
    setSelectedOperationId(operationId);
    setEditingMaterial(null);
    setMaterialForm({
      component_id: "",
      quantity: "",
      quantity_per: "unit",
      unit: "EA",
      scrap_factor: "0",
      is_cost_only: false,
      is_optional: false,
      notes: "",
    });
    setShowMaterialModal(true);
  };

  // Open edit material modal
  const handleEditMaterial = (material, operationId) => {
    setSelectedOperationId(operationId);
    setEditingMaterial(material);
    setMaterialForm({
      component_id: String(material.component_id),
      quantity: String(material.quantity),
      quantity_per: material.quantity_per,
      unit: material.unit,
      scrap_factor: String(material.scrap_factor || "0"),
      is_cost_only: material.is_cost_only,
      is_optional: material.is_optional,
      notes: material.notes || "",
    });
    setShowMaterialModal(true);
  };

  // Save material (create or update)
  const handleSaveMaterial = async () => {
    if (!materialForm.component_id || !materialForm.quantity) {
      toast.error("Component and quantity are required");
      return;
    }

    setSaving(true);
    try {
      const payload = {
        component_id: parseInt(materialForm.component_id),
        quantity: parseFloat(materialForm.quantity),
        quantity_per: materialForm.quantity_per,
        unit: materialForm.unit,
        scrap_factor: parseFloat(materialForm.scrap_factor) || 0,
        is_cost_only: materialForm.is_cost_only,
        is_optional: materialForm.is_optional,
        notes: materialForm.notes || null,
      };

      let res;
      if (editingMaterial) {
        // Update existing
        res = await fetch(
          `${API_URL}/api/v1/routings/materials/${editingMaterial.id}`,
          {
            method: "PUT",
            credentials: "include",
            headers: {
              "Content-Type": "application/json",
            },
            body: JSON.stringify(payload),
          }
        );
      } else {
        // Create new
        res = await fetch(
          `${API_URL}/api/v1/routings/operations/${selectedOperationId}/materials`,
          {
            method: "POST",
            credentials: "include",
            headers: {
              "Content-Type": "application/json",
            },
            body: JSON.stringify(payload),
          }
        );
      }

      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || "Failed to save material");
      }

      toast.success(editingMaterial ? "Material updated" : "Material added");
      setShowMaterialModal(false);
      fetchBOM(); // Refresh
      onSuccess?.();
    } catch (err) {
      toast.error(err.message);
    } finally {
      setSaving(false);
    }
  };

  // Delete material
  const handleDeleteMaterial = async (materialId) => {
    if (!confirm("Delete this material from the operation?")) return;

    try {
      const res = await fetch(
        `${API_URL}/api/v1/routings/materials/${materialId}`,
        {
          method: "DELETE",
          credentials: "include",
        }
      );

      if (!res.ok) throw new Error("Failed to delete material");

      toast.success("Material deleted");
      fetchBOM(); // Refresh
      onSuccess?.();
    } catch (err) {
      toast.error(err.message);
    }
  };

  // Format currency
  const formatCurrency = (value) => {
    const num = parseFloat(value) || 0;
    return `$${num.toFixed(2)}`;
  };

  // Format time
  const formatTime = (minutes) => {
    const mins = parseFloat(minutes) || 0;
    if (mins < 60) return `${mins.toFixed(1)} min`;
    const hours = Math.floor(mins / 60);
    const remainingMins = mins % 60;
    return `${hours}h ${remainingMins.toFixed(0)}m`;
  };

  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      title="Manufacturing BOM"
      className="w-full max-w-6xl max-h-[90vh] overflow-hidden flex flex-col"
    >
        {/* Header */}
        <div className="p-6 border-b border-gray-700 flex justify-between items-center">
          <div>
            <h2 className="text-2xl font-bold text-white">Manufacturing BOM</h2>
            {bom && (
              <p className="text-gray-400 mt-1">
                {bom.product_sku} - {bom.product_name}
              </p>
            )}
          </div>
          <button
            onClick={onClose}
            className="text-gray-400 hover:text-white"
          >
            <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        {/* Content */}
        <div className="flex-1 overflow-y-auto p-6">
          {loading ? (
            <div className="flex items-center justify-center py-12">
              <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-500"></div>
              <span className="ml-3 text-gray-400">Loading...</span>
            </div>
          ) : error ? (
            <div className="text-center py-12">
              <div className="text-red-400 mb-4">{error}</div>
              <button
                onClick={onClose}
                className="px-4 py-2 bg-gray-700 text-white rounded hover:bg-gray-600"
              >
                Close
              </button>
            </div>
          ) : bom ? (
            <>
              {/* Routing Info */}
              <div className="mb-6 p-4 bg-gray-800 rounded-lg border border-gray-700">
                <div className="grid grid-cols-4 gap-4 text-sm">
                  <div>
                    <span className="text-gray-400">Routing:</span>
                    <span className="ml-2 text-white font-medium">{bom.routing_code}</span>
                  </div>
                  <div>
                    <span className="text-gray-400">Version:</span>
                    <span className="ml-2 text-white">{bom.version}.{bom.revision}</span>
                  </div>
                  <div>
                    <span className="text-gray-400">Operations:</span>
                    <span className="ml-2 text-white">{bom.operations?.length || 0}</span>
                  </div>
                  <div>
                    <span className={`px-2 py-1 rounded text-xs ${bom.is_active ? 'bg-green-500/20 text-green-400' : 'bg-red-500/20 text-red-400'}`}>
                      {bom.is_active ? 'Active' : 'Inactive'}
                    </span>
                  </div>
                </div>
              </div>

              {/* Operations Tree */}
              <div className="space-y-2">
                {bom.operations?.map((op) => (
                  <div key={op.id} className="border border-gray-700 rounded-lg overflow-hidden">
                    {/* Operation Header */}
                    <div
                      className="flex items-center justify-between p-4 bg-gray-800 cursor-pointer hover:bg-gray-750"
                      onClick={() => toggleOperation(op.id)}
                    >
                      <div className="flex items-center gap-3">
                        <button className="text-gray-400">
                          <svg
                            className={`w-5 h-5 transition-transform ${expandedOps[op.id] ? 'rotate-90' : ''}`}
                            fill="none"
                            stroke="currentColor"
                            viewBox="0 0 24 24"
                          >
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
                          </svg>
                        </button>
                        <div>
                          <div className="flex items-center gap-2">
                            <span className="text-gray-400 font-mono text-sm">
                              {op.sequence.toString().padStart(2, '0')}
                            </span>
                            <span className="text-white font-medium">
                              {op.operation_name || op.operation_code || `Operation ${op.sequence}`}
                            </span>
                            {op.operation_code && op.operation_name && (
                              <span className="text-gray-500 text-sm">({op.operation_code})</span>
                            )}
                          </div>
                          <div className="text-sm text-gray-400">
                            {op.work_center_name} • {formatTime(op.total_time_minutes)}
                          </div>
                        </div>
                      </div>
                      <div className="flex items-center gap-6 text-sm">
                        <div className="text-right">
                          <div className="text-gray-400">Labor</div>
                          <div className="text-white">{formatCurrency(op.calculated_cost)}</div>
                        </div>
                        <div className="text-right">
                          <div className="text-gray-400">Material</div>
                          <div className="text-white">{formatCurrency(op.material_cost)}</div>
                        </div>
                        <div className="text-right">
                          <div className="text-gray-400">Total</div>
                          <div className="text-white font-medium">{formatCurrency(op.total_cost_with_materials)}</div>
                        </div>
                        <div className="text-gray-500">
                          {op.materials?.length || 0} materials
                        </div>
                      </div>
                    </div>

                    {/* Materials (expanded) */}
                    {expandedOps[op.id] && (
                      <div className="bg-gray-900 border-t border-gray-700">
                        {op.materials?.length > 0 ? (
                          <table className="w-full text-sm">
                            <thead>
                              <tr className="bg-gray-800/50 border-b border-gray-700">
                                <th className="text-left p-3 text-gray-400 font-medium">Component</th>
                                <th className="text-right p-3 text-gray-400 font-medium">Qty</th>
                                <th className="text-center p-3 text-gray-400 font-medium">Per</th>
                                <th className="text-right p-3 text-gray-400 font-medium">Scrap %</th>
                                <th className="text-right p-3 text-gray-400 font-medium">Unit Cost</th>
                                <th className="text-right p-3 text-gray-400 font-medium">Extended</th>
                                <th className="text-center p-3 text-gray-400 font-medium">Flags</th>
                                <th className="text-center p-3 text-gray-400 font-medium">Actions</th>
                              </tr>
                            </thead>
                            <tbody>
                              {op.materials.map((mat) => (
                                <tr key={mat.id} className="border-b border-gray-800 hover:bg-gray-800/30">
                                  <td className="p-3">
                                    <div className="text-white">{mat.component_name}</div>
                                    <div className="text-gray-500 text-xs">{mat.component_sku}</div>
                                  </td>
                                  <td className="p-3 text-right text-white">
                                    {parseFloat(mat.quantity).toFixed(2)} {mat.unit}
                                  </td>
                                  <td className="p-3 text-center">
                                    <span className={`px-2 py-1 rounded text-xs ${
                                      mat.quantity_per === 'unit' ? 'bg-blue-500/20 text-blue-400' :
                                      mat.quantity_per === 'batch' ? 'bg-purple-500/20 text-purple-400' :
                                      'bg-orange-500/20 text-orange-400'
                                    }`}>
                                      {mat.quantity_per}
                                    </span>
                                  </td>
                                  <td className="p-3 text-right text-white">
                                    {parseFloat(mat.scrap_factor || 0).toFixed(1)}%
                                  </td>
                                  <td className="p-3 text-right text-white">
                                    {formatCurrency(mat.unit_cost)}
                                  </td>
                                  <td className="p-3 text-right text-white font-medium">
                                    {formatCurrency(mat.extended_cost)}
                                  </td>
                                  <td className="p-3 text-center">
                                    {mat.is_cost_only && (
                                      <span className="px-2 py-1 bg-yellow-500/20 text-yellow-400 text-xs rounded mr-1" title="Cost only - no inventory consumption">
                                        $
                                      </span>
                                    )}
                                    {mat.is_optional && (
                                      <span className="px-2 py-1 bg-gray-500/20 text-gray-400 text-xs rounded" title="Optional material">
                                        ?
                                      </span>
                                    )}
                                  </td>
                                  <td className="p-3 text-center">
                                    <button
                                      onClick={(e) => {
                                        e.stopPropagation();
                                        handleEditMaterial(mat, op.id);
                                      }}
                                      className="text-blue-400 hover:text-blue-300 mr-2"
                                    >
                                      Edit
                                    </button>
                                    <button
                                      onClick={(e) => {
                                        e.stopPropagation();
                                        handleDeleteMaterial(mat.id);
                                      }}
                                      className="text-red-400 hover:text-red-300"
                                    >
                                      Delete
                                    </button>
                                  </td>
                                </tr>
                              ))}
                            </tbody>
                          </table>
                        ) : (
                          <div className="p-4 text-center text-gray-500">
                            No materials assigned to this operation
                          </div>
                        )}
                        
                        {/* Add Material Button */}
                        <div className="p-3 border-t border-gray-800">
                          <button
                            onClick={(e) => {
                              e.stopPropagation();
                              handleAddMaterial(op.id);
                            }}
                            className="text-sm text-blue-400 hover:text-blue-300 flex items-center gap-1"
                          >
                            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
                            </svg>
                            Add Material
                          </button>
                        </div>
                      </div>
                    )}
                  </div>
                ))}
              </div>

              {/* Cost Summary */}
              <div className="mt-6 p-4 bg-gray-800 rounded-lg border border-gray-700">
                <h3 className="text-lg font-semibold text-white mb-3">Cost Summary</h3>
                <div className="grid grid-cols-3 gap-4">
                  <div className="p-3 bg-gray-900 rounded">
                    <div className="text-gray-400 text-sm">Total Labor Cost</div>
                    <div className="text-xl font-bold text-white">{formatCurrency(bom.total_labor_cost)}</div>
                  </div>
                  <div className="p-3 bg-gray-900 rounded">
                    <div className="text-gray-400 text-sm">Total Material Cost</div>
                    <div className="text-xl font-bold text-white">{formatCurrency(bom.total_material_cost)}</div>
                  </div>
                  <div className="p-3 bg-blue-900/30 rounded border border-blue-500/30">
                    <div className="text-blue-400 text-sm">Total Manufacturing Cost</div>
                    <div className="text-xl font-bold text-blue-300">{formatCurrency(bom.total_cost)}</div>
                  </div>
                </div>
              </div>
            </>
          ) : null}
        </div>

        {/* Footer */}
        <div className="p-4 border-t border-gray-700 flex justify-end">
          <button
            onClick={onClose}
            className="px-4 py-2 bg-gray-700 text-white rounded hover:bg-gray-600"
          >
            Close
          </button>
        </div>

      {/* Add/Edit Material Modal */}
      <Modal
        isOpen={showMaterialModal}
        onClose={() => setShowMaterialModal(false)}
        title={editingMaterial ? "Edit Material" : "Add Material"}
        disableClose={saving}
      >
        <div className="p-6">
            <h3 className="text-xl font-bold text-white mb-4">
              {editingMaterial ? "Edit Material" : "Add Material"}
            </h3>

            <div className="space-y-4">
              {/* Component Selection */}
              <div>
                <label className="block text-sm font-medium text-gray-300 mb-1">
                  Component *
                </label>
                <select
                  value={materialForm.component_id}
                  onChange={(e) => setMaterialForm({ ...materialForm, component_id: e.target.value })}
                  className="w-full bg-gray-800 border border-gray-700 rounded px-3 py-2 text-white"
                >
                  <option value="">Select component...</option>
                  {components.map((c) => (
                    <option key={c.id} value={c.id}>
                      {c.sku} - {c.name}
                    </option>
                  ))}
                </select>
              </div>

              {/* Quantity & Unit */}
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-sm font-medium text-gray-300 mb-1">
                    Quantity *
                  </label>
                  <input
                    type="number"
                    step="0.001"
                    min="0"
                    value={materialForm.quantity}
                    onChange={(e) => setMaterialForm({ ...materialForm, quantity: e.target.value })}
                    className="w-full bg-gray-800 border border-gray-700 rounded px-3 py-2 text-white"
                    placeholder="0.00"
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-300 mb-1">
                    Unit
                  </label>
                  <input
                    type="text"
                    value={materialForm.unit}
                    onChange={(e) => setMaterialForm({ ...materialForm, unit: e.target.value.toUpperCase() })}
                    className="w-full bg-gray-800 border border-gray-700 rounded px-3 py-2 text-white"
                    placeholder="EA, G, KG, etc."
                  />
                </div>
              </div>

              {/* Quantity Per */}
              <div>
                <label className="block text-sm font-medium text-gray-300 mb-1">
                  Quantity Per
                </label>
                <select
                  value={materialForm.quantity_per}
                  onChange={(e) => setMaterialForm({ ...materialForm, quantity_per: e.target.value })}
                  className="w-full bg-gray-800 border border-gray-700 rounded px-3 py-2 text-white"
                >
                  {QUANTITY_PER_OPTIONS.map((opt) => (
                    <option key={opt.value} value={opt.value}>
                      {opt.label} - {opt.description}
                    </option>
                  ))}
                </select>
              </div>

              {/* Scrap Factor */}
              <div>
                <label className="block text-sm font-medium text-gray-300 mb-1">
                  Scrap Factor (%)
                </label>
                <input
                  type="number"
                  step="0.1"
                  min="0"
                  max="100"
                  value={materialForm.scrap_factor}
                  onChange={(e) => setMaterialForm({ ...materialForm, scrap_factor: e.target.value })}
                  className="w-full bg-gray-800 border border-gray-700 rounded px-3 py-2 text-white"
                  placeholder="0"
                />
                <p className="text-xs text-gray-500 mt-1">
                  Additional quantity to account for waste/scrap
                </p>
              </div>

              {/* Flags */}
              <div className="flex gap-6">
                <label className="flex items-center gap-2 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={materialForm.is_cost_only}
                    onChange={(e) => setMaterialForm({ ...materialForm, is_cost_only: e.target.checked })}
                    className="w-4 h-4 rounded border-gray-600 bg-gray-800"
                  />
                  <span className="text-sm text-gray-300">Cost Only</span>
                  <span className="text-xs text-gray-500">(Don't consume inventory)</span>
                </label>
                <label className="flex items-center gap-2 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={materialForm.is_optional}
                    onChange={(e) => setMaterialForm({ ...materialForm, is_optional: e.target.checked })}
                    className="w-4 h-4 rounded border-gray-600 bg-gray-800"
                  />
                  <span className="text-sm text-gray-300">Optional</span>
                </label>
              </div>

              {/* Notes */}
              <div>
                <label className="block text-sm font-medium text-gray-300 mb-1">
                  Notes
                </label>
                <textarea
                  value={materialForm.notes}
                  onChange={(e) => setMaterialForm({ ...materialForm, notes: e.target.value })}
                  className="w-full bg-gray-800 border border-gray-700 rounded px-3 py-2 text-white"
                  rows={2}
                  placeholder="Optional notes about this material..."
                />
              </div>
            </div>

            {/* Modal Actions */}
            <div className="flex justify-end gap-3 mt-6">
              <button
                onClick={() => setShowMaterialModal(false)}
                className="px-4 py-2 bg-gray-700 text-white rounded hover:bg-gray-600"
                disabled={saving}
              >
                Cancel
              </button>
              <button
                onClick={handleSaveMaterial}
                className="px-4 py-2 bg-blue-600 text-white rounded hover:bg-blue-700 disabled:opacity-50"
                disabled={saving}
              >
                {saving ? "Saving..." : editingMaterial ? "Update" : "Add Material"}
              </button>
            </div>
        </div>
      </Modal>
    </Modal>
  );
}
