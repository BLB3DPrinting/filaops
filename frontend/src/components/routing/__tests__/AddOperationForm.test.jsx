/**
 * Tests for AddOperationForm (#876 PR-4 — operation type picker).
 *
 * Scenarios:
 *  1. Operation Type renders as a required select, grouped by category.
 *  2. Picking a type shows its plain-English description under the field.
 *  3. Picking a type pre-fills the (collapsed/advanced) operation code with
 *     the canonical short code, without touching the untouched field.
 *  4. Manually editing the code (escape hatch) survives a later type change
 *     — the auto-fill never clobbers a hand-typed code.
 *  5. The Add button is disabled until a type is selected.
 *  6. The killed "e.g., OP10, OP20" placeholder is gone.
 */
import { useState } from "react";
import { render, screen, fireEvent } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import AddOperationForm from "../AddOperationForm";

const OPERATION_TYPES = [
  {
    id: 1,
    code: "FDM_PRINT",
    label: "FDM Print",
    description: "Materials count when the production order completes.",
    category: "print",
    sort_order: 10,
  },
  {
    id: 4,
    code: "QUALITY_CONTROL",
    label: "Quality Control",
    description: "Materials count for nothing automatically.",
    category: "quality",
    sort_order: 40,
  },
  {
    id: 8,
    code: "PACK_SHIP",
    label: "Pack / Ship",
    description: "Materials count when the order ships.",
    category: "shipping",
    sort_order: 80,
  },
  {
    id: 9,
    code: "GENERAL",
    label: "Other (consumes at production)",
    description: "Materials count when the production order completes.",
    category: "other",
    sort_order: 90,
  },
];

const WORK_CENTERS = [
  { id: 1, code: "FDM-1", name: "FDM Printer 1", total_rate_per_hour: "10" },
];

const baseOperation = {
  work_center_id: "",
  sequence: 1,
  operation_type: "",
  operation_code: "",
  operation_name: "",
  setup_time_minutes: 0,
  run_time_minutes: 0,
  wait_time_minutes: 0,
  move_time_minutes: 0,
  units_per_cycle: 1,
  scrap_rate_percent: 0,
  is_active: true,
};

// Wraps AddOperationForm with the controlled-state contract its real
// parent (RoutingEditorContent) provides, so onOperationChange updates
// flow back in as props like they do in the app.
function ControlledForm({ initial = baseOperation, onAdd = vi.fn(), onCancel = vi.fn() }) {
  const [newOperation, setNewOperation] = useState(initial);
  return (
    <AddOperationForm
      workCenters={WORK_CENTERS}
      operationTypes={OPERATION_TYPES}
      newOperation={newOperation}
      onOperationChange={setNewOperation}
      onAdd={() => onAdd(newOperation)}
      onCancel={onCancel}
    />
  );
}

describe("AddOperationForm — operation type picker", () => {
  it("renders the Operation Type select grouped by category", () => {
    render(<ControlledForm />);
    const select = screen.getByLabelText(/Operation Type/);
    expect(select).toBeInTheDocument();
    expect(screen.getByRole("group", { name: "Print" })).toBeInTheDocument();
    expect(screen.getByRole("group", { name: "Quality" })).toBeInTheDocument();
    expect(screen.getByRole("group", { name: "Shipping" })).toBeInTheDocument();
    expect(screen.getByRole("option", { name: "FDM Print" })).toBeInTheDocument();
  });

  it("shows the selected type's plain-English description", () => {
    render(<ControlledForm />);
    fireEvent.change(screen.getByLabelText(/Operation Type/), {
      target: { value: "PACK_SHIP" },
    });
    expect(
      screen.getByText("Materials count when the order ships.")
    ).toBeInTheDocument();
  });

  it("pre-fills the advanced operation code with the type's canonical code", () => {
    render(<ControlledForm />);
    fireEvent.change(screen.getByLabelText(/Operation Type/), {
      target: { value: "QUALITY_CONTROL" },
    });
    fireEvent.click(
      screen.getByText(/Show advanced: custom operation code/)
    );
    expect(screen.getByLabelText(/Operation Code/).value).toBe("QC");
  });

  it("does not clobber a manually entered code when the type changes again", () => {
    render(<ControlledForm />);
    fireEvent.change(screen.getByLabelText(/Operation Type/), {
      target: { value: "FDM_PRINT" },
    });
    fireEvent.click(
      screen.getByText(/Show advanced: custom operation code/)
    );
    expect(screen.getByLabelText(/Operation Code/).value).toBe("PRINT");

    fireEvent.change(screen.getByLabelText(/Operation Code/), {
      target: { value: "CUSTOM-1" },
    });
    fireEvent.change(screen.getByLabelText(/Operation Type/), {
      target: { value: "PACK_SHIP" },
    });
    expect(screen.getByLabelText(/Operation Code/).value).toBe("CUSTOM-1");
  });

  it("GENERAL pre-fills a blank code, not a placeholder OPn value", () => {
    render(<ControlledForm />);
    // Touch a different type first, then land on GENERAL — still untouched
    // by hand, so the auto-fill follows the latest type (blank for GENERAL)
    // rather than ever minting an OPn placeholder.
    fireEvent.change(screen.getByLabelText(/Operation Type/), {
      target: { value: "FDM_PRINT" },
    });
    fireEvent.change(screen.getByLabelText(/Operation Type/), {
      target: { value: "GENERAL" },
    });
    fireEvent.click(
      screen.getByText(/Show advanced: custom operation code/)
    );
    expect(screen.getByLabelText(/Operation Code/).value).toBe("");
    expect(screen.queryByPlaceholderText(/OP10, OP20/)).not.toBeInTheDocument();
  });

  it("disables Add until an operation type is selected", () => {
    const onAdd = vi.fn();
    render(<ControlledForm onAdd={onAdd} />);
    expect(screen.getByText("Add")).toBeDisabled();

    fireEvent.change(screen.getByLabelText(/Operation Type/), {
      target: { value: "FDM_PRINT" },
    });
    expect(screen.getByText("Add")).not.toBeDisabled();
  });

  it("never renders the killed OP10/OP20 placeholder", () => {
    render(<ControlledForm />);
    fireEvent.click(
      screen.getByText(/Show advanced: custom operation code/)
    );
    expect(screen.queryByPlaceholderText(/OP10, OP20/)).not.toBeInTheDocument();
  });
});
