import { useState, useEffect, useMemo } from "react";
import { API_URL } from "../config/api";
import Modal from "./Modal";
import BasicInfoStep from "./items/BasicInfoStep";
import BomBuilderStep from "./items/BomBuilderStep";
import PricingStep from "./items/PricingStep";

/**
 * ItemWizard - Reusable item creation wizard with BOM builder
 *
 * Props:
 * - isOpen: boolean - Whether the wizard is open
 * - onClose: () => void - Called when wizard is closed
 * - onSuccess: (item) => void - Called when item is created successfully
 * - editingItem: object|null - If provided, edits existing item instead of creating new
 * - categories: array - Available categories (optional, will fetch if not provided)
 * - showPricing: boolean - Whether to show pricing step (default: true)
 */
export default function ItemWizard({ isOpen, onClose, onSuccess, editingItem = null, categories: propCategories = null, showPricing = true }) {
  // Wizard step tracking
  const [currentStep, setCurrentStep] = useState(1);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  // Data loaded from API
  const [categories, setCategories] = useState(propCategories || []);
  const [components, setComponents] = useState([]);
  const [_workCenters, setWorkCenters] = useState([]); // Reserved for routing step
  const [routingTemplates, setRoutingTemplates] = useState([]);

  // Material wizard state
  const [materialTypes, setMaterialTypes] = useState([]);
  const [allColors, setAllColors] = useState([]);
  const [showMaterialWizard, setShowMaterialWizard] = useState(false);
  const [newMaterial, setNewMaterial] = useState({
    material_type_code: "",
    color_code: "",
    quantity_kg: 1.0,
    cost_per_kg: null,
    in_stock: true,
  });

  // Sub-component wizard state
  const [showSubComponentWizard, setShowSubComponentWizard] = useState(false);
  const [subComponent, setSubComponent] = useState({
    sku: "",
    name: "",
    description: "",
    item_type: "component",
    procurement_type: "buy",
    unit: "EA",
    standard_cost: null,
  });

  // Item form state
  const [item, setItem] = useState({
    sku: editingItem?.sku || "",
    name: editingItem?.name || "",
    description: editingItem?.description || "",
    item_type: editingItem?.item_type || "finished_good",
    procurement_type: editingItem?.procurement_type || "make",
    category_id: editingItem?.category_id || null,
    unit: editingItem?.unit || "EA",
    standard_cost: editingItem?.standard_cost || null,
    selling_price: editingItem?.selling_price || null,
  });

  // BOM state
  const [bomLines, setBomLines] = useState([]);
  const [calculatedCost, setCalculatedCost] = useState(0);

  // Routing state
  const [routingOperations, setRoutingOperations] = useState([]);
  const [selectedTemplate, setSelectedTemplate] = useState(null);
  const [laborCost, setLaborCost] = useState(0);

  // Pricing state
  const [targetMargin, setTargetMargin] = useState(40);

  // Load data when wizard opens
  useEffect(() => {
    if (isOpen) {
      if (!propCategories) fetchCategories();
      fetchComponents();
      fetchWorkCenters();
      fetchRoutingTemplates();
      fetchMaterialTypesAndColors();
    }
  }, [isOpen]);

  // Auto-generate SKU when name changes
  useEffect(() => {
    if (item.name && !item.sku && !editingItem) {
      const prefix = item.item_type === "finished_good" ? "FG" :
                     item.item_type === "component" ? "CP" :
                     item.item_type === "supply" ? "SP" : "SV";
      const timestamp = Date.now().toString(36).toUpperCase();
      setItem(prev => ({ ...prev, sku: `${prefix}-${timestamp}` }));
    }
  }, [item.name, item.item_type]);

  // Calculate cost from BOM lines
  useEffect(() => {
    const total = bomLines.reduce((sum, line) => {
      const lineCost = (line.quantity || 0) * (line.component_cost || 0);
      return sum + lineCost;
    }, 0);
    setCalculatedCost(total);
  }, [bomLines]);

  // Calculate labor cost from routing
  useEffect(() => {
    const total = routingOperations.reduce((sum, op) => {
      const timeHours = ((op.setup_time_minutes || 0) + (op.run_time_minutes || 0)) / 60;
      const rate = op.rate_per_hour || 0;
      return sum + (timeHours * rate);
    }, 0);
    setLaborCost(total);
  }, [routingOperations]);

  const totalCost = useMemo(() => calculatedCost + laborCost, [calculatedCost, laborCost]);
  const suggestedPrice = useMemo(() => {
    if (totalCost <= 0) return 0;
    return totalCost / (1 - targetMargin / 100);
  }, [totalCost, targetMargin]);

  // Determine if item needs BOM based on procurement type
  const itemNeedsBom = item.procurement_type === "make" || item.procurement_type === "make_or_buy";

  // Steps config
  const steps = showPricing
    ? [
        { id: 1, name: "Basic Info", description: "Item details & type" },
        { id: 2, name: "BOM", description: "Components & materials", skip: !itemNeedsBom },
        { id: 3, name: "Pricing", description: "Cost & margin" },
      ]
    : [
        { id: 1, name: "Basic Info", description: "Item details & type" },
        { id: 2, name: "BOM", description: "Components & materials", skip: !itemNeedsBom },
      ];

  const activeSteps = steps.filter(s => !s.skip);
  const maxStep = activeSteps.length;

  // Fetch functions
  const fetchCategories = async () => {
    try {
      const res = await fetch(`${API_URL}/api/v1/items/categories`, {
        credentials: "include",
      });
      if (res.ok) {
        const data = await res.json();
        setCategories(data);
      }
    } catch {
      // Categories fetch failure is non-critical - category selector will be empty
    }
  };

  const fetchComponents = async () => {
    try {
      const itemsRes = await fetch(`${API_URL}/api/v1/items?limit=500&active_only=true`, {
        credentials: "include",
      });
      const materialsRes = await fetch(`${API_URL}/api/v1/materials/for-bom`, {
        credentials: "include",
      });

      let allComponents = [];

      if (itemsRes.ok) {
        const data = await itemsRes.json();
        allComponents = data.items || [];
      }

      if (materialsRes.ok) {
        const materialsData = await materialsRes.json();
        const materialItems = (materialsData.items || []).map(m => ({
          ...m,
          is_material: true,
        }));
        const existingIds = new Set(allComponents.map(c => c.id));
        const newMaterials = materialItems.filter(m => !existingIds.has(m.id));
        allComponents = [...allComponents, ...newMaterials];
      }

      setComponents(allComponents);
    } catch {
      // Components fetch failure is non-critical - component selector will be empty
    }
  };

  const fetchWorkCenters = async () => {
    try {
      const res = await fetch(`${API_URL}/api/v1/work-centers/`, {
        credentials: "include",
      });
      if (res.ok) {
        const data = await res.json();
        setWorkCenters(data);
      }
    } catch {
      // Work centers fetch failure is non-critical - work center selector will be empty
    }
  };

  const fetchRoutingTemplates = async () => {
    try {
      const res = await fetch(`${API_URL}/api/v1/routings/?templates_only=true`, {
        credentials: "include",
      });
      if (res.ok) {
        const data = await res.json();
        setRoutingTemplates(data);
      }
    } catch {
      // Routing templates fetch failure is non-critical - templates list will be empty
    }
  };

  const fetchMaterialTypesAndColors = async () => {
    try {
      const typesRes = await fetch(`${API_URL}/api/v1/materials/types?customer_visible_only=false`, {
        credentials: "include",
      });
      if (typesRes.ok) {
        const data = await typesRes.json();
        setMaterialTypes(data.materials || []);
      }
    } catch {
      // Material types fetch failure is non-critical - material type selector will be empty
    }
  };

  // Fetch colors when material type is selected
  const fetchColorsForType = async (materialTypeCode) => {
    if (!materialTypeCode) {
      setAllColors([]);
      return;
    }
    try {
      const res = await fetch(
        `${API_URL}/api/v1/materials/types/${materialTypeCode}/colors?in_stock_only=false&customer_visible_only=false`,
        { credentials: "include" }
      );
      if (res.ok) {
        const data = await res.json();
        setAllColors(data.colors || []);
      }
    } catch {
      // Colors fetch failure - color selector will be empty
    }
  };

  // BOM Line handlers
  const addBomLine = (component) => {
    const existing = bomLines.find(bl => bl.component_id === component.id);
    if (!existing) {
      setBomLines([...bomLines, {
        component_id: component.id,
        component_sku: component.sku,
        component_name: component.name,
        component_unit: component.unit,
        component_cost: component.standard_cost || component.average_cost || component.cost || 0,
        quantity: component.unit === "kg" ? 0.05 : 1,
        is_material: component.is_material || false,
      }]);
    }
  };

  const removeBomLine = (componentId) => {
    setBomLines(bomLines.filter(bl => bl.component_id !== componentId));
  };

  const updateBomQuantity = (componentId, quantity) => {
    setBomLines(bomLines.map(bl =>
      bl.component_id === componentId
        ? { ...bl, quantity: Math.max(0.001, quantity) }
        : bl
    ));
  };

  // Sub-component creation
  const startSubComponent = () => {
    setSubComponent({
      sku: "",
      name: "",
      description: "",
      item_type: "component",
      procurement_type: "buy",
      unit: "EA",
      standard_cost: null,
    });
    setShowSubComponentWizard(true);
  };

  const handleSaveSubComponent = async () => {
    if (!subComponent.name) {
      setError("Component name is required");
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const sku = subComponent.sku || `CP-${Date.now().toString(36).toUpperCase()}`;
      const res = await fetch(`${API_URL}/api/v1/items`, {
        method: "POST",
        credentials: "include",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          ...subComponent,
          sku,
        }),
      });

      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || "Failed to create component");
      }

      const created = await res.json();
      setComponents(prev => [...prev, created]);
      addBomLine(created);
      setShowSubComponentWizard(false);
      await fetchComponents();
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  // Material creation
  const handleCreateMaterial = async () => {
    if (!newMaterial.material_type_code || !newMaterial.color_code) {
      setError("Material type and color are required");
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(`${API_URL}/api/v1/materials/inventory`, {
        method: "POST",
        credentials: "include",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify(newMaterial),
      });

      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || "Failed to create material");
      }

      const created = await res.json();
      const newComponent = {
        id: created.product_id,
        sku: created.sku,
        name: created.name,
        item_type: "supply",
        procurement_type: "buy",
        unit: "kg",
        standard_cost: created.cost_per_kg || 0,
        is_material: true,
        in_stock: created.in_stock,
      };
      setComponents(prev => [...prev, newComponent]);
      addBomLine(newComponent);
      setNewMaterial({
        material_type_code: "",
        color_code: "",
        quantity_kg: 1.0,
        cost_per_kg: null,
        in_stock: true,
      });
      setShowMaterialWizard(false);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  // Routing template application
  const applyRoutingTemplate = (template) => {
    if (!template) {
      setSelectedTemplate(null);
      setRoutingOperations([]);
      return;
    }
    setSelectedTemplate(template);
    if (template.operations) {
      setRoutingOperations(template.operations.map((op, idx) => ({
        ...op,
        id: `new-${idx}`,
        sequence: idx + 1,
      })));
    }
  };

  // Save item
  const handleSave = async () => {
    if (!item.sku || !item.name) {
      setError("SKU and Name are required");
      return;
    }

    setLoading(true);
    setError(null);

    try {
      // 1. Create/Update item
      const itemPayload = {
        sku: item.sku,
        name: item.name,
        description: item.description || null,
        item_type: item.item_type,
        procurement_type: item.procurement_type,
        category_id: item.category_id,
        unit: item.unit || "EA",
        standard_cost: totalCost > 0 ? totalCost : item.standard_cost,
        selling_price: item.selling_price,
      };

      const itemUrl = editingItem
        ? `${API_URL}/api/v1/items/${editingItem.id}`
        : `${API_URL}/api/v1/items`;
      const itemRes = await fetch(itemUrl, {
        method: editingItem ? "PATCH" : "POST",
        credentials: "include",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify(itemPayload),
      });

      if (!itemRes.ok) {
        const err = await itemRes.json();
        throw new Error(err.detail || "Failed to save item");
      }

      const createdItem = await itemRes.json();

      // 2. Create BOM if needed and has lines
      if (itemNeedsBom && bomLines.length > 0 && !editingItem) {
        const bomPayload = {
          product_id: createdItem.id,
          lines: bomLines.map((line, idx) => ({
            component_id: line.component_id,
            quantity: line.quantity,
            sequence: idx + 1,
          })),
        };

        const bomRes = await fetch(`${API_URL}/api/v1/admin/bom/`, {
          method: "POST",
          credentials: "include",
          headers: {
            "Content-Type": "application/json",
          },
          body: JSON.stringify(bomPayload),
        });

        if (!bomRes.ok) {
          // BOM creation failed but item was created - user can create BOM manually later
        }
      }

      // 3. Create Routing if has operations
      if (routingOperations.length > 0 && !editingItem) {
        const routingPayload = {
          product_id: createdItem.id,
          version: 1,
          revision: "1.0",
          is_active: true,
          operations: routingOperations.map(op => ({
            work_center_id: op.work_center_id,
            sequence: op.sequence,
            operation_code: op.operation_code,
            operation_name: op.operation_name,
            setup_time_minutes: op.setup_time_minutes,
            run_time_minutes: op.run_time_minutes,
            runtime_source: "manual",
          })),
        };

        const routingRes = await fetch(`${API_URL}/api/v1/routings/`, {
          method: "POST",
          credentials: "include",
          headers: {
            "Content-Type": "application/json",
          },
          body: JSON.stringify(routingPayload),
        });

        if (!routingRes.ok) {
          // Routing creation failed but item was created - user can create routing manually later
        }
      }

      // Success!
      if (onSuccess) onSuccess(createdItem);
      handleClose();
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const handleClose = () => {
    setCurrentStep(1);
    setItem({
      sku: "",
      name: "",
      description: "",
      item_type: "finished_good",
      procurement_type: "make",
      category_id: null,
      unit: "EA",
      standard_cost: null,
      selling_price: null,
    });
    setBomLines([]);
    setRoutingOperations([]);
    setError(null);
    if (onClose) onClose();
  };

  const nextStep = () => {
    const currentIdx = activeSteps.findIndex(s => s.id === currentStep);
    if (currentIdx < activeSteps.length - 1) {
      setCurrentStep(activeSteps[currentIdx + 1].id);
    }
  };

  const prevStep = () => {
    const currentIdx = activeSteps.findIndex(s => s.id === currentStep);
    if (currentIdx > 0) {
      setCurrentStep(activeSteps[currentIdx - 1].id);
    }
  };

  return (
    <Modal
      isOpen={isOpen}
      onClose={handleClose}
      title={editingItem ? "Edit Item" : "Create New Item"}
      className="w-full max-w-4xl max-h-[90vh] overflow-hidden flex flex-col"
      disableClose={loading}
    >
        {/* Header */}
        <div className="p-6 border-b border-gray-800 flex justify-between items-center">
          <div>
            <h2 className="text-xl font-bold text-white">
              {editingItem ? "Edit Item" : "Create New Item"}
            </h2>
            <p className="text-gray-400 text-sm mt-1">
              Step {activeSteps.findIndex(s => s.id === currentStep) + 1} of {maxStep}: {activeSteps.find(s => s.id === currentStep)?.name}
            </p>
          </div>
          <button onClick={handleClose} className="text-gray-400 hover:text-white p-2">
            <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        {/* Step indicators */}
        <div className="px-6 py-3 bg-gray-800/50 border-b border-gray-800">
          <div className="flex gap-4">
            {activeSteps.map((step, idx) => (
              <div key={step.id} className="flex items-center gap-2">
                <div className={`w-6 h-6 rounded-full flex items-center justify-center text-xs font-medium ${
                  currentStep === step.id
                    ? "bg-blue-600 text-white"
                    : activeSteps.findIndex(s => s.id === currentStep) > idx
                      ? "bg-green-600 text-white"
                      : "bg-gray-700 text-gray-400"
                }`}>
                  {activeSteps.findIndex(s => s.id === currentStep) > idx ? "✓" : idx + 1}
                </div>
                <span className={currentStep === step.id ? "text-white" : "text-gray-500"}>{step.name}</span>
                {idx < activeSteps.length - 1 && <span className="text-gray-600 mx-2">→</span>}
              </div>
            ))}
          </div>
        </div>

        {/* Error display */}
        {error && (
          <div className="mx-6 mt-4 p-3 bg-red-500/10 border border-red-500/30 rounded-lg text-red-400 text-sm">
            {error}
          </div>
        )}

        {/* Content */}
        <div className="flex-1 overflow-y-auto p-6">
          {/* Step 1: Basic Info */}
          {currentStep === 1 && (
            <BasicInfoStep
              item={item}
              categories={categories}
              itemNeedsBom={itemNeedsBom}
              onItemChange={setItem}
            />
          )}

          {/* Step 2: BOM Builder */}
          {currentStep === 2 && (
            <BomBuilderStep
              components={components}
              bomLines={bomLines}
              calculatedCost={calculatedCost}
              routingTemplates={routingTemplates}
              selectedTemplate={selectedTemplate}
              routingOperations={routingOperations}
              laborCost={laborCost}
              showMaterialWizard={showMaterialWizard}
              showSubComponentWizard={showSubComponentWizard}
              materialTypes={materialTypes}
              allColors={allColors}
              newMaterial={newMaterial}
              subComponent={subComponent}
              loading={loading}
              onAddBomLine={addBomLine}
              onRemoveBomLine={removeBomLine}
              onUpdateBomQuantity={updateBomQuantity}
              onShowMaterialWizard={setShowMaterialWizard}
              onShowSubComponentWizard={setShowSubComponentWizard}
              onMaterialChange={setNewMaterial}
              onColorTypeChange={(code) => {
                setNewMaterial({ ...newMaterial, material_type_code: code, color_code: "" });
                fetchColorsForType(code);
              }}
              onCreateMaterial={handleCreateMaterial}
              onSubComponentChange={setSubComponent}
              onSaveSubComponent={handleSaveSubComponent}
              onStartSubComponent={startSubComponent}
              onApplyRoutingTemplate={applyRoutingTemplate}
            />
          )}

          {/* Step 3: Pricing */}
          {currentStep === 3 && showPricing && (
            <PricingStep
              item={item}
              calculatedCost={calculatedCost}
              laborCost={laborCost}
              totalCost={totalCost}
              targetMargin={targetMargin}
              suggestedPrice={suggestedPrice}
              onItemChange={setItem}
              onTargetMarginChange={setTargetMargin}
            />
          )}
        </div>

        {/* Footer */}
        <div className="p-6 border-t border-gray-800 flex justify-between">
          <button
            type="button"
            onClick={prevStep}
            disabled={activeSteps.findIndex(s => s.id === currentStep) === 0}
            className="px-4 py-2 text-gray-400 hover:text-white disabled:opacity-50"
          >
            Back
          </button>
          <div className="flex gap-3">
            <button
              type="button"
              onClick={handleClose}
              className="px-4 py-2 text-gray-400 hover:text-white"
            >
              Cancel
            </button>
            {activeSteps.findIndex(s => s.id === currentStep) < activeSteps.length - 1 ? (
              <button
                type="button"
                onClick={nextStep}
                disabled={!item.name}
                className="px-6 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-500 disabled:opacity-50"
              >
                Next
              </button>
            ) : (
              <button
                type="button"
                onClick={handleSave}
                disabled={loading || !item.name || !item.sku}
                className="px-6 py-2 bg-gradient-to-r from-blue-600 to-purple-600 text-white rounded-lg hover:from-blue-500 hover:to-purple-500 disabled:opacity-50"
              >
                {loading ? "Creating..." : editingItem ? "Save Changes" : "Create Item"}
              </button>
            )}
          </div>
        </div>
    </Modal>
  );
}
