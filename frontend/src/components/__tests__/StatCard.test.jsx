import { render, screen, fireEvent } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { describe, it, expect, vi } from 'vitest'
import StatCard from '../StatCard'

function renderWithRouter(ui) {
  return render(<MemoryRouter>{ui}</MemoryRouter>)
}

describe('StatCard', () => {
  it('renders title and value', () => {
    renderWithRouter(<StatCard title="Total Orders" value={42} />)
    expect(screen.getByText('Total Orders')).toBeInTheDocument()
    expect(screen.getByText('42')).toBeInTheDocument()
  })

  it('renders subtitle when provided', () => {
    renderWithRouter(
      <StatCard title="Revenue" value="$1,200" subtitle="Last 30 days" />
    )
    expect(screen.getByText('Last 30 days')).toBeInTheDocument()
  })

  it('does not render subtitle when not provided', () => {
    renderWithRouter(<StatCard title="Count" value={5} />)
    // Title and value only
    expect(screen.getByText('Count')).toBeInTheDocument()
    expect(screen.getByText('5')).toBeInTheDocument()
  })

  it('renders as a link when "to" prop is provided', () => {
    renderWithRouter(<StatCard title="Orders" value={10} to="/orders" />)
    const link = screen.getByText('Orders').closest('a')
    expect(link).toBeInTheDocument()
    expect(link).toHaveAttribute('href', '/orders')
  })

  it('calls onClick handler when clicked', () => {
    const handleClick = vi.fn()
    renderWithRouter(
      <StatCard title="Active" value={3} variant="simple" onClick={handleClick} />
    )
    // The card with onClick should have role="button"
    const button = screen.getByRole('button')
    fireEvent.click(button)
    expect(handleClick).toHaveBeenCalledTimes(1)
  })

  it('renders simple variant with colored value text', () => {
    renderWithRouter(
      <StatCard title="Errors" value={7} color="danger" variant="simple" />
    )
    const value = screen.getByText('7')
    expect(value.className).toContain('text-status-red')
  })

  it('renders the dashboard (gradient) size by default', () => {
    const { container } = renderWithRouter(
      <StatCard title="Items" value={100} color="primary" />
    )
    // The gradient wash is retired (#846); the default variant is the larger p-6 tile
    const card = container.querySelector('.p-6')
    expect(card).toBeInTheDocument()
  })

  it('shows loading skeleton when loading is true', () => {
    const { container } = renderWithRouter(
      <StatCard title="Loading" value={0} loading={true} />
    )
    // Loading state should show skeleton pulse elements
    const pulses = container.querySelectorAll('.animate-pulse')
    expect(pulses.length).toBeGreaterThan(0)
    // Title and value text should NOT be rendered during loading
    expect(screen.queryByText('Loading')).not.toBeInTheDocument()
  })

  it('does not render icon when loading', () => {
    const icon = <span data-testid="test-icon">Icon</span>
    renderWithRouter(
      <StatCard title="Test" value={0} icon={icon} loading={true} />
    )
    expect(screen.queryByTestId('test-icon')).not.toBeInTheDocument()
  })

  it('renders icon when provided and not loading', () => {
    const icon = <span data-testid="test-icon">Icon</span>
    renderWithRouter(
      <StatCard title="Test" value={0} icon={icon} />
    )
    expect(screen.getByTestId('test-icon')).toBeInTheDocument()
  })
})
