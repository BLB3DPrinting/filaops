/**
 * Print batches (PRO, S9): the composer page's gates and the confirm-counts
 * modal. The batch logic is PRO's; these pin what the pages send and show.
 */
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach } from 'vitest'

const { mocks, flags } = vi.hoisted(() => ({
  mocks: { get: vi.fn(), post: vi.fn(), del: vi.fn(), success: vi.fn(), error: vi.fn() },
  flags: { isPro: true },
}))

vi.mock('../../../hooks/useApi', () => {
  const api = { get: mocks.get, post: mocks.post, del: mocks.del }
  return { useApi: () => api }
})

vi.mock('../../../components/Toast', () => {
  const toast = { success: mocks.success, error: mocks.error, warning: vi.fn(), info: vi.fn() }
  return { useToast: () => toast }
})

vi.mock('../../../hooks/useFeatureFlags', () => ({
  useFeatureFlags: () => ({ isPro: flags.isPro, hasFeature: () => false, loading: false }),
}))

import PrintBatchComposer from '../PrintBatchComposer'
import ConfirmBatchCountsModal from '../print-batches/ConfirmBatchCountsModal'
import CompositionPicker from '../print-batches/CompositionPicker'
import { partsOnPlate, printerModelKey } from '../print-batches/printBatchHelpers'

const BATCH = {
  id: 7,
  code: 'PB-000007',
  status: 'running',
  actual_run_minutes: 61,
  members: [
    { id: 1, product_id: 10, name: 'Body', quantity: 1, role: 'demand' },
    { id: 2, product_id: 10, name: 'Body', quantity: 7, role: 'topup' },
    { id: 3, product_id: 11, name: 'Wheel', quantity: 4, role: 'demand' },
  ],
}

beforeEach(() => {
  vi.clearAllMocks()
  flags.isPro = true
  mocks.get.mockImplementation(async (path) => {
    if (path.startsWith('/api/v1/pro/print-batches/candidates')) return { candidates: [] }
    if (path === '/api/v1/pro/print-batches') return { batches: [], support: { available: true } }
    if (path.startsWith('/api/v1/printers')) return { items: [{ model: 'Bambu Lab P1S' }, { model: 'A1' }] }
    if (path.includes('scrap-reasons')) return { details: [{ code: 'failed', name: 'Failed print' }] }
    return {}
  })
})

describe('print batch helpers', () => {
  it('adds a part on the plate for a sale and for stock into one row', () => {
    expect(partsOnPlate(BATCH.members)).toEqual([
      { product_id: 10, name: 'Body', planned: 8 },
      { product_id: 11, name: 'Wheel', planned: 4 },
    ])
  })

  it('names printer models as PRO does', () => {
    expect(printerModelKey('Bambu Lab P1S')).toBe('P1S')
    expect(printerModelKey('Bambu Lab X1 Carbon')).toBe('X1C')
    expect(printerModelKey('A1 mini')).toBe('A1 mini')
  })
})

describe('PrintBatchComposer', () => {
  it('shows the PRO upsell without PRO and calls nothing', () => {
    flags.isPro = false
    render(<PrintBatchComposer />)
    expect(screen.getByText(/Print batches are a PRO feature/)).toBeTruthy()
    expect(mocks.get).not.toHaveBeenCalled()
  })

  it('says batching needs Core 4.4.0 when PRO reports it cannot run here', async () => {
    mocks.get.mockImplementation(async (path) => {
      if (path === '/api/v1/pro/print-batches') {
        return {
          batches: [],
          support: { available: false, message: 'Print batching needs FilaOps Core 4.4.0 or later' },
        }
      }
      return { candidates: [], items: [] }
    })
    render(<PrintBatchComposer />)
    expect(await screen.findByText(/needs FilaOps Core 4.4.0/)).toBeTruthy()
  })

  it('offers the printer models the shop has', async () => {
    render(<PrintBatchComposer />)
    await waitFor(() => expect(screen.getByRole('option', { name: 'P1S' })).toBeTruthy())
    expect(screen.getByRole('option', { name: 'A1' })).toBeTruthy()
  })
})

