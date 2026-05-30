import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import ItemForm from '../ItemForm'

vi.mock('../Modal', () => ({
  default: ({ isOpen, children }) => (isOpen ? <div role="dialog">{children}</div> : null),
}))

const fetchOk = (body) => ({
  ok: true,
  json: async () => body,
})

const postBody = () => {
  const call = globalThis.fetch.mock.calls.find(
    ([url, options]) => String(url).includes('/api/v1/items') && options?.method === 'POST'
  )
  if (!call) {
    throw new Error('No POST /api/v1/items request was made')
  }
  return JSON.parse(call[1].body)
}

const renderForm = (props = {}) =>
  render(
    <ItemForm
      isOpen
      onClose={vi.fn()}
      onSuccess={vi.fn()}
      {...props}
    />
  )

beforeEach(() => {
  globalThis.fetch = vi.fn((url, options = {}) => {
    if (options.method === 'POST') {
      return Promise.resolve(fetchOk({
        id: 1,
        name: '12x9x4 Corrugated Box',
        item_type: 'packaging',
        weight_oz: '3.20',
        length_in: '12.00',
        width_in: '9.00',
        height_in: '4.00',
      }))
    }
    if (String(url).includes('/api/v1/admin/uom/classes')) {
      return Promise.resolve(fetchOk([]))
    }
    if (String(url).includes('/api/v1/items/categories')) {
      return Promise.resolve(fetchOk([]))
    }
    return Promise.resolve(fetchOk({}))
  })
})

describe('ItemForm packaging physical metadata', () => {
  it('requires weight and dimensions before saving packaging items', async () => {
    renderForm()

    fireEvent.change(screen.getByLabelText(/Name/), {
      target: { value: '12x9x4 Corrugated Box' },
    })
    fireEvent.change(screen.getByLabelText(/Item Type/), {
      target: { value: 'packaging' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Create Item' }))

    expect(await screen.findAllByText('Weight (oz) is required')).toHaveLength(2)
    expect(screen.getAllByText('Length (in) is required')).toHaveLength(2)
    expect(screen.getAllByText('Width (in) is required')).toHaveLength(2)
    expect(screen.getAllByText('Height (in) is required')).toHaveLength(2)
    expect(globalThis.fetch).not.toHaveBeenCalledWith(
      expect.stringContaining('/api/v1/items'),
      expect.objectContaining({ method: 'POST' })
    )
  })

  it('sends packaging weight and dimensions when all fields are filled', async () => {
    const onSuccess = vi.fn()
    renderForm({ onSuccess })

    fireEvent.change(screen.getByLabelText(/Name/), {
      target: { value: '12x9x4 Corrugated Box' },
    })
    fireEvent.change(screen.getByLabelText(/Item Type/), {
      target: { value: 'packaging' },
    })
    fireEvent.change(screen.getByLabelText(/Weight \(oz\)/), {
      target: { value: '3.2' },
    })
    fireEvent.change(screen.getByLabelText(/Length \(in\)/), {
      target: { value: '12' },
    })
    fireEvent.change(screen.getByLabelText(/Width \(in\)/), {
      target: { value: '9' },
    })
    fireEvent.change(screen.getByLabelText(/Height \(in\)/), {
      target: { value: '4' },
    })

    fireEvent.click(screen.getByRole('button', { name: 'Create Item' }))

    await waitFor(() => expect(onSuccess).toHaveBeenCalled())
    expect(postBody()).toMatchObject({
      item_type: 'packaging',
      weight_oz: 3.2,
      length_in: 12,
      width_in: 9,
      height_in: 4,
    })
  })
})
