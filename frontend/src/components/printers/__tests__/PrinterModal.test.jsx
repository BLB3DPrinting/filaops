import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach } from 'vitest'

const { mocks } = vi.hoisted(() => ({
  mocks: {
    toastError: vi.fn(),
    toastSuccess: vi.fn(),
  },
}))

vi.mock('../../Toast', () => ({
  useToast: () => ({
    error: mocks.toastError,
    success: mocks.toastSuccess,
    warning: vi.fn(),
    info: vi.fn(),
  }),
}))

vi.mock('../../../hooks/useFeatureFlags', () => ({
  useFeatureFlags: () => ({ isPro: false, hasFeature: () => false }),
}))

vi.mock('../../Modal', () => ({
  default: ({ children }) => <div role="dialog">{children}</div>,
}))

import PrinterModal from '../PrinterModal'

const brandInfo = [
  { code: 'generic', name: 'Generic', models: [] },
  { code: 'bambulab', name: 'Bambu Lab', models: [{ value: 'X1C', label: 'X1 Carbon' }] },
]

const editablePrinter = {
  id: 1,
  code: 'PRT-001',
  name: 'X1C Bay 1',
  brand: 'bambulab',
  model: 'X1C',
  serial_number: 'SN123',
  ip_address: '192.168.1.100',
  location: 'Farm A',
  work_center_id: null,
  notes: '',
  active: true,
  connection_config: { access_code: '12345678' },
  capabilities: { filament_diameters: [1.75] },
}

const fetchOk = (body = []) => ({
  ok: true,
  json: async () => body,
})

const lastPrinterPutBody = () => {
  const calls = globalThis.fetch.mock.calls
  for (let i = calls.length - 1; i >= 0; i--) {
    const [url, opts] = calls[i]
    if (typeof url === 'string' && /\/api\/v1\/printers\/\d+/.test(url) && opts?.method === 'PUT') {
      return JSON.parse(opts.body)
    }
  }
  throw new Error('No PUT to /api/v1/printers/:id was made')
}

beforeEach(() => {
  mocks.toastError.mockReset()
  mocks.toastSuccess.mockReset()
  globalThis.fetch = vi.fn((url) => {
    if (typeof url === 'string' && url.includes('/work-centers')) {
      return Promise.resolve(fetchOk([{ id: 5, name: 'Print Farm A' }]))
    }
    return Promise.resolve(fetchOk({}))
  })
})

describe('PrinterModal — discontinued models (WS1 catalog refresh)', () => {
  const brandInfoWithDiscontinued = [
    { code: 'generic', name: 'Generic', models: [] },
    {
      code: 'bambulab',
      name: 'Bambu Lab',
      models: [
        { value: 'H2D', label: 'H2D', discontinued: false },
        { value: 'P1S', label: 'P1S', discontinued: false },
        { value: 'X1C', label: 'X1 Carbon', discontinued: true },
        { value: 'X1', label: 'X1', discontinued: true },
      ],
    },
  ]

  const modelSelect = () =>
    Array.from(screen.getByRole('dialog').querySelectorAll('select')).find((s) =>
      Array.from(s.options).some((o) => o.value === 'H2D' || o.value === 'X1C')
    )

  it('hides discontinued models from the new-printer dropdown', () => {
    render(
      <PrinterModal
        printer={null}
        onClose={vi.fn()}
        onSave={vi.fn()}
        brandInfo={brandInfoWithDiscontinued}
      />
    )
    // Switch brand to bambulab so the model dropdown renders
    const brandSelect = Array.from(
      screen.getByRole('dialog').querySelectorAll('select')
    ).find((s) => Array.from(s.options).some((o) => o.value === 'bambulab'))
    fireEvent.change(brandSelect, { target: { value: 'bambulab' } })

    const options = Array.from(modelSelect().options).map((o) => o.value)
    expect(options).toContain('H2D')
    expect(options).toContain('P1S')
    expect(options).not.toContain('X1C')
    expect(options).not.toContain('X1')
  })

  it('keeps the printer\'s own discontinued model selectable in edit mode, with a suffix', () => {
    render(
      <PrinterModal
        printer={editablePrinter}
        onClose={vi.fn()}
        onSave={vi.fn()}
        brandInfo={brandInfoWithDiscontinued}
      />
    )
    const select = modelSelect()
    const x1c = Array.from(select.options).find((o) => o.value === 'X1C')
    expect(x1c).toBeTruthy()
    expect(x1c.textContent).toContain('(discontinued)')
    expect(select.value).toBe('X1C')
    // Other discontinued models stay hidden even in edit mode
    expect(Array.from(select.options).map((o) => o.value)).not.toContain('X1')
  })

  it('does not filter models that lack the discontinued flag (older API payloads)', () => {
    render(
      <PrinterModal
        printer={editablePrinter}
        onClose={vi.fn()}
        onSave={vi.fn()}
        brandInfo={brandInfo}
      />
    )
    const select = modelSelect()
    expect(Array.from(select.options).map((o) => o.value)).toContain('X1C')
  })
})

describe('PrinterModal — work_center_id payload (issue #577)', () => {
  it('sends work_center_id as null (not empty string) when editing a printer with no work center', async () => {
    const onSave = vi.fn()
    render(
      <PrinterModal
        printer={editablePrinter}
        onClose={vi.fn()}
        onSave={onSave}
        brandInfo={brandInfo}
      />
    )

    const form = screen.getByRole('dialog').querySelector('form')
    fireEvent.submit(form)

    await waitFor(() => expect(onSave).toHaveBeenCalled())

    const body = lastPrinterPutBody()
    expect(body.work_center_id).toBeNull()
    expect(body.work_center_id).not.toBe('')
    expect(mocks.toastError).not.toHaveBeenCalled()
  })

  it('sends work_center_id as null when user selects "None" in the dropdown', async () => {
    const onSave = vi.fn()
    render(
      <PrinterModal
        printer={{ ...editablePrinter, work_center_id: 5 }}
        onClose={vi.fn()}
        onSave={onSave}
        brandInfo={brandInfo}
      />
    )

    await waitFor(() => {
      expect(screen.getByText('Print Farm A')).toBeInTheDocument()
    })

    const wcSelect = Array.from(screen.getByRole('dialog').querySelectorAll('select')).find(
      (s) => Array.from(s.options).some((o) => o.textContent === 'None')
    )
    fireEvent.change(wcSelect, { target: { value: '' } })

    const form = screen.getByRole('dialog').querySelector('form')
    fireEvent.submit(form)

    await waitFor(() => expect(onSave).toHaveBeenCalled())

    const body = lastPrinterPutBody()
    expect(body.work_center_id).toBeNull()
  })

  it('sends work_center_id as integer when a work center is selected', async () => {
    const onSave = vi.fn()
    render(
      <PrinterModal
        printer={editablePrinter}
        onClose={vi.fn()}
        onSave={onSave}
        brandInfo={brandInfo}
      />
    )

    await waitFor(() => {
      expect(screen.getByText('Print Farm A')).toBeInTheDocument()
    })

    const wcSelect = Array.from(screen.getByRole('dialog').querySelectorAll('select')).find(
      (s) => Array.from(s.options).some((o) => o.textContent === 'None')
    )
    fireEvent.change(wcSelect, { target: { value: '5' } })

    const form = screen.getByRole('dialog').querySelector('form')
    fireEvent.submit(form)

    await waitFor(() => expect(onSave).toHaveBeenCalled())

    const body = lastPrinterPutBody()
    expect(body.work_center_id).toBe(5)
    expect(typeof body.work_center_id).toBe('number')
  })
})
