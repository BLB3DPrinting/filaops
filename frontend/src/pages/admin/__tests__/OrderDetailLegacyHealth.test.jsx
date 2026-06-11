/**
 * OrderDetailLegacyHealth.test.jsx — LEGACY-1 brownfield order data health
 *
 * Tests:
 * - Step 4 (Fulfillment) "done" requires shipment evidence, not just status
 * - Step 4 shows blocked + honest copy when status says shipped but nothing
 *   was recorded
 * - Legacy NULL-linked WOs count as production coverage (Step 3)
 * - Amber data-health banner appears only on a legacy fulfillment mismatch
 * - Banner buttons open a confirm dialog and call the resolve endpoint
 */
import { render, screen, waitFor, fireEvent } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { describe, it, expect, vi, beforeEach } from 'vitest'

const { mocks } = vi.hoisted(() => {
  const mocks = {
    get: vi.fn(),
    post: vi.fn(),
    toastError: vi.fn(),
    toastSuccess: vi.fn(),
    toastInfo: vi.fn(),
    navigate: vi.fn(),
  }
  mocks.api = {
    get: mocks.get,
    post: mocks.post,
  }
  mocks.toast = {
    error: mocks.toastError,
    success: mocks.toastSuccess,
    info: mocks.toastInfo,
  }
  return { mocks }
})

vi.mock('../../../hooks/useApi', () => ({
  useApi: () => mocks.api,
}))

vi.mock('../../../components/Toast', () => ({
  useToast: () => mocks.toast,
}))

vi.mock('react-router-dom', async (importOriginal) => {
  const actual = await importOriginal()
  return {
    ...actual,
    useNavigate: () => mocks.navigate,
  }
})

vi.mock('../../../hooks/useFulfillmentStatus', () => ({
  useFulfillmentStatus: () => ({
    data: null,
    loading: false,
    error: null,
    refetch: vi.fn(),
  }),
}))

vi.mock('../../../components/orders/BlockingIssuesPanel', () => ({
  default: () => <div data-testid="blocking-issues" />,
}))

vi.mock('../../../components/orders/FulfillmentProgress', () => ({
  default: () => <div data-testid="fulfillment-progress" />,
}))

vi.mock('../../../components/orders/ProductionStatusCards', () => ({
  ProductionProgressSummary: () => <div data-testid="production-summary" />,
  ProductionOrderStatusCard: ({ order }) => (
    <div data-testid={`po-card-${order.id}`}>{order.code}</div>
  ),
}))

vi.mock('../../../components/orders/MaterialRequirementsSection', () => ({
  default: () => <div data-testid="material-req" />,
}))

vi.mock('../../../components/orders/CapacityRequirementsSection', () => ({
  default: () => <div data-testid="capacity-req" />,
}))

vi.mock('../../../components/orders/PaymentsSection', () => ({
  default: () => <div data-testid="payments-section" />,
}))

vi.mock('../../../components/orders/ShippingAddressSection', () => ({
  default: () => <div data-testid="shipping-address" />,
}))

vi.mock('../../../components/orders/OrderModals', () => ({
  CancelOrderModal: () => <div data-testid="cancel-modal" />,
  DeleteOrderModal: () => <div data-testid="delete-modal" />,
}))

vi.mock('../../../components/payments/RecordPaymentModal', () => ({
  default: () => <div data-testid="payment-modal" />,
}))

vi.mock('../../../components/ActivityTimeline', () => ({
  default: () => <div data-testid="activity-timeline" />,
}))

vi.mock('../../../components/ShippingTimeline', () => ({
  default: () => <div data-testid="shipping-timeline" />,
}))

import OrderDetail from '../OrderDetail'

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/** SO-2026-0041 shape: completed order, nothing ever shipped. */
function makeLegacyOrder(overrides = {}) {
  return {
    id: 1001,
    order_number: 'SO-2026-0041',
    order_type: 'line_item',
    status: 'completed',
    fulfillment_status: 'pending',
    payment_status: 'paid',
    shipped_at: null,
    closed_short: false,
    quantity: 4,
    total_price: '40.00',
    grand_total: '40.00',
    product_id: null,
    product_name: null,
    lines: [
      {
        id: 101,
        product_id: 42,
        product_name: 'Test Widget',
        product_sku: 'TW-001',
        quantity: 2,
        unit_price: '10.00',
        total: '20.00',
        shipped_quantity: 0,
        line_type: 'product',
      },
      {
        id: 102,
        product_id: 43,
        product_name: 'Test Gadget',
        product_sku: 'TG-001',
        quantity: 2,
        unit_price: '10.00',
        total: '20.00',
        shipped_quantity: 0,
        line_type: 'product',
      },
    ],
    customer_name: 'ACME Corp',
    customer_email: 'acme@example.com',
    ...overrides,
  }
}

