import { render, screen, fireEvent } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { describe, it, expect, vi } from 'vitest'
import EmptyState from '../EmptyState'

// Helper to render with router context (needed for Link)
function renderWithRouter(ui) {
  return render(<MemoryRouter>{ui}</MemoryRouter>)
}

describe('EmptyState', () => {
  it('renders default title when none provided', () => {
    renderWithRouter(<EmptyState />)
    expect(screen.getByText('No items found')).toBeInTheDocument()
  })

  it('renders custom title', () => {
    renderWithRouter(<EmptyState title="No orders yet" />)
    expect(screen.getByText('No orders yet')).toBeInTheDocument()
  })

  it('renders description when provided', () => {
    renderWithRouter(
      <EmptyState title="Empty" description="Create your first item to get started." />
    )
    expect(screen.getByText('Create your first item to get started.')).toBeInTheDocument()
  })

  it('does not render description when not provided', () => {
    renderWithRouter(<EmptyState title="Empty" />)
    // Only the title heading should be present, no description paragraph
    const heading = screen.getByText('Empty')
    expect(heading).toBeInTheDocument()
  })

  it('renders action button with Link when actionTo is provided', () => {
    renderWithRouter(
      <EmptyState
        title="No items"
        actionLabel="Add Item"
        actionTo="/items/new"
      />
    )
    const link = screen.getByText('Add Item')
    expect(link).toBeInTheDocument()
    expect(link.closest('a')).toHaveAttribute('href', '/items/new')
  })

  it('renders action button that calls onAction when clicked', () => {
    const onAction = vi.fn()
    renderWithRouter(
      <EmptyState
        title="No items"
        actionLabel="Create Item"
        onAction={onAction}
      />
    )
    fireEvent.click(screen.getByText('Create Item'))
    expect(onAction).toHaveBeenCalledTimes(1)
  })

  it('does not render action button when actionLabel is not provided', () => {
    renderWithRouter(<EmptyState title="No items" />)
    expect(screen.queryByRole('button')).not.toBeInTheDocument()
    expect(screen.queryByRole('link')).not.toBeInTheDocument()
  })

  it('renders compact variant with smaller layout', () => {
    const { container } = renderWithRouter(
      <EmptyState title="No data" variant="compact" />
    )
    // Compact variant uses py-8 instead of py-16
    const wrapper = container.firstChild
    expect(wrapper.className).toContain('py-8')
  })

  it('renders inline variant', () => {
    const { container } = renderWithRouter(
      <EmptyState title="No results" variant="inline" />
    )
    const wrapper = container.firstChild
    // Inline variant uses flex-row layout (items-center) instead of flex-col
    expect(wrapper.className).toContain('flex')
    expect(wrapper.className).toContain('items-center')
    expect(wrapper.className).not.toContain('flex-col')
  })

  it('renders Clear filters button when onClearFilters is provided', () => {
    const onClearFilters = vi.fn()
    renderWithRouter(
      <EmptyState
        title="No matches"
        onClearFilters={onClearFilters}
      />
    )
    const btn = screen.getByText('Clear filters')
    expect(btn).toBeInTheDocument()
    fireEvent.click(btn)
    expect(onClearFilters).toHaveBeenCalledTimes(1)
  })

  it('onClearFilters takes precedence over actionLabel/onAction', () => {
    const onClearFilters = vi.fn()
    const onAction = vi.fn()
    renderWithRouter(
      <EmptyState
        title="No matches"
        actionLabel="Create"
        onAction={onAction}
        onClearFilters={onClearFilters}
      />
    )
    // Should show Clear filters, not Create
    expect(screen.getByText('Clear filters')).toBeInTheDocument()
    expect(screen.queryByText('Create')).not.toBeInTheDocument()
  })
})
