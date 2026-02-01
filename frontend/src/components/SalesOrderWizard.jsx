import { useState, useEffect, useMemo } from "react";
import { useNavigate } from "react-router-dom";
import { API_URL } from "../config/api";
import { validateRequired, validateQuantity } from "../utils/validation";
import CustomerSelectionStep from "./sales-order/CustomerSelectionStep";
import ItemCreationWizard from "./sales-order/ItemCreationWizard";
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
                <ItemCreationWizard
                  ITEM_TYPES={ITEM_TYPES}
                  PROCUREMENT_TYPES={PROCUREMENT_TYPES}
                  itemWizardStep={itemWizardStep}
                  setItemWizardStep={setItemWizardStep}
                  itemNeedsBom={itemNeedsBom}
                  newItem={newItem}
                  setNewItem={setNewItem}
                  categories={categories}
                  bomLines={bomLines}
                  addBomLine={addBomLine}
                  removeBomLine={removeBomLine}
                  updateBomQuantity={updateBomQuantity}
                  components={components}
                  showMaterialWizard={showMaterialWizard}
                  setShowMaterialWizard={setShowMaterialWizard}
                  newMaterial={newMaterial}
                  setNewMaterial={setNewMaterial}
                  materialTypes={materialTypes}
                  allColors={allColors}
                  fetchColorsForType={fetchColorsForType}
                  handleCreateMaterial={handleCreateMaterial}
                  showSubComponentWizard={showSubComponentWizard}
                  setShowSubComponentWizard={setShowSubComponentWizard}
                  startSubComponent={startSubComponent}
                  subComponent={subComponent}
                  setSubComponent={setSubComponent}
                  handleSaveSubComponent={handleSaveSubComponent}
                  routingOperations={routingOperations}
                  addRoutingOperation={addRoutingOperation}
                  removeRoutingOperation={removeRoutingOperation}
                  updateOperationTime={updateOperationTime}
                  workCenters={workCenters}
                  routingTemplates={routingTemplates}
                  selectedTemplate={selectedTemplate}
                  applyRoutingTemplate={applyRoutingTemplate}
                  imagePreviewUrls={imagePreviewUrls}
                  handleImageSelect={handleImageSelect}
                  handleImageDrop={handleImageDrop}
                  removeImage={removeImage}
                  calculatedCost={calculatedCost}
                  laborCost={laborCost}
                  totalCost={totalCost}
                  targetMargin={targetMargin}
                  setTargetMargin={setTargetMargin}
                  suggestedPrice={suggestedPrice}
                  loading={loading}
                  onSave={handleSaveNewItem}
                  onCancel={() => setShowItemWizard(false)}
                />
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
