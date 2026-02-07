/**
 * BOMEditor - Standalone BOM editor component
 *
 * Simple, focused editor for managing Bill of Materials.
 * Can be used from item detail pages or standalone.
 */
import { useState, useEffect, useCallback } from "react";
import { API_URL } from "../config/api";
import { convertUOM } from "../lib/uom";
import Modal from "./Modal";

export default function BOMEditor({
  isOpen,
  onClose,
  productId,
  bomId = null, // If editing existing BOM
  onSuccess,
}) {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [bom, setBom] = useState(null);
  const [lines, setLines] = useState([]);
  const [components, setComponents] = useState([]);
  const [materials, setMaterials] = useState([]);
  const [uomClasses, setUomClasses] = useState([]);
  const [showAddLine, setShowAddLine] = useState(false);
  const [_editingLine, _setEditingLine] = useState(null); // Reserved for inline editing

  const [newLine, setNewLine] = useState({
    component_id: "",
    quantity: 1,
    unit: "EA",
    sequence: 1,
    scrap_factor: 0,
    is_cost_only: false,
    notes: "",
  });

  const fetchBOM = useCallback(async () => {
    try {
      const res = await fetch(`${API_URL}/api/v1/admin/bom/${bomId}`, {
        credentials: "include",
      });
      if (res.ok) {
        const data = await res.json();
        setBom(data);
        setLines(data.lines || []);
      }
    } catch {
      // BOM fetch failure - will show empty editor
    }
  }, [bomId]);

  const fetchBOMByProduct = useCallback(async () => {
    try {
      const res = await fetch(
        `${API_URL}/api/v1/admin/bom/product/${productId}`,
        {
          credentials: "include",
        }
      );
      if (res.ok) {
        const data = await res.json();
        setBom(data);
        setLines(data.lines || []);
      } else if (res.status === 404) {
        // No BOM exists yet, that's okay
        setBom(null);
        setLines([]);
      }
    } catch {
      // BOM fetch failure - will show empty editor
    }
  }, [productId]);

  const fetchComponents = useCallback(async () => {
    try {
      const res = await fetch(
        `${API_URL}/api/v1/items?limit=500&active_only=true`,
        {
          credentials: "include",
        }
      );
      if (res.ok) {
        const data = await res.json();
        setComponents(data.items || []);
      }
    } catch {
      // Components fetch failure is non-critical
    }
  }, []);

  const fetchMaterials = useCallback(async () => {
    try {
      const res = await fetch(`${API_URL}/api/v1/materials/for-bom`, {
        credentials: "include",
      });
      if (res.ok) {
        const data = await res.json();
        setMaterials(data.items || []);
      }
    } catch {
      // Materials fetch failure is non-critical
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
    } catch {
      setUomClasses([]);
    }
  }, []);

  useEffect(() => {
    if (isOpen) {
      if (bomId) {
        fetchBOM();
      } else if (productId) {
        fetchBOMByProduct();
      }
      fetchComponents();
      fetchMaterials();
      fetchUomClasses();
      setError(null);
    }
  }, [
    isOpen,
    bomId,
    productId,
    fetchBOM,
    fetchBOMByProduct,
    fetchComponents,
    fetchMaterials,
    fetchUomClasses,
  ]);

  const allComponents = [...components, ...materials];

  const handleCreateBOM = async () => {
    if (!productId) {
      setError("Product ID is required");
      return;
    }

    setLoading(true);
    setError(null);

    try {
      const res = await fetch(`${API_URL}/api/v1/admin/bom/`, {
        method: "POST",
        credentials: "include",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          product_id: productId,
          lines: lines.map((line, idx) => ({
            component_id: line.component_id,
            quantity: line.quantity,
            unit: line.unit || "EA",
            sequence: idx + 1,
            scrap_factor: line.scrap_factor || 0,
            is_cost_only: line.is_cost_only || false,
            notes: line.notes || "",
          })),
        }),
      });

      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || "Failed to create BOM");
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

  const handleUpdateBOM = async () => {
    if (!bom) return;

    setLoading(true);
    setError(null);

    try {
      // Update BOM lines
      for (let i = 0; i < lines.length; i++) {
        const line = lines[i];
        if (line.id) {
          // Update existing line
          const res = await fetch(
            `${API_URL}/api/v1/admin/bom/${bom.id}/lines/${line.id}`,
            {
              method: "PATCH",
              credentials: "include",
              headers: {
                "Content-Type": "application/json",
              },
              body: JSON.stringify({
                quantity: line.quantity,
                unit: line.unit || "EA",
                sequence: i + 1,
                scrap_factor: line.scrap_factor || 0,
                is_cost_only: line.is_cost_only || false,
                notes: line.notes || "",
              }),
            }
          );
          if (!res.ok) throw new Error("Failed to update line");
        } else {
          // Add new line
          const res = await fetch(
            `${API_URL}/api/v1/admin/bom/${bom.id}/lines`,
            {
              method: "POST",
              credentials: "include",
              headers: {
                "Content-Type": "application/json",
              },
              body: JSON.stringify({
                component_id: line.component_id,
                quantity: line.quantity,
                unit: line.unit || "EA",
                sequence: i + 1,
                scrap_factor: line.scrap_factor || 0,
                is_cost_only: line.is_cost_only || false,
                notes: line.notes || "",
              }),
            }
          );
          if (!res.ok) throw new Error("Failed to add line");
        }
      }

      // Recalculate BOM cost
      await fetch(`${API_URL}/api/v1/admin/bom/${bom.id}/recalculate`, {
        method: "POST",
        credentials: "include",
      });

      onSuccess?.();
      onClose();
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const handleSave = () => {
    if (bom) {
      handleUpdateBOM();
    } else {
      handleCreateBOM();
    }
  };

  const addLine = () => {
    if (!newLine.component_id) {
      setError("Please select a component");
      return;
    }

    const component = allComponents.find(
      (c) => c.id === parseInt(newLine.component_id)
    );
    if (!component) {
      setError("Component not found. Please refresh and try again.");
      return;
    }

    // Check if component is already in BOM
    const existing = lines.find(
      (l) => l.component_id === parseInt(newLine.component_id)
    );
    if (existing) {
      setError("This component is already in the BOM");
      return;
    }

    // Set unit based on component type
    const defaultUnit =
      component.unit ||
      (component.item_type === "material" ? "G" :
       component.item_type === "supply" ? "KG" : "EA");

    setLines([
      ...lines,
      {
        ...newLine,
        component_id: parseInt(newLine.component_id),
        component_sku: component.sku,
        component_name: component.name,
        component_unit: defaultUnit,
        component_cost: component.standard_cost || component.average_cost || 0,
        unit: newLine.unit || defaultUnit,
      },
    ]);

    setNewLine({
      component_id: "",
      quantity: 1,
      unit: "EA",
      sequence: lines.length + 2,
      scrap_factor: 0,
      is_cost_only: false,
      notes: "",
    });
    setError(null);
    setShowAddLine(false);
  };

  const removeLine = (index) => {
    setLines(lines.filter((_, i) => i !== index));
  };

  // UOM conversion now uses shared lib/uom.js

  const updateLine = (index, field, value) => {
    const updated = [...lines];
    const currentLine = updated[index];
    
    // If unit is changing, convert quantity
    if (field === 'unit' && currentLine.component_unit) {
      const oldUnit = currentLine.unit || currentLine.component_unit;
      const newUnit = value;
      const currentQty = parseFloat(currentLine.quantity) || 0;
      
      if (oldUnit !== newUnit && currentQty > 0) {
        // Convert quantity when unit changes
        const convertedQty = convertUOM(currentQty, oldUnit, newUnit);
        updated[index] = { 
          ...currentLine, 
          [field]: value,
          quantity: convertedQty
        };
      } else {
        updated[index] = { ...currentLine, [field]: value };
      }
    } else {
      updated[index] = { ...currentLine, [field]: value };
    }
    
    setLines(updated);
  };

  // Render UOM select options
  const renderUomOptions = () => {
    if (uomClasses.length > 0) {
      return uomClasses.map((cls) => (
        <optgroup
          key={cls.uom_class}
          label={cls.uom_class.charAt(0).toUpperCase() + cls.uom_class.slice(1)}
        >
          {cls.units.map((u) => (
            <option key={u.code} value={u.code}>
              {u.code}
            </option>
          ))}
        </optgroup>
      ));
    }
    // Fallback
    return (
      <>
        <option value="EA">EA</option>
        <option value="KG">KG</option>
        <option value="G">G</option>
        <option value="LB">LB</option>
        <option value="M">M</option>
        <option value="FT">FT</option>
        <option value="HR">HR</option>
      </>
    );
  };

  const totalCost = lines.reduce((sum, line) => {
    const qty = line.quantity * (1 + (line.scrap_factor || 0) / 100);
    return sum + qty * (line.component_cost || 0);
  }, 0);

  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      title={bom ? `Edit BOM: ${bom.code || bom.name}` : "Create BOM"}
      className="w-full max-w-4xl max-h-[90vh] overflow-y-auto"
      disableClose={loading}
    >
      <div className="p-6">
          <div className="flex justify-between items-center mb-6">
            <h2 className="text-2xl font-bold text-white">
              {bom ? `Edit BOM: ${bom.code || bom.name}` : "Create BOM"}
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

          {/* BOM Lines */}
          <div className="mb-6">
            <div className="flex justify-between items-center mb-4">
              <h3 className="text-lg font-semibold text-white">Components</h3>
              <button
                onClick={() => setShowAddLine(true)}
                className="px-4 py-2 bg-blue-600 text-white rounded-lg font-medium hover:bg-blue-700"
              >
                + Add Component
              </button>
            </div>

            {lines.length === 0 ? (
              <div className="text-center py-8 text-gray-400">
                No components added yet. Click "Add Component" to get started.
              </div>
            ) : (
              <div className="border border-gray-700 rounded-xl overflow-hidden">
                <table className="w-full">
                  <thead>
                    <tr className="bg-gray-800/50">
                      <th className="px-4 py-3 text-left text-sm font-medium text-gray-300">
                        Seq
                      </th>
                      <th className="px-4 py-3 text-left text-sm font-medium text-gray-300">
                        Component
                      </th>
                      <th className="px-4 py-3 text-right text-sm font-medium text-gray-300">
                        Quantity
                      </th>
                      <th className="px-4 py-3 text-left text-sm font-medium text-gray-300">
                        Unit
                      </th>
                      <th className="px-4 py-3 text-right text-sm font-medium text-gray-300">
                        Scrap %
                      </th>
                      <th className="px-4 py-3 text-right text-sm font-medium text-gray-300">
                        Cost
                      </th>
                      <th className="px-4 py-3 text-center text-sm font-medium text-gray-300">
                        Cost Only
                      </th>
                      <th className="px-4 py-3 text-center text-sm font-medium text-gray-300">
                        Actions
                      </th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-800">
                    {lines.map((line, index) => (
                      <tr key={index} className="hover:bg-gray-800/30">
                        <td className="px-4 py-3 text-gray-300">{index + 1}</td>
                        <td className="px-4 py-3 text-white">
                          <span className="font-medium">
                            {line.component_sku || line.component?.sku}
                          </span>
                          <span className="text-gray-400">
                            {" "}
                            - {line.component_name || line.component?.name}
                          </span>
                        </td>
                        <td className="px-4 py-3">
                          <input
                            type="number"
                            step="0.001"
                            min="0"
                            value={line.quantity}
                            onChange={(e) =>
                              updateLine(
                                index,
                                "quantity",
                                parseFloat(e.target.value) || 0
                              )
                            }
                            className="w-24 text-right bg-gray-800 border border-gray-700 rounded-lg px-3 py-1 text-white focus:border-blue-500 focus:outline-none"
                          />
                        </td>
                        <td className="px-4 py-3">
                          <div className="flex items-center gap-1">
                            <select
                              value={line.unit || line.component_unit || "EA"}
                              onChange={(e) =>
                                updateLine(index, "unit", e.target.value)
                              }
                              className="w-20 bg-gray-800 border border-gray-700 rounded-lg px-2 py-1 text-white focus:border-blue-500 focus:outline-none"
                            >
                              {renderUomOptions()}
                            </select>
                            {line.component_unit && line.unit && line.unit !== line.component_unit && (
                              <span className="text-xs text-gray-500" title={`Component default: ${line.component_unit}`}>
                                ({line.component_unit})
                              </span>
                            )}
                          </div>
                        </td>
                        <td className="px-4 py-3">
                          <input
                            type="number"
                            step="0.1"
                            min="0"
                            max="100"
                            value={line.scrap_factor || 0}
                            onChange={(e) =>
                              updateLine(
                                index,
                                "scrap_factor",
                                parseFloat(e.target.value) || 0
                              )
                            }
                            className="w-20 text-right bg-gray-800 border border-gray-700 rounded-lg px-3 py-1 text-white focus:border-blue-500 focus:outline-none"
                          />
                        </td>
                        <td className="px-4 py-3 text-right text-white">
                          {line.line_cost != null ? (
                            <>
                              ${line.line_cost.toFixed(2)}
                              {line.is_material && (
                                <span className="text-xs text-gray-500 ml-1" title="Cost calculated: (quantity_g / 1000) × cost_per_kg">
                                  (${line.component_cost?.toFixed(4) || '0.0000'}/KG)
                                </span>
                              )}
                              {!line.is_material && line.unit && line.component_unit && line.unit !== line.component_unit && (
                                <span className="text-xs text-gray-500 ml-1" title="Cost converted from component unit">
                                  *
                                </span>
                              )}
                            </>
                          ) : line.component_cost != null ? (
                            <>
                              $
                              {(
                                line.quantity *
                                (1 + (line.scrap_factor || 0) / 100) *
                                (line.component_cost || 0)
                              ).toFixed(2)}
                              {line.unit && line.component_unit && line.unit !== line.component_unit && (
                                <span className="text-xs text-gray-500 ml-1" title="Cost converted from component unit">
                                  *
                                </span>
                              )}
                            </>
                          ) : (
                            "-"
                          )}
                        </td>
                        <td className="px-4 py-3 text-center">
                          <input
                            type="checkbox"
                            checked={line.is_cost_only || false}
                            onChange={(e) =>
                              updateLine(
                                index,
                                "is_cost_only",
                                e.target.checked
                              )
                            }
                            className="w-4 h-4 rounded border-gray-600 bg-gray-700 text-blue-600 focus:ring-blue-500"
                          />
                        </td>
                        <td className="px-4 py-3 text-center">
                          <button
                            onClick={() => removeLine(index)}
                            className="text-red-400 hover:text-red-300"
                          >
                            Remove
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                  <tfoot>
                    <tr className="bg-gray-800/50 font-semibold">
                      <td
                        colSpan="5"
                        className="px-4 py-3 text-right text-gray-300"
                      >
                        Total Material Cost:
                      </td>
                      <td className="px-4 py-3 text-right text-white">
                        ${totalCost.toFixed(2)}
                      </td>
                      <td colSpan="2"></td>
                    </tr>
                  </tfoot>
                </table>
              </div>
            )}
          </div>

          {/* Add Line Form */}
          {showAddLine && (
            <div className="mb-6 p-4 bg-gray-800 border border-gray-700 rounded-xl">
              <h4 className="font-semibold text-white mb-3">Add Component</h4>
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-sm font-medium text-gray-300 mb-1">
                    Component
                  </label>
                  <select
                    value={newLine.component_id}
                    onChange={(e) => {
                      const selectedId = e.target.value;
                      const selected = allComponents.find(
                        (c) => c.id === parseInt(selectedId)
                      );
                      setNewLine({
                        ...newLine,
                        component_id: selectedId,
                        unit:
                          selected?.unit ||
                          (selected?.item_type === "material" ? "G" :
                           selected?.item_type === "supply" ? "KG" : "EA"),
                      });
                    }}
                    className="w-full px-4 py-2 bg-gray-700 border border-gray-600 rounded-lg text-white focus:border-blue-500 focus:outline-none"
                  >
                    <option value="">Select component...</option>
                    <optgroup label="Components & Supplies">
                      {components
                        .filter(
                          (c) => !lines.find((l) => l.component_id === c.id)
                        )
                        .map((comp) => (
                          <option key={comp.id} value={comp.id}>
                            {comp.sku} - {comp.name} ({comp.unit || "EA"})
                          </option>
                        ))}
                    </optgroup>
                    {materials.length > 0 && (
                      <optgroup label="Materials (Filament)">
                        {materials
                          .filter(
                            (m) => !lines.find((l) => l.component_id === m.id)
                          )
                          .map((mat) => (
                            <option key={mat.id} value={mat.id}>
                              {mat.sku} - {mat.name} ({mat.unit || "KG"})
                            </option>
                          ))}
                      </optgroup>
                    )}
                  </select>
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-300 mb-1">
                    Quantity
                  </label>
                  <input
                    type="number"
                    step="0.001"
                    min="0"
                    value={newLine.quantity}
                    onChange={(e) =>
                      setNewLine({
                        ...newLine,
                        quantity: parseFloat(e.target.value) || 0,
                      })
                    }
                    className="w-full px-4 py-2 bg-gray-700 border border-gray-600 rounded-lg text-white focus:border-blue-500 focus:outline-none"
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-300 mb-1">
                    Unit
                  </label>
                  <div className="flex items-center gap-2">
                    <select
                      value={newLine.unit}
                      onChange={(e) => {
                        const newUnit = e.target.value;
                        const selected = allComponents.find(
                          (c) => c.id === parseInt(newLine.component_id)
                        );
                        const oldUnit = newLine.unit || (selected?.unit || 'EA');
                        const currentQty = parseFloat(newLine.quantity) || 0;
                        
                        // Convert quantity when unit changes
                        let convertedQty = currentQty;
                        if (oldUnit !== newUnit && currentQty > 0) {
                          convertedQty = convertUOM(currentQty, oldUnit, newUnit);
                        }
                        
                        setNewLine({ 
                          ...newLine, 
                          unit: newUnit,
                          quantity: convertedQty
                        });
                      }}
                      className="flex-1 px-4 py-2 bg-gray-700 border border-gray-600 rounded-lg text-white focus:border-blue-500 focus:outline-none"
                    >
                      {renderUomOptions()}
                    </select>
                    {newLine.component_id && (() => {
                      const selected = allComponents.find(
                        (c) => c.id === parseInt(newLine.component_id)
                      );
                      return selected?.unit && selected.unit !== newLine.unit ? (
                        <span className="text-xs text-gray-500" title={`Component default: ${selected.unit}`}>
                          ({selected.unit})
                        </span>
                      ) : null;
                    })()}
                  </div>
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-300 mb-1">
                    Scrap Factor (%)
                  </label>
                  <input
                    type="number"
                    step="0.1"
                    min="0"
                    max="100"
                    value={newLine.scrap_factor}
                    onChange={(e) =>
                      setNewLine({
                        ...newLine,
                        scrap_factor: parseFloat(e.target.value) || 0,
                      })
                    }
                    className="w-full px-4 py-2 bg-gray-700 border border-gray-600 rounded-lg text-white focus:border-blue-500 focus:outline-none"
                  />
                </div>
              </div>
              <div className="mt-3 flex items-center">
                <input
                  type="checkbox"
                  id="cost_only"
                  checked={newLine.is_cost_only}
                  onChange={(e) =>
                    setNewLine({ ...newLine, is_cost_only: e.target.checked })
                  }
                  className="w-4 h-4 rounded border-gray-600 bg-gray-700 text-blue-600 focus:ring-blue-500 mr-2"
                />
                <label htmlFor="cost_only" className="text-sm text-gray-300">
                  Cost only (not consumed from inventory)
                </label>
              </div>
              <div className="mt-4 flex gap-2">
                <button
                  onClick={addLine}
                  className="px-4 py-2 bg-green-600 text-white rounded-lg font-medium hover:bg-green-700"
                >
                  Add
                </button>
                <button
                  onClick={() => setShowAddLine(false)}
                  className="px-4 py-2 bg-gray-700 border border-gray-600 text-gray-300 rounded-lg hover:bg-gray-600"
                >
                  Cancel
                </button>
              </div>
            </div>
          )}

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
              onClick={handleSave}
              className="px-4 py-2 bg-blue-600 text-white rounded-lg font-medium hover:bg-blue-700 disabled:opacity-50"
              disabled={loading || lines.length === 0}
            >
              {loading ? "Saving..." : bom ? "Update BOM" : "Create BOM"}
            </button>
          </div>
        </div>
    </Modal>
  );
}
