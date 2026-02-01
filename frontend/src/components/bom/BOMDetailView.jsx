import React, { useState, useEffect, useCallback } from "react";
import { API_URL } from "../../config/api";
import { useToast } from "../Toast";
import Modal from "../Modal";
import SearchableSelect from "../SearchableSelect";
import PurchaseRequestModal from "./PurchaseRequestModal";
import WorkOrderRequestModal from "./WorkOrderRequestModal";

export default function BOMDetailView({
  bom,
  onClose,
  onUpdate,
  token,
  onCreateProductionOrder,
}) {
  const toast = useToast();
  const [lines, setLines] = useState(bom.lines || []);
  const [loading, setLoading] = useState(false);
  const [editingLine, setEditingLine] = useState(null);
  const [purchaseLine, setPurchaseLine] = useState(null);
  const [workOrderLine, setWorkOrderLine] = useState(null);
  const [newLine, setNewLine] = useState({
    component_id: "",
    quantity: "1",
    unit: "",
    sequence: "",
    scrap_factor: "0",
    notes: "",
  });
  const [showAddLine, setShowAddLine] = useState(false);
  const [products, setProducts] = useState([]);
  const [uoms, setUoms] = useState([]);

  // Sub-assembly state
  const [showExploded, setShowExploded] = useState(false);
  const [explodedData, setExplodedData] = useState(null);
  const [costRollup, setCostRollup] = useState(null);

  // Process Path / Routing state
  const [routingTemplates, setRoutingTemplates] = useState([]);
  const [productRouting, setProductRouting] = useState(null);

  // Operation materials state
  const [expandedOperations, setExpandedOperations] = useState({});
  const [operationMaterials, setOperationMaterials] = useState({});
  const [showAddMaterialModal, setShowAddMaterialModal] = useState(null); // operation_id or null
  const [newMaterial, setNewMaterial] = useState({
    component_id: "",
    quantity: "1",
    quantity_per: "unit",  // enum: unit, batch, order
    scrap_factor: "0",
    unit: "",
  });
  const [selectedTemplateId, setSelectedTemplateId] = useState("");
  const [timeOverrides, setTimeOverrides] = useState({});
  const [applyingTemplate, setApplyingTemplate] = useState(false);
  const showProcessPath = true;
  const [workCenters, setWorkCenters] = useState([]);
  const [showAddOperation, setShowAddOperation] = useState(false);
  const [showAddOperationToExisting, setShowAddOperationToExisting] = useState(false);
  const [pendingOperations, setPendingOperations] = useState([]);
  const [newOperation, setNewOperation] = useState({
    work_center_id: "",
    operation_name: "",
    run_time_minutes: "0",
    setup_time_minutes: "0",
  });
  const [savingRouting, setSavingRouting] = useState(false);
  const [addingOperation, setAddingOperation] = useState(false);

  // Memoized fetchProductRouting for use in useEffect and other handlers
  const fetchProductRouting = useCallback(async () => {
    if (!bom.product_id || !token) return;
    try {
      const res = await fetch(
        `${API_URL}/api/v1/routings?product_id=${bom.product_id}`,
        {
          headers: { Authorization: `Bearer ${token}` },
        }
      );
      if (res.ok) {
        const data = await res.json();
        const items = data.items || data;
        // Find the active routing for this product
        const activeRouting = items.find((r) => r.is_active && !r.is_template);
        if (activeRouting) {
          // Fetch full routing with operations
          const detailRes = await fetch(
            `${API_URL}/api/v1/routings/${activeRouting.id}`,
            {
              headers: { Authorization: `Bearer ${token}` },
            }
          );
          if (detailRes.ok) {
            const routingDetail = await detailRes.json();
            setProductRouting(routingDetail);
            // Initialize time overrides from existing routing
            const overrides = {};
            routingDetail.operations?.forEach((op) => {
              if (op.operation_code) {
                overrides[op.operation_code] = {
                  run_time_minutes: parseFloat(op.run_time_minutes || 0),
                  setup_time_minutes: parseFloat(op.setup_time_minutes || 0),
                };
              }
            });
            setTimeOverrides(overrides);
          }
        }
      }
    } catch {
      // Product routing fetch failure is non-critical - routing section will just be empty
    }
  }, [token, bom.product_id]);

  // Fetch manufacturing BOM with operation materials
  const fetchManufacturingBOM = useCallback(async () => {
    if (!bom?.product_id || !token) return;

    try {
      const res = await fetch(
        `${API_URL}/api/v1/routings/manufacturing-bom/${bom.product_id}`,
        { headers: { Authorization: `Bearer ${token}` } }
      );

      if (res.ok) {
        const data = await res.json();
        // Index materials by operation_id for easy lookup
        const materialsByOp = {};
        data.operations?.forEach((op) => {
          materialsByOp[op.id] = op.materials || [];
        });
        setOperationMaterials(materialsByOp);
      } else {
        // Non-critical failure - routing section will show empty materials
      }
    } catch {
      // Non-critical failure - routing section will show empty materials
    }
  }, [bom?.product_id, token]);

  // Fetch manufacturing BOM when productRouting is loaded
  useEffect(() => {
    if (productRouting) {
      fetchManufacturingBOM();
    }
  }, [productRouting, fetchManufacturingBOM]);

  // Add material to operation
  const handleAddMaterial = async (operationId) => {
    if (!newMaterial.component_id) return;

    try {
      const res = await fetch(
        `${API_URL}/api/v1/routings/operations/${operationId}/materials`,
        {
          method: "POST",
          headers: {
            Authorization: `Bearer ${token}`,
            "Content-Type": "application/json",
          },
          body: JSON.stringify({
            component_id: parseInt(newMaterial.component_id),
            quantity: parseFloat(newMaterial.quantity),
            quantity_per: newMaterial.quantity_per || "unit",
            unit: newMaterial.unit || "EA",
            scrap_factor: parseFloat(newMaterial.scrap_factor) || 0,
          }),
        }
      );

      if (res.ok) {
        toast.success("Material added to operation");
        setShowAddMaterialModal(null);
        setNewMaterial({
          component_id: "",
          quantity: "1",
          quantity_per: "unit",
          scrap_factor: "0",
          unit: "",
        });
        await fetchManufacturingBOM();
      } else {
        const err = await res.json();
        toast.error(err.detail || "Failed to add material");
      }
    } catch (err) {
      toast.error(err.message || "Network error");
    }
  };

  // Delete material from operation
  const handleDeleteMaterial = async (operationId, materialId) => {
    if (!window.confirm("Remove this material from the operation?")) return;

    try {
      const res = await fetch(
        `${API_URL}/api/v1/routings/materials/${materialId}`,
        {
          method: "DELETE",
          headers: { Authorization: `Bearer ${token}` },
        }
      );

      if (res.ok) {
        toast.success("Material removed");
        await fetchManufacturingBOM();
      } else {
        const err = await res.json();
        toast.error(err.detail || "Failed to remove material");
      }
    } catch (err) {
      toast.error(err.message || "Network error");
    }
  };

  // Calculate operation materials cost
  const calculateOperationMaterialsCost = () => {
    return Object.values(operationMaterials)
      .flat()
      .reduce((sum, m) => sum + parseFloat(m.extended_cost || 0), 0);
  };

  useEffect(() => {
    // Guard against running without token
    if (!token) return;

    const fetchCostRollup = async () => {
      try {
        const res = await fetch(
          `${API_URL}/api/v1/admin/bom/${bom.id}/cost-rollup`,
          {
            headers: { Authorization: `Bearer ${token}` },
          }
        );
        if (res.ok) {
          const data = await res.json();
          setCostRollup(data);
        }
      } catch {
        // Cost rollup fetch failure is non-critical - cost display will just be empty
      }
    };

    const fetchRoutingTemplates = async () => {
      try {
        const res = await fetch(
          `${API_URL}/api/v1/routings?templates_only=true`,
          {
            headers: { Authorization: `Bearer ${token}` },
          }
        );
        if (res.ok) {
          const data = await res.json();
          setRoutingTemplates(data.items || data);
        }
      } catch {
        // Routing templates fetch failure is non-critical - templates list will just be empty
      }
    };

    const fetchProducts = async () => {
      try {
        const res = await fetch(
          `${API_URL}/api/v1/products?limit=500&is_raw_material=true`,
          {
            headers: { Authorization: `Bearer ${token}` },
          }
        );
        if (res.ok) {
          const data = await res.json();
          setProducts(data.items || data);
        }
      } catch {
        toast.error("Failed to load products. Please refresh the page.");
      }
    };

    const fetchUOMs = async () => {
      try {
        const res = await fetch(`${API_URL}/api/v1/admin/uom`, {
          headers: { Authorization: `Bearer ${token}` },
        });
        if (res.ok) {
          const data = await res.json();
          setUoms(data);
        }
      } catch {
        // UOM fetch failure is non-critical
      }
    };

    const fetchWorkCenters = async () => {
      try {
        const res = await fetch(
          `${API_URL}/api/v1/work-centers/?active_only=true`,
          {
            headers: { Authorization: `Bearer ${token}` },
          }
        );
        if (res.ok) {
          const data = await res.json();
          setWorkCenters(data);
        }
      } catch {
        // Work centers fetch failure is non-critical
      }
    };

    fetchProducts();
    fetchUOMs();
    fetchCostRollup();
    fetchRoutingTemplates();
    fetchProductRouting();
    fetchWorkCenters();
  }, [token, bom.id, bom.product_id, fetchProductRouting, toast]);

  const handleApplyTemplate = async () => {
    if (!selectedTemplateId || !bom.product_id) return;

    setApplyingTemplate(true);
    try {
      // Convert timeOverrides to the format expected by the API
      const overrides = Object.entries(timeOverrides)
        .filter(
          ([, val]) =>
            val.run_time_minutes !== undefined ||
            val.setup_time_minutes !== undefined
        )
        .map(([code, val]) => ({
          operation_code: code,
          run_time_minutes: val.run_time_minutes,
          setup_time_minutes: val.setup_time_minutes,
        }));

      const res = await fetch(`${API_URL}/api/v1/routings/apply-template`, {
        method: "POST",
        headers: {
          Authorization: `Bearer ${token}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          product_id: bom.product_id,
          template_id: parseInt(selectedTemplateId),
          overrides,
        }),
      });

      if (res.ok) {
        const result = await res.json();
        setProductRouting(result);
        // Update time overrides from result
        const newOverrides = {};
        result.operations?.forEach((op) => {
          if (op.operation_code) {
            newOverrides[op.operation_code] = {
              run_time_minutes: parseFloat(op.run_time_minutes || 0),
              setup_time_minutes: parseFloat(op.setup_time_minutes || 0),
            };
          }
        });
        setTimeOverrides(newOverrides);
        setSelectedTemplateId("");
      } else {
        const errData = await res.json();
        toast.error(
          `Failed to apply routing template: ${
            errData.detail || "Unknown error"
          }`
        );
      }
    } catch (err) {
      toast.error(
        `Failed to apply routing template: ${err.message || "Network error"}`
      );
    } finally {
      setApplyingTemplate(false);
    }
  };

  const updateOperationTime = (opCode, field, value) => {
    setTimeOverrides((prev) => ({
      ...prev,
      [opCode]: {
        ...prev[opCode],
        [field]: parseFloat(value) || 0,
      },
    }));
  };

  // Save operation time to server and refresh routing
  const saveOperationTime = async (operationId, field, value) => {
    try {
      const res = await fetch(
        `${API_URL}/api/v1/routings/operations/${operationId}`,
        {
          method: "PUT",
          headers: {
            Authorization: `Bearer ${token}`,
            "Content-Type": "application/json",
          },
          body: JSON.stringify({
            [field]: parseFloat(value) || 0,
          }),
        }
      );

      if (res.ok) {
        // Refresh the routing to get updated costs
        await fetchProductRouting();
      } else {
        const errData = await res.json();
        toast.error(
          `Failed to update operation: ${errData.detail || "Unknown error"}`
        );
      }
    } catch (err) {
      toast.error(
        `Failed to update operation: ${err.message || "Network error"}`
      );
    }
  };

  // Delete operation from routing
  const handleDeleteOperation = async (operationId, operationName) => {
    if (
      !window.confirm(
        `Are you sure you want to remove operation "${operationName}"? This action cannot be undone.`
      )
    ) {
      return;
    }

    try {
      const res = await fetch(
        `${API_URL}/api/v1/routings/operations/${operationId}`,
        {
          method: "DELETE",
          headers: {
            Authorization: `Bearer ${token}`,
          },
        }
      );

      if (res.ok) {
        toast.success("Operation removed successfully");
        // Refresh the routing to get updated operation list and costs
        await fetchProductRouting();
      } else {
        const errData = await res.json();
        toast.error(
          `Failed to remove operation: ${errData.detail || "Unknown error"}`
        );
      }
    } catch (err) {
      toast.error(
        `Failed to remove operation: ${err.message || "Network error"}`
      );
    }
  };

  // Calculate total process cost from routing
  const calculateProcessCost = () => {
    if (!productRouting) return 0;
    return parseFloat(productRouting.total_cost || 0);
  };

  // Format minutes to hours:minutes
  const formatTime = (minutes) => {
    const mins = parseFloat(minutes || 0);
    if (mins < 60) return `${mins.toFixed(0)}m`;
    const hrs = Math.floor(mins / 60);
    const remainingMins = Math.round(mins % 60);
    return remainingMins > 0 ? `${hrs}h ${remainingMins}m` : `${hrs}h`;
  };

  const fetchExploded = async () => {
    setLoading(true);
    try {
      const res = await fetch(`${API_URL}/api/v1/admin/bom/${bom.id}/explode`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (res.ok) {
        const data = await res.json();
        setExplodedData(data);
        setShowExploded(true);
      } else {
        toast.error("Failed to load exploded BOM view. Please try again.");
      }
    } catch (err) {
      toast.error(
        `Failed to load exploded BOM: ${err.message || "Network error"}`
      );
    } finally {
      setLoading(false);
    }
  };

  // toggleSubAssembly removed - not currently used

  const handleAddPendingOperation = () => {
    if (!newOperation.work_center_id) return;
    const wc = workCenters.find(
      (w) => String(w.id) === String(newOperation.work_center_id)
    );
    setPendingOperations([
      ...pendingOperations,
      {
        ...newOperation,
        sequence: pendingOperations.length + 1,
        work_center_name: wc?.name || "",
        work_center_code: wc?.code || "",
      },
    ]);
    setNewOperation({
      work_center_id: "",
      operation_name: "",
      run_time_minutes: "0",
      setup_time_minutes: "0",
    });
    setShowAddOperation(false);
  };

  const handleRemovePendingOperation = (index) => {
    const updated = pendingOperations.filter((_, i) => i !== index);
    // Resequence
    updated.forEach((op, i) => {
      op.sequence = i + 1;
    });
    setPendingOperations(updated);
  };

  const handleSaveRouting = async () => {
    if (pendingOperations.length === 0) return;

    setSavingRouting(true);
    try {
      const res = await fetch(`${API_URL}/api/v1/routings/`, {
        method: "POST",
        headers: {
          Authorization: `Bearer ${token}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          product_id: bom.product_id,
          operations: pendingOperations.map((op) => ({
            work_center_id: parseInt(op.work_center_id),
            sequence: op.sequence,
            operation_name: op.operation_name || `Step ${op.sequence}`,
            run_time_minutes: parseFloat(op.run_time_minutes) || 0,
            setup_time_minutes: parseFloat(op.setup_time_minutes) || 0,
          })),
        }),
      });

      if (res.ok) {
        const routing = await res.json();
        setProductRouting(routing);
        setPendingOperations([]);
        toast.success("Routing created successfully");
        // Refresh to get full routing details
        await fetchProductRouting();
      } else {
        const errData = await res.json();
        toast.error(errData.detail || "Failed to create routing");
      }
    } catch (err) {
      toast.error(err.message || "Failed to create routing");
    } finally {
      setSavingRouting(false);
    }
  };

  // Add operation to existing routing
  const handleAddOperationToExisting = async () => {
    if (!productRouting?.id || !newOperation.work_center_id) return;

    setAddingOperation(true);
    try {
      // Calculate next sequence number
      const maxSequence = Math.max(
        0,
        ...(productRouting.operations || []).map((op) => op.sequence || 0)
      );
      const nextSequence = maxSequence + 1;

      const res = await fetch(
        `${API_URL}/api/v1/routings/${productRouting.id}/operations`,
        {
          method: "POST",
          headers: {
            Authorization: `Bearer ${token}`,
            "Content-Type": "application/json",
          },
          body: JSON.stringify({
            work_center_id: parseInt(newOperation.work_center_id),
            sequence: nextSequence,
            operation_name: newOperation.operation_name || `Step ${nextSequence}`,
            run_time_minutes: parseFloat(newOperation.run_time_minutes) || 0,
            setup_time_minutes: parseFloat(newOperation.setup_time_minutes) || 0,
          }),
        }
      );

      if (res.ok) {
        toast.success("Operation added to routing");
        setNewOperation({
          work_center_id: "",
          operation_name: "",
          run_time_minutes: "0",
          setup_time_minutes: "0",
        });
        setShowAddOperationToExisting(false);
        // Refresh routing to get updated operations
        await fetchProductRouting();
      } else {
        const errData = await res.json();
        toast.error(errData.detail || "Failed to add operation");
      }
    } catch (err) {
      toast.error(err.message || "Failed to add operation");
    } finally {
      setAddingOperation(false);
    }
  };

  const handleAddLine = async () => {
    if (!newLine.component_id) return;

    setLoading(true);
    try {
      const res = await fetch(`${API_URL}/api/v1/admin/bom/${bom.id}/lines`, {
        method: "POST",
        headers: {
          Authorization: `Bearer ${token}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          component_id: parseInt(newLine.component_id),
          quantity: parseFloat(newLine.quantity),
          unit: newLine.unit || null,
          sequence: parseInt(newLine.sequence, 10) || lines.length + 1,
          scrap_factor: parseFloat(newLine.scrap_factor),
          notes: newLine.notes || null,
        }),
      });

      if (res.ok) {
        const addedLine = await res.json();
        setLines([...lines, addedLine]);
        setNewLine({
          component_id: "",
          quantity: "1",
          unit: "",
          sequence: "",
          scrap_factor: "0",
          notes: "",
        });
        setShowAddLine(false);
        onUpdate();
      } else {
        const errorData = await res.json();
        toast.error(
          `Failed to add BOM line: ${errorData.detail || "Unknown error"}`
        );
      }
    } catch (err) {
      toast.error(`Failed to add BOM line: ${err.message || "Network error"}`);
    } finally {
      setLoading(false);
    }
  };

  const handleUpdateLine = async (lineId, updates) => {
    setLoading(true);
    try {
      const res = await fetch(
        `${API_URL}/api/v1/admin/bom/${bom.id}/lines/${lineId}`,
        {
          method: "PATCH",
          headers: {
            Authorization: `Bearer ${token}`,
            "Content-Type": "application/json",
          },
          body: JSON.stringify(updates),
        }
      );

      if (res.ok) {
        const updatedLine = await res.json();
        setLines(lines.map((l) => (l.id === lineId ? updatedLine : l)));
        setEditingLine(null);
        onUpdate();
      } else {
        const errorData = await res.json();
        toast.error(
          `Failed to update BOM line: ${errorData.detail || "Unknown error"}`
        );
      }
    } catch (err) {
      toast.error(
        `Failed to update BOM line: ${err.message || "Network error"}`
      );
    } finally {
      setLoading(false);
    }
  };

  const handleDeleteLine = async (lineId) => {
    if (!confirm("Are you sure you want to delete this line?")) return;

    setLoading(true);
    try {
      const res = await fetch(
        `${API_URL}/api/v1/admin/bom/${bom.id}/lines/${lineId}`,
        {
          method: "DELETE",
          headers: { Authorization: `Bearer ${token}` },
        }
      );

      if (res.ok) {
        setLines(lines.filter((l) => l.id !== lineId));
        onUpdate();
      } else {
        const errorData = await res.json();
        toast.error(
          `Failed to delete BOM line: ${errorData.detail || "Unknown error"}`
        );
      }
    } catch (err) {
      toast.error(
        `Failed to delete BOM line: ${err.message || "Network error"}`
      );
    } finally {
      setLoading(false);
    }
  };

  // handleRecalculate removed - not currently used

  return (
    <div className="space-y-6">
      {/* BOM Header Info */}
      <div className="grid grid-cols-2 gap-4 text-sm">
        <div>
          <span className="text-gray-400">Code:</span>
          <span className="text-white ml-2">{bom.code}</span>
        </div>
        <div>
          <span className="text-gray-400">Version:</span>
          <span className="text-white ml-2">
            {bom.version} ({bom.revision})
          </span>
        </div>
        <div>
          <span className="text-gray-400">Product:</span>
          <span className="text-white ml-2">
            {bom.product?.name || bom.product_id}
          </span>
        </div>
        <div>
          <span className="text-gray-400">
            {productRouting ? "Material Cost:" : "Total Cost:"}
          </span>
          <span className="text-white ml-2">
            ${parseFloat(bom.total_cost || 0).toFixed(2)}
          </span>
          {productRouting && (
            <>
              <span className="text-gray-400 ml-4">+ Labor:</span>
              <span className="text-amber-400 ml-1">
                ${calculateProcessCost().toFixed(2)}
              </span>
              {calculateOperationMaterialsCost() > 0 && (
                <>
                  <span className="text-gray-400 ml-4">+ Op Materials:</span>
                  <span className="text-blue-400 ml-1">
                    ${calculateOperationMaterialsCost().toFixed(2)}
                  </span>
                </>
              )}
              <span className="text-gray-400 ml-4">= Total:</span>
              <span className="text-green-400 ml-1 font-semibold">
                $
                {(
                  parseFloat(bom.total_cost || 0) +
                  calculateProcessCost() +
                  calculateOperationMaterialsCost()
                ).toFixed(2)}
              </span>
            </>
          )}
        </div>
      </div>

      {/* Cost Rollup Display */}
      {costRollup && costRollup.has_sub_assemblies && (
        <div className="bg-gradient-to-r from-purple-600/10 to-blue-600/10 border border-purple-500/30 rounded-lg p-4">
          <div className="flex items-center justify-between mb-2">
            <div className="flex items-center gap-2">
              <svg
                className="w-5 h-5 text-purple-400"
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 012-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10"
                />
              </svg>
              <span className="text-purple-300 font-medium">
                Multi-Level BOM
              </span>
            </div>
            <span className="text-xs bg-purple-500/20 text-purple-300 px-2 py-1 rounded-full">
              {costRollup.sub_assembly_count} Sub-Assemblies
            </span>
          </div>
          <div className="grid grid-cols-3 gap-4 text-sm">
            <div>
              <span className="text-gray-400">Direct Cost:</span>
              <span className="text-white ml-2">
                ${parseFloat(costRollup.direct_cost || 0).toFixed(2)}
              </span>
            </div>
            <div>
              <span className="text-gray-400">Sub-Assembly Cost:</span>
              <span className="text-purple-400 ml-2">
                ${parseFloat(costRollup.sub_assembly_cost || 0).toFixed(2)}
              </span>
            </div>
            <div>
              <span className="text-gray-400">Rolled-Up Total:</span>
              <span className="text-green-400 ml-2 font-semibold">
                ${parseFloat(costRollup.rolled_up_cost || 0).toFixed(2)}
              </span>
            </div>
          </div>
        </div>
      )}

      {/* Actions */}
      <div className="flex gap-2 flex-wrap">
        <button
          onClick={() => setShowAddLine(true)}
          disabled={loading}
          className="px-3 py-1.5 bg-green-600 text-white rounded-lg text-sm hover:bg-green-700 disabled:opacity-50"
        >
          Add Component
        </button>
        <button
          onClick={fetchExploded}
          disabled={loading}
          className="px-3 py-1.5 bg-purple-600 text-white rounded-lg text-sm hover:bg-purple-700 disabled:opacity-50 flex items-center gap-1"
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
              d="M4 6h16M4 10h16M4 14h16M4 18h16"
            />
          </svg>
          Explode BOM
        </button>
        <button
          onClick={() => onCreateProductionOrder(bom)}
          className="px-3 py-1.5 bg-gradient-to-r from-orange-600 to-amber-600 text-white rounded-lg text-sm hover:from-orange-500 hover:to-amber-500 flex items-center gap-1"
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
              d="M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 012-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10"
            />
          </svg>
          Create Production Order
        </button>
      </div>

      {/* Routing Materials Precedence Warning */}
      {productRouting && Object.values(operationMaterials).flat().length > 0 && (
        <div className="bg-gradient-to-r from-amber-600/10 to-orange-600/10 border border-amber-500/30 rounded-lg p-4 mb-4">
          <div className="flex items-start gap-3">
            <svg
              className="w-5 h-5 text-amber-400 flex-shrink-0 mt-0.5"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"
              />
            </svg>
            <div>
              <h4 className="text-amber-300 font-medium text-sm">Routing Materials Take Precedence</h4>
              <p className="text-amber-200/70 text-xs mt-1">
                This product has materials defined on routing operations. For MRP and production orders,
                <strong className="text-amber-200"> routing materials are used instead of the BOM lines below</strong>.
                Edit operation materials in the <span className="text-amber-300">Manufacturing Operations</span> section above.
              </p>
              <p className="text-amber-200/50 text-xs mt-1">
                BOM lines are only used as a fallback for products without routing materials.
              </p>
            </div>
          </div>
        </div>
      )}

      {/* BOM Lines Table */}
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="bg-gray-800">
            <tr>
              <th className="text-left py-2 px-3 text-gray-400">#</th>
              <th className="text-left py-2 px-3 text-gray-400">Component</th>
              <th className="text-left py-2 px-3 text-gray-400">Qty Needed</th>
              <th className="text-left py-2 px-3 text-gray-400">Unit Cost</th>
              <th className="text-left py-2 px-3 text-gray-400">Line Cost</th>
              <th className="text-right py-2 px-3 text-gray-400">Actions</th>
            </tr>
          </thead>
          <tbody>
            {lines.map((line) => (
              <tr key={line.id} className="border-b border-gray-800">
                <td className="py-2 px-3 text-gray-500">{line.sequence}</td>
                <td className="py-2 px-3">
                  <div className="flex items-center gap-2">
                    <div>
                      <div className="text-white font-medium flex items-center gap-1.5">
                        {line.component_name || `Product #${line.component_id}`}
                        {line.has_bom && (
                          <span
                            className="inline-flex items-center gap-0.5 px-1.5 py-0.5 bg-purple-500/20 text-purple-400 rounded text-xs"
                            title="Sub-assembly - has its own BOM"
                          >
                            <svg
                              className="w-3 h-3"
                              fill="none"
                              stroke="currentColor"
                              viewBox="0 0 24 24"
                            >
                              <path
                                strokeLinecap="round"
                                strokeLinejoin="round"
                                strokeWidth={2}
                                d="M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 012-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10"
                              />
                            </svg>
                            Sub
                          </span>
                        )}
                      </div>
                      <div className="text-gray-500 text-xs">
                        {line.component_sku}
                      </div>
                    </div>
                  </div>
                </td>
                <td className="py-2 px-3 text-gray-300">
                  {editingLine === line.id ? (
                    <div className="flex items-center gap-2">
                      <input
                        type="number"
                        defaultValue={line.quantity}
                        step="0.01"
                        className="w-20 bg-gray-800 border border-gray-700 rounded px-2 py-1 text-white"
                        onBlur={(e) =>
                          handleUpdateLine(line.id, {
                            quantity: parseFloat(e.target.value),
                          })
                        }
                      />
                      <select
                        defaultValue={line.unit || ""}
                        className="w-20 bg-gray-800 border border-gray-700 rounded px-2 py-1 text-white text-sm"
                        onChange={(e) =>
                          handleUpdateLine(line.id, {
                            unit: e.target.value || null,
                          })
                        }
                      >
                        <option value="">Default</option>
                        {uoms.map((u) => (
                          <option key={u.code} value={u.code}>
                            {u.code}
                          </option>
                        ))}
                      </select>
                    </div>
                  ) : (
                    <span>
                      {parseFloat(line.quantity).toFixed(2)}{" "}
                      {line.unit || line.component_unit || "EA"}
                    </span>
                  )}
                </td>
                <td className="py-2 px-3 text-gray-400">
                  ${parseFloat(line.component_cost || 0).toFixed(2)}/
                  {(() => {
                    // For materials, always show /KG regardless of line unit
                    // Materials have unit="G" (we changed all materials to G)
                    // and cost is stored per-KG (typically > $1)
                    const isMaterial =
                      line.is_material ||
                      line.component_cost_unit === "KG" ||
                      (line.component_unit === "G" &&
                        line.component_cost &&
                        parseFloat(line.component_cost) > 0.01);

                    if (isMaterial) {
                      return "KG";
                    }
                    return line.unit || line.component_unit || "EA";
                  })()}
                </td>
                <td className="py-2 px-3 text-green-400 font-medium">
                  ${parseFloat(line.line_cost || 0).toFixed(2)}
                </td>
                <td className="py-2 px-3 text-right">
                  <button
                    onClick={() =>
                      setEditingLine(editingLine === line.id ? null : line.id)
                    }
                    className="text-blue-400 hover:text-blue-300 px-2"
                  >
                    {editingLine === line.id ? "Done" : "Edit"}
                  </button>
                  <button
                    onClick={() => handleDeleteLine(line.id)}
                    className="text-red-400 hover:text-red-300 px-2"
                  >
                    Delete
                  </button>
                </td>
              </tr>
            ))}
            {lines.length === 0 && (
              <tr>
                <td colSpan={6} className="py-8 text-center text-gray-500">
                  No components added yet
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      {/* Process Path / Routing Section */}
      {showProcessPath && (
        <div className="bg-gradient-to-r from-amber-600/10 to-orange-600/10 border border-amber-500/30 rounded-lg p-4">
          <div className="flex items-center justify-between mb-3">
            <div className="flex items-center gap-2">
              <svg
                className="w-5 h-5 text-amber-400"
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2m-3 7h3m-3 4h3m-6-4h.01M9 16h.01"
                />
              </svg>
              <span className="text-amber-300 font-medium">Process Path</span>
            </div>
            {productRouting && (
              <span className="text-xs bg-amber-500/20 text-amber-300 px-2 py-1 rounded-full">
                {productRouting.operations?.length || 0} Operations
              </span>
            )}
          </div>

          {/* No routing yet - allow creating operations */}
          {!productRouting && (
            <div className="space-y-3">
              {/* Pending operations list */}
              {pendingOperations.length > 0 && (
                <div className="space-y-2">
                  <div className="text-sm text-gray-400">
                    Operations to create:
                  </div>
                  {pendingOperations.map((op, idx) => (
                    <div
                      key={idx}
                      className="flex items-center justify-between bg-gray-800 rounded-lg px-3 py-2"
                    >
                      <div className="flex items-center gap-3">
                        <span className="text-gray-500 font-mono text-sm w-6">
                          {op.sequence}
                        </span>
                        <span className="text-white">
                          {op.operation_name || op.work_center_name}
                        </span>
                        <span className="text-gray-500 text-sm">
                          @ {op.work_center_code}
                        </span>
                        <span className="text-amber-400 text-sm">
                          {op.run_time_minutes}m
                        </span>
                      </div>
                      <button
                        onClick={() => handleRemovePendingOperation(idx)}
                        className="text-red-400 hover:text-red-300 text-sm px-2"
                      >
                        ×
                      </button>
                    </div>
                  ))}
                </div>
              )}

              {/* Add operation form */}
              {showAddOperation ? (
                <div className="bg-gray-800 rounded-lg p-3 space-y-3">
                  <div className="grid grid-cols-2 gap-3">
                    <div>
                      <label className="block text-xs text-gray-400 mb-1">
                        Work Center *
                      </label>
                      <select
                        value={newOperation.work_center_id}
                        onChange={(e) =>
                          setNewOperation({
                            ...newOperation,
                            work_center_id: e.target.value,
                          })
                        }
                        className="w-full bg-gray-900 border border-gray-700 rounded px-2 py-1.5 text-white text-sm"
                      >
                        <option value="">Select work center...</option>
                        {workCenters.map((wc) => (
                          <option key={wc.id} value={wc.id}>
                            {wc.code} - {wc.name}
                          </option>
                        ))}
                      </select>
                    </div>
                    <div>
                      <label className="block text-xs text-gray-400 mb-1">
                        Operation Name
                      </label>
                      <input
                        type="text"
                        value={newOperation.operation_name}
                        onChange={(e) =>
                          setNewOperation({
                            ...newOperation,
                            operation_name: e.target.value,
                          })
                        }
                        placeholder="e.g., Print Part"
                        className="w-full bg-gray-900 border border-gray-700 rounded px-2 py-1.5 text-white text-sm"
                      />
                    </div>
                  </div>
                  <div className="grid grid-cols-2 gap-3">
                    <div>
                      <label className="block text-xs text-gray-400 mb-1">
                        Run Time (min)
                      </label>
                      <input
                        type="number"
                        step="0.1"
                        value={newOperation.run_time_minutes}
                        onChange={(e) =>
                          setNewOperation({
                            ...newOperation,
                            run_time_minutes: e.target.value,
                          })
                        }
                        className="w-full bg-gray-900 border border-gray-700 rounded px-2 py-1.5 text-white text-sm"
                      />
                    </div>
                    <div>
                      <label className="block text-xs text-gray-400 mb-1">
                        Setup Time (min)
                      </label>
                      <input
                        type="number"
                        step="0.1"
                        value={newOperation.setup_time_minutes}
                        onChange={(e) =>
                          setNewOperation({
                            ...newOperation,
                            setup_time_minutes: e.target.value,
                          })
                        }
                        className="w-full bg-gray-900 border border-gray-700 rounded px-2 py-1.5 text-white text-sm"
                      />
                    </div>
                  </div>
                  <div className="flex gap-2">
                    <button
                      onClick={handleAddPendingOperation}
                      disabled={!newOperation.work_center_id}
                      className="px-3 py-1.5 bg-amber-600 text-white rounded text-sm hover:bg-amber-700 disabled:opacity-50"
                    >
                      Add Operation
                    </button>
                    <button
                      onClick={() => setShowAddOperation(false)}
                      className="px-3 py-1.5 bg-gray-700 text-white rounded text-sm hover:bg-gray-600"
                    >
                      Cancel
                    </button>
                  </div>
                </div>
              ) : (
                <div className="flex gap-2">
                  <button
                    onClick={() => setShowAddOperation(true)}
                    className="px-3 py-1.5 bg-amber-600 text-white rounded-lg text-sm hover:bg-amber-700 flex items-center gap-1"
                  >
                    <span>+</span> Add Operation
                  </button>
                  {pendingOperations.length > 0 && (
                    <button
                      onClick={handleSaveRouting}
                      disabled={savingRouting}
                      className="px-3 py-1.5 bg-green-600 text-white rounded-lg text-sm hover:bg-green-700 disabled:opacity-50"
                    >
                      {savingRouting ? "Saving..." : "Save Routing"}
                    </button>
                  )}
                </div>
              )}

              {/* Template option - show only if templates exist and no pending ops */}
              {routingTemplates.length > 0 &&
                pendingOperations.length === 0 &&
                !showAddOperation && (
                  <div className="pt-2 border-t border-gray-700">
                    <p className="text-xs text-gray-500 mb-2">
                      Or apply a template:
                    </p>
                    <div className="flex gap-2">
                      <select
                        value={selectedTemplateId}
                        onChange={(e) => setSelectedTemplateId(e.target.value)}
                        className="flex-1 bg-gray-800 border border-gray-700 rounded-lg px-3 py-1.5 text-white text-sm"
                      >
                        <option value="">Select template...</option>
                        {routingTemplates.map((t) => (
                          <option key={t.id} value={t.id}>
                            {t.code} - {t.name || "Unnamed"}
                          </option>
                        ))}
                      </select>
                      <button
                        onClick={handleApplyTemplate}
                        disabled={!selectedTemplateId || applyingTemplate}
                        className="px-3 py-1.5 bg-gray-700 text-white rounded-lg text-sm hover:bg-gray-600 disabled:opacity-50"
                      >
                        {applyingTemplate ? "..." : "Apply"}
                      </button>
                    </div>
                  </div>
                )}
            </div>
          )}

          {/* Existing routing - show operations */}
          {productRouting && (
            <div className="space-y-3">
              <div className="flex items-center justify-between text-sm">
                <span className="text-gray-400">
                  Routing:{" "}
                  <span className="text-white">
                    {productRouting.code || productRouting.routing_code}
                  </span>
                </span>
                <span className="text-gray-400">
                  Total Time:{" "}
                  <span className="text-amber-400 font-medium">
                    {formatTime(productRouting.total_run_time_minutes)}
                  </span>
                </span>
              </div>

              {/* Operations table */}
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead className="bg-gray-800/50">
                    <tr>
                      <th className="text-left py-2 px-3 text-gray-400">#</th>
                      <th className="text-left py-2 px-3 text-gray-400">
                        Operation
                      </th>
                      <th className="text-left py-2 px-3 text-gray-400">
                        Work Center
                      </th>
                      <th className="text-left py-2 px-3 text-gray-400">
                        Run Time
                      </th>
                      <th className="text-left py-2 px-3 text-gray-400">
                        Setup
                      </th>
                      <th className="text-left py-2 px-3 text-gray-400">
                        Cost
                      </th>
                      <th className="text-center py-2 px-3 text-gray-400">
                        Actions
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {(productRouting.operations || []).map((op, idx) => (
                      <React.Fragment key={op.id || idx}>
                        {/* Main operation row */}
                        <tr className="border-b border-gray-800">
                          <td className="py-2 px-3">
                            <div className="flex items-center gap-2">
                              <button
                                onClick={() =>
                                  setExpandedOperations((prev) => ({
                                    ...prev,
                                    [op.id]: !prev[op.id],
                                  }))
                                }
                                className="text-gray-400 hover:text-white p-1 rounded hover:bg-gray-700 transition-colors"
                                title="Show materials"
                              >
                                <svg
                                  className={`w-4 h-4 transition-transform ${
                                    expandedOperations[op.id] ? "rotate-90" : ""
                                  }`}
                                  fill="none"
                                  stroke="currentColor"
                                  viewBox="0 0 24 24"
                                >
                                  <path
                                    strokeLinecap="round"
                                    strokeLinejoin="round"
                                    strokeWidth={2}
                                    d="M9 5l7 7-7 7"
                                  />
                                </svg>
                              </button>
                              <input
                                type="number"
                                min="1"
                                step="1"
                                defaultValue={op.sequence}
                                onBlur={async (e) => {
                                  const newSequence =
                                    parseInt(e.target.value) || 1;
                                  if (newSequence === op.sequence) return;
                                  try {
                                    const res = await fetch(
                                      `${API_URL}/api/v1/routings/operations/${op.id}`,
                                      {
                                        method: "PUT",
                                        headers: {
                                          Authorization: `Bearer ${token}`,
                                          "Content-Type": "application/json",
                                        },
                                        body: JSON.stringify({
                                          sequence: newSequence,
                                        }),
                                      }
                                    );
                                    if (res.ok) {
                                      await fetchProductRouting();
                                    } else {
                                      toast.error("Failed to update sequence");
                                    }
                                  } catch (err) {
                                    toast.error(`Error: ${err.message}`);
                                  }
                                }}
                                className="w-12 text-center bg-gray-800 border border-gray-700 rounded px-2 py-1 text-white"
                              />
                            </div>
                          </td>
                          <td className="py-2 px-3">
                            <div className="text-white font-medium">
                              {op.operation_name || op.operation_code}
                            </div>
                            {op.operation_code && op.operation_name && (
                              <div className="text-gray-500 text-xs">
                                {op.operation_code}
                              </div>
                            )}
                          </td>
                          <td className="py-2 px-3 text-gray-400">
                            {op.work_center_name || op.work_center_code}
                          </td>
                          <td className="py-2 px-3">
                            <input
                              type="number"
                              step="0.1"
                              value={
                                timeOverrides[op.operation_code]
                                  ?.run_time_minutes ??
                                parseFloat(op.run_time_minutes || 0)
                              }
                              onChange={(e) =>
                                updateOperationTime(
                                  op.operation_code,
                                  "run_time_minutes",
                                  e.target.value
                                )
                              }
                              onBlur={(e) =>
                                saveOperationTime(
                                  op.id,
                                  "run_time_minutes",
                                  e.target.value
                                )
                              }
                              className="w-20 bg-gray-800 border border-gray-700 rounded px-2 py-1 text-white text-sm"
                            />
                            <span className="text-gray-500 text-xs ml-1">
                              min
                            </span>
                          </td>
                          <td className="py-2 px-3">
                            <input
                              type="number"
                              step="0.1"
                              value={
                                timeOverrides[op.operation_code]
                                  ?.setup_time_minutes ??
                                parseFloat(op.setup_time_minutes || 0)
                              }
                              onChange={(e) =>
                                updateOperationTime(
                                  op.operation_code,
                                  "setup_time_minutes",
                                  e.target.value
                                )
                              }
                              onBlur={(e) =>
                                saveOperationTime(
                                  op.id,
                                  "setup_time_minutes",
                                  e.target.value
                                )
                              }
                              className="w-16 bg-gray-800 border border-gray-700 rounded px-2 py-1 text-white text-sm"
                            />
                            <span className="text-gray-500 text-xs ml-1">
                              min
                            </span>
                          </td>
                          <td className="py-2 px-3 text-green-400">
                            ${parseFloat(op.calculated_cost || 0).toFixed(2)}
                          </td>
                          <td className="py-2 px-3 text-center">
                            <button
                              onClick={() =>
                                handleDeleteOperation(
                                  op.id,
                                  op.operation_name || op.operation_code
                                )
                              }
                              className="text-red-400 hover:text-red-300 text-sm px-2 py-1 rounded hover:bg-red-400/10 transition-colors"
                              title="Remove operation"
                            >
                              Remove
                            </button>
                          </td>
                        </tr>

                        {/* Expanded materials section */}
                        {expandedOperations[op.id] && (
                          <tr className="bg-gray-800/30">
                            <td colSpan={7} className="py-3 px-6">
                              <div className="ml-6 border-l-2 border-blue-500/30 pl-4">
                                <div className="flex items-center justify-between mb-2">
                                  <span className="text-sm text-blue-400 font-medium flex items-center gap-2">
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
                                        d="M20 7l-8-4-8 4m16 0l-8 4m8-4v10l-8 4m0-10L4 7m8 4v10M4 7v10l8 4"
                                      />
                                    </svg>
                                    Materials Consumed at this Operation
                                  </span>
                                  <button
                                    onClick={() =>
                                      setShowAddMaterialModal(op.id)
                                    }
                                    className="px-2 py-1 bg-blue-600 text-white rounded text-xs hover:bg-blue-700 flex items-center gap-1"
                                  >
                                    <span>+</span> Add Material
                                  </button>
                                </div>

                                {/* Materials list */}
                                {operationMaterials[op.id] &&
                                operationMaterials[op.id].length > 0 ? (
                                  <table className="w-full text-xs">
                                    <thead className="bg-gray-900/50">
                                      <tr>
                                        <th className="text-left py-1.5 px-2 text-gray-500">
                                          Component
                                        </th>
                                        <th className="text-left py-1.5 px-2 text-gray-500">
                                          Qty/Unit
                                        </th>
                                        <th className="text-left py-1.5 px-2 text-gray-500">
                                          Scrap %
                                        </th>
                                        <th className="text-left py-1.5 px-2 text-gray-500">
                                          Unit Cost
                                        </th>
                                        <th className="text-left py-1.5 px-2 text-gray-500">
                                          Ext. Cost
                                        </th>
                                        <th className="text-right py-1.5 px-2 text-gray-500">
                                          Actions
                                        </th>
                                      </tr>
                                    </thead>
                                    <tbody>
                                      {operationMaterials[op.id].map((mat) => (
                                        <tr
                                          key={mat.id}
                                          className="border-b border-gray-700/50"
                                        >
                                          <td className="py-1.5 px-2">
                                            <div className="text-white">
                                              {mat.component_name}
                                            </div>
                                            <div className="text-gray-500 text-xs">
                                              {mat.component_sku}
                                            </div>
                                          </td>
                                          <td className="py-1.5 px-2 text-gray-300">
                                            {parseFloat(
                                              mat.quantity || 0
                                            ).toFixed(3)}{" "}
                                            {mat.unit ||
                                              mat.component_unit ||
                                              "EA"}
                                            {mat.quantity_per !== "unit" && (
                                              <span className="text-gray-500 text-xs ml-1">/{mat.quantity_per}</span>
                                            )}
                                          </td>
                                          <td className="py-1.5 px-2 text-gray-400">
                                            {parseFloat(
                                              mat.scrap_factor || 0
                                            ).toFixed(1)}
                                            %
                                          </td>
                                          <td className="py-1.5 px-2 text-gray-400">
                                            $
                                            {parseFloat(
                                              mat.unit_cost || 0
                                            ).toFixed(4)}
                                          </td>
                                          <td className="py-1.5 px-2 text-green-400">
                                            $
                                            {parseFloat(
                                              mat.extended_cost || 0
                                            ).toFixed(4)}
                                          </td>
                                          <td className="py-1.5 px-2 text-right">
                                            <button
                                              onClick={() =>
                                                handleDeleteMaterial(
                                                  op.id,
                                                  mat.id
                                                )
                                              }
                                              className="text-red-400 hover:text-red-300"
                                            >
                                              ×
                                            </button>
                                          </td>
                                        </tr>
                                      ))}
                                    </tbody>
                                  </table>
                                ) : (
                                  <div className="text-gray-500 text-xs py-2 italic">
                                    No materials assigned to this operation.
                                    Click "+ Add Material" to assign components.
                                  </div>
                                )}
                              </div>
                            </td>
                          </tr>
                        )}
                      </React.Fragment>
                    ))}
                  </tbody>
                </table>
              </div>

              {/* Actions for existing routing */}
              <div className="pt-2 border-t border-gray-700 space-y-3">
                {/* Add Operation Form */}
                {showAddOperationToExisting ? (
                  <div className="bg-gray-800 rounded-lg p-3 space-y-3">
                    <div className="grid grid-cols-2 gap-3">
                      <div>
                        <label className="block text-xs text-gray-400 mb-1">
                          Work Center *
                        </label>
                        <select
                          value={newOperation.work_center_id}
                          onChange={(e) =>
                            setNewOperation({
                              ...newOperation,
                              work_center_id: e.target.value,
                            })
                          }
                          className="w-full bg-gray-900 border border-gray-700 rounded px-2 py-1.5 text-white text-sm"
                        >
                          <option value="">Select work center...</option>
                          {workCenters.map((wc) => (
                            <option key={wc.id} value={wc.id}>
                              {wc.code} - {wc.name}
                            </option>
                          ))}
                        </select>
                      </div>
                      <div>
                        <label className="block text-xs text-gray-400 mb-1">
                          Operation Name
                        </label>
                        <input
                          type="text"
                          value={newOperation.operation_name}
                          onChange={(e) =>
                            setNewOperation({
                              ...newOperation,
                              operation_name: e.target.value,
                            })
                          }
                          placeholder="e.g., Print, QC, Pack"
                          className="w-full bg-gray-900 border border-gray-700 rounded px-2 py-1.5 text-white text-sm"
                        />
                      </div>
                    </div>
                    <div className="grid grid-cols-2 gap-3">
                      <div>
                        <label className="block text-xs text-gray-400 mb-1">
                          Run Time (min)
                        </label>
                        <input
                          type="number"
                          value={newOperation.run_time_minutes}
                          onChange={(e) =>
                            setNewOperation({
                              ...newOperation,
                              run_time_minutes: e.target.value,
                            })
                          }
                          className="w-full bg-gray-900 border border-gray-700 rounded px-2 py-1.5 text-white text-sm"
                        />
                      </div>
                      <div>
                        <label className="block text-xs text-gray-400 mb-1">
                          Setup Time (min)
                        </label>
                        <input
                          type="number"
                          value={newOperation.setup_time_minutes}
                          onChange={(e) =>
                            setNewOperation({
                              ...newOperation,
                              setup_time_minutes: e.target.value,
                            })
                          }
                          className="w-full bg-gray-900 border border-gray-700 rounded px-2 py-1.5 text-white text-sm"
                        />
                      </div>
                    </div>
                    <div className="flex gap-2">
                      <button
                        onClick={handleAddOperationToExisting}
                        disabled={!newOperation.work_center_id || addingOperation}
                        className="px-3 py-1.5 bg-green-600 text-white rounded text-sm hover:bg-green-700 disabled:opacity-50"
                      >
                        {addingOperation ? "Adding..." : "Add Operation"}
                      </button>
                      <button
                        onClick={() => setShowAddOperationToExisting(false)}
                        className="px-3 py-1.5 bg-gray-700 text-white rounded text-sm hover:bg-gray-600"
                      >
                        Cancel
                      </button>
                    </div>
                  </div>
                ) : (
                  <div className="flex gap-2">
                    <button
                      onClick={() => setShowAddOperationToExisting(true)}
                      className="px-3 py-1.5 bg-amber-600 text-white rounded-lg text-sm hover:bg-amber-700 flex items-center gap-1"
                    >
                      <span>+</span> Add Operation
                    </button>
                  </div>
                )}

                {/* Template selector */}
                <div className="flex gap-2">
                  <select
                    value={selectedTemplateId}
                    onChange={(e) => setSelectedTemplateId(e.target.value)}
                    className="bg-gray-800 border border-gray-700 rounded-lg px-3 py-1.5 text-white text-sm"
                  >
                    <option value="">Change template...</option>
                    {routingTemplates.map((t) => (
                      <option key={t.id} value={t.id}>
                        {t.code} - {t.name || "Unnamed"}
                      </option>
                    ))}
                  </select>
                  <button
                    onClick={handleApplyTemplate}
                    disabled={!selectedTemplateId || applyingTemplate}
                    className="px-3 py-1.5 bg-amber-600 text-white rounded-lg text-sm hover:bg-amber-700 disabled:opacity-50"
                  >
                    {applyingTemplate ? "Applying..." : "Apply"}
                  </button>
                </div>
              </div>
            </div>
          )}
        </div>
      )}

      {/* Add Line Form */}
      {showAddLine && (
        <div className="bg-gray-800 rounded-lg p-4 space-y-4">
          <h4 className="font-medium text-white">Add Component</h4>
          {/* Selected component info */}
          {newLine.component_id &&
            (() => {
              const selected = products.find(
                (p) => String(p.id) === String(newLine.component_id)
              );
              if (!selected) return null;
              const cost =
                selected.standard_cost ||
                selected.average_cost ||
                selected.selling_price ||
                0;
              return (
                <div className="bg-gray-900 rounded-lg p-3 flex items-center justify-between">
                  <div>
                    <span className="text-white font-medium">
                      {selected.name}
                    </span>
                    <span className="text-gray-500 ml-2">({selected.sku})</span>
                  </div>
                  <div className="text-right">
                    <span className="text-green-400 font-mono">
                      ${parseFloat(cost).toFixed(2)}
                    </span>
                    <span className="text-gray-500 ml-1">
                      / {selected.unit || "EA"}
                    </span>
                  </div>
                </div>
              );
            })()}
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-sm text-gray-400 mb-1">
                Component
              </label>
              <SearchableSelect
                options={products}
                value={newLine.component_id}
                onChange={(val) => {
                  const selected = products.find(
                    (p) => String(p.id) === String(val)
                  );
                  setNewLine({
                    ...newLine,
                    component_id: val,
                    unit: selected?.unit || newLine.unit,
                  });
                }}
                placeholder="Select component..."
                displayKey="name"
                valueKey="id"
                formatOption={(p) => {
                  const cost =
                    p.standard_cost || p.average_cost || p.selling_price || 0;
                  return `${p.name} (${p.sku}) - $${parseFloat(cost).toFixed(
                    2
                  )}/${p.unit || "EA"}`;
                }}
              />
            </div>
            <div>
              <label className="block text-sm text-gray-400 mb-1">
                Quantity
              </label>
              <div className="flex">
                <input
                  type="number"
                  step="0.001"
                  value={newLine.quantity}
                  onChange={(e) =>
                    setNewLine({ ...newLine, quantity: e.target.value })
                  }
                  className="flex-1 bg-gray-900 border border-gray-700 rounded-l-lg px-3 py-2 text-white"
                />
                <span className="bg-gray-700 border border-l-0 border-gray-700 rounded-r-lg px-3 py-2 text-gray-300 font-mono text-sm">
                  {newLine.unit ||
                    (() => {
                      const selected = products.find(
                        (p) => String(p.id) === String(newLine.component_id)
                      );
                      return selected?.unit || "EA";
                    })()}
                </span>
              </div>
            </div>
            <div>
              <label className="block text-sm text-gray-400 mb-1">
                Unit Override
              </label>
              <select
                value={newLine.unit}
                onChange={(e) =>
                  setNewLine({ ...newLine, unit: e.target.value })
                }
                className="w-full bg-gray-900 border border-gray-700 rounded-lg px-3 py-2 text-white"
              >
                <option value="">Use component default</option>
                {uoms.map((u) => (
                  <option key={u.code} value={u.code}>
                    {u.code} - {u.name}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label className="block text-sm text-gray-400 mb-1">
                Scrap Factor %
              </label>
              <input
                type="number"
                step="0.1"
                value={newLine.scrap_factor}
                onChange={(e) =>
                  setNewLine({ ...newLine, scrap_factor: e.target.value })
                }
                className="w-full bg-gray-900 border border-gray-700 rounded-lg px-3 py-2 text-white"
              />
            </div>
            <div>
              <label className="block text-sm text-gray-400 mb-1">Notes</label>
              <input
                type="text"
                value={newLine.notes}
                onChange={(e) =>
                  setNewLine({ ...newLine, notes: e.target.value })
                }
                className="w-full bg-gray-900 border border-gray-700 rounded-lg px-3 py-2 text-white"
              />
            </div>
          </div>
          <div className="flex gap-2">
            <button
              onClick={handleAddLine}
              disabled={loading || !newLine.component_id}
              className="px-4 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700 disabled:opacity-50"
            >
              Add Component
            </button>
            <button
              onClick={() => setShowAddLine(false)}
              className="px-4 py-2 bg-gray-700 text-white rounded-lg hover:bg-gray-600"
            >
              Cancel
            </button>
          </div>
        </div>
      )}

      <div className="flex justify-end pt-4 border-t border-gray-800">
        <button
          onClick={onClose}
          className="px-4 py-2 bg-gray-700 text-white rounded-lg hover:bg-gray-600"
        >
          Close
        </button>
      </div>

      {/* Purchase Request Modal */}
      <Modal
        isOpen={!!purchaseLine}
        onClose={() => setPurchaseLine(null)}
        title="Create Purchase Request"
        className="w-full max-w-2xl"
      >
        <div className="p-6">
          <div className="flex justify-between items-center mb-4">
            <h2 className="text-lg font-semibold text-white">Create Purchase Request</h2>
            <button onClick={() => setPurchaseLine(null)} className="text-gray-400 hover:text-white p-1" aria-label="Close">
              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          </div>
          {purchaseLine && (
            <PurchaseRequestModal
              line={purchaseLine}
              onClose={() => setPurchaseLine(null)}
              token={token}
              onSuccess={() => {
                setPurchaseLine(null);
                onUpdate && onUpdate();
              }}
            />
          )}
        </div>
      </Modal>

      {/* Work Order Request Modal */}
      <Modal
        isOpen={!!workOrderLine}
        onClose={() => setWorkOrderLine(null)}
        title="Create Work Order"
        className="w-full max-w-2xl"
      >
        <div className="p-6">
          <div className="flex justify-between items-center mb-4">
            <h2 className="text-lg font-semibold text-white">Create Work Order</h2>
            <button onClick={() => setWorkOrderLine(null)} className="text-gray-400 hover:text-white p-1" aria-label="Close">
              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          </div>
          {workOrderLine && (
            <WorkOrderRequestModal
              line={workOrderLine}
              onClose={() => setWorkOrderLine(null)}
              token={token}
              onSuccess={() => {
                setWorkOrderLine(null);
                onUpdate && onUpdate();
              }}
            />
          )}
        </div>
      </Modal>

      {/* Add Material to Operation Modal */}
      <Modal
        isOpen={!!showAddMaterialModal}
        onClose={() => {
          setShowAddMaterialModal(null);
          setNewMaterial({
            component_id: "",
            quantity: "1",
            quantity_per: "unit",
            scrap_factor: "0",
            unit: "",
          });
        }}
        title="Add Material to Operation"
        className="w-full max-w-2xl"
      >
        <div className="p-6">
          <div className="flex justify-between items-center mb-4">
            <h2 className="text-lg font-semibold text-white">Add Material to Operation</h2>
            <button onClick={() => {
              setShowAddMaterialModal(null);
              setNewMaterial({
                component_id: "",
                quantity: "1",
                quantity_per: "unit",
                scrap_factor: "0",
                unit: "",
              });
            }} className="text-gray-400 hover:text-white p-1" aria-label="Close">
              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          </div>
          <div className="space-y-4">
            <div>
              <label className="block text-sm text-gray-400 mb-1">
                Component *
              </label>
              <SearchableSelect
                options={products}
                value={newMaterial.component_id}
                onChange={(val) => {
                  const selected = products.find(
                    (p) => String(p.id) === String(val)
                  );
                  setNewMaterial({
                    ...newMaterial,
                    component_id: val,
                    unit: selected?.unit || "",
                  });
                }}
                placeholder="Select component..."
                displayKey="name"
                valueKey="id"
                formatOption={(p) => {
                  const cost =
                    p.standard_cost || p.average_cost || p.selling_price || 0;
                  return `${p.name} (${p.sku}) - ${parseFloat(cost).toFixed(2)}/${
                    p.unit || "EA"
                  }`;
                }}
              />
            </div>

            <div className="grid grid-cols-3 gap-4">
              <div>
                <label className="block text-sm text-gray-400 mb-1">
                  Quantity *
                </label>
                <input
                  type="number"
                  step="0.001"
                  value={newMaterial.quantity}
                  onChange={(e) =>
                    setNewMaterial({
                      ...newMaterial,
                      quantity: e.target.value,
                    })
                  }
                  className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-white"
                />
              </div>
              <div>
                <label className="block text-sm text-gray-400 mb-1">
                  Scrap %
                </label>
                <input
                  type="number"
                  step="0.1"
                  value={newMaterial.scrap_factor}
                  onChange={(e) =>
                    setNewMaterial({
                      ...newMaterial,
                      scrap_factor: e.target.value,
                    })
                  }
                  className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-white"
                />
              </div>
              <div>
                <label className="block text-sm text-gray-400 mb-1">
                  Unit
                </label>
                <select
                  value={newMaterial.unit}
                  onChange={(e) =>
                    setNewMaterial({ ...newMaterial, unit: e.target.value })
                  }
                  className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-white"
                >
                  <option value="">Use component default</option>
                  {uoms.map((u) => (
                    <option key={u.code} value={u.code}>
                      {u.code} - {u.name}
                    </option>
                  ))}
                </select>
              </div>
            </div>

            <div className="flex gap-2 pt-2">
              <button
                onClick={() => handleAddMaterial(showAddMaterialModal)}
                disabled={!newMaterial.component_id}
                className="flex-1 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50"
              >
                Add Material
              </button>
              <button
                onClick={() => {
                  setShowAddMaterialModal(null);
                  setNewMaterial({
                    component_id: "",
                    quantity: "1",
                    quantity_per: "unit",
                    scrap_factor: "0",
                    unit: "",
                  });
                }}
                className="px-4 py-2 bg-gray-700 text-white rounded-lg hover:bg-gray-600"
              >
                Cancel
              </button>
            </div>
          </div>
        </div>
      </Modal>

      {/* Exploded BOM View Modal */}
      <Modal
        isOpen={showExploded && !!explodedData}
        onClose={() => setShowExploded(false)}
        title="Exploded BOM View"
        className="w-full max-w-4xl"
      >
        {explodedData && (
          <div className="p-6">
            <div className="flex justify-between items-center mb-4">
              <div>
                <h2 className="text-lg font-semibold text-white">
                  Exploded BOM View
                </h2>
                <p className="text-sm text-gray-400">
                  All components flattened through sub-assemblies
                </p>
              </div>
              <button
                onClick={() => setShowExploded(false)}
                className="text-gray-400 hover:text-white p-1"
                aria-label="Close"
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
                    d="M6 18L18 6M6 6l12 12"
                  />
                </svg>
              </button>
            </div>

            {/* Summary Stats */}
            <div className="grid grid-cols-4 gap-4 mb-4">
              <div className="bg-gray-800 rounded-lg p-3 text-center">
                <div className="text-2xl font-bold text-white">
                  {explodedData.total_components}
                </div>
                <div className="text-xs text-gray-400">Total Components</div>
              </div>
              <div className="bg-gray-800 rounded-lg p-3 text-center">
                <div className="text-2xl font-bold text-purple-400">
                  {explodedData.max_depth}
                </div>
                <div className="text-xs text-gray-400">Max Depth</div>
              </div>
              <div className="bg-gray-800 rounded-lg p-3 text-center">
                <div className="text-2xl font-bold text-green-400">
                  ${parseFloat(explodedData.total_cost || 0).toFixed(2)}
                </div>
                <div className="text-xs text-gray-400">Total Cost</div>
              </div>
              <div className="bg-gray-800 rounded-lg p-3 text-center">
                <div className="text-2xl font-bold text-blue-400">
                  {explodedData.unique_components}
                </div>
                <div className="text-xs text-gray-400">Unique Parts</div>
              </div>
            </div>

            {/* Exploded Lines Table */}
            <div className="max-h-96 overflow-y-auto">
              <table className="w-full text-sm">
                <thead className="bg-gray-800 sticky top-0">
                  <tr>
                    <th className="text-left py-2 px-3 text-gray-400">
                      Level
                    </th>
                    <th className="text-left py-2 px-3 text-gray-400">
                      Component
                    </th>
                    <th className="text-left py-2 px-3 text-gray-400">
                      Qty/Unit
                    </th>
                    <th className="text-left py-2 px-3 text-gray-400">
                      Extended Qty
                    </th>
                    <th className="text-left py-2 px-3 text-gray-400">
                      Unit Cost
                    </th>
                    <th className="text-left py-2 px-3 text-gray-400">
                      Line Cost
                    </th>
                    <th className="text-left py-2 px-3 text-gray-400">
                      Stock
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {explodedData.lines?.map((line, idx) => (
                    <tr
                      key={idx}
                      className={`border-b border-gray-800 ${
                        line.is_sub_assembly ? "bg-purple-500/5" : ""
                      }`}
                    >
                      <td className="py-2 px-3">
                        <div className="flex items-center gap-1">
                          {/* Indent based on level */}
                          <span
                            style={{ marginLeft: `${line.level * 12}px` }}
                            className="text-gray-500"
                          >
                            {line.level === 0 ? "" : "└─"}
                          </span>
                          <span
                            className={`px-1.5 py-0.5 rounded text-xs ${
                              line.level === 0
                                ? "bg-blue-500/20 text-blue-400"
                                : line.level === 1
                                ? "bg-green-500/20 text-green-400"
                                : line.level === 2
                                ? "bg-yellow-500/20 text-yellow-400"
                                : "bg-gray-500/20 text-gray-400"
                            }`}
                          >
                            L{line.level}
                          </span>
                        </div>
                      </td>
                      <td className="py-2 px-3">
                        <div className="flex items-center gap-2">
                          <div>
                            <div className="text-white font-medium flex items-center gap-1">
                              {line.component_name}
                              {line.is_sub_assembly && (
                                <span className="text-purple-400 text-xs">
                                  (Sub)
                                </span>
                              )}
                            </div>
                            <div className="text-gray-500 text-xs">
                              {line.component_sku}
                            </div>
                          </div>
                        </div>
                      </td>
                      <td className="py-2 px-3 text-gray-400">
                        {parseFloat(line.quantity_per_unit || 0).toFixed(2)}
                      </td>
                      <td className="py-2 px-3 text-white font-medium">
                        {parseFloat(line.extended_quantity || 0).toFixed(2)}
                      </td>
                      <td className="py-2 px-3 text-gray-400">
                        ${parseFloat(line.unit_cost || 0).toFixed(2)}
                      </td>
                      <td className="py-2 px-3 text-green-400">
                        ${parseFloat(line.line_cost || 0).toFixed(2)}
                      </td>
                      <td className="py-2 px-3">
                        {line.inventory_available >=
                        line.extended_quantity ? (
                          <span className="text-green-400 text-xs">
                            OK ({line.inventory_available?.toFixed(1)})
                          </span>
                        ) : (
                          <span className="text-red-400 text-xs">
                            Low ({line.inventory_available?.toFixed(1)})
                          </span>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            <div className="flex justify-end pt-4 border-t border-gray-800 mt-4">
              <button
                onClick={() => setShowExploded(false)}
                className="px-4 py-2 bg-gray-700 text-white rounded-lg hover:bg-gray-600"
              >
                Close
              </button>
            </div>
          </div>
        )}
      </Modal>
    </div>
  );
}
