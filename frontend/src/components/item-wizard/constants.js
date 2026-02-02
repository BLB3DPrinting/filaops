/**
 * ItemWizard constants — shared across item-wizard components.
 *
 * Extracted from ItemWizard.jsx (ARCHITECT-002)
 */

// Item type options
export const ITEM_TYPES = [
  { value: "finished_good", label: "Finished Good", color: "blue", defaultProcurement: "make" },
  { value: "component", label: "Component", color: "purple", defaultProcurement: "buy" },
  { value: "supply", label: "Supply", color: "orange", defaultProcurement: "buy" },
  { value: "service", label: "Service", color: "green", defaultProcurement: "buy" },
  { value: "material", label: "Material (Filament)", color: "yellow", defaultProcurement: "buy" },
];

// Procurement type options (Make vs Buy)
export const PROCUREMENT_TYPES = [
  { value: "make", label: "Make (Manufactured)", color: "green", needsBom: true, description: "Produced in-house with BOM & routing" },
  { value: "buy", label: "Buy (Purchased)", color: "blue", needsBom: false, description: "Purchased from suppliers" },
  { value: "make_or_buy", label: "Make or Buy", color: "yellow", needsBom: true, description: "Flexible sourcing" },
];
