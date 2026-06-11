/**
 * SCHED-3 — DispatchChip unit tests
 *
 * Coverage:
 *   - chip renders order/product/qty/due
 *   - maintenance_warning badge visible when present
 *   - canAutoDispatch() returns false for suggestions with maintenance_warning
 *   - canAutoDispatch() returns true when no maintenance_warning
 *   - Confirm button triggers confirmDispatch
 *   - Pick different button triggers onPickDifferent
 */
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import DispatchChip, { canAutoDispatch, confirmDispatch } from '../DispatchChip';

// ─── Mock fetch ──────────────────────────────────────────────────────────────

const mockFetch = vi.fn();
global.fetch = mockFetch;

// ─── Fixture helpers ──────────────────────────────────────────────────────────

function buildSuggestion(overrides = {}) {
  return {
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
    why: ['Priority 2', 'Due 2026-06-30'],
    maintenance_warning: null,
    ...overrides,
  };
}

// ─── canAutoDispatch ──────────────────────────────────────────────────────────

describe('canAutoDispatch()', () => {
  it('returns true when no maintenance_warning', () => {
    expect(canAutoDispatch(buildSuggestion())).toBe(true);
  });

  it('returns false when maintenance_warning is a non-empty string', () => {
    expect(canAutoDispatch(buildSuggestion({ maintenance_warning: 'Maintenance due in 30 min' }))).toBe(false);
  });

  it('returns false for null suggestion', () => {
    expect(canAutoDispatch(null)).toBe(false);
  });
});

// ─── Render ───────────────────────────────────────────────────────────────────

describe('DispatchChip render', () => {
  it('renders production order code and product name', () => {
    render(
      <DispatchChip
        suggestion={buildSuggestion()}
        printerId={1}
        onConfirmed={vi.fn()}
        onPickDifferent={vi.fn()}
      />
    );
    expect(screen.getByText('WO-2026-000001')).toBeInTheDocument();
    expect(screen.getByText('Red Widget')).toBeInTheDocument();
  });

  it('shows quantity and due date', () => {
    render(
      <DispatchChip
        suggestion={buildSuggestion()}
        printerId={1}
        onConfirmed={vi.fn()}
        onPickDifferent={vi.fn()}
      />
    );
    expect(screen.getByText(/Qty 5/)).toBeInTheDocument();
    expect(screen.getByText(/Due/)).toBeInTheDocument();
  });

  it('renders Confirm and Pick different buttons', () => {
    render(
      <DispatchChip
        suggestion={buildSuggestion()}
        printerId={1}
        onConfirmed={vi.fn()}
        onPickDifferent={vi.fn()}
      />
    );
    expect(screen.getByTestId('confirm-btn')).toBeInTheDocument();
    expect(screen.getByTestId('pick-different-btn')).toBeInTheDocument();
  });

  it('returns null when suggestion is null', () => {
    const { container } = render(
      <DispatchChip
        suggestion={null}
        printerId={1}
        onConfirmed={vi.fn()}
        onPickDifferent={vi.fn()}
      />
    );
    expect(container.firstChild).toBeNull();
  });
});

// ─── Maintenance warning badge ────────────────────────────────────────────────

describe('DispatchChip — maintenance_warning badge', () => {
  it('shows maintenance-warning-badge when maintenance_warning is set', () => {
    render(
      <DispatchChip
        suggestion={buildSuggestion({ maintenance_warning: 'Maintenance due in 30 min' })}
        printerId={1}
        onConfirmed={vi.fn()}
        onPickDifferent={vi.fn()}
      />
    );
    expect(screen.getByTestId('maintenance-warning-badge')).toBeInTheDocument();
    expect(screen.getByText(/Maintenance due in 30 min/)).toBeInTheDocument();
  });

  it('does NOT show badge when maintenance_warning is null', () => {
    render(
      <DispatchChip
        suggestion={buildSuggestion({ maintenance_warning: null })}
        printerId={1}
        onConfirmed={vi.fn()}
        onPickDifferent={vi.fn()}
      />
    );
    expect(screen.queryByTestId('maintenance-warning-badge')).toBeNull();
  });
});

// ─── Confirm action ───────────────────────────────────────────────────────────

describe('DispatchChip — confirm button', () => {
  beforeEach(() => {
    mockFetch.mockResolvedValue({
      ok: true,
      json: async () => ({ operation_id: 1, printer_id: 1, operation_status: 'queued' }),
    });
  });

  afterEach(() => {
    mockFetch.mockReset();
  });

  it('calls onConfirmed after successful dispatch', async () => {
    const onConfirmed = vi.fn();
    render(
      <DispatchChip
        suggestion={buildSuggestion()}
        printerId={42}
        onConfirmed={onConfirmed}
        onPickDifferent={vi.fn()}
      />
    );

    fireEvent.click(screen.getByTestId('confirm-btn'));

    await waitFor(() => expect(onConfirmed).toHaveBeenCalledTimes(1));
    expect(mockFetch).toHaveBeenCalledWith(
      expect.stringContaining('/dispatch/assign'),
      expect.objectContaining({ method: 'POST' })
    );
  });

  it('shows error message on dispatch failure', async () => {
    mockFetch.mockResolvedValue({
      ok: false,
      json: async () => ({ detail: 'Printer unavailable' }),
    });

    render(
      <DispatchChip
        suggestion={buildSuggestion()}
        printerId={42}
        onConfirmed={vi.fn()}
        onPickDifferent={vi.fn()}
      />
    );

    fireEvent.click(screen.getByTestId('confirm-btn'));

    await waitFor(() => expect(screen.getByText('Printer unavailable')).toBeInTheDocument());
  });
});

// ─── Pick different ───────────────────────────────────────────────────────────

describe('DispatchChip — pick different button', () => {
  it('calls onPickDifferent with operation and productionOrder objects', () => {
    const onPickDifferent = vi.fn();
    render(
      <DispatchChip
        suggestion={buildSuggestion()}
        printerId={1}
        onConfirmed={vi.fn()}
        onPickDifferent={onPickDifferent}
      />
    );

    fireEvent.click(screen.getByTestId('pick-different-btn'));

    expect(onPickDifferent).toHaveBeenCalledTimes(1);
    const [operation, productionOrder] = onPickDifferent.mock.calls[0];
    expect(operation.id).toBe(1);
    expect(productionOrder.id).toBe(10);
    expect(productionOrder.code).toBe('WO-2026-000001');
  });
});
