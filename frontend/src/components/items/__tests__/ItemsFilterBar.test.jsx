import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import ItemsFilterBar from '../ItemsFilterBar'

const baseProps = {
  filters: { search: '', itemType: 'all', includeVariants: false },
  onFiltersChange: vi.fn(),
  quickFilter: null,
  onQuickFilterChange: vi.fn(),
  stats: {},
}

describe('ItemsFilterBar active filter', () => {
  it('offers Active, Inactive and All and reflects the current value', () => {
    render(<ItemsFilterBar {...baseProps} activeFilter="inactive" onActiveFilterChange={vi.fn()} />)
    const select = screen.getByRole('combobox', { name: 'Status' })
    expect(select).toHaveValue('inactive')
    expect(Array.from(select.options).map((o) => o.value)).toEqual(['active', 'inactive', 'all'])
  })

  it('reports changes', () => {
    const onChange = vi.fn()
    render(<ItemsFilterBar {...baseProps} activeFilter="active" onActiveFilterChange={onChange} />)
    fireEvent.change(screen.getByRole('combobox', { name: 'Status' }), { target: { value: 'all' } })
    expect(onChange).toHaveBeenCalledWith('all')
  })
})
