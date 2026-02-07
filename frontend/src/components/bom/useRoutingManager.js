import { useState, useEffect, useCallback } from "react";
import { API_URL } from "../../config/api.js";

/**
 * Custom hook that manages all routing-related state and operations
 * for a BOM detail view: product routing, templates, operations,
 * operation materials, and time overrides.
 */
export default function useRoutingManager({ bom, toast }) {
  // Process Path / Routing state
  const [routingTemplates, setRoutingTemplates] = useState([]);
  const [productRouting, setProductRouting] = useState(null);

  // Operation materials state
  const [expandedOperations, setExpandedOperations] = useState({});
  const [operationMaterials, setOperationMaterials] = useState({});
  const [showAddMaterialModal, setShowAddMaterialModal] = useState(null);
  const [newMaterial, setNewMaterial] = useState({
    component_id: "",
    quantity: "1",
    quantity_per: "unit",
    scrap_factor: "0",
    unit: "",
  });

  const [selectedTemplateId, setSelectedTemplateId] = useState("");
  const [timeOverrides, setTimeOverrides] = useState({});
  const [applyingTemplate, setApplyingTemplate] = useState(false);
  const [workCenters, setWorkCenters] = useState([]);
  const [showAddOperation, setShowAddOperation] = useState(false);
  const [showAddOperationToExisting, setShowAddOperationToExisting] =
    useState(false);
  const [pendingOperations, setPendingOperations] = useState([]);
  const [newOperation, setNewOperation] = useState({
    work_center_id: "",
    operation_name: "",
    run_time_minutes: "0",
    setup_time_minutes: "0",
  });
  const [savingRouting, setSavingRouting] = useState(false);
  const [addingOperation, setAddingOperation] = useState(false);

  // ─── Data fetching ───────────────────────────────────────────

  const fetchProductRouting = useCallback(async () => {
    if (!bom.product_id) return;
    try {
      const res = await fetch(
        `${API_URL}/api/v1/routings?product_id=${bom.product_id}`,
        { credentials: "include" }
      );
      if (res.ok) {
        const data = await res.json();
        const items = data.items || data;
        const activeRouting = items.find((r) => r.is_active && !r.is_template);
        if (activeRouting) {
          const detailRes = await fetch(
            `${API_URL}/api/v1/routings/${activeRouting.id}`,
            { credentials: "include" }
          );
          if (detailRes.ok) {
            const routingDetail = await detailRes.json();
            setProductRouting(routingDetail);
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
      // Product routing fetch failure is non-critical
    }
  }, [bom.product_id]);

  const fetchManufacturingBOM = useCallback(async () => {
    if (!bom?.product_id) return;
    try {
      const res = await fetch(
        `${API_URL}/api/v1/routings/manufacturing-bom/${bom.product_id}`,
        { credentials: "include" }
      );
      if (res.ok) {
        const data = await res.json();
        const materialsByOp = {};
        data.operations?.forEach((op) => {
          materialsByOp[op.id] = op.materials || [];
        });
        setOperationMaterials(materialsByOp);
      }
    } catch {
      // Non-critical failure
    }
  }, [bom?.product_id]);

  // Fetch manufacturing BOM when productRouting is loaded
  useEffect(() => {
    if (productRouting) {
      fetchManufacturingBOM();
    }
  }, [productRouting, fetchManufacturingBOM]);

  // ─── Material handlers ───────────────────────────────────────

  function closeMaterialModal() {
    setShowAddMaterialModal(null);
    setNewMaterial({
      component_id: "",
      quantity: "1",
      quantity_per: "unit",
      scrap_factor: "0",
      unit: "",
    });
  }

  async function handleAddMaterial(operationId) {
    if (!newMaterial.component_id) return;

    try {
      const res = await fetch(
        `${API_URL}/api/v1/routings/operations/${operationId}/materials`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          credentials: "include",
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
        closeMaterialModal();
        await fetchManufacturingBOM();
      } else {
        const err = await res.json();
        toast.error(err.detail || "Failed to add material");
      }
    } catch (err) {
      toast.error(err.message || "Network error");
    }
  }

  async function handleDeleteMaterial(operationId, materialId) {
    if (!window.confirm("Remove this material from the operation?")) return;

    try {
      const res = await fetch(
        `${API_URL}/api/v1/routings/materials/${materialId}`,
        {
          method: "DELETE",
          credentials: "include",
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
  }

  function calculateOperationMaterialsCost() {
    return Object.values(operationMaterials)
      .flat()
      .reduce((sum, m) => sum + parseFloat(m.extended_cost || 0), 0);
  }

  // ─── Template & time handlers ────────────────────────────────

  async function handleApplyTemplate() {
    if (!selectedTemplateId || !bom.product_id) return;

    setApplyingTemplate(true);
    try {
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
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify({
          product_id: bom.product_id,
          template_id: parseInt(selectedTemplateId),
          overrides,
        }),
      });

      if (res.ok) {
        const result = await res.json();
        setProductRouting(result);
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
          `Failed to apply routing template: ${errData.detail || "Unknown error"}`
        );
      }
    } catch (err) {
      toast.error(
        `Failed to apply routing template: ${err.message || "Network error"}`
      );
    } finally {
      setApplyingTemplate(false);
    }
  }

  function updateOperationTime(opCode, field, value) {
    setTimeOverrides((prev) => ({
      ...prev,
      [opCode]: {
        ...prev[opCode],
        [field]: parseFloat(value) || 0,
      },
    }));
  }

  async function saveOperationTime(operationId, field, value) {
    try {
      const res = await fetch(
        `${API_URL}/api/v1/routings/operations/${operationId}`,
        {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          credentials: "include",
          body: JSON.stringify({
            [field]: parseFloat(value) || 0,
          }),
        }
      );

      if (res.ok) {
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
  }

  // ─── Operation CRUD ──────────────────────────────────────────

  async function handleDeleteOperation(operationId, operationName) {
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
          credentials: "include",
        }
      );

      if (res.ok) {
        toast.success("Operation removed successfully");
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
  }

  function handleAddPendingOperation() {
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
  }

  function handleRemovePendingOperation(index) {
    const updated = pendingOperations.filter((_, i) => i !== index);
    updated.forEach((op, i) => {
      op.sequence = i + 1;
    });
    setPendingOperations(updated);
  }

  async function handleSaveRouting() {
    if (pendingOperations.length === 0) return;

    setSavingRouting(true);
    try {
      const res = await fetch(`${API_URL}/api/v1/routings/`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
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
  }

  async function handleAddOperationToExisting() {
    if (!productRouting?.id || !newOperation.work_center_id) return;

    setAddingOperation(true);
    try {
      const maxSequence = Math.max(
        0,
        ...(productRouting.operations || []).map((op) => op.sequence || 0)
      );
      const nextSequence = maxSequence + 1;

      const res = await fetch(
        `${API_URL}/api/v1/routings/${productRouting.id}/operations`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          credentials: "include",
          body: JSON.stringify({
            work_center_id: parseInt(newOperation.work_center_id),
            sequence: nextSequence,
            operation_name:
              newOperation.operation_name || `Step ${nextSequence}`,
            run_time_minutes: parseFloat(newOperation.run_time_minutes) || 0,
            setup_time_minutes:
              parseFloat(newOperation.setup_time_minutes) || 0,
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
  }

  // ─── Utility ─────────────────────────────────────────────────

  function calculateProcessCost() {
    if (!productRouting) return 0;
    return parseFloat(productRouting.total_cost || 0);
  }

  function formatTime(minutes) {
    const mins = parseFloat(minutes || 0);
    if (mins < 60) return `${mins.toFixed(0)}m`;
    const hrs = Math.floor(mins / 60);
    const remainingMins = Math.round(mins % 60);
    return remainingMins > 0 ? `${hrs}h ${remainingMins}m` : `${hrs}h`;
  }

  // ─── Initialization fetches (called once) ────────────────────

  function fetchInitialRoutingData() {
    const fetchRoutingTemplates = async () => {
      try {
        const res = await fetch(
          `${API_URL}/api/v1/routings?templates_only=true`,
          { credentials: "include" }
        );
        if (res.ok) {
          const data = await res.json();
          setRoutingTemplates(data.items || data);
        }
      } catch {
        // Non-critical
      }
    };

    const fetchWorkCenters = async () => {
      try {
        const res = await fetch(
          `${API_URL}/api/v1/work-centers/?active_only=true`,
          { credentials: "include" }
        );
        if (res.ok) {
          const data = await res.json();
          setWorkCenters(data);
        }
      } catch {
        // Non-critical
      }
    };

    fetchRoutingTemplates();
    fetchProductRouting();
    fetchWorkCenters();
  }

  return {
    // State
    productRouting,
    routingTemplates,
    selectedTemplateId,
    setSelectedTemplateId,
    timeOverrides,
    applyingTemplate,
    workCenters,
    showAddOperation,
    setShowAddOperation,
    showAddOperationToExisting,
    setShowAddOperationToExisting,
    pendingOperations,
    newOperation,
    setNewOperation,
    savingRouting,
    addingOperation,
    expandedOperations,
    setExpandedOperations,
    operationMaterials,
    showAddMaterialModal,
    setShowAddMaterialModal,
    newMaterial,
    setNewMaterial,

    // Handlers
    fetchProductRouting,
    closeMaterialModal,
    handleAddMaterial,
    handleDeleteMaterial,
    calculateOperationMaterialsCost,
    handleApplyTemplate,
    updateOperationTime,
    saveOperationTime,
    handleDeleteOperation,
    handleAddPendingOperation,
    handleRemovePendingOperation,
    handleSaveRouting,
    handleAddOperationToExisting,
    calculateProcessCost,
    formatTime,

    // Initialization
    fetchInitialRoutingData,
  };
}
