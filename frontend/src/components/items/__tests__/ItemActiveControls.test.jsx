import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import ItemActiveControls from '../ItemActiveControls'

const item = { id: 7, sku: 'GOOSE-1', active: true }

beforeEach(() => {
  globalThis.fetch = vi.fn()
})

describe('ItemActiveControls', () => {
  it('deactivates after confirmation, tolerating an empty body', async () => {
    globalThis.fetch.mockResolvedValue({ ok: true, status: 204, json: async () => { throw new Error('no body') } })
    const onChanged = vi.fn()
    render(<ItemActiveControls item={item} onChanged={onChanged} />)

    fireEvent.click(screen.getByRole('button', { name: 'Deactivate' }))
    expect(globalThis.fetch).not.toHaveBeenCalled()
    fireEvent.click(screen.getAllByRole('button', { name: 'Deactivate' }).at(-1))

    await waitFor(() => expect(onChanged).toHaveBeenCalledWith({ ...item, active: false }))
    const [url, opts] = globalThis.fetch.mock.calls[0]
    expect(url).toContain('/api/v1/items/7')
    expect(opts.method).toBe('DELETE')
  })

  it('shows the server reason when deactivation is refused', async () => {
    globalThis.fetch.mockResolvedValue({
      ok: false,
      json: async () => ({ detail: 'Cannot delete item with 3 units on hand' }),
    })
    const onChanged = vi.fn()
    render(<ItemActiveControls item={item} onChanged={onChanged} />)
    fireEvent.click(screen.getByRole('button', { name: 'Deactivate' }))
    fireEvent.click(screen.getAllByRole('button', { name: 'Deactivate' }).at(-1))

    expect(await screen.findByRole('alert')).toHaveTextContent('3 units on hand')
    expect(onChanged).not.toHaveBeenCalled()
  })

  it('cancel makes no request', () => {
    render(<ItemActiveControls item={item} onChanged={vi.fn()} />)
    fireEvent.click(screen.getByRole('button', { name: 'Deactivate' }))
    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }))
    expect(globalThis.fetch).not.toHaveBeenCalled()
  })

  it('shows inactive state and reactivates via PATCH active:true', async () => {
    globalThis.fetch.mockResolvedValue({ ok: true, json: async () => ({}) })
    const onChanged = vi.fn()
    const inactive = { ...item, active: false }
    render(<ItemActiveControls item={inactive} onChanged={onChanged} />)

    expect(screen.getByRole('status')).toHaveTextContent('Inactive')
    expect(screen.queryByRole('button', { name: 'Deactivate' })).toBeNull()
    fireEvent.click(screen.getByRole('button', { name: 'Reactivate' }))

    await waitFor(() => expect(onChanged).toHaveBeenCalledWith({ ...inactive, active: true }))
    const [, opts] = globalThis.fetch.mock.calls[0]
    expect(opts.method).toBe('PATCH')
    expect(JSON.parse(opts.body)).toEqual({ active: true })
  })

  it('renders nothing without a saved item', () => {
    const { container } = render(<ItemActiveControls item={null} onChanged={vi.fn()} />)
    expect(container).toBeEmptyDOMElement()
  })
})