describe('ConfirmBatchCountsModal', () => {
  it('prefills the plan and posts per-part counts with a scrap reason', async () => {
    mocks.post.mockResolvedValue({ members: [] })
    const onCompleted = vi.fn()
    render(<ConfirmBatchCountsModal batch={BATCH} isOpen onClose={() => {}} onCompleted={onCompleted} />)
    expect(screen.getByLabelText('Body good').value).toBe('8')

    fireEvent.change(screen.getByLabelText('Body good'), { target: { value: '6' } })
    expect(screen.getByText(/Body: good \+ scrapped must be 8/)).toBeTruthy()
    fireEvent.change(screen.getByLabelText('Body scrapped'), { target: { value: '2' } })
    expect(screen.getByText(/choose why pieces were scrapped/)).toBeTruthy()

    await waitFor(() => expect(screen.getByRole('option', { name: 'Failed print' })).toBeTruthy())
    fireEvent.change(screen.getByLabelText('Scrap reason'), { target: { value: 'failed' } })
    fireEvent.click(screen.getByRole('button', { name: 'Confirm counts' }))

    await waitFor(() => expect(mocks.post).toHaveBeenCalled())
    const [path, body] = mocks.post.mock.calls[0]
    expect(path).toBe('/api/v1/pro/print-batches/7/complete')
    expect(body).toEqual({
      dry_run: false,
      run_minutes: 61,
      parts: [
        { product_id: 10, good: 6, scrapped: 2 },
        { product_id: 11, good: 4, scrapped: 0 },
      ],
      scrap_reason: 'failed',
      accept_short: true,
    })
    await waitFor(() => expect(onCompleted).toHaveBeenCalled())
  })

  it('previews with a dry run and shows what would happen', async () => {
    mocks.post.mockResolvedValue({
      run_minutes: 61,
      members: [{ member_id: 3, order_id: 42, role: 'demand', good: 4, scrapped: 0, minutes: 17.12, order_outcome: 'continues' }],
    })
    render(<ConfirmBatchCountsModal batch={BATCH} isOpen onClose={() => {}} />)
    fireEvent.click(screen.getByRole('button', { name: 'Preview' }))
    expect(await screen.findByText(/Goes on to its next step/)).toBeTruthy()
    expect(mocks.post.mock.calls[0][1].dry_run).toBe(true)
  })
})

describe('CompositionPicker', () => {
  const composition = (id, code) => ({
    id,
    code,
    printer_model: 'A1',
    verbatim: true,
    current_version: { id: id * 10, version: 1, plate_time_minutes: 60, items: [{ product_id: 1, quantity: 2 }, { product_id: 2, quantity: 1 }] },
  })

  it('shows the plan of the composition chosen last, whatever answers first', async () => {
    const answers = {}
    mocks.get.mockResolvedValue({ compositions: [composition(1, 'PLATE-A'), composition(2, 'PLATE-B')] })
    mocks.post.mockImplementation((path, body) => new Promise((resolve) => { answers[body.composition_version_id] = resolve }))
    render(<CompositionPicker isOpen onClose={() => {}} printerModel="A1" />)
    fireEvent.click(await screen.findByText('PLATE-A'))
    fireEvent.click(screen.getByText('PLATE-B'))
    const plan = (code) => ({ code, version: 1, printer_model: 'A1', parts: [] })
    answers[20](plan('PLATE-B'))
    await screen.findByText(/PLATE-B v1: books only on a A1/)
    answers[10](plan('PLATE-A'))
    await new Promise((r) => setTimeout(r, 0))
    expect(screen.queryByText(/PLATE-A v1: books only/)).toBeNull()
  })
})
