/**
 * ItemForm, edit mode: saving an item must not change a field the user did not touch.
 *
 * The Items page opens the form with a row of GET /api/v1/items. That row has no
 * weight or dimensions (and rescales the reorder point of material items), so the
 * form used to send weight_oz, length_in, width_in and height_in as null on every
 * save and wipe what was stored. The form now loads the full item
 * (GET /api/v1/items/{id}) before it can be edited or saved.
 *
 * Both fixtures below mirror the real API: the row has exactly the keys the list
 * builder returns, and the detail has what ItemResponse returns, including its
 * quirks (stocking_policy is always "on_demand", there is no image_url).
 */
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import ItemForm from '../ItemForm'

vi.mock('../Modal', () => ({
  default: ({ isOpen, children }) => (isOpen ? <div role="dialog">{children}</div> : null),
}))

const ok = (body) => ({ ok: true, status: 200, json: async () => body })
const failed = (status = 500) => ({ ok: false, status, json: async () => ({ detail: 'boom' }) })

/** One row of GET /api/v1/items, no weight or dimensions. */
const listRow = (overrides = {}) => ({
  id: 7,
  sku: 'COMP-001',
  name: 'Bracket',
  item_type: 'component',
  procurement_type: 'buy',
  category_id: null,
  category_name: null,
  unit: 'EA',
  standard_cost: '0.0200',
  average_cost: '0.0200',
  selling_price: null,
  active: true,
  on_hand_qty: 0,
  available_qty: 0,
  reorder_point: null,
  stocking_policy: 'on_demand',
  needs_reorder: false,
  description: null,
  image_url: null,
  has_bom: false,
  has_routing: false,
  parent_product_id: null,
  is_template: false,
  variant_count: 0,
  ...overrides,
})

/** GET /api/v1/items/7 for the same item. Note: no image_url, stocking_policy always on_demand. */
const detail = (overrides = {}) => ({
  id: 7,
  sku: 'COMP-001',
  name: 'Bracket',
  description: null,
  unit: 'EA',
  purchase_uom: 'EA',
  item_type: 'component',
  procurement_type: 'buy',
  category_id: null,
  cost_method: 'average',
  standard_cost: '0.0200',
  selling_price: null,
  weight_oz: '3.20',
  length_in: '12.00',
  width_in: '9.00',
  height_in: '4.00',
  reorder_point: null,
  stocking_policy: 'on_demand',
  active: true,
  ...overrides,
})

/** Route fetch like the backend would. `item` is the detail response, a function, or a status. */
const installFetch = ({ item = detail() } = {}) => {
  globalThis.fetch = vi.fn((url, options = {}) => {
    const path = String(url).replace(/^.*\/api/, '/api')
    if (options.method === 'PATCH') return Promise.resolve(ok({ id: 7 }))
    if (path.startsWith('/api/v1/admin/uom/classes')) return Promise.resolve(ok([]))
    if (path.startsWith('/api/v1/items/categories')) return Promise.resolve(ok([]))
    if (path === '/api/v1/items/7') {
      return Promise.resolve(typeof item === 'function' ? item() : ok(item))
    }
    return Promise.resolve(ok({}))
  })
}

/** Every PATCH the form has sent. */
const patchCalls = () =>
  globalThis.fetch.mock.calls.filter(([, options]) => options?.method === 'PATCH')

/** The parsed body of the first PATCH; throws if none was sent. */
const patchBody = () => {
  const calls = patchCalls()
  if (calls.length === 0) throw new Error('No PATCH request was made')
  return JSON.parse(calls[0][1].body)
}

/** Every GET of /api/v1/items/7 the form has made. */
const detailRequests = () =>
  globalThis.fetch.mock.calls.filter(
    ([url, options]) =>
      String(url).endsWith('/api/v1/items/7') && (options?.method ?? 'GET') === 'GET'
  )

/** Render the form open for editing the given list row. */
const renderForm = (row = listRow()) =>
  render(<ItemForm isOpen onClose={vi.fn()} onSuccess={vi.fn()} editingItem={row} />)

/** The form is usable once the loaded weight is in its field. */
const waitForLoadedForm = async () => {
  const weight = await screen.findByLabelText(/Weight \(oz\)/)
  await waitFor(() => expect(weight).toHaveValue(3.2))
}

beforeEach(() => {
  installFetch()
})

