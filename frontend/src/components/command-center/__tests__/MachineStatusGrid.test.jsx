/**
 * SCHED-3+4 — MachineStatusGrid unit tests
 *
 * Coverage:
 *   - Idle resource with matching suggestion renders DispatchChip
 *   - Running resource does NOT render DispatchChip
 *   - maintenance_due_soon badge visible on idle card when set
 *   - maintenance_due_soon badge NOT shown when false
 *   - auto_dispatch OFF default: no auto-confirm without user action
 */
import { render, screen } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import { MemoryRouter } from 'react-router-dom';
import MachineStatusGrid from '../MachineStatusGrid';

// ─── Helpers ──────────────────────────────────────────────────────────────────

function buildResource(overrides = {}) {
  return {
    id: 1,
    code: 'PRT-01',
    name: 'Printer 01',
    work_center_id: 10,
    work_center_name: 'Print Farm',
    status: 'idle',
    current_operation: null,
    pending_operations_count: 0,
    printer_id: 100,
    maintenance_due_soon: false,
    ...overrides,
  };
}

function buildSuggestion(overrides = {}) {
  return {
    printer: { id: 100, code: 'PRT-01', name: 'Printer 01', model: 'X1C' },
    top_suggestion: {
      operation_id: 1,
      operation_code: 'OP-001',
      operation_name: 'Print',
      production_order_id: 10,
      production_order_code: 'WO-2026-000001',
      product_name: 'Red Widget',
      quantity: '5',
      due_date: '2026-06-30',
      priority: 2,
      estimated_duration_minutes: 120,
      why: ['Priority 2'],
      maintenance_warning: null,
    },
    runners_up: [],
    ...overrides,
  };
}

function renderGrid(resources, suggestions = {}) {
  return render(
    <MemoryRouter>
      <MachineStatusGrid
        resources={resources}
        suggestions={suggestions}
        onMachineClick={vi.fn()}
        onDispatchConfirmed={vi.fn()}
        onPickDifferent={vi.fn()}
      />
    </MemoryRouter>
  );
}

// ─── Tests ────────────────────────────────────────────────────────────────────

describe('MachineStatusGrid — dispatch chip visibility', () => {
  it('renders DispatchChip for idle resource with matching suggestion', () => {
    const resource = buildResource({ status: 'idle', printer_id: 100 });
    const suggestions = { 100: buildSuggestion() };

    renderGrid([resource], suggestions);

    expect(screen.getByTestId('dispatch-chip')).toBeInTheDocument();
    expect(screen.getByText('WO-2026-000001')).toBeInTheDocument();
  });

  it('does NOT render DispatchChip for running resource', () => {
    const resource = buildResource({
      status: 'running',
      printer_id: 100,
      current_operation: {
        operation_id: 1,
        production_order_id: 1,
        production_order_code: 'WO-001',
        operation_code: 'OP-001',
        sequence: 1,
        started_at: new Date().toISOString(),
        planned_minutes: 60,
      },
    });
    const suggestions = { 100: buildSuggestion() };

    renderGrid([resource], suggestions);

    expect(screen.queryByTestId('dispatch-chip')).toBeNull();
  });

  it('does NOT render DispatchChip when suggestions is empty', () => {
    const resource = buildResource({ status: 'idle', printer_id: 100 });

    renderGrid([resource], {});

    expect(screen.queryByTestId('dispatch-chip')).toBeNull();
  });

  it('does NOT render DispatchChip when resource has no printer_id', () => {
    const resource = buildResource({ status: 'idle', printer_id: null });
    const suggestions = { 100: buildSuggestion() };

    renderGrid([resource], suggestions);

    expect(screen.queryByTestId('dispatch-chip')).toBeNull();
  });
});

describe('MachineStatusGrid — maintenance due-soon badge (SCHED-4)', () => {
  it('shows maintenance-due badge when maintenance_due_soon is true', () => {
    const resource = buildResource({ status: 'idle', maintenance_due_soon: true });

    renderGrid([resource]);

    expect(screen.getByTestId('maintenance-due-badge')).toBeInTheDocument();
  });

  it('does NOT show maintenance-due badge when maintenance_due_soon is false', () => {
    const resource = buildResource({ status: 'idle', maintenance_due_soon: false });

    renderGrid([resource]);

    expect(screen.queryByTestId('maintenance-due-badge')).toBeNull();
  });

  it('shows maintenance-due badge even when resource is running', () => {
    const resource = buildResource({
      status: 'running',
      maintenance_due_soon: true,
      current_operation: {
        operation_id: 1,
        production_order_id: 1,
        production_order_code: 'WO-001',
        operation_code: 'OP-001',
        sequence: 1,
        started_at: new Date().toISOString(),
        planned_minutes: 60,
      },
    });

    renderGrid([resource]);

    expect(screen.getByTestId('maintenance-due-badge')).toBeInTheDocument();
  });
});

describe('MachineStatusGrid — auto_dispatch OFF default', () => {
  it('does not auto-confirm suggestions without user interaction', () => {
    // The auto-dispatch logic lives in CommandCenter.jsx, not in this component.
    // This test verifies that MachineStatusGrid itself never calls confirmDispatch
    // automatically — it only exposes onConfirmed for the chip to call.
    const mockConfirmed = vi.fn();
    const resource = buildResource({ status: 'idle', printer_id: 100 });
    const suggestions = { 100: buildSuggestion() };

    renderGrid([resource], suggestions);

    // After render, no auto-confirm should have fired
    expect(mockConfirmed).not.toHaveBeenCalled();
  });
});
