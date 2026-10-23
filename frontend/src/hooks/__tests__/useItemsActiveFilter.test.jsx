import { act, renderHook } from '@testing-library/react'
import { MemoryRouter, useLocation } from 'react-router-dom'
import { describe, expect, it } from 'vitest'
import useItemsActiveFilter, { activeFilterToQuery } from '../useItemsActiveFilter'

const setup = (initial = '/admin/items') =>
  renderHook(
    () => ({ filter: useItemsActiveFilter(), location: useLocation() }),
    { wrapper: ({ children }) => <MemoryRouter initialEntries={[initial]}>{children}</MemoryRouter> }
  )

describe('useItemsActiveFilter', () => {
  it('defaults to active with a clean URL', () => {
    const { result } = setup()
    expect(result.current.filter[0]).toBe('active')
    expect(result.current.location.search).toBe('')
  })

  it('reads inactive and all from ?active=', () => {
    expect(setup('/admin/items?active=inactive').result.current.filter[0]).toBe('inactive')
    expect(setup('/admin/items?active=all').result.current.filter[0]).toBe('all')
  })

  it('falls back to active for unknown values', () => {
    expect(setup('/admin/items?active=bogus').result.current.filter[0]).toBe('active')
  })

  it('persists changes in the URL and drops the param for the default', () => {
    const { result } = setup('/admin/items?q=goose')
    act(() => result.current.filter[1]('inactive'))
    expect(result.current.location.search).toBe('?q=goose&active=inactive')
    expect(result.current.filter[0]).toBe('inactive')
    act(() => result.current.filter[1]('active'))
    expect(result.current.location.search).toBe('?q=goose')
  })

  it('maps each state to list query params', () => {
    expect(activeFilterToQuery('active')).toEqual({ active_only: 'true' })
    expect(activeFilterToQuery('inactive')).toEqual({ active: 'false' })
    expect(activeFilterToQuery('all')).toEqual({ active_only: 'false' })
  })
})
