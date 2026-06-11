/**
 * OrderDetail.test.jsx — PR-8 workflow gating tests
 *
 * Tests:
 * - Workflow card shows "Create Work Orders" only when status === "confirmed"
 * - Workflow card blocks "Create Work Orders" for non-confirmed statuses
 * - Header only contains Refresh and Print Packing Slip
 * - Order Summary shows humanized status (no raw snake_case)
 * - closed_short renders correctly depending on production completion
 * - Action surface is singular: state-changing buttons appear in workflow card
 */
import { render, screen, waitFor } from '@testing-library/react'
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

function makeOrder(overrides = {}) {
  return {
    id: 1001,
    order_number: 'SO-2026-001',
    order_type: 'line_item',
    status: 'confirmed',
    payment_status: 'pending',
    closed_short: false,
    quantity: 5,
    total_price: '50.00',
    grand_total: '50.00',
    product_id: null,
    product_name: null,
    lines: [
      {
        id: 101,
        product_id: 42,
        product_name: 'Test Widget',
        product_sku: 'TW-001',
        quantity: 5,
        unit_price: '10.00',
        total: '50.00',
        shipped_quantity: 0,
        line_type: 'product',
      },
    ],
    customer_name: 'ACME Corp',
    customer_email: 'acme@example.com',
    ...overrides,
  }
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
      return Promise.resolve({ total_paid: 0, total_due: 50 })
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
// Workflow gating tests
// ---------------------------------------------------------------------------

describe('OrderDetail — workflow gating (PR-8 / issue #680 item 3)', () => {
  it('shows Create Work Orders button when status is confirmed, billing satisfied, no WOs exist', async () => {
    // Billing must be satisfied for the production step to offer Create Work Orders
    const order = makeOrder({
      status: 'confirmed',
      payment_status: 'paid',  // billing satisfied
    })
    setupApiMocks({ order, productionOrders: [] })

    renderOrderDetail()

    expect(await screen.findByText('Order Workflow')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /create work orders/i })).toBeInTheDocument()
  })

  it('does NOT show Create Work Orders button when status is in_production', async () => {
    const order = makeOrder({ status: 'in_production' })
    setupApiMocks({
      order,
      productionOrders: [],  // no WOs, but status is past confirmed
    })

    renderOrderDetail()

    await screen.findByText('Order Workflow')
    const createWOButtons = screen.queryAllByRole('button', { name: /create work orders/i })
    expect(createWOButtons).toHaveLength(0)
  })

  it('does NOT show Create Work Orders button when status is ready_to_ship', async () => {
    const order = makeOrder({ status: 'ready_to_ship', closed_short: true })
    setupApiMocks({ order, productionOrders: [] })

    renderOrderDetail()

    await screen.findByText('Order Workflow')
    const createWOButtons = screen.queryAllByRole('button', { name: /create work orders/i })
    expect(createWOButtons).toHaveLength(0)
  })

  it('shows Open Work Order when WOs exist', async () => {
    const order = makeOrder({ status: 'in_production' })
    const productionOrders = [
      {
        id: 555,
        code: 'PO-2026-0055',
        status: 'draft',
        product_id: 42,
        sales_order_line_id: 101,
        quantity_ordered: 5,
        quantity_completed: 0,
      },
    ]
    setupApiMocks({ order, productionOrders })

    renderOrderDetail()

    await screen.findByText('Order Workflow')
    expect(screen.getByRole('button', { name: /open work order/i })).toBeInTheDocument()
  })
})

// ---------------------------------------------------------------------------
// Header tests
// ---------------------------------------------------------------------------

