/**
 * Timezone tests for OperationSchedulerModal datetime-local seeding (SCHED-TZ).
 *
 * Regression for the UTC/local double-shift: the modal used to seed its
 * datetime-local inputs with `Date.toISOString().slice(0, 16)` (UTC wall
 * time) — at 2:42 PM Eastern the default start showed 6:45 PM (+4h) and the
 * auto-calculated end showed start + duration + ANOTHER offset hop. Edit
 * mode additionally mis-parsed naive-UTC server strings as local.
 *
 * The bug is invisible when tests run in UTC, so we pin a non-UTC timezone
 * via process.env.TZ at the very top — before any import constructs a Date.
 * CI (Linux) honors TZ; platforms that ignore it (some Windows local runs)
 * skip the TZ-dependent assertions instead of silently passing.
 *
 * Mock setup mirrors OperationSchedulerModal.test.jsx.
 */
globalThis.process.env.TZ = "America/New_York";

import { render, screen, act } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import OperationSchedulerModal from '../OperationSchedulerModal'
import { toLocalInputValue } from '../../../utils/formatting'

// Verify the TZ pin took effect (Jan 1 in America/New_York = EST = UTC-5).
const TZ_PINNED = new Date(2026, 0, 1).getTimezoneOffset() === 300
if (!TZ_PINNED) {
  console.warn(
    '[OperationSchedulerModal.tz.test] process.env.TZ pin ignored by this ' +
      'platform — skipping TZ-dependent assertions (they run in CI on Linux).',
  )
}

let _mockResources = []

vi.mock('../../../hooks/useResources', () => ({
  useResources: () => ({ resources: _mockResources, loading: false, error: null }),
  useResourceConflicts: () => ({
    conflicts: [],
    checking: false,
    error: null,
    hasConflicts: false,
  }),
}))

beforeEach(() => {
  _mockResources = [
    { id: 7, code: 'PRINTER-01', name: 'Bambu X1C', is_printer: true },
  ]
  // Silence fetch calls the component fires (compat check, next-available, etc.)
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: false, json: async () => ({}) }))
})

afterEach(() => {
  vi.restoreAllMocks()
})

// Naive-UTC strings exactly as the backend serializes them (no 'Z' suffix).
const NAIVE_START = '2026-06-12T18:45:00'
const NAIVE_END = '2026-06-12T20:25:00' // start + 100 min (10 setup + 90 run)

const scheduledOp = {
  id: 50,
  sequence: 10,
  operation_code: 'PRINT',
  operation_name: 'FDM Print',
  work_center_id: 1,
  resource_id: null,
  printer_id: 7,
  planned_setup_minutes: '10.00',
  planned_run_minutes: '90.00',
  status: 'queued',
  scheduled_start: NAIVE_START,
  scheduled_end: NAIVE_END,
}

const productionOrder = { id: 1, code: 'PO-2026-000001' }

function getDateTimeInputs(container) {
  return Array.from(container.querySelectorAll('input[type="datetime-local"]'))
}

async function renderEditModal() {
  let utils
  await act(async () => {
    utils = render(
      <OperationSchedulerModal
        isOpen={true}
        onClose={vi.fn()}
        operation={scheduledOp}
        productionOrder={productionOrder}
        onScheduled={vi.fn()}
      />,
    )
  })
  return utils
}

describe('OperationSchedulerModal — edit-mode prefill is local wall time (SCHED-TZ)', () => {
  it('seeds the start input with toLocalInputValue of the naive-UTC scheduled_start', async () => {
    const { container } = await renderEditModal()

    // Sanity: it's edit mode
    expect(screen.getAllByText('Edit Schedule').length).toBeGreaterThanOrEqual(1)

    const [startInput] = getDateTimeInputs(container)
    expect(startInput).toBeDefined()
    expect(startInput.value).toBe(toLocalInputValue(NAIVE_START))
  })

  it('auto-calculated end is start + duration with no extra offset hop', async () => {
    const { container } = await renderEditModal()

    const [, endInput] = getDateTimeInputs(container)
    expect(endInput).toBeDefined()
    // Auto-calc: end = local-parse(startInput.value) + 100 min, serialized
    // back as local wall time. Equals toLocalInputValue(NAIVE_END) because
    // the fixture's scheduled_end is exactly start + 100 min.
    expect(endInput.value).toBe(toLocalInputValue(NAIVE_END))
  })

  it.skipIf(!TZ_PINNED)(
    'start input shows Eastern wall time, NOT the raw UTC slice (18:45 → 14:45 EDT)',
    async () => {
      const { container } = await renderEditModal()

      const [startInput] = getDateTimeInputs(container)
      expect(startInput.value).toBe('2026-06-12T14:45')
      // Explicit regression guard against the old broken seeding
      expect(startInput.value).not.toBe('2026-06-12T18:45')
    },
  )

  it.skipIf(!TZ_PINNED)(
    'end input shows start + 1h40m, not start + 1h40m + timezone offset',
    async () => {
      const { container } = await renderEditModal()

      const [, endInput] = getDateTimeInputs(container)
      expect(endInput.value).toBe('2026-06-12T16:25')
    },
  )
})
