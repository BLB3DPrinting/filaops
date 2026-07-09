/**
 * Display helpers for the operation-type catalog (#876 PR-4).
 *
 * The catalog itself is fetched once by RoutingEditorContent from
 * GET /api/v1/operation-types and passed down as a prop. This module is
 * presentation-only: grouping for the picker's <optgroup>s, the canonical
 * short operation_code each type pre-fills into the (now secondary/
 * editable) Operation Code field, and a frozen fallback label/description
 * table so an already-typed operation's badge never goes blank if its type
 * isn't in the currently-fetched active-only catalog (e.g. a deactivated
 * custom type still stamped on an existing operation).
 */

// Canonical short operation_code pre-filled when a type is picked. This is
// a display convenience only — the backend drives all real semantics off
// operation_type, not this code (see operation_material_mapping.py
// resolve_consume_stages). GENERAL has no single canonical short code.
export const CANONICAL_OPERATION_CODE = {
  FDM_PRINT: "PRINT",
  RESIN_PRINT: "PRINT",
  ASSEMBLY: "ASSEMBLE",
  QUALITY_CONTROL: "QC",
  SUPPORT_REMOVAL: "CLEAN",
  SANDING: "SAND",
  PAINTING: "PAINT",
  PACK_SHIP: "PACK",
  GENERAL: "",
};

// Fallback label/description/category for the 9 system types, verbatim
// from migrations/versions/101_operation_types.py SEED_OPERATION_TYPES.
// Only consulted when a code isn't present in the fetched (active-only)
// catalog prop.
export const OPERATION_TYPE_FALLBACK = {
  FDM_PRINT: {
    label: "FDM Print",
    description: "Materials count when the production order completes.",
    category: "print",
  },
  RESIN_PRINT: {
    label: "Resin Print",
    description: "Materials count when the production order completes.",
    category: "print",
  },
  ASSEMBLY: {
    label: "Assembly",
    description: "Materials count when the production order completes.",
    category: "assembly",
  },
  QUALITY_CONTROL: {
    label: "Quality Control",
    description: "Materials count for nothing automatically.",
    category: "quality",
  },
  SUPPORT_REMOVAL: {
    label: "Support Removal / Cleanup",
    description: "Materials count for nothing automatically.",
    category: "finishing",
  },
  SANDING: {
    label: "Sanding",
    description: "Materials count for nothing automatically.",
    category: "finishing",
  },
  PAINTING: {
    label: "Painting",
    description: "Materials count for nothing automatically.",
    category: "finishing",
  },
  PACK_SHIP: {
    label: "Pack / Ship",
    description: "Materials count when the order ships.",
    category: "shipping",
  },
  GENERAL: {
    label: "Other (consumes at production)",
    description: "Materials count when the production order completes.",
    category: "other",
  },
};

// Shown under/inside the picker for an operation with no type assigned —
// mirrors resolve_consume_stages()'s NULL-type fallback
// (["production", "any"]) in operation_material_mapping.py.
export const UNTYPED_LABEL = "No type — treated as Production";
export const UNTYPED_DESCRIPTION =
  "Materials count when the production order completes (default — no type set).";

const CATEGORY_LABELS = {
  print: "Print",
  assembly: "Assembly",
  quality: "Quality",
  finishing: "Finishing",
  shipping: "Shipping",
  other: "Other",
};

export function categoryLabel(category) {
  if (!category) return "Other";
  return (
    CATEGORY_LABELS[category] ||
    category.charAt(0).toUpperCase() + category.slice(1)
  );
}

/**
 * Group a flat operation-types catalog array into [category, types[]]
 * entries, ordered by each group's lowest sort_order, for <optgroup>
 * display. Falls back to a flat "other" group when categories are absent.
 */
export function groupOperationTypes(operationTypes) {
  const groups = new Map();
  for (const t of operationTypes || []) {
    const key = t.category || "other";
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key).push(t);
  }
  return Array.from(groups.entries()).sort((a, b) => {
    const aOrder = Math.min(...a[1].map((t) => t.sort_order ?? 0));
    const bOrder = Math.min(...b[1].map((t) => t.sort_order ?? 0));
    return aOrder - bOrder;
  });
}

/**
 * Resolve {label, description, category} for an operation_type code:
 * prefer the live fetched catalog, then the frozen system-type fallback,
 * then just the bare code with no description. Returns null for an empty
 * code (caller decides how to render the untyped/warning state).
 */
export function describeOperationType(code, operationTypes) {
  if (!code) return null;
  const fromCatalog = (operationTypes || []).find((t) => t.code === code);
  if (fromCatalog) {
    return {
      label: fromCatalog.label,
      description: fromCatalog.description,
      category: fromCatalog.category,
    };
  }
  const fallback = OPERATION_TYPE_FALLBACK[code];
  if (fallback) return fallback;
  return { label: code, description: null, category: null };
}