describe('ItemForm edit: weight and dimensions', () => {
  it('opens with the weight and dimensions stored on the item', async () => {
    renderForm()
    await waitForLoadedForm()

    expect(screen.getByLabelText(/Length \(in\)/)).toHaveValue(12)
    expect(screen.getByLabelText(/Width \(in\)/)).toHaveValue(9)
    expect(screen.getByLabelText(/Height \(in\)/)).toHaveValue(4)
  })

  it('sends the stored weight and dimensions back unchanged when only the standard cost is edited', async () => {
    renderForm()
    await waitForLoadedForm()

    fireEvent.change(screen.getByLabelText(/Standard Cost/), { target: { value: '20.00' } })
    fireEvent.click(screen.getByRole('button', { name: 'Update Item' }))

    await waitFor(() => expect(patchCalls()).toHaveLength(1))
    expect(patchBody()).toMatchObject({
      standard_cost: 20,
      weight_oz: 3.2,
      length_in: 12,
      width_in: 9,
      height_in: 4,
    })
  })

  it('sends null for a dimension the user clears on purpose and keeps the rest', async () => {
    renderForm()
    await waitForLoadedForm()

    fireEvent.change(screen.getByLabelText(/Width \(in\)/), { target: { value: '' } })
    fireEvent.click(screen.getByRole('button', { name: 'Update Item' }))

    await waitFor(() => expect(patchCalls()).toHaveLength(1))
    expect(patchBody()).toMatchObject({
      weight_oz: 3.2,
      length_in: 12,
      width_in: null,
      height_in: 4,
    })
  })

  it('saves a packaging item without asking for its weight and dimensions again', async () => {
    installFetch({ item: detail({ item_type: 'packaging' }) })
    renderForm(listRow({ item_type: 'packaging' }))
    await waitForLoadedForm()

    fireEvent.click(screen.getByRole('button', { name: 'Update Item' }))

    await waitFor(() => expect(patchCalls()).toHaveLength(1))
    expect(screen.queryByText(/is required/)).not.toBeInTheDocument()
    expect(patchBody()).toMatchObject({
      item_type: 'packaging',
      weight_oz: 3.2,
      length_in: 12,
      width_in: 9,
      height_in: 4,
    })
  })
})

describe('ItemForm edit: fields the list row already carries', () => {
  it('keeps the stocking policy and image from the row, not the detail defaults', async () => {
    installFetch({ item: detail({ stocking_policy: 'on_demand', reorder_point: '25.00' }) })
    renderForm(
      listRow({
        stocking_policy: 'stocked',
        reorder_point: 25,
        image_url: '/uploads/products/bracket.png',
      })
    )
    await waitForLoadedForm()

    fireEvent.click(screen.getByRole('button', { name: 'Update Item' }))

    await waitFor(() => expect(patchCalls()).toHaveLength(1))
    expect(patchBody()).toMatchObject({
      stocking_policy: 'stocked',
      reorder_point: 25,
      image_url: '/uploads/products/bracket.png',
    })
  })

  it("shows and saves a stocked material's reorder point as stored, not as the list rescales it", async () => {
    // The list reports material reorder points in grams (stored kg x 1000).
    installFetch({ item: detail({ item_type: 'material', unit: 'G', reorder_point: '5.00' }) })
    renderForm(
      listRow({ item_type: 'material', unit: 'G', stocking_policy: 'stocked', reorder_point: 5000 })
    )
    await waitForLoadedForm()

    const reorder = screen.getByLabelText(/Reorder Point/)
    await waitFor(() => expect(reorder).toHaveValue(5))

    fireEvent.click(screen.getByRole('button', { name: 'Update Item' }))

    await waitFor(() => expect(patchCalls()).toHaveLength(1))
    expect(patchBody().reorder_point).toBe(5)
  })
})

describe('ItemForm edit: loading the item', () => {
  it('shows no editable form and cannot save while the item is still loading', async () => {
    let release
    installFetch({
      item: () =>
        new Promise((resolve) => {
          release = () => resolve(ok(detail()))
        }),
    })
    renderForm()

    expect(await screen.findByRole('status')).toHaveTextContent(/loading/i)
    expect(screen.queryByRole('button', { name: 'Update Item' })).not.toBeInTheDocument()
    expect(patchCalls()).toHaveLength(0)

    release()
    await waitForLoadedForm()
    expect(screen.getByRole('button', { name: 'Update Item' })).toBeEnabled()
  })

  it('cannot save when the item fails to load, and loads it on retry', async () => {
    let attempts = 0
    installFetch({
      item: () => {
        attempts += 1
        return Promise.resolve(attempts === 1 ? failed(500) : ok(detail()))
      },
    })
    renderForm()

    expect(await screen.findByRole('alert')).toHaveTextContent(/could not load/i)
    expect(screen.queryByRole('button', { name: 'Update Item' })).not.toBeInTheDocument()
    expect(patchCalls()).toHaveLength(0)

    fireEvent.click(screen.getByRole('button', { name: /try again/i }))

    await waitForLoadedForm()
    expect(detailRequests()).toHaveLength(2)
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })

  it('does not fetch an item when creating a new one', async () => {
    render(<ItemForm isOpen onClose={vi.fn()} onSuccess={vi.fn()} />)

    expect(await screen.findByRole('button', { name: 'Create Item' })).toBeEnabled()
    expect(detailRequests()).toHaveLength(0)
  })
})
