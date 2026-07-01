import { render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { describe, it, expect, vi, beforeEach } from 'vitest'

const { mocks } = vi.hoisted(() => {
  const mocks = {
    get: vi.fn(),
    post: vi.fn(),
    patch: vi.fn(),
    toastError: vi.fn(),
    toastSuccess: vi.fn(),
    formatCurrency: vi.fn((v) => `$${Number(v).toFixed(2)}`),
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

import AdminShipping from '../AdminShipping'

function renderWithParam(search = '') {
  return render(
    <MemoryRouter initialEntries={[`/admin/shipping${search}`]}>
      <Routes>
        <Route path="/admin/shipping" element={<AdminShipping />} />
      </Routes>
    </MemoryRouter>,
  )
}

beforeEach(() => {
  mocks.get.mockReset()
  // Default: all API calls resolve with empty arrays
  mocks.get.mockImplementation((path) => {
    if (path.includes('shipping-trend')) {
      return Promise.resolve({ data: [], start_date: null, end_date: null })
    }
    if (path.includes('shipped_after')) {
      return Promise.resolve([])
    }
    if (path.includes('production-orders')) {
      return Promise.resolve([])
    }
    // sales-orders ready-to-ship list
    return Promise.resolve([])
  })
})

describe('AdminShipping — deep-link banner', () => {
  it('shows no banner when orderId param is absent', async () => {
    renderWithParam()
    await waitFor(() => expect(mocks.get).toHaveBeenCalled())
    expect(
      screen.queryByText(/isn't in an active shipping stage/),
    ).not.toBeInTheDocument()
  })

  it('shows banner when orderId param is present and order is not in the fetched set', async () => {
    renderWithParam('?orderId=999')
    await waitFor(() =>
      expect(
        screen.getByText(/isn't in an active shipping stage/),
      ).toBeInTheDocument(),
    )
  })

  it('does not show banner when the order IS in the fetched ready-to-ship set', async () => {
    mocks.get.mockImplementation((path) => {
      if (path.includes('shipping-trend')) {
        return Promise.resolve({ data: [], start_date: null, end_date: null })
      }
      if (path.includes('shipped_after')) return Promise.resolve([])
      if (path.includes('production-orders')) return Promise.resolve([])
      // Return the target order in the list
      return Promise.resolve([
        {
          id: 42,
          order_number: 'SO-2026-042',
          product_name: 'Test Product',
          quantity: 1,
          grand_total: 100,
          tracking_number: null,
          status: 'confirmed',
          shipping_address_line1: null,
          shipping_city: null,
        },
      ])
    })

    renderWithParam('?orderId=42')
    await waitFor(() => expect(mocks.get).toHaveBeenCalled())
    // Wait for loading to complete
    await waitFor(() =>
      expect(screen.queryByText('Refresh')).toBeInTheDocument(),
    )
    expect(
      screen.queryByText(/isn't ready to ship yet/),
    ).not.toBeInTheDocument()
  })
})
