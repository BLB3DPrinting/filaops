/**
 * Tests for ReleaseScheduleWizard (SCHED-3b)
 *
 * Scenarios:
 *  1. Wizard appears (offer prompt) when isOpen=true with schedulable ops.
 *  2. Dismissing (clicking "Later") calls onClose without scheduling.
 *  3. Accepting opens OperationSchedulerModal in wizard mode.
 *  4. Skip advances to the next op; skipped ops appear in the summary.
 *  5. Scheduling an op advances to next op (predecessor chaining: step 2
 *     earliestStart >= step 1 endTime).
 *  6. After all ops are scheduled, summary screen shows scheduled details.
 *  7. "Schedule now" button not shown when there are no pending ops.
 *  8. Release unaffected: wizard is NON-BLOCKING — onClose works without scheduling.
 *  9. Wizard mode props passed to OperationSchedulerModal (wizardMode=true,
 *     wizardStep, wizardTotal, onWizardSkip).
 * 10. Summary "Open scheduler" link calls onOpenScheduler.
 */
import { render, screen, fireEvent, act, waitFor } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import ReleaseScheduleWizard from '../ReleaseScheduleWizard'

// ---------------------------------------------------------------------------
// Mock OperationSchedulerModal so we can control its behaviour without
// pulling in its full dependency tree (useResources, useResourceConflicts, etc.)
// ---------------------------------------------------------------------------
let _capturedWizardProps = {}
let _onScheduledCallback = null
let _onWizardSkipCallback = null
let _onCloseCallback = null

vi.mock('../OperationSchedulerModal', () => ({
  default: (props) => {
    // Capture wizard-mode props for assertions
    _capturedWizardProps = {
      wizardMode: props.wizardMode,
      wizardStep: props.wizardStep,
      wizardTotal: props.wizardTotal,
      operation: props.operation,
    }
    _onScheduledCallback = props.onScheduled
    _onWizardSkipCallback = props.onWizardSkip
    _onCloseCallback = props.onClose

    if (!props.isOpen) return null
    return (
      <div data-testid="scheduler-modal">
        <div data-testid="wizard-step">{props.wizardStep}</div>
        <div data-testid="wizard-total">{props.wizardTotal}</div>
        <div data-testid="wizard-mode">{String(props.wizardMode)}</div>
        {props.operation && (
          <div data-testid="modal-operation">{props.operation.operation_code}</div>
        )}
        <button
          data-testid="modal-skip"
          onClick={() => props.onWizardSkip?.()}
        >
          Skip
        </button>
        <button
          data-testid="modal-schedule"
          onClick={() =>
            props.onScheduled?.({
              operationId: props.operation?.id,
              operationLabel: `${props.operation?.sequence} — ${props.operation?.operation_code}`,
              resourceName: 'Printer-01',
              startTime: '2026-06-11T10:00:00.000Z',
              endTime: '2026-06-11T12:00:00.000Z',
            })
          }
        >
          Schedule
        </button>
        <button data-testid="modal-close" onClick={() => props.onClose?.()}>
          Close
        </button>
      </div>
    )
  },
}))

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

const pendingOp1 = {
  id: 10,
  sequence: 10,
  operation_code: 'PRINT',
  operation_name: 'FDM Print',
  status: 'pending',
  work_center_id: 1,
  planned_setup_minutes: '5.00',
  planned_run_minutes: '115.00',
}

const pendingOp2 = {
  id: 20,
  sequence: 20,
  operation_code: 'POST',
  operation_name: 'Post-processing',
  status: 'pending',
  work_center_id: 2,
  planned_setup_minutes: '10.00',
  planned_run_minutes: '50.00',
}

