import { useState, useEffect, useMemo } from "react";
import { useNavigate } from "react-router-dom";
import { API_URL } from "../config/api";
import { validateRequired, validateQuantity } from "../utils/validation";
import CustomerSelectionStep from "./sales-order/CustomerSelectionStep";
import ReviewStep from "./sales-order/ReviewStep";

// Item type options
const ITEM_TYPES = [
  {
    value: "finished_good",
    label: "Finished Good",
    color: "blue",
    defaultProcurement: "make",
  },
  {
    value: "component",
    label: "Component",
    color: "purple",
    defaultProcurement: "buy",
  },
  {
    value: "supply",
    label: "Supply",
    color: "orange",
    defaultProcurement: "buy",
  },
  {
    value: "service",
    label: "Service",
    color: "green",
    defaultProcurement: "buy",
  },
];

// Procurement type options (Make vs Buy)
const PROCUREMENT_TYPES = [
  {
    value: "make",
    label: "Make (Manufactured)",
    color: "green",
    needsBom: true,
    description: "Produced in-house with BOM & routing",
  },
  {
    value: "buy",
    label: "Buy (Purchased)",
    color: "blue",
    needsBom: false,
    description: "Purchased from suppliers",
  },
  {
    value: "make_or_buy",
    label: "Make or Buy",
    color: "yellow",
    needsBom: true,
    description: "Flexible sourcing",
  },
];

// Steps definition
const STEPS = [
  { id: 1, name: "Customer", description: "Select or create customer" },
  { id: 2, name: "Products", description: "Add line items" },
  { id: 3, name: "Review", description: "Review and submit" },
];

