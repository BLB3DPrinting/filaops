import { useState } from "react";
import { API_URL } from "../../config/api.js";

/**
 * Custom hook that manages BOM line CRUD operations,
 * product/UOM reference data, and the exploded BOM view.
 */
export default function useBOMLines({ bom, toast, onUpdate }) {
  const [lines, setLines] = useState(bom.lines || []);
  const [loading, setLoading] = useState(false);
  const [editingLine, setEditingLine] = useState(null);
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

  // Sub-assembly / exploded view state
  const [showExploded, setShowExploded] = useState(false);
  const [explodedData, setExplodedData] = useState(null);
  const [costRollup, setCostRollup] = useState(null);

  // ─── Initialization fetches ──────────────────────────────────

  function fetchInitialLineData() {
    const fetchProducts = async () => {
      try {
        const res = await fetch(
          `${API_URL}/api/v1/products?limit=500&is_raw_material=true`,
          { credentials: "include" }
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
          credentials: "include",
        });
        if (res.ok) {
          const data = await res.json();
          setUoms(data);
        }
      } catch {
        // Non-critical
      }
    };

    const fetchCostRollup = async () => {
      try {
        const res = await fetch(
          `${API_URL}/api/v1/admin/bom/${bom.id}/cost-rollup`,
          { credentials: "include" }
        );
        if (res.ok) {
          const data = await res.json();
          setCostRollup(data);
        }
      } catch {
        // Non-critical
      }
    };

    fetchProducts();
    fetchUOMs();
    fetchCostRollup();
  }

  // ─── Exploded BOM ────────────────────────────────────────────

  async function fetchExploded() {
    setLoading(true);
    try {
      const res = await fetch(
        `${API_URL}/api/v1/admin/bom/${bom.id}/explode`,
        { credentials: "include" }
      );
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
  }

  // ─── Line CRUD ──────────────────────────────────────────────

  async function handleAddLine() {
    if (!newLine.component_id) return;

    setLoading(true);
    try {
      const res = await fetch(`${API_URL}/api/v1/admin/bom/${bom.id}/lines`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
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
      toast.error(
        `Failed to add BOM line: ${err.message || "Network error"}`
      );
    } finally {
      setLoading(false);
    }
  }

  async function handleUpdateLine(lineId, updates) {
    setLoading(true);
    try {
      const res = await fetch(
        `${API_URL}/api/v1/admin/bom/${bom.id}/lines/${lineId}`,
        {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          credentials: "include",
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
  }

  async function handleDeleteLine(lineId) {
    if (!confirm("Are you sure you want to delete this line?")) return;

    setLoading(true);
    try {
      const res = await fetch(
        `${API_URL}/api/v1/admin/bom/${bom.id}/lines/${lineId}`,
        {
          method: "DELETE",
          credentials: "include",
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
  }

  return {
    // Line state
    lines,
    loading,
    editingLine,
    setEditingLine,
    newLine,
    setNewLine,
    showAddLine,
    setShowAddLine,
    products,
    uoms,

    // Exploded / cost rollup state
    showExploded,
    setShowExploded,
    explodedData,
    costRollup,

    // Handlers
    fetchInitialLineData,
    fetchExploded,
    handleAddLine,
    handleUpdateLine,
    handleDeleteLine,
  };
}
