import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import PurchaseRequestModal from '../PurchaseRequestModal'

const vendors = [{ id: 7, name: 'Filament Co', code: 'FIL' }]

// 500 g of filament short. The server suggests the purchase line: 0.5 KG at
// the per-KG price, the unit receiving can convert.
const filamentLine = {
  component_id: 42,
  component_name: 'PLA Black',
  component_sku: 'MAT-PLA-BLK',
  component_unit: 'G',
  component_cost: 20,
  component_cost_unit: 'KG',
  inventory_available: 0,
  shortage: 500,
  suggested_purchase: { quantity: 0.5, unit: 'KG', unit_cost: 20 },
}

const postedBody = () => {
  const post = global.fetch.mock.calls.find(([, options]) => options?.method === 'POST')
  return JSON.parse(post[1].body)
}

const createOrder = async (line) => {
  render(<PurchaseRequestModal line={line} onClose={vi.fn()} onSuccess={vi.fn()} />)
  await screen.findByRole('option', { name: /Filament Co/ })
  fireEvent.change(screen.getByRole('combobox'), { target: { value: '7' } })
  fireEvent.click(screen.getByRole('button', { name: /Create Purchase Order/ }))
  await waitFor(() => expect(screen.getByText(/Purchase Order Created/)).toBeInTheDocument())
}

describe('PurchaseRequestModal', () => {
  beforeEach(() => {
    global.fetch = vi.fn((url, options) =>
      Promise.resolve({
        ok: true,
        json: () =>
          Promise.resolve(options?.method === 'POST' ? { po_number: 'PO-0001' } : vendors),
      })
    )
  })

  it('orders the suggested quantity in the suggested unit at the suggested cost', async () => {
    await createOrder(filamentLine)

    const [poLine] = postedBody().lines
    expect(poLine.quantity_ordered).toBe(0.5)
    expect(poLine.purchase_unit).toBe('KG')
    expect(poLine.unit_cost).toBe(20)
  })

  it('names the unit beside the quantity and the unit cost', async () => {
    render(<PurchaseRequestModal line={filamentLine} onClose={vi.fn()} onSuccess={vi.fn()} />)
    await screen.findByRole('option', { name: /Filament Co/ })

    expect(screen.getByText(/Quantity to Order \(KG\)/)).toBeInTheDocument()
    expect(screen.getByText(/Unit Cost \(\$ per KG\)/)).toBeInTheDocument()
  })

  it('still shows the shortage in the stock unit', async () => {
    render(<PurchaseRequestModal line={filamentLine} onClose={vi.fn()} onSuccess={vi.fn()} />)
    await screen.findByRole('option', { name: /Filament Co/ })

    expect(screen.getByText(/500\.00 G/)).toBeInTheDocument()
  })

  it('without a suggestion, orders in the stock unit and leaves the cost to be typed', async () => {
    const line = { ...filamentLine, suggested_purchase: null }
    await createOrder(line)

    const [poLine] = postedBody().lines
    expect(poLine.quantity_ordered).toBe(500)
    expect(poLine.purchase_unit).toBe('G')
    expect(poLine.unit_cost).toBe(0)
  })
})