/** Legacy WOs: complete but sales_order_line_id = null (pre-#713). */
function makeLegacyWOs() {
  return [
    {
      id: 555,
      code: 'PO-2026-0055',
      status: 'complete',
      product_id: 42,
      sales_order_line_id: null,
      quantity_ordered: 2,
      quantity_completed: 2,
    },
    {
      id: 556,
      code: 'PO-2026-0056',
      status: 'complete',
      product_id: 43,
      sales_order_line_id: null,
      quantity_ordered: 2,
      quantity_completed: 2,
    },
  ]
}

function setupApiMocks({ order, productionOrders = [], invoice = null } = {}) {
  mocks.get.mockImplementation((path) => {
    if (path.includes('/api/v1/sales-orders/1001') && !path.includes('material')) {
      return Promise.resolve(order)
    }
    if (path.includes('material-requirements')) {
      return Promise.resolve({ requirements: [], summary: null })
    }
    if (path.includes('/api/v1/production-orders')) {
      return Promise.resolve({ items: productionOrders })
    }
    if (path.includes('/api/v1/payments/order')) {
      return Promise.resolve({ total_paid: 40, total_due: 0 })
    }
    if (path.includes('/api/v1/payments')) {
      return Promise.resolve({ items: [] })
    }
    if (path.includes('/api/v1/invoices')) {
      return Promise.resolve({ items: invoice ? [invoice] : [] })
    }
    return Promise.resolve({})
  })
}

function renderOrderDetail() {
  return render(
    <MemoryRouter initialEntries={['/admin/orders/1001']}>
      <Routes>
        <Route path="/admin/orders/:orderId" element={<OrderDetail />} />
      </Routes>
    </MemoryRouter>,
  )
}

beforeEach(() => {
  mocks.get.mockReset()
  mocks.post.mockReset()
  mocks.toastError.mockReset()
  mocks.toastSuccess.mockReset()
  mocks.navigate.mockReset()
})

// ---------------------------------------------------------------------------
// Step 4 — shipment evidence
// ---------------------------------------------------------------------------

describe('OrderDetail — Step 4 fulfillment evidence (LEGACY-1)', () => {
  it('marks Step 4 blocked with honest copy when status is completed but nothing shipped', async () => {
    setupApiMocks({ order: makeLegacyOrder(), productionOrders: makeLegacyWOs() })

    renderOrderDetail()

    await screen.findByText('Order Workflow')
    expect(
      screen.getByText(/order status says completed, but no shipment was recorded/i),
    ).toBeInTheDocument()
    expect(screen.getByText(/needs review/i)).toBeInTheDocument()
  })

  it('marks Step 4 done when shipped_at evidence exists', async () => {
    const order = makeLegacyOrder({ shipped_at: '2026-01-15T12:00:00Z' })
    setupApiMocks({ order, productionOrders: makeLegacyWOs() })

    renderOrderDetail()

    await screen.findByText('Order Workflow')
    expect(
      screen.queryByText(/no shipment was recorded/i),
    ).not.toBeInTheDocument()
    expect(
      screen.getByText(/shipment is already in progress or complete/i),
    ).toBeInTheDocument()
  })

  it('marks Step 4 done when a line has shipped_quantity > 0', async () => {
    const order = makeLegacyOrder()
    order.lines[0].shipped_quantity = 2
    setupApiMocks({ order, productionOrders: makeLegacyWOs() })

    renderOrderDetail()

    await screen.findByText('Order Workflow')
    expect(
      screen.queryByText(/no shipment was recorded/i),
    ).not.toBeInTheDocument()
  })

  it('marks Step 4 done when fulfillment_status is shipped', async () => {
    const order = makeLegacyOrder({ fulfillment_status: 'shipped' })
    setupApiMocks({ order, productionOrders: makeLegacyWOs() })

    renderOrderDetail()

    await screen.findByText('Order Workflow')
    expect(
      screen.queryByText(/no shipment was recorded/i),
    ).not.toBeInTheDocument()
  })
})

// ---------------------------------------------------------------------------
// Step 3 — legacy NULL-linked WO coverage
// ---------------------------------------------------------------------------