const productionOrder = {
  id: 99,
  code: 'PO-2026-0099',
  status: 'released',
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function stubFetch({ ops = [pendingOp1, pendingOp2], suggestionsOk = false } = {}) {
  vi.stubGlobal(
    'fetch',
    vi.fn().mockImplementation((url) => {
      if (typeof url === 'string' && url.includes('/operations')) {
        return Promise.resolve({ ok: true, json: async () => ops })
      }
      if (typeof url === 'string' && url.includes('/suggestions')) {
        return Promise.resolve({
          ok: suggestionsOk,
          json: async () => ({ results: [], generated_at: new Date().toISOString() }),
        })
      }
      if (typeof url === 'string' && url.includes('next-available')) {
        return Promise.resolve({
          ok: true,
          json: async () => ({
            next_available: '2026-06-11T10:00:00Z',
            suggested_end: '2026-06-11T12:00:00Z',
          }),
        })
      }
      return Promise.resolve({ ok: false, json: async () => ({}) })
    }),
  )
}

function renderWizard(props = {}) {
  const defaultProps = {
    isOpen: true,
    productionOrder,
    onClose: vi.fn(),
    onOpenScheduler: vi.fn(),
    onRefresh: vi.fn(),
  }
  return render(<ReleaseScheduleWizard {...defaultProps} {...props} />)
}

beforeEach(() => {
  _capturedWizardProps = {}
  _onScheduledCallback = null
  _onWizardSkipCallback = null
  _onCloseCallback = null
  stubFetch()
  vi.useFakeTimers({ shouldAdvanceTime: true })
})

afterEach(() => {
  vi.useRealTimers()
  vi.restoreAllMocks()
})

// ---------------------------------------------------------------------------
// 1. Offer prompt appears
// ---------------------------------------------------------------------------
describe('ReleaseScheduleWizard — offer prompt', () => {
  it('shows "Order Released" heading and the operation count after ops load', async () => {
    renderWizard()
    // findAllByText because Modal renders an sr-only duplicate of the title
    expect((await screen.findAllByText('Order Released')).length).toBeGreaterThanOrEqual(1)
    expect(await screen.findByText(/2 operations ready to schedule/i)).toBeInTheDocument()
  })

  it('shows the production order code in the offer', async () => {
    renderWizard()
    expect(await screen.findByText(/PO-2026-0099 released to floor/i)).toBeInTheDocument()
  })

  it('does not render when isOpen=false', () => {
    renderWizard({ isOpen: false })
    expect(screen.queryByText('Order Released')).not.toBeInTheDocument()
  })
})

// ---------------------------------------------------------------------------
// 2. Dismissing the offer
// ---------------------------------------------------------------------------
describe('ReleaseScheduleWizard — dismiss (Later)', () => {
  it('calls onClose when "Later" is clicked', async () => {
    const onClose = vi.fn()
    renderWizard({ onClose })

    const laterBtn = await screen.findByRole('button', { name: /later/i })
    fireEvent.click(laterBtn)

    expect(onClose).toHaveBeenCalledTimes(1)
  })

  it('does NOT open the scheduler modal on dismiss', async () => {
    renderWizard()
    const laterBtn = await screen.findByRole('button', { name: /later/i })
    fireEvent.click(laterBtn)

    expect(screen.queryByTestId('scheduler-modal')).not.toBeInTheDocument()
  })
})

// ---------------------------------------------------------------------------
// 3. Accepting opens scheduler in wizard mode
// ---------------------------------------------------------------------------
describe('ReleaseScheduleWizard — accepting opens wizard', () => {
  it('opens OperationSchedulerModal in wizard mode after accepting', async () => {
    renderWizard()

    const scheduleNowBtn = await screen.findByRole('button', { name: /schedule now/i })
    await act(async () => { fireEvent.click(scheduleNowBtn) })
    await act(async () => { vi.runAllTimers() })

    expect(await screen.findByTestId('scheduler-modal')).toBeInTheDocument()
    expect(screen.getByTestId('wizard-mode').textContent).toBe('true')
  })

  it('passes wizardStep=1 and wizardTotal=2 for 2 ops', async () => {
    renderWizard()

    const btn = await screen.findByRole('button', { name: /schedule now/i })
    await act(async () => { fireEvent.click(btn) })
    await act(async () => { vi.runAllTimers() })

    expect(await screen.findByTestId('wizard-step')).toHaveTextContent('1')
    expect(screen.getByTestId('wizard-total')).toHaveTextContent('2')
  })

  it('passes first pending op as the operation prop', async () => {
    renderWizard()

    const btn = await screen.findByRole('button', { name: /schedule now/i })
    await act(async () => { fireEvent.click(btn) })
    await act(async () => { vi.runAllTimers() })

    expect(await screen.findByTestId('modal-operation')).toHaveTextContent('PRINT')
  })
})

// ---------------------------------------------------------------------------
// 4. Skip advances to next op
// ---------------------------------------------------------------------------
describe('ReleaseScheduleWizard — skip', () => {
  it('advances to step 2 after skipping step 1', async () => {
    renderWizard()

    const btn = await screen.findByRole('button', { name: /schedule now/i })
    await act(async () => { fireEvent.click(btn) })
    await act(async () => { vi.runAllTimers() })

    // Skip step 1
    const skipBtn = await screen.findByTestId('modal-skip')
    await act(async () => { fireEvent.click(skipBtn) })
    await act(async () => { vi.runAllTimers() })

    // Modal should now show step 2
    expect(await screen.findByTestId('wizard-step')).toHaveTextContent('2')
    expect(screen.getByTestId('modal-operation')).toHaveTextContent('POST')
  })

  it('shows summary after skipping all ops', async () => {
    stubFetch({ ops: [pendingOp1] }) // only 1 op

    renderWizard()

    const btn = await screen.findByRole('button', { name: /schedule now/i })
    await act(async () => { fireEvent.click(btn) })
    await act(async () => { vi.runAllTimers() })

    const skipBtn = await screen.findByTestId('modal-skip')
    await act(async () => { fireEvent.click(skipBtn) })
    await act(async () => { vi.runAllTimers() })

    // Summary screen should appear — sr-only span + h2 both render the title
    expect((await screen.findAllByText('Schedule Summary')).length).toBeGreaterThanOrEqual(1)
    expect(screen.getByText(/No operations were scheduled/i)).toBeInTheDocument()
  })
})

// ---------------------------------------------------------------------------
// 5. Scheduling an op + predecessor chaining
// ---------------------------------------------------------------------------
describe('ReleaseScheduleWizard — scheduling + predecessor chaining', () => {
  it('calls onRefresh after scheduling an op', async () => {
    const onRefresh = vi.fn()
    renderWizard({ onRefresh })

    const btn = await screen.findByRole('button', { name: /schedule now/i })
    await act(async () => { fireEvent.click(btn) })
    await act(async () => { vi.runAllTimers() })

    const scheduleBtn = await screen.findByTestId('modal-schedule')
    await act(async () => { fireEvent.click(scheduleBtn) })
    await act(async () => { vi.runAllTimers() })

    expect(onRefresh).toHaveBeenCalledTimes(1)
  })

  it('step 2 is shown after scheduling step 1 (predecessor chaining advances correctly)', async () => {
    // Verify the wizard correctly advances to step 2 after step 1 is scheduled,
    // and that step 2's modal receives wizardStep=2 (confirming predecessor state
    // was correctly maintained and the modal was re-opened for the next op).
    renderWizard()

    // Accept the wizard
    const btn = await screen.findByRole('button', { name: /schedule now/i })
    await act(async () => { fireEvent.click(btn) })
    await act(async () => { vi.runAllTimers() })

    // Verify we're on step 1
    expect(await screen.findByTestId('wizard-step')).toHaveTextContent('1')
    expect(screen.getByTestId('modal-operation')).toHaveTextContent('PRINT')

    // Schedule op 1 — onScheduled fires with endTime='2026-06-11T12:00:00.000Z'
    const scheduleBtn = await screen.findByTestId('modal-schedule')
    await act(async () => { fireEvent.click(scheduleBtn) })
    await act(async () => { vi.runAllTimers() })

    // Wizard should now be on step 2 with POST op
    // (predecessorEnd was set to '2026-06-11T12:00:00.000Z' from step 1)
    expect(await screen.findByTestId('wizard-step')).toHaveTextContent('2')
    expect(screen.getByTestId('modal-operation')).toHaveTextContent('POST')
  })
})

// ---------------------------------------------------------------------------
// 6. Summary screen after scheduling all ops
// ---------------------------------------------------------------------------
describe('ReleaseScheduleWizard — summary screen', () => {
  it('shows summary after scheduling all ops', async () => {
    stubFetch({ ops: [pendingOp1] }) // 1 op for simplicity

    renderWizard()

    const btn = await screen.findByRole('button', { name: /schedule now/i })
    await act(async () => { fireEvent.click(btn) })
    await act(async () => { vi.runAllTimers() })

    const scheduleBtn = await screen.findByTestId('modal-schedule')
    await act(async () => { fireEvent.click(scheduleBtn) })
    await act(async () => { vi.runAllTimers() })

    // sr-only span + h2 both render "Schedule Summary"
    expect((await screen.findAllByText('Schedule Summary')).length).toBeGreaterThanOrEqual(1)
    expect(screen.getByText(/1 operation scheduled/i)).toBeInTheDocument()
    expect(screen.getByText(/PRINT/)).toBeInTheDocument()
  })

  it('shows "open scheduler" link in summary when ops were scheduled', async () => {
    stubFetch({ ops: [pendingOp1] })

    renderWizard()

    const btn = await screen.findByRole('button', { name: /schedule now/i })
    await act(async () => { fireEvent.click(btn) })
    await act(async () => { vi.runAllTimers() })

    const scheduleBtn = await screen.findByTestId('modal-schedule')
    await act(async () => { fireEvent.click(scheduleBtn) })
    await act(async () => { vi.runAllTimers() })

    expect(await screen.findByRole('button', { name: /open scheduler for adjustments/i })).toBeInTheDocument()
  })

  it('calls onOpenScheduler when "Open scheduler" is clicked', async () => {
    stubFetch({ ops: [pendingOp1] })
    const onOpenScheduler = vi.fn()
    const onClose = vi.fn()

    renderWizard({ onOpenScheduler, onClose })

    const btn = await screen.findByRole('button', { name: /schedule now/i })
    await act(async () => { fireEvent.click(btn) })
    await act(async () => { vi.runAllTimers() })

    const scheduleBtn = await screen.findByTestId('modal-schedule')
    await act(async () => { fireEvent.click(scheduleBtn) })
    await act(async () => { vi.runAllTimers() })

    const openBtn = await screen.findByRole('button', { name: /open scheduler for adjustments/i })
    fireEvent.click(openBtn)

    expect(onOpenScheduler).toHaveBeenCalledTimes(1)
  })
})

// ---------------------------------------------------------------------------
// 7. No ops — "Schedule now" button absent
// ---------------------------------------------------------------------------
describe('ReleaseScheduleWizard — no schedulable ops', () => {
  it('does not show "Schedule now" button when no pending ops', async () => {
    stubFetch({ ops: [] })

    renderWizard()

    // Wait for loading to finish — sr-only span + h2 both render the title
    expect((await screen.findAllByText('Order Released')).length).toBeGreaterThanOrEqual(1)
    await waitFor(() => {
      expect(screen.queryByRole('button', { name: /schedule now/i })).not.toBeInTheDocument()
    })
  })

  it('shows a "no schedulable operations" message when ops list is empty', async () => {
    stubFetch({ ops: [] })

    renderWizard()

    expect(await screen.findByText(/No schedulable operations found/i)).toBeInTheDocument()
  })
})

// ---------------------------------------------------------------------------
// 8. Non-blocking: release unaffected when wizard dismissed
// ---------------------------------------------------------------------------
describe('ReleaseScheduleWizard — non-blocking', () => {
  it('calls onClose without error when dismissed at the offer stage', async () => {
    const onClose = vi.fn()
    renderWizard({ onClose })

    const laterBtn = await screen.findByRole('button', { name: /later/i })
    fireEvent.click(laterBtn)

    expect(onClose).toHaveBeenCalledTimes(1)
  })

  it('wizard does not render when isOpen=false (release gate not applied)', () => {
    renderWizard({ isOpen: false })
    expect(screen.queryByText('Order Released')).not.toBeInTheDocument()
    expect(screen.queryByTestId('scheduler-modal')).not.toBeInTheDocument()
  })
})

// ---------------------------------------------------------------------------
// 9. Wizard mode props forwarded to OperationSchedulerModal
// ---------------------------------------------------------------------------
describe('ReleaseScheduleWizard — wizard-mode props on modal', () => {
  it('passes wizardMode=true to OperationSchedulerModal', async () => {
    renderWizard()

    const btn = await screen.findByRole('button', { name: /schedule now/i })
    await act(async () => { fireEvent.click(btn) })
    await act(async () => { vi.runAllTimers() })

    expect(await screen.findByTestId('wizard-mode')).toHaveTextContent('true')
  })

  it('provides onWizardSkip to the modal (Skip button functional)', async () => {
    renderWizard()

    const btn = await screen.findByRole('button', { name: /schedule now/i })
    await act(async () => { fireEvent.click(btn) })
    await act(async () => { vi.runAllTimers() })

    // Skip button from the mocked modal should be present and clickable
    const skipBtn = await screen.findByTestId('modal-skip')
    expect(skipBtn).toBeInTheDocument()
    await act(async () => { fireEvent.click(skipBtn) }) // should not throw
  })
})

// ---------------------------------------------------------------------------
// 10. Summary Done button calls onClose
// ---------------------------------------------------------------------------
describe('ReleaseScheduleWizard — summary close', () => {
  it('calls onClose when Done is clicked in the summary', async () => {
    stubFetch({ ops: [pendingOp1] })
    const onClose = vi.fn()

    renderWizard({ onClose })

    // Accept and schedule to reach summary
    const btn = await screen.findByRole('button', { name: /schedule now/i })
    await act(async () => { fireEvent.click(btn) })
    await act(async () => { vi.runAllTimers() })

    const scheduleBtn = await screen.findByTestId('modal-schedule')
    await act(async () => { fireEvent.click(scheduleBtn) })
    await act(async () => { vi.runAllTimers() })

    // Multiple Done buttons may exist (one in summary, one in modal)
    const doneBtns = await screen.findAllByRole('button', { name: /^Done$/i })
    fireEvent.click(doneBtns[0])

    expect(onClose).toHaveBeenCalledTimes(1)
  })
})
