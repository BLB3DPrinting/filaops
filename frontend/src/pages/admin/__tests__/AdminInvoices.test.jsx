/**
 * AdminInvoices — PR-7 tests
 *
 * Verifies that the Invoices page opens RecordPaymentModal (not the old
 * inline bespoke form) when the user clicks "Record Payment".
 */
import { render, screen, waitFor, fireEvent } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { describe, it, expect, vi, beforeEach } from 'vitest'

// ---------------------------------------------------------------------------
// Hoisted mocks
// ---------------------------------------------------------------------------
const { mocks } = vi.hoisted(() => {
  const mocks = {
    get: vi.fn(),
    post: vi.fn(),
    patch: vi.fn(),
    toastError: vi.fn(),
    toastSuccess: vi.fn(),
    formatCurrency: vi.fn((v) => `$${Number(v || 0).toFixed(2)}`),
    modalRendered: vi.fn(),
  }
  mocks.api = { get: mocks.get, post: mocks.post, patch: mocks.patch }
  mocks.toast = { error: mocks.toastError, success: mocks.toastSuccess }
  return { mocks }
})

vi.mock('../../../hooks/useApi', () => ({ useApi: () => mocks.api }))
vi.mock('../../../components/Toast', () => ({ useToast: () => mocks.toast }))
vi.mock('../../../hooks/useFormatCurrency', () => ({
  useFormatCurrency: () => mocks.formatCurrency,
}))
vi.mock('../../../contexts/LocaleContext', () => ({
  useLocale: () => ({ currency_code: 'USD', locale: 'en-US' }),
}))

// Spy on RecordPaymentModal to verify it's mounted with the right props
vi.mock('../../../components/payments/RecordPaymentModal', () => ({
  default: (props) => {
    mocks.modalRendered(props)
    return (
      <div data-testid="record-payment-modal">
        <span data-testid="modal-order-id">{String(props.orderId)}</span>
        <span data-testid="modal-invoice-id">{String(props.invoiceId)}</span>
        <span data-testid="modal-balance">{String(props.invoiceBalanceDue)}</span>
        <button onClick={props.onClose} data-testid="modal-close">Close</button>
      </div>
    )
  },
}))

import AdminInvoices from '../AdminInvoices'

// ---------------------------------------------------------------------------
// Sample data
// ---------------------------------------------------------------------------
const INVOICE_LIST = [
  {
    id: 42,
    invoice_number: 'INV-2026-001',
    sales_order_id: 99,
    order_number: 'SO-TEST-001',
    customer_name: 'Test Customer',
    customer_company: null,
    payment_terms: 'net30',
    due_date: '2026-07-01',
    total: 200,
    amount_paid: 0,
    amount_due: 200,
    status: 'sent',
    created_at: '2026-06-01T00:00:00Z',
    sent_at: '2026-06-01T00:00:00Z',
  },
]

const INVOICE_DETAIL = {
  ...INVOICE_LIST[0],
  lines: [],
  subtotal: 200,
  discount_amount: 0,
  tax_amount: 0,
  shipping_amount: 0,
  balance_due: 200,
}

function renderInvoices() {
  return render(
    <MemoryRouter>
      <AdminInvoices />
    </MemoryRouter>,
  )
}