describe('OrderDetail — legacy WO coverage fallback (LEGACY-1)', () => {
  it('treats NULL-linked WOs matching line products as production coverage', async () => {
    setupApiMocks({ order: makeLegacyOrder(), productionOrders: makeLegacyWOs() })

    renderOrderDetail()

    await screen.findByText('Order Workflow')
    // Step 3 considers production released → Open Work Order, no misleading block
    expect(screen.getByRole('button', { name: /open work order/i })).toBeInTheDocument()
    expect(
      screen.queryByText(/work orders can only be created while the order is in confirmed status/i),
    ).not.toBeInTheDocument()
  })

  it('does NOT count a NULL-linked WO toward lines of a different product', async () => {
    // Only one legacy WO (product 42); line for product 43 is uncovered.
    setupApiMocks({
      order: makeLegacyOrder(),
      productionOrders: [makeLegacyWOs()[0]],
    })

    renderOrderDetail()

    await screen.findByText('Order Workflow')
    expect(
      screen.getByText(/work orders can only be created while the order is in confirmed status; this order is completed/i),
    ).toBeInTheDocument()
  })
})

// ---------------------------------------------------------------------------
// Legacy data-health banner + guided resolution
// ---------------------------------------------------------------------------

describe('OrderDetail — legacy fulfillment banner (LEGACY-1)', () => {
  it('shows the amber banner when status claims shipped but no evidence exists', async () => {
    setupApiMocks({ order: makeLegacyOrder(), productionOrders: makeLegacyWOs() })

    renderOrderDetail()

    await screen.findByText('Order Workflow')
    expect(
      screen.getByText(/no shipment was ever recorded — likely data from an older filaops version/i),
    ).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /close out as fulfilled/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /reopen for shipping/i })).toBeInTheDocument()
  })

  it('does NOT show the banner when shipment evidence exists', async () => {
    const order = makeLegacyOrder({ shipped_at: '2026-01-15T12:00:00Z' })
    setupApiMocks({ order, productionOrders: makeLegacyWOs() })

    renderOrderDetail()

    await screen.findByText('Order Workflow')
    expect(
      screen.queryByText(/no shipment was ever recorded/i),
    ).not.toBeInTheDocument()
  })

  it('does NOT show the banner for non-shipped statuses', async () => {
    const order = makeLegacyOrder({ status: 'in_production' })
    setupApiMocks({ order, productionOrders: makeLegacyWOs() })

    renderOrderDetail()

    await screen.findByText('Order Workflow')
    expect(
      screen.queryByText(/no shipment was ever recorded/i),
    ).not.toBeInTheDocument()
  })

  it('Close Out opens confirm dialog and posts action=close_out', async () => {
    setupApiMocks({ order: makeLegacyOrder(), productionOrders: makeLegacyWOs() })
    mocks.post.mockResolvedValue({})

    renderOrderDetail()

    const closeOutBtn = await screen.findByRole('button', { name: /close out as fulfilled/i })
    fireEvent.click(closeOutBtn)

    // Confirm dialog with the no-inventory/no-GL explanation
    expect(
      await screen.findByText(/no inventory movements or accounting entries are created/i),
    ).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: /^close out$/i }))

    await waitFor(() => {
      expect(mocks.post).toHaveBeenCalledWith(
        '/api/v1/sales-orders/1001/resolve-legacy-fulfillment',
        { action: 'close_out' },
      )
    })
    await waitFor(() => {
      expect(mocks.toastSuccess).toHaveBeenCalledWith(
        expect.stringMatching(/closed out/i),
      )
    })
  })

  it('Reopen opens confirm dialog and posts action=reopen', async () => {
    setupApiMocks({ order: makeLegacyOrder(), productionOrders: makeLegacyWOs() })
    mocks.post.mockResolvedValue({})

    renderOrderDetail()

    const reopenBtn = await screen.findByRole('button', { name: /reopen for shipping/i })
    fireEvent.click(reopenBtn)

    expect(
      await screen.findByText(/sets the order back to ready to ship/i),
    ).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: /reopen order/i }))

    await waitFor(() => {
      expect(mocks.post).toHaveBeenCalledWith(
        '/api/v1/sales-orders/1001/resolve-legacy-fulfillment',
        { action: 'reopen' },
      )
    })
  })

  it('shows an error toast and keeps the dialog usable when the resolve call fails', async () => {
    setupApiMocks({ order: makeLegacyOrder(), productionOrders: makeLegacyWOs() })
    mocks.post.mockRejectedValue(new Error('No legacy fulfillment mismatch on this order'))

    renderOrderDetail()

    fireEvent.click(await screen.findByRole('button', { name: /close out as fulfilled/i }))
    fireEvent.click(await screen.findByRole('button', { name: /^close out$/i }))

    await waitFor(() => {
      expect(mocks.toastError).toHaveBeenCalledWith(
        'No legacy fulfillment mismatch on this order',
      )
    })
  })
})