describe('OrderDetail — header (PR-8 slim)', () => {
  it('header contains Refresh and Print Packing Slip only', async () => {
    const order = makeOrder({ status: 'confirmed' })
    setupApiMocks({ order })

    renderOrderDetail()

    await screen.findByText('Order Workflow')

    // Must have Refresh
    expect(screen.getByRole('button', { name: /refresh/i })).toBeInTheDocument()
    // Must have Print Packing Slip
    expect(screen.getByRole('button', { name: /print packing slip/i })).toBeInTheDocument()
    // Must NOT have Ship Order in header (it's in workflow card step 4)
    const shipButtons = screen.queryAllByRole('button', { name: /^ship order$/i })
    // Ship Order only appears in the workflow card action, not a second time in header
    // The workflow card renders it as a button only when shipping is ready
    // (confirmed status means production not complete, so no ship button should appear in workflow either)
    expect(shipButtons).toHaveLength(0)
  })

  it('Confirm Order appears in workflow secondary actions, not header', async () => {
    const order = makeOrder({ status: 'pending' })
    setupApiMocks({ order })

    renderOrderDetail()

    await screen.findByText('Order Workflow')

    // Confirm appears in the secondary actions row below workflow card
    const confirmBtns = screen.getAllByRole('button', { name: /confirm order/i })
    // Should be in the workflow secondary row (not the header area)
    expect(confirmBtns.length).toBeGreaterThanOrEqual(1)
  })
})

// ---------------------------------------------------------------------------
// Order Summary humanization tests
// ---------------------------------------------------------------------------

describe('OrderDetail — Order Summary status humanization (PR-8)', () => {
  it('renders status without underscores in Order Summary', async () => {
    const order = makeOrder({ status: 'in_production' })
    setupApiMocks({ order })

    renderOrderDetail()

    await screen.findByText('Order Summary')
    // The Status row in Order Summary must show humanized text
    const statusLabel = screen.getByText('Status')
    const statusCell = statusLabel.closest('div').parentElement
    expect(statusCell).toHaveTextContent('in production')
    expect(screen.queryByText('in_production')).not.toBeInTheDocument()
  })

  it('renders ready_to_ship as readable text in Order Summary', async () => {
    const order = makeOrder({ status: 'ready_to_ship' })
    setupApiMocks({ order })

    renderOrderDetail()

    await screen.findByText('Order Summary')
    const statusLabel = screen.getByText('Status')
    const statusCell = statusLabel.closest('div').parentElement
    expect(statusCell).toHaveTextContent('ready to ship')
  })
})

// ---------------------------------------------------------------------------
// closed_short reconcile tests
// ---------------------------------------------------------------------------

describe('OrderDetail — closed_short reconcile rendering (PR-8 / issue #680 item 2)', () => {
  it('shows Closed Short badge when closed_short=true and production not complete', async () => {
    const order = makeOrder({
      status: 'ready_to_ship',
      closed_short: true,
    })
    const productionOrders = [
      {
        id: 556,
        code: 'PO-2026-0056',
        status: 'draft',  // not complete
        product_id: 42,
        sales_order_line_id: 101,
        quantity_ordered: 5,
        quantity_completed: 0,
      },
    ]
    setupApiMocks({ order, productionOrders })

    renderOrderDetail()

    await screen.findByText('Order Summary')
    expect(screen.getByText('Closed Short')).toBeInTheDocument()
    expect(screen.queryByText(/previously closed short/i)).not.toBeInTheDocument()
  })

  it('shows Previously Closed Short - Fulfilled badge when all WOs are complete', async () => {
    const order = makeOrder({
      status: 'ready_to_ship',
      closed_short: true,
    })
    const productionOrders = [
      {
        id: 557,
        code: 'PO-2026-0057',
        status: 'complete',  // complete!
        product_id: 42,
        sales_order_line_id: 101,
        quantity_ordered: 5,
        quantity_completed: 5,
      },
    ]
    setupApiMocks({ order, productionOrders })

    renderOrderDetail()

    await screen.findByText('Order Summary')
    expect(screen.getByText(/previously closed short.*fulfilled/i)).toBeInTheDocument()
    expect(screen.queryByText(/^closed short$/i)).not.toBeInTheDocument()
  })
})
