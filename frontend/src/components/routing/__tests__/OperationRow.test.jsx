/**
 * Tests for OperationRow's operation-type badge/picker (#876 PR-4).
 *
 * Scenarios:
 *  1. An untyped operation renders the "No type — treated as Production"
 *     warning chip and its default-consumption description.
 *  2. A typed operation renders its label as the badge and its catalog
 *     description underneath.
 *  3. Changing the select calls onUpdateOperation(index, "operation_type", value).
 *  4. A type stamped on the op but absent from the fetched (active-only)
 *     catalog still renders instead of silently disappearing.
 */
import { render, screen, fireEvent, within } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import OperationRow from "../OperationRow";

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
    id: 8,
    code: "PACK_SHIP",
    label: "Pack / Ship",
    description: "Materials count when the order ships.",
    category: "shipping",
    sort_order: 80,
  },
];

function makeOp(overrides = {}) {
  return {
    id: 1,
    sequence: 1,
    operation_name: "3D Print",
    operation_code: "PRINT",
    operation_type: null,
    work_center_name: "FDM Printer 1",
    setup_time_minutes: 5,
    run_time_minutes: 60,
    calculated_cost: 10,
    ...overrides,
  };
}

function renderRow(op, extraProps = {}) {
  const onUpdateOperation = vi.fn();
  const utils = render(
    <table>
      <tbody>
        <OperationRow
          op={op}
          index={0}
          materials={[]}
          isExpanded={false}
          loading={false}
          operationTypes={OPERATION_TYPES}
          operations={[op]}
          onToggleExpand={vi.fn()}
          onUpdateOperation={onUpdateOperation}
          onRemoveOperation={vi.fn()}
          onAddMaterial={vi.fn()}
          onEditMaterial={vi.fn()}
          {...extraProps}
        />
      </tbody>
    </table>
  );
  return { ...utils, onUpdateOperation };
}

describe("OperationRow — operation type badge/picker", () => {
  it("shows the untyped warning chip and default description", () => {
    renderRow(makeOp({ operation_type: null }));
    const select = screen.getByRole("combobox");
    expect(select.value).toBe("");
    expect(
      within(select).getByRole("option", { name: "No type — treated as Production" })
    ).toBeInTheDocument();
    expect(
      screen.getByText(/Materials count when the production order completes \(default/)
    ).toBeInTheDocument();
  });

  it("shows the assigned type's label and description for a typed op", () => {
    renderRow(makeOp({ operation_type: "PACK_SHIP" }));
    const select = screen.getByRole("combobox");
    expect(select.value).toBe("PACK_SHIP");
    expect(
      screen.getByText(/Pack \/ Ship.*Materials count when the order ships\./)
    ).toBeInTheDocument();
  });

  it("calls onUpdateOperation with the new type when changed", () => {
    const { onUpdateOperation } = renderRow(makeOp({ operation_type: null }));
    fireEvent.change(screen.getByRole("combobox"), {
      target: { value: "FDM_PRINT" },
    });
    expect(onUpdateOperation).toHaveBeenCalledWith(0, "operation_type", "FDM_PRINT");
  });

  it("keeps an orphaned type (not in the active catalog) visible", () => {
    renderRow(makeOp({ operation_type: "LEGACY_CUSTOM_TYPE" }));
    const select = screen.getByRole("combobox");
    expect(select.value).toBe("LEGACY_CUSTOM_TYPE");
    expect(
      within(select).getByRole("option", { name: "LEGACY_CUSTOM_TYPE" })
    ).toBeInTheDocument();
  });

  it("applies warning styling when untyped and info styling when typed", () => {
    const { rerender } = render(
      <table>
        <tbody>
          <OperationRow
            op={makeOp({ operation_type: null })}
            index={0}
            materials={[]}
            isExpanded={false}
            loading={false}
            operationTypes={OPERATION_TYPES}
            operations={[makeOp({ operation_type: null })]}
            onToggleExpand={vi.fn()}
            onUpdateOperation={vi.fn()}
            onRemoveOperation={vi.fn()}
            onAddMaterial={vi.fn()}
            onEditMaterial={vi.fn()}
          />
        </tbody>
      </table>
    );
    expect(screen.getByRole("combobox").className).toMatch(/yellow/);

    rerender(
      <table>
        <tbody>
          <OperationRow
            op={makeOp({ operation_type: "FDM_PRINT" })}
            index={0}
            materials={[]}
            isExpanded={false}
            loading={false}
            operationTypes={OPERATION_TYPES}
            operations={[makeOp({ operation_type: "FDM_PRINT" })]}
            onToggleExpand={vi.fn()}
            onUpdateOperation={vi.fn()}
            onRemoveOperation={vi.fn()}
            onAddMaterial={vi.fn()}
            onEditMaterial={vi.fn()}
          />
        </tbody>
      </table>
    );
    expect(screen.getByRole("combobox").className).toMatch(/blue/);
  });
});
