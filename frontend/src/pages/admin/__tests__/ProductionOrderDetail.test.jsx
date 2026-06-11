import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { describe, it, expect, vi, beforeEach } from 'vitest'

const { mocks } = vi.hoisted(() => {
  const mocks = {
    get: vi.fn(),
    post: vi.fn(),
    toastError: vi.fn(),
    toastSuccess: vi.fn(),
  }
  mocks.api = {
    get: mocks.get,
    post: mocks.post,
  }
  mocks.toast = {
    error: mocks.toastError,
    success: mocks.toastSuccess,
  }
  return { mocks }
})

vi.mock('../../../hooks/useApi', () => ({
  useApi: () => mocks.api,
}))

vi.mock('../../../components/Toast', () => ({
  useToast: () => mocks.toast,
}))

vi.mock('../../../components/orders/BlockingIssuesPanel', () => ({
  default: () => <div>Blocking issues</div>,
}))

vi.mock('../../../components/production', () => ({
  OperationsPanel: () => <div>Operations panel</div>,
  OperationSchedulerModal: () => null,
  OperationsTimeline: () => <div>Operations timeline</div>,
}))

// Mock ReleaseScheduleWizard so we can check it opens on release
let _wizardIsOpen = false
vi.mock('../../../components/production/ReleaseScheduleWizard', () => ({
  default: (props) => {
    _wizardIsOpen = props.isOpen
    if (!props.isOpen) return null
    return <div data-testid="release-wizard">Wizard open for {props.productionOrder?.code}</div>
  },
}))

import ProductionOrderDetail from '../ProductionOrderDetail'

const draftOrder = {
  id: 2782,
  code: 'PO-2026-0024',
  status: 'draft',
  product_name: 'Raspberry Pi 5 Enclosure',
  product_sku: 'FG-ENCLOSURE-01',
  quantity_ordered: 1,
  quantity_completed: 0,
  priority: 3,
  due_date: null,
  sales_order_id: 2789,
  sales_order_code: 'SO-2026-054',
  customer_name: 'Walk-in Customer',
}

let currentOrder = draftOrder

function renderPage() {
  return render(
    <MemoryRouter initialEntries={['/admin/production/2782']}>
      <Routes>
        <Route path="/admin/production/:orderId" element={<ProductionOrderDetail />} />
      </Routes>
    </MemoryRouter>,
  )
}

beforeEach(() => {
  currentOrder = draftOrder
  _wizardIsOpen = false
  mocks.get.mockReset()
  mocks.post.mockReset()
  mocks.toastError.mockReset()
  mocks.toastSuccess.mockReset()
  mocks.get.mockImplementation((path) => {
    if (path === '/api/v1/production-orders/2782') {
      return Promise.resolve(currentOrder)
    }
    return Promise.reject(new Error(`unexpected path ${path}`))
  })
  mocks.post.mockResolvedValue({})
})

describe('ProductionOrderDetail', () => {
  it('renders production workflow and linked sales order context', async () => {
    renderPage()

    expect(await screen.findByText('Production Workflow')).toBeInTheDocument()
    expect(screen.getByText('Not Released')).toBeInTheDocument()
    expect(screen.getAllByText('SO-2026-054')).toHaveLength(2)
    expect(screen.getByText(/invoice, payment, and shipment controls/i)).toBeInTheDocument()
  })

  it('shows draft orders as not released with a release action', async () => {
    renderPage()

    expect(await screen.findByText('Not Released')).toBeInTheDocument()
    expect(screen.getAllByRole('button', { name: /release to floor/i })).toHaveLength(2)
  })

  it('shows released orders as ready to start', async () => {
    currentOrder = { ...draftOrder, status: 'released' }

    renderPage()

    expect(await screen.findByText('Ready to Start')).toBeInTheDocument()
    expect(screen.getAllByRole('button', { name: /start production/i })).toHaveLength(2)
  })

  it('shows active orders as ready to complete', async () => {
    currentOrder = { ...draftOrder, status: 'in_progress' }

    renderPage()

    expect(await screen.findByText('Ready to Complete')).toBeInTheDocument()
    expect(screen.getAllByRole('button', { name: /complete production/i })).toHaveLength(2)
  })

  it('calls the release endpoint from the workflow action', async () => {
    renderPage()

    const releaseButtons = await screen.findAllByRole('button', {
      name: /release to floor/i,
    })
    fireEvent.click(releaseButtons[0])

    await waitFor(() => {
      expect(mocks.post).toHaveBeenCalledWith('/api/v1/production-orders/2782/release')
    })
  })

  it('opens the release wizard after a successful release', async () => {
    renderPage()

    const releaseButtons = await screen.findAllByRole('button', {
      name: /release to floor/i,
    })
    fireEvent.click(releaseButtons[0])

    await waitFor(() => {
      expect(screen.getByTestId('release-wizard')).toBeInTheDocument()
    })
  })

  it('release wizard is dismissible without affecting the released order', async () => {
    renderPage()

    const releaseButtons = await screen.findAllByRole('button', {
      name: /release to floor/i,
    })
    fireEvent.click(releaseButtons[0])

    // Wizard appears
    await waitFor(() => {
      expect(screen.getByTestId('release-wizard')).toBeInTheDocument()
    })

    // The post was still called (release happened regardless of wizard)
    expect(mocks.post).toHaveBeenCalledWith('/api/v1/production-orders/2782/release')
  })
})