export default function SalesOrderWizard({ isOpen, onClose, onSuccess }) {
  const navigate = useNavigate();
  const [currentStep, setCurrentStep] = useState(1);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const token = localStorage.getItem("adminToken");

  // Data loaded from API
  const [customers, setCustomers] = useState([]);
  const [products, setProducts] = useState([]);
  const [categories, setCategories] = useState([]);
  const [components, setComponents] = useState([]); // For BOM builder
  const [workCenters, setWorkCenters] = useState([]); // For routing/processes
  const [routingTemplates, setRoutingTemplates] = useState([]); // Template routings

  // Order form state
  const [orderData, setOrderData] = useState({
    customer_id: null,
    shipping_address_line1: "",
    shipping_city: "",
    shipping_state: "",
    shipping_zip: "",
    customer_notes: "",
  });

  // Line items state
  const [lineItems, setLineItems] = useState([]);

  // Product search state
  const [productSearch, setProductSearch] = useState("");

  // New item wizard state
  const [showItemWizard, setShowItemWizard] = useState(false);
  const [itemWizardStep, setItemWizardStep] = useState(1); // 1=basic, 2=bom, 3=pricing
  const [newItem, setNewItem] = useState({
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

  // Inline sub-component creation (nested wizard within BOM builder)
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

  // Inline material (filament) creation
  const [showMaterialWizard, setShowMaterialWizard] = useState(false);
  const [materialTypes, setMaterialTypes] = useState([]);
  const [allColors, setAllColors] = useState([]);
  const [newMaterial, setNewMaterial] = useState({
    material_type_code: "",
    color_code: "",
    quantity_kg: 1.0,
    cost_per_kg: null,
    in_stock: true,
  });

  const [bomLines, setBomLines] = useState([]);
  const [routingOperations, setRoutingOperations] = useState([]); // Process steps
  const [selectedTemplate, setSelectedTemplate] = useState(null); // Selected routing template
  const [productImages, setProductImages] = useState([]); // Image files for upload
  const [imagePreviewUrls, setImagePreviewUrls] = useState([]); // Preview URLs
  const [calculatedCost, setCalculatedCost] = useState(0);
  const [laborCost, setLaborCost] = useState(0); // Cost from routing operations
  const [targetMargin, setTargetMargin] = useState(40); // Default 40% margin

  // Tax settings from company settings
  const [taxSettings, setTaxSettings] = useState({
    tax_enabled: false,
    tax_rate: 0,
    tax_name: "Sales Tax",
  });

  // Load initial data
  useEffect(() => {
    if (isOpen) {
      // Check if returning from customer/item creation
      const pendingData = sessionStorage.getItem("pendingOrderData");
      let pendingCustomerId = null;
      if (pendingData) {
        try {
          const data = JSON.parse(pendingData);
          // If a new customer was created, use that ID
          pendingCustomerId = data.newCustomerId || data.customer_id || null;
          setOrderData({
            customer_id: pendingCustomerId,
            shipping_address_line1: data.shipping_address_line1 || "",
            shipping_city: data.shipping_city || "",
            shipping_state: data.shipping_state || "",
            shipping_zip: data.shipping_zip || "",
            customer_notes: data.customer_notes || "",
          });
          setLineItems(data.lineItems || []);
          setCurrentStep(data.currentStep || 1);
          sessionStorage.removeItem("pendingOrderData");
        } catch {
          // Session storage failure is non-critical - order creation will proceed
        }
      }

      // Fetch data - customers will be fetched and then we'll ensure the customer is selected
      fetchCustomers().then((customersList) => {
        // After customers are loaded, ensure the pending customer is selected
        if (
          pendingCustomerId &&
          customersList.find((c) => c.id === pendingCustomerId)
        ) {
          // Customer exists in the list, ensure it's selected
          const customer = customersList.find(
            (c) => c.id === pendingCustomerId
          );
          setOrderData((prev) => ({
            ...prev,
            customer_id: pendingCustomerId,
            shipping_address_line1:
              customer?.shipping_address_line1 ||
              prev.shipping_address_line1 ||
              "",
            shipping_city: customer?.shipping_city || prev.shipping_city || "",
            shipping_state:
              customer?.shipping_state || prev.shipping_state || "",
            shipping_zip: customer?.shipping_zip || prev.shipping_zip || "",
          }));
        }
      });
      fetchProducts();
      fetchCategories();
      fetchComponents();
      fetchWorkCenters();
      fetchRoutingTemplates();
      fetchMaterialTypesAndColors();
      fetchTaxSettings();
    }
  }, [isOpen]);

  // Auto-generate SKU when name changes for new items
  useEffect(() => {
    if (newItem.name && !newItem.sku) {
      const prefix =
        newItem.item_type === "finished_good"
          ? "FG"
          : newItem.item_type === "component"
          ? "CP"
          : newItem.item_type === "supply"
          ? "SP"
          : "SV";
      const timestamp = Date.now().toString(36).toUpperCase();
      setNewItem((prev) => ({
        ...prev,
        sku: `${prefix}-${timestamp}`,
      }));
    }
  }, [newItem.name, newItem.item_type]);

  // Calculate cost from BOM lines
  useEffect(() => {
    const total = bomLines.reduce((sum, line) => {
      const lineCost = (line.quantity || 0) * (line.component_cost || 0);
      return sum + lineCost;
    }, 0);
    setCalculatedCost(total);
  }, [bomLines]);

  // Calculate labor cost from routing operations
  useEffect(() => {
    const total = routingOperations.reduce((sum, op) => {
      const timeHours =
        ((op.setup_time_minutes || 0) + (op.run_time_minutes || 0)) / 60;
      const rate = op.rate_per_hour || 0;
      return sum + timeHours * rate;
    }, 0);
    setLaborCost(total);
  }, [routingOperations]);

  // Calculate total cost (materials + labor)
  const totalCost = useMemo(
    () => calculatedCost + laborCost,
    [calculatedCost, laborCost]
  );

  // Calculate suggested price from margin
  const suggestedPrice = useMemo(() => {
    if (totalCost <= 0) return 0;
    return totalCost / (1 - targetMargin / 100);
  }, [totalCost, targetMargin]);

  const fetchCustomers = async () => {
    try {
      const res = await fetch(`${API_URL}/api/v1/admin/customers?limit=200`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (res.ok) {
        const data = await res.json();
        const customersList = Array.isArray(data.items)
          ? data.items
          : Array.isArray(data)
          ? data
          : [];
        setCustomers(customersList);
        return customersList;
      }
    } catch {
      // Customers fetch failure is non-critical - customer selector will be empty
    }
    return [];
  };

  const fetchProducts = async () => {
    try {
      const res = await fetch(
        `${API_URL}/api/v1/products?limit=500&active_only=true`,
        {
          headers: { Authorization: `Bearer ${token}` },
        }
      );
      if (res.ok) {
        const data = await res.json();
        setProducts(data.items || data || []);
      }
    } catch {
      // Products fetch failure is non-critical - product selector will be empty
    }
  };

  const fetchCategories = async () => {
    try {
      const res = await fetch(`${API_URL}/api/v1/items/categories`, {
        headers: { Authorization: `Bearer ${token}` },
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
      // Fetch all items that can be BOM components
      const itemsRes = await fetch(
        `${API_URL}/api/v1/items?limit=500&active_only=true`,
        {
          headers: { Authorization: `Bearer ${token}` },
        }
      );

      // Fetch materials with real product IDs (creates products if needed)
      const materialsRes = await fetch(`${API_URL}/api/v1/materials/for-bom`, {
        headers: { Authorization: `Bearer ${token}` },
      });

      let allComponents = [];

      if (itemsRes.ok) {
        const data = await itemsRes.json();
        allComponents = data.items || [];
      }

      // Materials from /for-bom have real product IDs ready for BOM
      if (materialsRes.ok) {
        const materialsData = await materialsRes.json();
        const materialItems = (materialsData.items || []).map((m) => ({
          ...m,
          is_material: true,
        }));

        // Avoid duplicates if material already in items list
        const existingIds = new Set(allComponents.map((c) => c.id));
        const newMaterials = materialItems.filter(
          (m) => !existingIds.has(m.id)
        );

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
        headers: { Authorization: `Bearer ${token}` },
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
      const res = await fetch(
        `${API_URL}/api/v1/routings/?templates_only=true`,
        {
          headers: { Authorization: `Bearer ${token}` },
        }
      );
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
      const typesRes = await fetch(
        `${API_URL}/api/v1/materials/types?customer_visible_only=false`,
        {
          headers: { Authorization: `Bearer ${token}` },
        }
      );
      if (typesRes.ok) {
        const data = await typesRes.json();
        setMaterialTypes(data.materials || []);
      }
    } catch {
      // Material types fetch failure is non-critical - material type selector will be empty
    }
  };

  const fetchTaxSettings = async () => {
    try {
      const res = await fetch(`${API_URL}/api/v1/settings/company`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (res.ok) {
        const data = await res.json();
        setTaxSettings({
          tax_enabled: data.tax_enabled || false,
          tax_rate: parseFloat(data.tax_rate) || 0,
          tax_name: data.tax_name || "Sales Tax",
        });
      }
    } catch {
      // Tax settings fetch failure is non-critical - tax will be calculated on backend
    }
  };

  // Fetch colors dynamically when material type is selected
  const fetchColorsForType = async (materialTypeCode) => {
    if (!materialTypeCode) {
      setAllColors([]);
      return;
    }
    try {
      const res = await fetch(
        `${API_URL}/api/v1/materials/types/${materialTypeCode}/colors?in_stock_only=false&customer_visible_only=false`,
        { headers: { Authorization: `Bearer ${token}` } }
      );
      if (res.ok) {
        const data = await res.json();
        setAllColors(data.colors || []);
      }
    } catch {
      // Colors fetch failure - color selector will be empty
    }
  };

  // Handle creating new material (filament) inline
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
        headers: {
          Authorization: `Bearer ${token}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify(newMaterial),
      });

      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || "Failed to create material");
      }

      const created = await res.json();

      // Add to components list
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
      setComponents((prev) => [...prev, newComponent]);

      // Add to BOM
      addBomLine(newComponent);

      // Reset and close wizard
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

  // Add existing product to line items
  const addLineItem = (product) => {
    const existing = lineItems.find((li) => li.product_id === product.id);
    if (existing) {
      setLineItems(
        lineItems.map((li) =>
          li.product_id === product.id
            ? { ...li, quantity: li.quantity + 1 }
            : li
        )
      );
    } else {
      setLineItems([
        ...lineItems,
        {
          product_id: product.id,
          product: product,
          quantity: 1,
          unit_price: product.selling_price || 0,
        },
      ]);
    }
  };

  // Remove line item
  const removeLineItem = (productId) => {
    setLineItems(lineItems.filter((li) => li.product_id !== productId));
  };

  // Update line item quantity
  const updateLineQuantity = (productId, quantity) => {
    setLineItems(
      lineItems.map((li) =>
        li.product_id === productId
          ? { ...li, quantity: Math.max(1, quantity) }
          : li
      )
    );
  };

  // Update line item price
  const updateLinePrice = (productId, price) => {
    setLineItems(
      lineItems.map((li) =>
        li.product_id === productId ? { ...li, unit_price: price } : li
      )
    );
  };

  // Start creating a new item
  const startNewItem = () => {
    // Navigate to items page to create new item
    // Store current order data in sessionStorage so we can restore it
    sessionStorage.setItem(
      "pendingOrderData",
      JSON.stringify({
        customer_id: orderData.customer_id,
        shipping_address_line1: orderData.shipping_address_line1,
        shipping_city: orderData.shipping_city,
        shipping_state: orderData.shipping_state,
        shipping_zip: orderData.shipping_zip,
        customer_notes: orderData.customer_notes,
        lineItems: lineItems,
        currentStep: currentStep,
      })
    );
    navigate("/admin/items?action=new&returnTo=order");
  };

  // Start creating a sub-component inline (while building BOM)
  const startSubComponent = () => {
    const timestamp = Date.now().toString(36).toUpperCase();
    setSubComponent({
      sku: `CP-${timestamp}`,
      name: "",
      description: "",
      item_type: "component",
      procurement_type: "buy",
      unit: "EA",
      standard_cost: null,
    });
    setShowSubComponentWizard(true);
  };

  // Save sub-component and add to BOM
  const handleSaveSubComponent = async () => {
    if (!subComponent.name || !subComponent.sku) return;

    setLoading(true);
    try {
      const res = await fetch(`${API_URL}/api/v1/items`, {
        method: "POST",
        headers: {
          Authorization: `Bearer ${token}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify(subComponent),
      });

      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || "Failed to create component");
      }

      const created = await res.json();

      // Add to BOM lines
      setBomLines([
        ...bomLines,
        {
          component_id: created.id,
          component_sku: created.sku,
          component_name: created.name,
          component_unit: created.unit,
          component_cost: created.standard_cost || 0,
          quantity: 1,
        },
      ]);

      // Refresh components list and close wizard
      await fetchComponents();
      setShowSubComponentWizard(false);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  // Add BOM line
  const addBomLine = (component) => {
    const existing = bomLines.find((bl) => bl.component_id === component.id);
    if (!existing) {
      setBomLines([
        ...bomLines,
        {
          component_id: component.id,
          component_sku: component.sku,
          component_name: component.name,
          component_unit: component.unit,
          component_cost:
            component.standard_cost ||
            component.average_cost ||
            component.cost ||
            0,
          quantity: component.unit === "g" ? 50 : 1, // Default 50g for filament
          is_material: component.is_material || false,
          material_code: component.material_code,
          color_code: component.color_code,
        },
      ]);
    }
  };

  // Remove BOM line
  const removeBomLine = (componentId) => {
    setBomLines(bomLines.filter((bl) => bl.component_id !== componentId));
  };

  // Update BOM line quantity
  const updateBomQuantity = (componentId, quantity) => {
    setBomLines(
      bomLines.map((bl) =>
        bl.component_id === componentId
          ? { ...bl, quantity: Math.max(0.01, quantity) }
          : bl
      )
    );
  };

  // Apply routing template
  const applyRoutingTemplate = (template) => {
    if (!template) {
      setRoutingOperations([]);
      setSelectedTemplate(null);
      return;
    }
    setSelectedTemplate(template);
    // Create operations from template (if template has operations array)
    if (template.operations) {
      setRoutingOperations(
        template.operations.map((op, idx) => ({
          id: `temp-${idx}`,
          sequence: op.sequence || (idx + 1) * 10,
          work_center_id: op.work_center_id,
          work_center_code: op.work_center_code,
          work_center_name: op.work_center_name,
          operation_code: op.operation_code,
          operation_name: op.operation_name,
          setup_time_minutes: op.setup_time_minutes || 0,
          run_time_minutes: op.run_time_minutes || 0,
          rate_per_hour: op.total_rate_per_hour || 0,
        }))
      );
    }
  };

  // Add routing operation manually
  const addRoutingOperation = (workCenter) => {
    const nextSeq =
      routingOperations.length > 0
        ? Math.max(...routingOperations.map((o) => o.sequence)) + 10
        : 10;
    setRoutingOperations([
      ...routingOperations,
      {
        id: `temp-${Date.now()}`,
        sequence: nextSeq,
        work_center_id: workCenter.id,
        work_center_code: workCenter.code,
        work_center_name: workCenter.name,
        operation_code: workCenter.code,
        operation_name: workCenter.name,
        setup_time_minutes: 0,
        run_time_minutes: 0,
        rate_per_hour: parseFloat(workCenter.total_rate_per_hour || 0),
      },
    ]);
  };

  // Remove routing operation
  const removeRoutingOperation = (opId) => {
    setRoutingOperations(routingOperations.filter((op) => op.id !== opId));
  };

  // Update routing operation time
  const updateOperationTime = (opId, field, value) => {
    setRoutingOperations(
      routingOperations.map((op) =>
        op.id === opId
          ? { ...op, [field]: Math.max(0, parseFloat(value) || 0) }
          : op
      )
    );
  };

  // Handle image file selection
  const handleImageSelect = (e) => {
    const files = Array.from(e.target.files);
    const validFiles = files.filter((f) => f.type.startsWith("image/"));

    // Create preview URLs
    const newPreviews = validFiles.map((file) => URL.createObjectURL(file));

    setProductImages((prev) => [...prev, ...validFiles]);
    setImagePreviewUrls((prev) => [...prev, ...newPreviews]);
  };

  // Handle image drop
  const handleImageDrop = (e) => {
    e.preventDefault();
    const files = Array.from(e.dataTransfer.files);
    const validFiles = files.filter((f) => f.type.startsWith("image/"));

    const newPreviews = validFiles.map((file) => URL.createObjectURL(file));

    setProductImages((prev) => [...prev, ...validFiles]);
    setImagePreviewUrls((prev) => [...prev, ...newPreviews]);
  };

  // Remove image
  const removeImage = (index) => {
    URL.revokeObjectURL(imagePreviewUrls[index]);
    setProductImages((prev) => prev.filter((_, i) => i !== index));
    setImagePreviewUrls((prev) => prev.filter((_, i) => i !== index));
  };

  // Check if item needs BOM based on procurement type (Make items need BOM)
  const itemNeedsBom = PROCUREMENT_TYPES.find(
    (t) => t.value === newItem.procurement_type
  )?.needsBom;

  // Save new item and optionally BOM, routing, and images
  const handleSaveNewItem = async () => {
    setLoading(true);
    setError(null);
    try {
      // 1. Create the item
      const itemPayload = {
        ...newItem,
        procurement_type: newItem.procurement_type || "buy",
        standard_cost: totalCost > 0 ? totalCost : newItem.standard_cost,
        selling_price: newItem.selling_price || suggestedPrice,
      };

      const itemRes = await fetch(`${API_URL}/api/v1/items`, {
        method: "POST",
        headers: {
          Authorization: `Bearer ${token}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify(itemPayload),
      });

      if (!itemRes.ok) {
        const err = await itemRes.json();
        throw new Error(err.detail || "Failed to create item");
      }

      const createdItem = await itemRes.json();

      // 2. Create BOM if needed and has lines
      // All components (including materials) now have real product IDs
      if (itemNeedsBom && bomLines.length > 0) {
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
          headers: {
            Authorization: `Bearer ${token}`,
            "Content-Type": "application/json",
          },
          body: JSON.stringify(bomPayload),
        });

        if (!bomRes.ok) {
          // BOM creation failed but item was created - user can create BOM manually later
        }
      }

      // 3. Create Routing if has operations
      if (routingOperations.length > 0) {
        const routingPayload = {
          product_id: createdItem.id,
          version: 1,
          revision: "1.0",
          is_active: true,
          operations: routingOperations.map((op) => ({
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
          headers: {
            Authorization: `Bearer ${token}`,
            "Content-Type": "application/json",
          },
          body: JSON.stringify(routingPayload),
        });

        if (!routingRes.ok) {
          // Routing creation failed but item was created - user can create routing manually later
        }
      }

      // 4. Upload images if any (endpoint TBD - store for later)
      if (productImages.length > 0) {
        // TODO: Implement image upload when backend endpoint is ready
        // Images are stored but not uploaded yet
      }

      // 5. Add to line items
      addLineItem({
        ...createdItem,
        id: createdItem.id,
        sku: createdItem.sku,
        name: createdItem.name,
        selling_price: createdItem.selling_price,
      });

      // 6. Refresh products list
      await fetchProducts();

      // 7. Close wizard
      setShowItemWizard(false);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  // Validate current step before proceeding
  const validateStep = (step) => {
    setError(null);

    if (step === 1) {
      // Validate customer selection
      const customerError = validateRequired(
        orderData.customer_id,
        "Customer"
      );
      if (customerError) {
        setError(customerError);
        return false;
      }
    }

    if (step === 2) {
      // Validate line items
      if (lineItems.length === 0) {
        setError("Please add at least one product to the order");
        return false;
      }

      // Validate each line item has quantity > 0
      for (const item of lineItems) {
        const qtyError = validateQuantity(item.quantity, "Quantity");
        if (qtyError) {
          setError(`${item.name}: ${qtyError}`);
          return false;
        }
      }
    }

    return true;
  };

  // Handle step transition
  const handleNextStep = () => {
    if (validateStep(currentStep)) {
      setCurrentStep(currentStep + 1);
    }
  };

  // Submit the order
  const handleSubmitOrder = async () => {
    if (lineItems.length === 0) {
      setError("Please add at least one line item");
      return;
    }

    setLoading(true);
    setError(null);

    try {
      const payload = {
        customer_id: orderData.customer_id || null,
        lines: lineItems.map((li) => ({
          product_id: li.product_id,
          quantity: li.quantity,
          unit_price: li.unit_price,
        })),
        source: "manual",
        shipping_address_line1: orderData.shipping_address_line1 || null,
        shipping_city: orderData.shipping_city || null,
        shipping_state: orderData.shipping_state || null,
        shipping_zip: orderData.shipping_zip || null,
        customer_notes: orderData.customer_notes || null,
      };

      const res = await fetch(`${API_URL}/api/v1/sales-orders/`, {
        method: "POST",
        headers: {
          Authorization: `Bearer ${token}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify(payload),
      });

      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || "Failed to create order");
      }

      const order = await res.json();
      onSuccess?.(order);
      handleClose();
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  // Reset and close
  const handleClose = () => {
    setCurrentStep(1);
    setOrderData({
      customer_id: null,
      shipping_address_line1: "",
      shipping_city: "",
      shipping_state: "",
      shipping_zip: "",
      customer_notes: "",
    });
    setLineItems([]);
    setError(null);
    setShowItemWizard(false);
    onClose();
  };

  // Calculate order total
  const orderTotal = lineItems.reduce(
    (sum, li) => sum + li.quantity * li.unit_price,
    0
  );

  // Selected customer
  const selectedCustomer = customers.find(
    (c) => c.id === orderData.customer_id
  );

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 bg-black/70 flex items-center justify-center z-50 p-4">
      <div className="bg-gray-900 border border-gray-700 rounded-xl w-full max-w-4xl max-h-[90vh] flex flex-col">
        {/* Header */}
        <div className="p-6 border-b border-gray-800">
          <div className="flex justify-between items-start">
            <div>
              <h2 className="text-xl font-bold text-white">
                Create Sales Order
              </h2>
              <p className="text-gray-400 text-sm mt-1">
                Complete workflow: Customer → Products → Review
              </p>
            </div>
            <button
              onClick={handleClose}
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

          {/* Progress Steps */}
          <div className="flex items-center mt-6 gap-2">
            {STEPS.map((step, idx) => (
              <div key={step.id} className="flex items-center">
                <button
                  onClick={() =>
                    step.id < currentStep && setCurrentStep(step.id)
                  }
                  className={`flex items-center gap-2 px-3 py-2 rounded-lg transition-colors ${
                    step.id === currentStep
                      ? "bg-blue-600/20 text-blue-400 border border-blue-500/30"
                      : step.id < currentStep
                      ? "bg-green-600/20 text-green-400 border border-green-500/30 cursor-pointer hover:bg-green-600/30"
                      : "bg-gray-800 text-gray-500 border border-gray-700"
                  }`}
                >
                  <span
                    className={`w-6 h-6 rounded-full flex items-center justify-center text-sm font-medium ${
                      step.id === currentStep
                        ? "bg-blue-600 text-white"
                        : step.id < currentStep
                        ? "bg-green-600 text-white"
                        : "bg-gray-700 text-gray-400"
                    }`}
                  >
                    {step.id < currentStep ? "✓" : step.id}
                  </span>
                  <span className="font-medium">{step.name}</span>
                </button>
                {idx < STEPS.length - 1 && (
                  <div
                    className={`w-8 h-0.5 mx-2 ${
                      step.id < currentStep ? "bg-green-500" : "bg-gray-700"
                    }`}
                  />
                )}
              </div>
            ))}
          </div>
        </div>

        {/* Error Display */}
        {error && (
          <div className="mx-6 mt-4 bg-red-500/20 border border-red-500/30 rounded-lg p-3 text-red-400 text-sm">
            {error}
            <button
              onClick={() => setError(null)}
              className="float-right text-red-300 hover:text-white"
            >
              ×
            </button>
          </div>
        )}

        {/* Content */}
        <div className="flex-1 overflow-auto p-6">
          {/* Step 1: Customer */}
          {currentStep === 1 && (
            <CustomerSelectionStep
              customers={customers}
              orderData={orderData}
              setOrderData={setOrderData}
              selectedCustomer={selectedCustomer}
              lineItems={lineItems}
              currentStep={currentStep}
              onNavigateToNewCustomer={() => {
                sessionStorage.setItem(
                  "pendingOrderData",
                  JSON.stringify({
                    customer_id: orderData.customer_id,
                    shipping_address_line1: orderData.shipping_address_line1,
                    shipping_city: orderData.shipping_city,
                    shipping_state: orderData.shipping_state,
                    shipping_zip: orderData.shipping_zip,
                    customer_notes: orderData.customer_notes,
                    lineItems: lineItems,
                    currentStep: currentStep,
                  })
                );
                navigate("/admin/customers?action=new&returnTo=order");
              }}
            />
          )}

          {/* Step 2: Products */}
          {currentStep === 2 && (
            <div className="space-y-6">
              {!showItemWizard ? (
                <>
                  <div className="flex justify-between items-center">
                    <h3 className="text-lg font-semibold text-white">
                      Add Products
                    </h3>
                    <button
                      onClick={startNewItem}
                      className="px-4 py-2 bg-gradient-to-r from-green-600 to-emerald-600 text-white rounded-lg hover:from-green-500 hover:to-emerald-500 text-sm"
                    >
                      + Create New Product
                    </button>
                  </div>

                  {/* Product Search */}
                  <div className="relative">
                    <input
                      type="text"
                      placeholder="Search products by SKU or name..."
                      value={productSearch}
                      onChange={(e) => setProductSearch(e.target.value)}
                      className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-3 text-white pl-10"
                    />
                    <svg
                      className="w-5 h-5 absolute left-3 top-3.5 text-gray-500"
                      fill="none"
                      stroke="currentColor"
                      viewBox="0 0 24 24"
                    >
                      <path
                        strokeLinecap="round"
                        strokeLinejoin="round"
                        strokeWidth={2}
                        d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z"
                      />
                    </svg>
                    {productSearch && (
                      <button
                        onClick={() => setProductSearch("")}
                        className="absolute right-3 top-3.5 text-gray-500 hover:text-white"
                      >
                        <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                        </svg>
                      </button>
                    )}
                  </div>

                  {/* Product Grid */}
                  <div className="grid grid-cols-3 gap-3 max-h-[300px] overflow-auto">
                    {(() => {
                      const searchTerm = productSearch.trim().toLowerCase();
                      const filteredProducts = products.filter((p) => {
                        // Must be a sellable product (has BOM for costing)
                        if (!p.has_bom) return false;

                        // Filter by search term
                        if (!searchTerm) return true;
                        const nameMatch = (p.name || "").toLowerCase().includes(searchTerm);
                        const skuMatch = (p.sku || "").toLowerCase().includes(searchTerm);
                        return nameMatch || skuMatch;
                      });

                      if (filteredProducts.length === 0) {
                        return (
                          <div className="col-span-3 text-center py-8 text-gray-500">
                            {searchTerm
                              ? `No products with BOM found matching "${productSearch}"`
                              : "No products with BOM available. Create a BOM for your products to sell them."}
                          </div>
                        );
                      }

                      return filteredProducts.map((product) => (
                        <button
                          key={product.id}
                          onClick={() => addLineItem(product)}
                          className="text-left p-3 bg-gray-800 border border-gray-700 rounded-lg hover:border-blue-500 hover:bg-gray-800/80 transition-colors"
                        >
                          <div className="text-white font-medium text-sm truncate">
                            {product.name}
                          </div>
                          <div className="text-gray-500 text-xs font-mono">
                            {product.sku}
                          </div>
                          <div className="text-green-400 text-sm mt-1">
                            ${parseFloat(product.selling_price || 0).toFixed(2)}
                          </div>
                        </button>
                      ));
                    })()}
                  </div>

                  {/* Selected Line Items */}
                  {lineItems.length > 0 && (
                    <div className="space-y-2">
                      <h4 className="text-md font-medium text-white">
                        Order Lines
                      </h4>
                      <div className="bg-gray-800/50 rounded-lg border border-gray-700 divide-y divide-gray-700">
                        {lineItems.map((li) => (
                          <div
                            key={li.product_id}
                            className="p-3 flex items-center gap-4"
                          >
                            <div className="flex-1">
                              <div className="text-white font-medium">
                                {li.product?.name}
                              </div>
                              <div className="text-gray-500 text-xs font-mono">
                                {li.product?.sku}
                              </div>
                            </div>
                            <div className="flex items-center gap-2">
                              <label className="text-gray-400 text-sm">
                                Qty:
                              </label>
                              <input
                                type="number"
                                min="1"
                                value={li.quantity}
                                onChange={(e) =>
                                  updateLineQuantity(
                                    li.product_id,
                                    parseInt(e.target.value) || 1
                                  )
                                }
                                className="w-16 bg-gray-800 border border-gray-700 rounded px-2 py-1 text-white text-center"
                              />
                            </div>
                            <div className="flex items-center gap-2">
                              <label className="text-gray-400 text-sm">$</label>
                              <input
                                type="number"
                                step="0.01"
                                value={li.unit_price}
                                onChange={(e) =>
                                  updateLinePrice(
                                    li.product_id,
                                    parseFloat(e.target.value) || 0
                                  )
                                }
                                className="w-24 bg-gray-800 border border-gray-700 rounded px-2 py-1 text-white text-right"
                              />
                            </div>
                            <div className="text-green-400 font-medium w-24 text-right">
                              ${(li.quantity * li.unit_price).toFixed(2)}
                            </div>
                            <button
                              onClick={() => removeLineItem(li.product_id)}
                              className="text-red-400 hover:text-red-300 p-1"
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
                                  d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"
                                />
                              </svg>
                            </button>
                          </div>
                        ))}
                        <div className="p-3 flex justify-between items-center bg-gray-800/80">
                          <span className="text-white font-medium">
                            Order Total
                          </span>
                          <span className="text-green-400 font-bold text-lg">
                            ${orderTotal.toFixed(2)}
                          </span>
                        </div>
                      </div>
                    </div>
                  )}
                </>
              ) : (
                /* New Item Wizard */
                <div className="space-y-6">
                  <div className="flex items-center justify-between">
                    <h3 className="text-lg font-semibold text-white">
                      Create New Product - Step {itemWizardStep} of{" "}
                      {itemNeedsBom ? 3 : 2}
                    </h3>
                    <button
                      onClick={() => setShowItemWizard(false)}
                      className="text-gray-400 hover:text-white text-sm"
                    >
                      Cancel
                    </button>
                  </div>

                  {/* Progress indicator */}
                  <div className="flex gap-2">
                    <div
                      className={`flex-1 h-1 rounded ${
                        itemWizardStep >= 1 ? "bg-blue-500" : "bg-gray-700"
                      }`}
                    />
                    {itemNeedsBom && (
                      <div
                        className={`flex-1 h-1 rounded ${
                          itemWizardStep >= 2 ? "bg-blue-500" : "bg-gray-700"
                        }`}
                      />
                    )}
                    <div
                      className={`flex-1 h-1 rounded ${
                        itemWizardStep >= (itemNeedsBom ? 3 : 2)
                          ? "bg-blue-500"
                          : "bg-gray-700"
                      }`}
                    />
                  </div>

                  {/* Item Wizard Step 1: Basic Info */}
                  {itemWizardStep === 1 && (
                    <div className="space-y-4">
                      <div className="grid grid-cols-2 gap-4">
                        <div>
                          <label className="block text-sm text-gray-400 mb-1">
                            Item Type
                          </label>
                          <select
                            value={newItem.item_type}
                            onChange={(e) => {
                              const itemType = ITEM_TYPES.find(
                                (t) => t.value === e.target.value
                              );
                              setNewItem({
                                ...newItem,
                                item_type: e.target.value,
                                procurement_type:
                                  itemType?.defaultProcurement || "buy",
                                sku: "",
                              });
                            }}
                            className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-2 text-white"
                          >
                            {ITEM_TYPES.map((t) => (
                              <option key={t.value} value={t.value}>
                                {t.label}
                              </option>
                            ))}
                          </select>
                        </div>
                        <div>
                          <label className="block text-sm text-gray-400 mb-1">
                            Category
                          </label>
                          <select
                            value={newItem.category_id || ""}
                            onChange={(e) =>
                              setNewItem({
                                ...newItem,
                                category_id: e.target.value
                                  ? parseInt(e.target.value)
                                  : null,
                              })
                            }
                            className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-2 text-white"
                          >
                            <option value="">-- None --</option>
                            {categories.map((c) => (
                              <option key={c.id} value={c.id}>
                                {c.full_path || c.name}
                              </option>
                            ))}
                          </select>
                        </div>
                      </div>

                      {/* Make vs Buy selector */}
                      <div>
                        <label className="block text-sm text-gray-400 mb-2">
                          Procurement Type (Make vs Buy)
                        </label>
                        <div className="grid grid-cols-3 gap-2">
                          {PROCUREMENT_TYPES.map((pt) => (
                            <button
                              key={pt.value}
                              type="button"
                              onClick={() =>
                                setNewItem({
                                  ...newItem,
                                  procurement_type: pt.value,
                                })
                              }
                              className={`p-3 rounded-lg border text-left transition-colors ${
                                newItem.procurement_type === pt.value
                                  ? pt.value === "make"
                                    ? "bg-green-600/20 border-green-500 text-green-400"
                                    : pt.value === "buy"
                                    ? "bg-blue-600/20 border-blue-500 text-blue-400"
                                    : "bg-yellow-600/20 border-yellow-500 text-yellow-400"
                                  : "bg-gray-800 border-gray-700 text-gray-400 hover:border-gray-500"
                              }`}
                            >
                              <div className="font-medium text-sm">
                                {pt.label}
                              </div>
                              <div className="text-xs opacity-70 mt-1">
                                {pt.description}
                              </div>
                            </button>
                          ))}
                        </div>
                        {itemNeedsBom && (
                          <p className="text-xs text-green-400 mt-2">
                            This item will have a BOM and/or routing
                          </p>
                        )}
                      </div>

                      <div>
                        <label className="block text-sm text-gray-400 mb-1">
                          Product Name *
                        </label>
                        <input
                          type="text"
                          value={newItem.name}
                          onChange={(e) =>
                            setNewItem({ ...newItem, name: e.target.value })
                          }
                          placeholder="e.g. Custom Widget Assembly"
                          className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-2 text-white"
                        />
                      </div>

                      <div className="grid grid-cols-2 gap-4">
                        <div>
                          <label className="block text-sm text-gray-400 mb-1">
                            SKU (auto-generated)
                          </label>
                          <input
                            type="text"
                            value={newItem.sku}
                            onChange={(e) =>
                              setNewItem({
                                ...newItem,
                                sku: e.target.value.toUpperCase(),
                              })
                            }
                            className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-2 text-white font-mono"
                          />
                          <p className="text-xs text-gray-500 mt-1">
                            Auto-generated from type + timestamp
                          </p>
                        </div>
                        <div>
                          <label className="block text-sm text-gray-400 mb-1">
                            Unit
                          </label>
                          <input
                            type="text"
                            value={newItem.unit}
                            onChange={(e) =>
                              setNewItem({
                                ...newItem,
                                unit: e.target.value.toUpperCase(),
                              })
                            }
                            className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-2 text-white"
                          />
                        </div>
                      </div>

                      <div>
                        <label className="block text-sm text-gray-400 mb-1">
                          Description
                        </label>
                        <textarea
                          value={newItem.description}
                          onChange={(e) =>
                            setNewItem({
                              ...newItem,
                              description: e.target.value,
                            })
                          }
                          rows={2}
                          className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-2 text-white"
                        />
                      </div>

                      <div className="flex justify-end">
                        <button
                          onClick={() =>
                            setItemWizardStep(
                              itemNeedsBom ? 2 : itemNeedsBom ? 3 : 2
                            )
                          }
                          disabled={!newItem.name}
                          className="px-6 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-500 disabled:opacity-50"
                        >
                          {itemNeedsBom
                            ? "Next: Add BOM Components"
                            : "Next: Set Pricing"}
                        </button>
                      </div>
                    </div>
                  )}

                  {/* Item Wizard Step 2: BOM Builder (only for finished goods) */}
                  {itemWizardStep === 2 && itemNeedsBom && (
                    <div className="space-y-4 max-h-[60vh] overflow-auto pr-2">
                      <div className="bg-blue-500/10 border border-blue-500/30 rounded-lg p-4">
                        <p className="text-blue-400 text-sm">
                          Add components, processes, and images for this
                          product. Costs are calculated automatically.
                        </p>
                      </div>

                      {/* Image Dropbox */}
                      <div>
                        <label className="block text-sm text-gray-400 mb-2">
                          Product Images
                        </label>
                        <div
                          onDrop={handleImageDrop}
                          onDragOver={(e) => e.preventDefault()}
                          className="border-2 border-dashed border-gray-600 rounded-lg p-4 text-center hover:border-blue-500 transition-colors cursor-pointer"
                          onClick={() =>
                            document.getElementById("image-input").click()
                          }
                        >
                          <input
                            type="file"
                            id="image-input"
                            multiple
                            accept="image/*"
                            onChange={handleImageSelect}
                            className="hidden"
                          />
                          <svg
                            className="w-8 h-8 mx-auto text-gray-500 mb-2"
                            fill="none"
                            stroke="currentColor"
                            viewBox="0 0 24 24"
                          >
                            <path
                              strokeLinecap="round"
                              strokeLinejoin="round"
                              strokeWidth={2}
                              d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z"
                            />
                          </svg>
                          <p className="text-gray-400 text-sm">
                            Drop images here or click to browse
                          </p>
                          <p className="text-gray-500 text-xs mt-1">
                            For online marketplaces
                          </p>
                        </div>
                        {imagePreviewUrls.length > 0 && (
                          <div className="flex gap-2 mt-3 flex-wrap">
                            {imagePreviewUrls.map((url, idx) => (
                              <div key={idx} className="relative group">
                                <img
                                  src={url}
                                  alt={`Preview ${idx + 1}`}
                                  className="w-16 h-16 object-cover rounded-lg border border-gray-700"
                                />
                                <button
                                  onClick={(e) => {
                                    e.stopPropagation();
                                    removeImage(idx);
                                  }}
                                  className="absolute -top-2 -right-2 w-5 h-5 bg-red-500 rounded-full text-white text-xs opacity-0 group-hover:opacity-100 transition-opacity"
                                >
                                  ×
                                </button>
                              </div>
                            ))}
                          </div>
                        )}
                      </div>

                      {/* BOM Components Section */}
                      <div className="border-t border-gray-700 pt-4">
                        <div className="flex justify-between items-center mb-2">
                          <label className="text-sm text-gray-400">
                            BOM Components (Materials)
                          </label>
                          <div className="flex gap-2">
                            <button
                              type="button"
                              onClick={() => setShowMaterialWizard(true)}
                              className="text-xs px-2 py-1 bg-pink-600/20 border border-pink-500/30 text-pink-400 rounded hover:bg-pink-600/30"
                            >
                              + Add Filament
                            </button>
                            <button
                              type="button"
                              onClick={startSubComponent}
                              className="text-xs px-2 py-1 bg-purple-600/20 border border-purple-500/30 text-purple-400 rounded hover:bg-purple-600/30"
                            >
                              + Create Component
                            </button>
                          </div>
                        </div>

                        {/* Inline Material (Filament) Wizard */}
                        {showMaterialWizard && (
                          <div className="bg-pink-900/20 border border-pink-500/30 rounded-lg p-4 mb-3 space-y-3">
                            <div className="flex justify-between items-center">
                              <span className="text-pink-400 font-medium text-sm">
                                Add Filament to Inventory
                              </span>
                              <button
                                type="button"
                                onClick={() => setShowMaterialWizard(false)}
                                className="text-gray-400 hover:text-white text-xs"
                              >
                                Cancel
                              </button>
                            </div>
                            <div className="grid grid-cols-2 gap-3">
                              <div>
                                <label className="block text-xs text-gray-400 mb-1">
                                  Material Type *
                                </label>
                                <select
                                  value={newMaterial.material_type_code}
                                  onChange={(e) => {
                                    const code = e.target.value;
                                    setNewMaterial({
                                      ...newMaterial,
                                      material_type_code: code,
                                      color_code: "",
                                    });
                                    fetchColorsForType(code);
                                  }}
                                  className="w-full bg-gray-800 border border-gray-700 rounded px-3 py-1.5 text-white text-sm"
                                >
                                  <option value="">Select material...</option>
                                  {materialTypes.map((mt) => (
                                    <option key={mt.code} value={mt.code}>
                                      {mt.name}
                                    </option>
                                  ))}
                                </select>
                              </div>
                              <div>
                                <label className="block text-xs text-gray-400 mb-1">
                                  Color *
                                </label>
                                <select
                                  value={newMaterial.color_code}
                                  onChange={(e) =>
                                    setNewMaterial({
                                      ...newMaterial,
                                      color_code: e.target.value,
                                    })
                                  }
                                  disabled={!newMaterial.material_type_code}
                                  className="w-full bg-gray-800 border border-gray-700 rounded px-3 py-1.5 text-white text-sm disabled:opacity-50"
                                >
                                  <option value="">
                                    {newMaterial.material_type_code
                                      ? "Select color..."
                                      : "Select material first"}
                                  </option>
                                  {allColors.map((c) => (
                                    <option key={c.code} value={c.code}>
                                      {c.name}
                                    </option>
                                  ))}
                                </select>
                              </div>
                              <div>
                                <label className="block text-xs text-gray-400 mb-1">
                                  Quantity (kg)
                                </label>
                                <input
                                  type="number"
                                  step="0.1"
                                  value={newMaterial.quantity_kg}
                                  onChange={(e) =>
                                    setNewMaterial({
                                      ...newMaterial,
                                      quantity_kg:
                                        parseFloat(e.target.value) || 1.0,
                                    })
                                  }
                                  className="w-full bg-gray-800 border border-gray-700 rounded px-3 py-1.5 text-white text-sm"
                                />
                              </div>
                              <div>
                                <label className="block text-xs text-gray-400 mb-1">
                                  Cost per kg ($)
                                </label>
                                <input
                                  type="number"
                                  step="0.01"
                                  value={newMaterial.cost_per_kg || ""}
                                  onChange={(e) =>
                                    setNewMaterial({
                                      ...newMaterial,
                                      cost_per_kg:
                                        parseFloat(e.target.value) || null,
                                    })
                                  }
                                  placeholder="Auto from material"
                                  className="w-full bg-gray-800 border border-gray-700 rounded px-3 py-1.5 text-white text-sm"
                                />
                              </div>
                            </div>
                            <div className="flex justify-end">
                              <button
                                type="button"
                                onClick={handleCreateMaterial}
                                disabled={
                                  loading ||
                                  !newMaterial.material_type_code ||
                                  !newMaterial.color_code
                                }
                                className="px-3 py-1.5 bg-pink-600 text-white text-sm rounded hover:bg-pink-500 disabled:opacity-50"
                              >
                                {loading
                                  ? "Creating..."
                                  : "Add to Inventory & BOM"}
                              </button>
                            </div>
                          </div>
                        )}

                        {/* Inline Sub-Component Wizard */}
                        {showSubComponentWizard && (
                          <div className="bg-purple-900/20 border border-purple-500/30 rounded-lg p-4 mb-3 space-y-3">
                            <div className="flex justify-between items-center">
                              <span className="text-purple-400 font-medium text-sm">
                                New Component
                              </span>
                              <button
                                type="button"
                                onClick={() => setShowSubComponentWizard(false)}
                                className="text-gray-400 hover:text-white text-xs"
                              >
                                Cancel
                              </button>
                            </div>
                            <div className="grid grid-cols-2 gap-3">
                              <div>
                                <label className="block text-xs text-gray-400 mb-1">
                                  Component Name *
                                </label>
                                <input
                                  type="text"
                                  value={subComponent.name}
                                  onChange={(e) =>
                                    setSubComponent({
                                      ...subComponent,
                                      name: e.target.value,
                                    })
                                  }
                                  placeholder="e.g. M3 Heat Insert"
                                  className="w-full bg-gray-800 border border-gray-700 rounded px-3 py-1.5 text-white text-sm"
                                />
                              </div>
                              <div>
                                <label className="block text-xs text-gray-400 mb-1">
                                  SKU
                                </label>
                                <input
                                  type="text"
                                  value={subComponent.sku}
                                  onChange={(e) =>
                                    setSubComponent({
                                      ...subComponent,
                                      sku: e.target.value.toUpperCase(),
                                    })
                                  }
                                  className="w-full bg-gray-800 border border-gray-700 rounded px-3 py-1.5 text-white text-sm font-mono"
                                />
                              </div>
                              <div>
                                <label className="block text-xs text-gray-400 mb-1">
                                  Unit Cost ($)
                                </label>
                                <input
                                  type="number"
                                  step="0.01"
                                  value={subComponent.standard_cost || ""}
                                  onChange={(e) =>
                                    setSubComponent({
                                      ...subComponent,
                                      standard_cost:
                                        parseFloat(e.target.value) || null,
                                    })
                                  }
                                  placeholder="0.00"
                                  className="w-full bg-gray-800 border border-gray-700 rounded px-3 py-1.5 text-white text-sm"
                                />
                              </div>
                              <div>
                                <label className="block text-xs text-gray-400 mb-1">
                                  Unit
                                </label>
                                <input
                                  type="text"
                                  value={subComponent.unit}
                                  onChange={(e) =>
                                    setSubComponent({
                                      ...subComponent,
                                      unit: e.target.value.toUpperCase(),
                                    })
                                  }
                                  className="w-full bg-gray-800 border border-gray-700 rounded px-3 py-1.5 text-white text-sm"
                                />
                              </div>
                            </div>
                            <div className="flex justify-end">
                              <button
                                type="button"
                                onClick={handleSaveSubComponent}
                                disabled={loading || !subComponent.name}
                                className="px-3 py-1.5 bg-purple-600 text-white text-sm rounded hover:bg-purple-500 disabled:opacity-50"
                              >
                                {loading
                                  ? "Creating..."
                                  : "Create & Add to BOM"}
                              </button>
                            </div>
                          </div>
                        )}

                        <select
                          onChange={(e) => {
                            const val = e.target.value;
                            // Handle both numeric IDs (items) and string IDs (materials)
                            const comp = components.find(
                              (c) => String(c.id) === val
                            );
                            if (comp) addBomLine(comp);
                            e.target.value = "";
                          }}
                          className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-2 text-white"
                        >
                          <option value="">
                            -- Select component or material to add --
                          </option>
                          <optgroup label="📦 Components & Supplies">
                            {components
                              .filter(
                                (c) =>
                                  !c.is_material &&
                                  !bomLines.find(
                                    (bl) => bl.component_id === c.id
                                  )
                              )
                              .map((c) => (
                                <option key={c.id} value={c.id}>
                                  {c.sku} - {c.name} ($
                                  {parseFloat(
                                    c.standard_cost ||
                                      c.average_cost ||
                                      c.cost ||
                                      0
                                  ).toFixed(2)}
                                  /{c.unit})
                                </option>
                              ))}
                          </optgroup>
                          <optgroup label="🎨 Filament / Materials">
                            {components
                              .filter(
                                (c) =>
                                  c.is_material &&
                                  !bomLines.find(
                                    (bl) => bl.component_id === c.id
                                  )
                              )
                              .map((c) => (
                                <option key={c.id} value={c.id}>
                                  {c.name} {c.in_stock ? "" : "(Out of Stock)"}{" "}
                                  ($
                                  {parseFloat(c.standard_cost || 0).toFixed(3)}/
                                  {c.unit})
                                </option>
                              ))}
                          </optgroup>
                        </select>
                      </div>

                      {/* BOM Lines */}
                      {bomLines.length > 0 && (
                        <div className="bg-gray-800/50 rounded-lg border border-gray-700 divide-y divide-gray-700">
                          {bomLines.map((line) => (
                            <div
                              key={line.component_id}
                              className="p-3 flex items-center gap-4"
                            >
                              <div className="flex-1">
                                <div className="flex items-center gap-2">
                                  <span className="text-white font-medium">
                                    {line.component_name}
                                  </span>
                                  {line.is_material && (
                                    <span className="text-xs bg-purple-600/30 text-purple-300 px-1.5 py-0.5 rounded">
                                      Filament
                                    </span>
                                  )}
                                </div>
                                <div className="text-gray-500 text-xs font-mono">
                                  {line.component_sku}
                                </div>
                              </div>
                              <div className="flex items-center gap-2">
                                <label className="text-gray-400 text-sm">
                                  Qty:
                                </label>
                                <input
                                  type="number"
                                  min="0.01"
                                  step="0.01"
                                  value={line.quantity}
                                  onChange={(e) =>
                                    updateBomQuantity(
                                      line.component_id,
                                      parseFloat(e.target.value) || 0.01
                                    )
                                  }
                                  className="w-20 bg-gray-800 border border-gray-700 rounded px-2 py-1 text-white text-center"
                                />
                                <span className="text-gray-500 text-sm">
                                  {line.component_unit}
                                </span>
                              </div>
                              <div className="text-gray-400 text-sm">
                                @ ${parseFloat(line.component_cost).toFixed(2)}
                              </div>
                              <div className="text-green-400 font-medium w-20 text-right">
                                $
                                {(line.quantity * line.component_cost).toFixed(
                                  2
                                )}
                              </div>
                              <button
                                onClick={() => removeBomLine(line.component_id)}
                                className="text-red-400 hover:text-red-300 p-1"
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
                          ))}
                          <div className="p-3 flex justify-between items-center bg-gray-800/80">
                            <span className="text-white font-medium">
                              Material Cost
                            </span>
                            <span className="text-green-400 font-bold">
                              ${calculatedCost.toFixed(2)}
                            </span>
                          </div>
                        </div>
                      )}

                      {/* Processes/Routing Section */}
                      <div className="border-t border-gray-700 pt-4">
                        <div className="flex justify-between items-center mb-2">
                          <label className="text-sm text-gray-400">
                            Manufacturing Processes
                          </label>
                          {routingTemplates.length > 0 && (
                            <select
                              value={selectedTemplate?.id || ""}
                              onChange={(e) => {
                                const tpl = routingTemplates.find(
                                  (t) => t.id === parseInt(e.target.value)
                                );
                                applyRoutingTemplate(tpl || null);
                              }}
                              className="text-xs bg-gray-800 border border-gray-700 rounded px-2 py-1 text-gray-300"
                            >
                              <option value="">Use Template...</option>
                              {routingTemplates.map((t) => (
                                <option key={t.id} value={t.id}>
                                  {t.name || t.code}
                                </option>
                              ))}
                            </select>
                          )}
                        </div>
                        <select
                          onChange={(e) => {
                            const wc = workCenters.find(
                              (w) => w.id === parseInt(e.target.value)
                            );
                            if (wc) addRoutingOperation(wc);
                            e.target.value = "";
                          }}
                          className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-2 text-white"
                        >
                          <option value="">-- Add process step --</option>
                          {workCenters.map((wc) => (
                            <option key={wc.id} value={wc.id}>
                              {wc.name} ($
                              {parseFloat(wc.total_rate_per_hour || 0).toFixed(
                                2
                              )}
                              /hr)
                            </option>
                          ))}
                        </select>
                      </div>

                      {/* Routing Operations */}
                      {routingOperations.length > 0 && (
                        <div className="bg-purple-500/10 border border-purple-500/30 rounded-lg divide-y divide-purple-500/20">
                          {routingOperations.map((op, idx) => (
                            <div
                              key={op.id}
                              className="p-3 flex items-center gap-3"
                            >
                              <div className="w-6 h-6 rounded-full bg-purple-600 text-white text-xs flex items-center justify-center font-medium">
                                {idx + 1}
                              </div>
                              <div className="flex-1">
                                <div className="text-white font-medium">
                                  {op.operation_name}
                                </div>
                                <div className="text-purple-400 text-xs">
                                  {op.work_center_code}
                                </div>
                              </div>
                              <div className="flex items-center gap-2">
                                <div className="text-xs text-gray-400">
                                  Setup:
                                </div>
                                <input
                                  type="number"
                                  min="0"
                                  step="1"
                                  value={op.setup_time_minutes}
                                  onChange={(e) =>
                                    updateOperationTime(
                                      op.id,
                                      "setup_time_minutes",
                                      e.target.value
                                    )
                                  }
                                  className="w-14 bg-gray-800 border border-gray-700 rounded px-2 py-1 text-white text-center text-sm"
                                />
                                <span className="text-gray-500 text-xs">
                                  min
                                </span>
                              </div>
                              <div className="flex items-center gap-2">
                                <div className="text-xs text-gray-400">
                                  Run:
                                </div>
                                <input
                                  type="number"
                                  min="0"
                                  step="1"
                                  value={op.run_time_minutes}
                                  onChange={(e) =>
                                    updateOperationTime(
                                      op.id,
                                      "run_time_minutes",
                                      e.target.value
                                    )
                                  }
                                  className="w-14 bg-gray-800 border border-gray-700 rounded px-2 py-1 text-white text-center text-sm"
                                />
                                <span className="text-gray-500 text-xs">
                                  min
                                </span>
                              </div>
                              <div className="text-purple-400 font-medium w-16 text-right text-sm">
                                $
                                {(
                                  ((op.setup_time_minutes +
                                    op.run_time_minutes) /
                                    60) *
                                  op.rate_per_hour
                                ).toFixed(2)}
                              </div>
                              <button
                                onClick={() => removeRoutingOperation(op.id)}
                                className="text-red-400 hover:text-red-300 p-1"
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
                                    d="M6 18L18 6M6 6l12 12"
                                  />
                                </svg>
                              </button>
                            </div>
                          ))}
                          <div className="p-3 flex justify-between items-center bg-purple-900/30">
                            <span className="text-white font-medium">
                              Labor Cost
                            </span>
                            <span className="text-purple-400 font-bold">
                              ${laborCost.toFixed(2)}
                            </span>
                          </div>
                        </div>
                      )}

                      {/* Cost Summary */}
                      {(bomLines.length > 0 ||
                        routingOperations.length > 0) && (
                        <div className="bg-gray-800 rounded-lg p-4 border border-gray-700">
                          <div className="flex justify-between items-center">
                            <div>
                              <span className="text-gray-400 text-sm">
                                Total Product Cost
                              </span>
                              <div className="text-xs text-gray-500">
                                Materials + Labor
                              </div>
                            </div>
                            <span className="text-green-400 font-bold text-xl">
                              ${totalCost.toFixed(2)}
                            </span>
                          </div>
                        </div>
                      )}

                      <div className="flex justify-between pt-2">
                        <button
                          onClick={() => setItemWizardStep(1)}
                          className="px-4 py-2 text-gray-400 hover:text-white"
                        >
                          Back
                        </button>
                        <button
                          onClick={() => setItemWizardStep(3)}
                          className="px-6 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-500"
                        >
                          Next: Set Pricing
                        </button>
                      </div>
                    </div>
                  )}

                  {/* Item Wizard Step 3 (or 2 if no BOM): Pricing */}
                  {itemWizardStep === (itemNeedsBom ? 3 : 2) && (
                    <div className="space-y-4">
                      <div className="bg-gray-800/50 rounded-lg p-4 border border-gray-700">
                        <div className="grid grid-cols-3 gap-4">
                          <div>
                            <div className="text-gray-400 text-sm">
                              Material Cost
                            </div>
                            <div className="text-xl font-bold text-green-400">
                              ${calculatedCost.toFixed(2)}
                            </div>
                          </div>
                          <div>
                            <div className="text-gray-400 text-sm">
                              Labor Cost
                            </div>
                            <div className="text-xl font-bold text-purple-400">
                              ${laborCost.toFixed(2)}
                            </div>
                          </div>
                          <div>
                            <div className="text-gray-400 text-sm">
                              Total Cost
                            </div>
                            <div className="text-xl font-bold text-white">
                              ${totalCost.toFixed(2)}
                            </div>
                          </div>
                        </div>
                      </div>

                      <div className="bg-gray-800/50 rounded-lg p-4 border border-gray-700">
                        <div className="text-gray-400 text-sm mb-2">
                          <label>Target Margin %</label>
                        </div>
                        <input
                          type="number"
                          min="0"
                          max="99"
                          value={targetMargin}
                          onChange={(e) =>
                            setTargetMargin(parseFloat(e.target.value) || 0)
                          }
                          className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-2 text-white text-xl font-bold"
                        />
                      </div>

                      <div className="bg-green-500/10 border border-green-500/30 rounded-lg p-4">
                        <div className="flex justify-between items-center">
                          <div>
                            <div className="text-gray-400 text-sm">
                              Suggested Selling Price
                            </div>
                            <div className="text-3xl font-bold text-green-400">
                              ${suggestedPrice.toFixed(2)}
                            </div>
                            <div className="text-gray-500 text-xs mt-1">
                              Based on {targetMargin}% margin
                            </div>
                          </div>
                          <button
                            onClick={() =>
                              setNewItem({
                                ...newItem,
                                selling_price: suggestedPrice,
                              })
                            }
                            className="px-4 py-2 bg-green-600/20 border border-green-500/30 text-green-400 rounded-lg hover:bg-green-600/30"
                          >
                            Use Suggested
                          </button>
                        </div>
                      </div>

                      <div className="grid grid-cols-2 gap-4">
                        <div>
                          <label className="block text-sm text-gray-400 mb-1">
                            Standard Cost
                          </label>
                          <input
                            type="number"
                            step="0.01"
                            value={newItem.standard_cost || totalCost || ""}
                            onChange={(e) =>
                              setNewItem({
                                ...newItem,
                                standard_cost:
                                  parseFloat(e.target.value) || null,
                              })
                            }
                            className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-2 text-white"
                          />
                          <p className="text-xs text-gray-500 mt-1">
                            Auto-filled from BOM + Labor
                          </p>
                        </div>
                        <div>
                          <label className="block text-sm text-gray-400 mb-1">
                            Selling Price *
                          </label>
                          <input
                            type="number"
                            step="0.01"
                            value={newItem.selling_price || ""}
                            onChange={(e) =>
                              setNewItem({
                                ...newItem,
                                selling_price:
                                  parseFloat(e.target.value) || null,
                              })
                            }
                            placeholder={suggestedPrice.toFixed(2)}
                            className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-2 text-white"
                          />
                        </div>
                      </div>

                      {/* Margin Preview */}
                      {newItem.selling_price > 0 && totalCost > 0 && (
                        <div className="bg-gray-800/50 rounded-lg p-4 border border-gray-700">
                          <div className="text-gray-400 text-sm mb-2">
                            Actual Margin Preview
                          </div>
                          <div className="flex gap-8">
                            <div>
                              <div className="text-gray-500 text-xs">
                                Gross Profit
                              </div>
                              <div className="text-white font-medium">
                                $
                                {(newItem.selling_price - totalCost).toFixed(2)}
                              </div>
                            </div>
                            <div>
                              <div className="text-gray-500 text-xs">
                                Margin %
                              </div>
                              <div
                                className={`font-medium ${
                                  ((newItem.selling_price - totalCost) /
                                    newItem.selling_price) *
                                    100 >=
                                  targetMargin
                                    ? "text-green-400"
                                    : "text-yellow-400"
                                }`}
                              >
                                {(
                                  ((newItem.selling_price - totalCost) /
                                    newItem.selling_price) *
                                  100
                                ).toFixed(1)}
                                %
                              </div>
                            </div>
                            <div>
                              <div className="text-gray-500 text-xs">
                                Markup %
                              </div>
                              <div className="text-white font-medium">
                                {(
                                  ((newItem.selling_price - totalCost) /
                                    totalCost) *
                                  100
                                ).toFixed(1)}
                                %
                              </div>
                            </div>
                          </div>
                        </div>
                      )}

                      <div className="flex justify-between">
                        <button
                          onClick={() =>
                            setItemWizardStep(itemNeedsBom ? 2 : 1)
                          }
                          className="px-4 py-2 text-gray-400 hover:text-white"
                        >
                          Back
                        </button>
                        <button
                          onClick={handleSaveNewItem}
                          disabled={loading || !newItem.name || !newItem.sku}
                          className="px-6 py-2 bg-gradient-to-r from-green-600 to-emerald-600 text-white rounded-lg hover:from-green-500 hover:to-emerald-500 disabled:opacity-50"
                        >
                          {loading
                            ? "Creating..."
                            : "Create Product & Add to Order"}
                        </button>
                      </div>
                    </div>
                  )}
                </div>
              )}
            </div>
          )}

          {/* Step 3: Review */}
          {currentStep === 3 && (
            <ReviewStep
              selectedCustomer={selectedCustomer}
              orderData={orderData}
              lineItems={lineItems}
              orderTotal={orderTotal}
              taxSettings={taxSettings}
            />
          )}
        </div>

        {/* Footer */}
        <div className="p-6 border-t border-gray-800 flex justify-between">
          <button
            onClick={
              currentStep === 1
                ? handleClose
                : () => setCurrentStep(currentStep - 1)
            }
            className="px-4 py-2 text-gray-400 hover:text-white"
          >
            {currentStep === 1 ? "Cancel" : "Back"}
          </button>

          {currentStep < 3 ? (
            <button
              onClick={handleNextStep}
              disabled={currentStep === 2 && lineItems.length === 0}
              className="px-6 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-500 disabled:opacity-50"
            >
              Continue
            </button>
          ) : (
            <button
              onClick={handleSubmitOrder}
              disabled={loading || lineItems.length === 0}
              className="px-6 py-2 bg-gradient-to-r from-green-600 to-emerald-600 text-white rounded-lg hover:from-green-500 hover:to-emerald-500 disabled:opacity-50"
            >
              {loading ? "Creating Order..." : "Create Sales Order"}
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
