/**
 * RoutingEditorContent - Core routing editor logic and UI
 *
 * Single source of truth for routing CRUD. Used by:
 * - RoutingEditor.jsx (modal wrapper — Items/Manufacturing pages)
 * - BOMDetailView.jsx (embedded — BOM page)
 */
import { useState, useEffect, useCallback, useMemo } from "react";
import { API_URL } from "../../config/api";
import OperationMaterialModal from "../OperationMaterialModal";
import OperationRow from "./OperationRow";
import AddOperationForm from "./AddOperationForm";

export default function RoutingEditorContent({
  productId = null,
  routingId = null,
  products = [],
  isActive = false,
  embedded = false,
  onSuccess,
  onCancel,
  onRoutingDataChange,
}) {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [routing, setRouting] = useState(null);
  const [operations, setOperations] = useState([]);
  const [workCenters, setWorkCenters] = useState([]);
  const [templates, setTemplates] = useState([]);
  const [showAddOperation, setShowAddOperation] = useState(false);
  const [selectedTemplate, setSelectedTemplate] = useState("");
  const [selectedProductId, setSelectedProductId] = useState(productId || "");
  const [productList] = useState(products || []);

  // Materials state
  const [operationMaterials, setOperationMaterials] = useState({});
  const [expandedOperations, setExpandedOperations] = useState({});
  const [materialModalOpen, setMaterialModalOpen] = useState(false);
  const [selectedOperationId, setSelectedOperationId] = useState(null);
  const [selectedMaterial, setSelectedMaterial] = useState(null);

  const [newOperation, setNewOperation] = useState({
    work_center_id: "",
    sequence: 1,
    operation_code: "",
    operation_name: "",
    setup_time_minutes: 0,
    run_time_minutes: 0,
    wait_time_minutes: 0,
    move_time_minutes: 0,
    units_per_cycle: 1,
    scrap_rate_percent: 0,
    is_active: true,
  });

  const fetchRouting = useCallback(async () => {
    try {
      const res = await fetch(`${API_URL}/api/v1/routings/${routingId}`, {
        credentials: "include",
      });
      if (res.ok) {
        const data = await res.json();
        setRouting(data);
        setOperations(data.operations || []);
      }
    } catch {
      // Routing fetch failure - will show empty editor
    }
  }, [routingId]);

  const fetchRoutingByProduct = useCallback(async (overrideProductId = null) => {
    const finalProductId = overrideProductId || selectedProductId || productId;
    if (!finalProductId) return;
    try {
      const res = await fetch(
        `${API_URL}/api/v1/routings/product/${finalProductId}`,
        { credentials: "include" }
      );
      if (res.ok) {
        const data = await res.json();
        setRouting(data);
        setOperations(data.operations || []);
      } else if (res.status === 404) {
        setRouting(null);
        setOperations([]);
      }
    } catch {
      // Routing fetch failure - will show empty editor
    }
  }, [selectedProductId, productId]);

  const fetchWorkCenters = useCallback(async () => {
    try {
      const res = await fetch(
        `${API_URL}/api/v1/work-centers?active_only=true`,
        { credentials: "include" }
      );
      if (res.ok) {
        const data = await res.json();
        setWorkCenters(data || []);
      }
    } catch {
      // Work centers fetch failure is non-critical
    }
  }, []);

  const fetchTemplates = useCallback(async () => {
    try {
      const res = await fetch(
        `${API_URL}/api/v1/routings?templates_only=true&active_only=true`,
        { credentials: "include" }
      );
      if (res.ok) {
        const data = await res.json();
        setTemplates(data || []);
      }
    } catch {
      // Templates fetch failure is non-critical
    }
  }, []);

  const fetchOperationMaterials = useCallback(async (operationId) => {
    if (!operationId) return;
    try {
      const res = await fetch(
        `${API_URL}/api/v1/routings/operations/${operationId}/materials`,
        { credentials: "include" }
      );
      if (res.ok) {
        const data = await res.json();
        setOperationMaterials((prev) => ({
          ...prev,
          [operationId]: data || [],
        }));
      }
    } catch {
      // Material fetch failure - materials will show as empty
    }
  }, []);

  // Stable key derived from operation IDs only — prevents re-fetching
  // materials on every keystroke (updateOperation creates a new array ref)
  const operationIdsKey = useMemo(
    () => operations.map((op) => op.id).filter(Boolean).join(","),
    [operations]
  );

  // Fetch materials for all operations when the set of operations changes
  useEffect(() => {
    if (!operationIdsKey) return;
    operationIdsKey
      .split(",")
      .map(Number)
      .forEach((id) => fetchOperationMaterials(id));
  }, [operationIdsKey, fetchOperationMaterials]);

  // Initial data load when activated
  useEffect(() => {
    if (isActive) {
      if (routingId) {
        fetchRouting();
      } else if (productId) {
        fetchRoutingByProduct();
      }
      fetchWorkCenters();
      fetchTemplates();
      setError(null);
      setOperationMaterials({});
      setExpandedOperations({});
    }
  }, [
    isActive,
    routingId,
    productId,
    fetchRouting,
    fetchRoutingByProduct,
    fetchWorkCenters,
    fetchTemplates,
  ]);

  // Notify parent of routing data changes (used by BOM page for cost display)
  useEffect(() => {
    onRoutingDataChange?.({
      routing,
      operations,
      operationMaterials,
      laborCost: routing?.total_cost ? parseFloat(routing.total_cost) : 0,
      opMaterialsCost: Object.values(operationMaterials)
        .flat()
        .reduce((sum, m) => sum + parseFloat(m.extended_cost || 0), 0),
    });
  }, [routing, operations, operationMaterials, onRoutingDataChange]);

  const handleApplyTemplate = async () => {
    if (!selectedTemplate) return;

    const finalProductId = parseInt(selectedProductId || productId);
    if (!finalProductId) return;

    setLoading(true);
    try {
      const res = await fetch(`${API_URL}/api/v1/routings/apply-template`, {
        method: "POST",
        credentials: "include",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          template_id: parseInt(selectedTemplate),
          product_id: finalProductId,
          overrides: [],
        }),
      });

      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || "Failed to apply template");
      }

      // Re-fetch full routing data (apply-template returns ApplyTemplateResponse,
      // but we need the full RoutingResponse shape for the editor)
      await fetchRoutingByProduct();
      setSelectedTemplate("");
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const handleCreateRouting = async () => {
    const finalProductId = selectedProductId || productId;
    if (!finalProductId) {
      setError("Please select a product");
      return;
    }

    setLoading(true);
    setError(null);

    try {
      const res = await fetch(`${API_URL}/api/v1/routings/`, {
        method: "POST",
        credentials: "include",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          product_id: finalProductId,
          version: 1,
          revision: "1.0",
          is_active: true,
          operations: operations.map((op, idx) => ({
            work_center_id: op.work_center_id,
            sequence: idx + 1,
            operation_code: op.operation_code || `OP${idx + 1}`,
            operation_name: op.operation_name || "",
            setup_time_minutes: op.setup_time_minutes || 0,
            run_time_minutes: op.run_time_minutes || 0,
            wait_time_minutes: op.wait_time_minutes || 0,
            move_time_minutes: op.move_time_minutes || 0,
            units_per_cycle: op.units_per_cycle || 1,
            scrap_rate_percent: op.scrap_rate_percent || 0,
            is_active: op.is_active !== false,
          })),
        }),
      });

      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || "Failed to create routing");
      }

      const data = await res.json();
      onSuccess?.(data);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const handleUpdateRouting = async () => {
    if (!routing) return;

    setLoading(true);
    setError(null);

    try {
      for (let i = 0; i < operations.length; i++) {
        const op = operations[i];
        if (op.id) {
          const res = await fetch(
            `${API_URL}/api/v1/routings/operations/${op.id}`,
            {
              method: "PUT",
              credentials: "include",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({
                work_center_id: op.work_center_id,
                sequence: i + 1,
                operation_code: op.operation_code || `OP${i + 1}`,
                operation_name: op.operation_name || "",
                setup_time_minutes: op.setup_time_minutes || 0,
                run_time_minutes: op.run_time_minutes || 0,
                wait_time_minutes: op.wait_time_minutes || 0,
                move_time_minutes: op.move_time_minutes || 0,
                units_per_cycle: op.units_per_cycle || 1,
                scrap_rate_percent: op.scrap_rate_percent || 0,
                is_active: op.is_active !== false,
              }),
            }
          );
          if (!res.ok) throw new Error("Failed to update operation");
        } else {
          const res = await fetch(
            `${API_URL}/api/v1/routings/${routing.id}/operations`,
            {
              method: "POST",
              credentials: "include",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({
                work_center_id: op.work_center_id,
                sequence: i + 1,
                operation_code: op.operation_code || `OP${i + 1}`,
                operation_name: op.operation_name || "",
                setup_time_minutes: op.setup_time_minutes || 0,
                run_time_minutes: op.run_time_minutes || 0,
                wait_time_minutes: op.wait_time_minutes || 0,
                move_time_minutes: op.move_time_minutes || 0,
                units_per_cycle: op.units_per_cycle || 1,
                scrap_rate_percent: op.scrap_rate_percent || 0,
                is_active: op.is_active !== false,
              }),
            }
          );
          if (!res.ok) throw new Error("Failed to add operation");
        }
      }

      onSuccess?.();
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const handleSave = () => {
    if (routing) {
      handleUpdateRouting();
    } else {
      handleCreateRouting();
    }
  };

  const addOperation = () => {
    const workCenter = workCenters.find(
      (wc) => wc.id === parseInt(newOperation.work_center_id)
    );
    if (!workCenter) {
      setError("Please select a work center");
      return;
    }

    setOperations(
      [
        ...operations,
        {
          ...newOperation,
          work_center_id: parseInt(newOperation.work_center_id),
          work_center_name: workCenter.name,
          work_center_code: workCenter.code,
          hourly_rate: parseFloat(workCenter.total_rate_per_hour) || 0,
        },
      ].sort((a, b) => (a.sequence || 0) - (b.sequence || 0))
    );

    setNewOperation({
      work_center_id: "",
      sequence: operations.length + 2,
      operation_code: "",
      operation_name: "",
      setup_time_minutes: 0,
      run_time_minutes: 0,
      wait_time_minutes: 0,
      move_time_minutes: 0,
      units_per_cycle: 1,
      scrap_rate_percent: 0,
      is_active: true,
    });
    setShowAddOperation(false);
  };

  const removeOperation = async (index) => {
    const operation = operations[index];

    if (operation.id) {
      if (
        !window.confirm(
          `Remove operation "${operation.operation_name || operation.operation_code || "Unnamed"}"? This cannot be undone.`
        )
      ) {
        return;
      }

      try {
        setLoading(true);
        const res = await fetch(
          `${API_URL}/api/v1/routings/operations/${operation.id}`,
          {
            method: "DELETE",
            credentials: "include",
          }
        );

        if (!res.ok) {
          const errorData = await res.json().catch(() => ({}));
          throw new Error(
            errorData.detail || `Failed to delete operation: ${res.status}`
          );
        }

        setOperations((prev) => prev.filter((_, i) => i !== index));
        setOperationMaterials((prev) => {
          const next = { ...prev };
          delete next[operation.id];
          return next;
        });
        setError(null);
      } catch (err) {
        setError(err.message || "Failed to remove operation");
        console.error("Failed to remove operation:", err);
      } finally {
        setLoading(false);
      }
    } else {
      setOperations((prev) => prev.filter((_, i) => i !== index));
    }
  };

  const updateOperation = (index, field, value) => {
    const updated = [...operations];
    updated[index] = { ...updated[index], [field]: value };
    setOperations(updated);
  };

  const toggleOperationExpanded = (operationId) => {
    setExpandedOperations((prev) => ({
      ...prev,
      [operationId]: !prev[operationId],
    }));
  };

  const handleAddMaterial = (operationId) => {
    setSelectedOperationId(operationId);
    setSelectedMaterial(null);
    setMaterialModalOpen(true);
  };

  const handleEditMaterial = (operationId, material) => {
    setSelectedOperationId(operationId);
    setSelectedMaterial(material);
    setMaterialModalOpen(true);
  };

  const handleMaterialSave = (savedMaterial) => {
    if (savedMaterial === null) {
      // Material was deleted
      setOperationMaterials((prev) => ({
        ...prev,
        [selectedOperationId]: (prev[selectedOperationId] || []).filter(
          (m) => m.id !== selectedMaterial?.id
        ),
      }));
    } else if (selectedMaterial) {
      // Material was updated
      setOperationMaterials((prev) => ({
        ...prev,
        [selectedOperationId]: (prev[selectedOperationId] || []).map((m) =>
          m.id === savedMaterial.id ? savedMaterial : m
        ),
      }));
    } else {
      // New material was added
      setOperationMaterials((prev) => ({
        ...prev,
        [selectedOperationId]: [
          ...(prev[selectedOperationId] || []),
          savedMaterial,
        ],
      }));
    }
  };

  const totalSetup = operations.reduce(
    (sum, op) => sum + (parseFloat(op.setup_time_minutes) || 0),
    0
  );
  const totalRun = operations.reduce(
    (sum, op) => sum + (parseFloat(op.run_time_minutes) || 0),
    0
  );
  const totalCost = operations.reduce((sum, op) => {
    let laborCost;
    if (op.calculated_cost != null) {
      laborCost = parseFloat(op.calculated_cost);
    } else {
      // Fallback for newly-added operations not yet saved to backend.
      // Uses work center total_rate (rate overrides not applied until save).
      const totalMinutes = (parseFloat(op.setup_time_minutes) || 0) + (parseFloat(op.run_time_minutes) || 0);
      const rate = parseFloat(op.hourly_rate) || 0;
      laborCost = (totalMinutes / 60) * rate;
    }
    // Sum per-unit material costs from operationMaterials state.
    // Skip batch/order materials to match backend routing total.
    const mats = op.id ? operationMaterials[op.id] || [] : [];
    const materialCost = mats
      .filter((m) => !m.quantity_per || m.quantity_per.toLowerCase() === "unit")
      .reduce((s, m) => s + parseFloat(m.extended_cost || 0), 0);
    return sum + laborCost + materialCost;
  }, 0);

  const needsProductSelection =
    !selectedProductId && !productId && !routingId && !routing;

  return (
    <>
      {/* Header — shown in modal mode only */}
      {!embedded && (
        <div className="flex justify-between items-center mb-6">
          <h2 className="text-2xl font-bold text-white">
            {routing
              ? `Edit Routing: ${routing.code || routing.name}`
              : "Create Routing"}
          </h2>
          <button
            onClick={onCancel}
            className="text-gray-400 hover:text-white"
          >
            <svg
              className="w-6 h-6"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M6 18L18 6M6 6l12 12"
              />
            </svg>
          </button>
        </div>
      )}

      {error && (
        <div className="mb-4 p-3 bg-red-500/10 border border-red-500/30 text-red-400 rounded">
          {error}
        </div>
      )}

      {/* Product Selection (if needed) */}
      {needsProductSelection && (
        <div className="mb-6 p-4 bg-gray-800 rounded-lg border border-gray-700">
          <label className="block text-sm font-medium text-gray-300 mb-2">
            Select Product *
          </label>
          <select
            value={selectedProductId}
            onChange={(e) => {
              const nextProductId = e.target.value;
              setSelectedProductId(nextProductId);
              if (nextProductId) {
                fetchRoutingByProduct(nextProductId);
              }
            }}
            className="w-full bg-gray-900 border border-gray-700 rounded px-3 py-2 text-white"
            required
          >
            <option value="">Select a product...</option>
            {productList.map((p) => (
              <option key={p.id} value={p.id}>
                {p.sku} - {p.name}
              </option>
            ))}
          </select>
          <p className="text-xs text-gray-500 mt-2">
            Select a product to create or edit its routing
          </p>
        </div>
      )}

      {/* Editor content — shown when product is selected or routing exists */}
      {!needsProductSelection && (
        <>
          {/* Template Selection */}
          {!routing && templates.length > 0 && (
            <div className="mb-6 p-4 bg-blue-500/10 border border-blue-500/30 rounded-lg">
              <h4 className="font-semibold mb-3 text-blue-400">
                Apply Template
              </h4>
              <div className="flex gap-2">
                <select
                  value={selectedTemplate}
                  onChange={(e) => setSelectedTemplate(e.target.value)}
                  className="flex-1 px-3 py-2 bg-gray-800 border border-gray-700 rounded text-white"
                >
                  <option value="">Select a template...</option>
                  {templates.map((tpl) => (
                    <option key={tpl.id} value={tpl.id}>
                      {tpl.code} - {tpl.name} ({tpl.operation_count} operations)
                    </option>
                  ))}
                </select>
                <button
                  onClick={handleApplyTemplate}
                  disabled={!selectedTemplate || loading}
                  className="px-4 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700 disabled:opacity-50"
                >
                  Apply Template
                </button>
              </div>
            </div>
          )}

          {/* Operations */}
          <div className="mb-6">
            <div className="flex justify-between items-center mb-4">
              <h3 className="text-lg font-semibold">Operations</h3>
              <button
                onClick={() => setShowAddOperation(true)}
                className="px-4 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700"
              >
                + Add Operation
              </button>
            </div>

            {operations.length === 0 ? (
              <div className="text-center py-8 text-gray-400">
                No operations added yet. Click &quot;Add Operation&quot; to get
                started.
              </div>
            ) : (
              <table className="w-full border-collapse">
                <thead>
                  <tr className="bg-gray-800 border-b border-gray-700">
                    <th className="border border-gray-700 p-2 text-left text-gray-300">
                      Seq
                    </th>
                    <th className="border border-gray-700 p-2 text-left text-gray-300">
                      Operation
                    </th>
                    <th className="border border-gray-700 p-2 text-left text-gray-300">
                      Work Center
                    </th>
                    <th className="border border-gray-700 p-2 text-right text-gray-300">
                      Setup (min)
                    </th>
                    <th className="border border-gray-700 p-2 text-right text-gray-300">
                      Run (min)
                    </th>
                    <th className="border border-gray-700 p-2 text-right text-gray-300">
                      Cost
                    </th>
                    <th className="border border-gray-700 p-2 text-center text-gray-300">
                      Actions
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {operations.map((op, index) => (
                    <OperationRow
                      key={op.id || index}
                      op={op}
                      index={index}
                      materials={
                        op.id ? operationMaterials[op.id] || [] : []
                      }
                      isExpanded={op.id && expandedOperations[op.id]}
                      loading={loading}
                      operations={operations}
                      onToggleExpand={toggleOperationExpanded}
                      onUpdateOperation={updateOperation}
                      onRemoveOperation={removeOperation}
                      onAddMaterial={handleAddMaterial}
                      onEditMaterial={handleEditMaterial}
                    />
                  ))}
                </tbody>
                <tfoot>
                  <tr className="bg-gray-800 font-semibold border-t border-gray-700">
                    <td
                      colSpan="3"
                      className="border border-gray-700 p-2 text-right text-gray-300"
                    >
                      Total:
                    </td>
                    <td className="border border-gray-700 p-2 text-right text-white">
                      {totalSetup.toFixed(1)} min
                    </td>
                    <td className="border border-gray-700 p-2 text-right text-white">
                      {totalRun.toFixed(1)} min
                    </td>
                    <td className="border border-gray-700 p-2 text-right text-white">
                      ${totalCost.toFixed(2)}
                    </td>
                    <td className="border border-gray-700"></td>
                  </tr>
                </tfoot>
              </table>
            )}
          </div>

          {/* Add Operation Form */}
          {showAddOperation && (
            <AddOperationForm
              workCenters={workCenters}
              newOperation={newOperation}
              onOperationChange={setNewOperation}
              onAdd={addOperation}
              onCancel={() => setShowAddOperation(false)}
            />
          )}

          {/* Actions — Cancel hidden in embedded mode, Save always available */}
          <div className="flex justify-end gap-3 pt-4 border-t">
            {!embedded && (
              <button
                type="button"
                onClick={onCancel}
                className="px-4 py-2 border rounded-md hover:bg-gray-50"
                disabled={loading}
              >
                Cancel
              </button>
            )}
            <button
              onClick={handleSave}
              className="px-4 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700 disabled:opacity-50"
              disabled={loading || operations.length === 0}
            >
              {loading
                ? "Saving..."
                : routing
                  ? "Update Routing"
                  : "Create Routing"}
            </button>
          </div>
        </>
      )}

      {/* Operation Material Modal */}
      <OperationMaterialModal
        isOpen={materialModalOpen}
        onClose={() => {
          setMaterialModalOpen(false);
          setSelectedMaterial(null);
        }}
        operationId={selectedOperationId}
        material={selectedMaterial}
        onSave={handleMaterialSave}
      />
    </>
  );
}