beforeEach(() => {
  mocks.get.mockReset()
  mocks.modalRendered.mockReset()
  mocks.toastError.mockReset()
  mocks.toastSuccess.mockReset()

  mocks.get.mockImplementation((path) => {
    if (path.includes('/summary')) return Promise.resolve({ total_ar: 200, overdue_count: 0, open_count: 1, paid_last_30_days: 0 })
    if (path.includes('/invoices/42')) return Promise.resolve(INVOICE_DETAIL)
    if (path.includes('/invoices')) return Promise.resolve(INVOICE_LIST)
    return Promise.resolve([])
  })
})

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('AdminInvoices — RecordPaymentModal integration (PR-7)', () => {
  it('renders the invoice list', async () => {
    renderInvoices()
    await waitFor(() => {
      expect(screen.getByText('INV-2026-001')).toBeInTheDocument()
    })
  })

  it('opens RecordPaymentModal (not the old inline form) when Record Payment is clicked', async () => {
    renderInvoices()

    // Wait for list to render then click on invoice row to open detail modal
    await waitFor(() => screen.getByText('INV-2026-001'))
    fireEvent.click(screen.getByText('INV-2026-001'))

    // Wait for detail modal to load
    await waitFor(() => screen.getByText('Record Payment'))

    // Click the Record Payment button
    fireEvent.click(screen.getByText('Record Payment'))

    // RecordPaymentModal should now be rendered
    await waitFor(() => {
      expect(screen.getByTestId('record-payment-modal')).toBeInTheDocument()
    })
  })

  it('passes correct orderId and invoiceId props to RecordPaymentModal', async () => {
    renderInvoices()
    await waitFor(() => screen.getByText('INV-2026-001'))
    fireEvent.click(screen.getByText('INV-2026-001'))
    await waitFor(() => screen.getByText('Record Payment'))
    fireEvent.click(screen.getByText('Record Payment'))

    await waitFor(() => screen.getByTestId('record-payment-modal'))

    expect(screen.getByTestId('modal-order-id').textContent).toBe('99')
    expect(screen.getByTestId('modal-invoice-id').textContent).toBe('42')
  })

  it('passes invoiceBalanceDue to RecordPaymentModal', async () => {
    renderInvoices()
    await waitFor(() => screen.getByText('INV-2026-001'))
    fireEvent.click(screen.getByText('INV-2026-001'))
    await waitFor(() => screen.getByText('Record Payment'))
    fireEvent.click(screen.getByText('Record Payment'))

    await waitFor(() => screen.getByTestId('record-payment-modal'))

    // Balance should be 200 (total - amount_paid)
    const balance = parseFloat(screen.getByTestId('modal-balance').textContent)
    expect(balance).toBeGreaterThan(0)
  })

  it('does NOT render the old inline payment form markup', async () => {
    renderInvoices()
    await waitFor(() => screen.getByText('INV-2026-001'))
    fireEvent.click(screen.getByText('INV-2026-001'))
    await waitFor(() => screen.getByText('Record Payment'))
    fireEvent.click(screen.getByText('Record Payment'))

    // The old form had a "Submit Payment" button — it should not exist
    expect(screen.queryByText('Submit Payment')).not.toBeInTheDocument()
  })

  it('hides Record Payment button when invoice is already paid', async () => {
    const paidInvoice = { ...INVOICE_LIST[0], status: 'paid', amount_paid: 200, amount_due: 0 }
    const paidDetail = { ...INVOICE_DETAIL, status: 'paid', amount_paid: 200, balance_due: 0 }

    mocks.get.mockImplementation((path) => {
      if (path.includes('/summary')) return Promise.resolve({ total_ar: 0, overdue_count: 0, open_count: 0, paid_last_30_days: 200 })
      if (path.includes('/invoices/42')) return Promise.resolve(paidDetail)
      if (path.includes('/invoices')) return Promise.resolve([paidInvoice])
      return Promise.resolve([])
    })

    renderInvoices()
    await waitFor(() => screen.getByText('INV-2026-001'))
    fireEvent.click(screen.getByText('INV-2026-001'))
    await waitFor(() => expect(mocks.get).toHaveBeenCalledWith(expect.stringContaining('/invoices/42')))

    // "Record Payment" button should not be visible for a paid invoice
    expect(screen.queryByText('Record Payment')).not.toBeInTheDocument()
  })

  it('closes RecordPaymentModal when onClose is called', async () => {
    renderInvoices()
    await waitFor(() => screen.getByText('INV-2026-001'))
    fireEvent.click(screen.getByText('INV-2026-001'))
    await waitFor(() => screen.getByText('Record Payment'))
    fireEvent.click(screen.getByText('Record Payment'))
    await waitFor(() => screen.getByTestId('record-payment-modal'))

    // Close the modal
    fireEvent.click(screen.getByTestId('modal-close'))
    await waitFor(() => {
      expect(screen.queryByTestId('record-payment-modal')).not.toBeInTheDocument()
    })
  })
})

describe('AdminInvoices — quote descriptions, discounts and notes', () => {
  const DISCOUNTED_DETAIL = {
    ...INVOICE_DETAIL,
    total: 81.97,
    subtotal: '85.12',
    discount_amount: '8.51',
    discount_label: '10% discount',
    tax_amount: '5.36',
    notes: 'Thanks for the order!',
    lines: [{
      id: 1,
      sku: 'TROPHY',
      description: 'Custom Trophy',
      long_description: 'Black Base (PLA Matte Charcoal)\nGold Top (PLA Silk Gold)',
      quantity: 2,
      unit_price: '42.56',
      line_total: '85.12',
    }],
  }

  const openInvoice = async (detail) => {
    mocks.get.mockImplementation((path) => {
      if (path.includes('/summary')) return Promise.resolve({ total_ar: 0, overdue_count: 0, open_count: 1, paid_last_30_days: 0 })
      if (path.includes('/invoices/42')) return Promise.resolve(detail)
      if (path.includes('/invoices')) return Promise.resolve(INVOICE_LIST)
      return Promise.resolve([])
    })
    renderInvoices()
    await waitFor(() => screen.getByText('INV-2026-001'))
    fireEvent.click(screen.getByText('INV-2026-001'))
    await waitFor(() => screen.getByText('Custom Trophy'))
  }

  it('shows the description, discount rows, discounted subtotal and notes', async () => {
    await openInvoice(DISCOUNTED_DETAIL)
    expect(screen.getByText(/Gold Top \(PLA Silk Gold\)/)).toBeInTheDocument()
    expect(screen.getByText('Items total')).toBeInTheDocument()
    expect(screen.getByText('10% discount')).toBeInTheDocument()
    expect(screen.getByText('-$8.51')).toBeInTheDocument()
    expect(screen.getByText('$76.61')).toBeInTheDocument()
    expect(screen.getByText('$81.97')).toBeInTheDocument()
    expect(screen.getByText('Thanks for the order!')).toBeInTheDocument()
  })

  it('keeps the old totals layout for an invoice without a discount label', async () => {
    await openInvoice({ ...DISCOUNTED_DETAIL, discount_label: null, notes: null })
    expect(screen.queryByText('Items total')).not.toBeInTheDocument()
    expect(screen.getByText('Discount')).toBeInTheDocument()
    expect(screen.getAllByText('$85.12').length).toBe(2) // line + subtotal
  })
})
