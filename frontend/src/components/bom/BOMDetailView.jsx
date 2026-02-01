import { useState, useEffect, useCallback } from "react";
import { API_URL } from "../../config/api";
import { useToast } from "../Toast";
import Modal from "../Modal";
import PurchaseRequestModal from "./PurchaseRequestModal";
import WorkOrderRequestModal from "./WorkOrderRequestModal";
import ExplodedBOMView from "./ExplodedBOMView";
import BOMLinesList from "./BOMLinesList";
import BOMAddLineForm from "./BOMAddLineForm";
import BOMRoutingSection from "./BOMRoutingSection";
import AddOperationMaterialForm from "./AddOperationMaterialForm";

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
  const closeMaterialModal = () => {
    setShowAddMaterialModal(null);
    setNewMaterial({
      component_id: "",
      quantity: "1",
      quantity_per: "unit",
      scrap_factor: "0",
      unit: "",
    });
  };

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
      <BOMLinesList
        lines={lines}
        editingLine={editingLine}
        setEditingLine={setEditingLine}
        uoms={uoms}
        onUpdateLine={handleUpdateLine}
        onDeleteLine={handleDeleteLine}
      />

      <BOMRoutingSection
        showProcessPath={showProcessPath}
        productRouting={productRouting}
        operationMaterials={operationMaterials}
        expandedOperations={expandedOperations}
        setExpandedOperations={setExpandedOperations}
        timeOverrides={timeOverrides}
        showAddOperation={showAddOperation}
        setShowAddOperation={setShowAddOperation}
        showAddOperationToExisting={showAddOperationToExisting}
        setShowAddOperationToExisting={setShowAddOperationToExisting}
        pendingOperations={pendingOperations}
        newOperation={newOperation}
        setNewOperation={setNewOperation}
        workCenters={workCenters}
        routingTemplates={routingTemplates}
        selectedTemplateId={selectedTemplateId}
        setSelectedTemplateId={setSelectedTemplateId}
        applyingTemplate={applyingTemplate}
        savingRouting={savingRouting}
        addingOperation={addingOperation}
        setShowAddMaterialModal={setShowAddMaterialModal}
        token={token}
        handleAddPendingOperation={handleAddPendingOperation}
        handleRemovePendingOperation={handleRemovePendingOperation}
        handleSaveRouting={handleSaveRouting}
        handleApplyTemplate={handleApplyTemplate}
        updateOperationTime={updateOperationTime}
        saveOperationTime={saveOperationTime}
        handleDeleteOperation={handleDeleteOperation}
        handleDeleteMaterial={handleDeleteMaterial}
        handleAddOperationToExisting={handleAddOperationToExisting}
        formatTime={formatTime}
        fetchProductRouting={fetchProductRouting}
        toast={toast}
      />

      {/* Add Line Form */}
      {showAddLine && (
        <BOMAddLineForm
          newLine={newLine}
          setNewLine={setNewLine}
          products={products}
          uoms={uoms}
          loading={loading}
          onAddLine={handleAddLine}
          onCancel={() => setShowAddLine(false)}
        />
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
        onClose={closeMaterialModal}
        title="Add Material to Operation"
        className="w-full max-w-2xl"
      >
        <AddOperationMaterialForm
          newMaterial={newMaterial}
          setNewMaterial={setNewMaterial}
          products={products}
          uoms={uoms}
          onSubmit={() => handleAddMaterial(showAddMaterialModal)}
          onClose={closeMaterialModal}
        />
      </Modal>

      {/* Exploded BOM View Modal */}
      <Modal
        isOpen={showExploded && !!explodedData}
        onClose={() => setShowExploded(false)}
        title="Exploded BOM View"
        className="w-full max-w-4xl"
      >
        {explodedData && (
          <ExplodedBOMView
            explodedData={explodedData}
            onClose={() => setShowExploded(false)}
          />
        )}
      </Modal>
    </div>
  );
}
