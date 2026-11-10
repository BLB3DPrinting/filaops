import { render, screen } from '@testing-library/react'
import { describe, it, expect, vi } from 'vitest'
import BOMLinesList from '../BOMLinesList'
import { MockLocaleProvider } from '../../../test/mockLocaleProvider'

const lines = [
  {
    id: 1,
    sequence: 1,
    component_id: 10,
    component_name: 'Steel Widget',
    component_sku: 'SW-001',
    component_unit: 'EA',
    component_cost: '15.50',
    component_cost_unit: 'EA',
    is_material: false,
    quantity: '2.00',
    unit: 'EA',
    line_cost: '31.00',
    has_bom: false,
  },
]

const baseProps = {
  lines,
  editingLine: null,
  setEditingLine: vi.fn(),
  uoms: [],
  onUpdateLine: vi.fn(),
  onDeleteLine: vi.fn(),
}

const renderWith = (currency, locale = 'en-US') =>
  render(
    <MockLocaleProvider currency={currency} locale={locale}>
      <BOMLinesList {...baseProps} />
    </MockLocaleProvider>
  )

describe('BOMLinesList — currency display', () => {
  it('shows $ with USD for component_cost', () => {
    renderWith('USD')
    // component_cost renders as "$15.50/EA"
    expect(screen.getByText(/\$15\.50/)).toBeInTheDocument()
  })

  it('shows € instead of $ with EUR for component_cost', () => {
    renderWith('EUR')
    expect(screen.getByText(/€15\.50/)).toBeInTheDocument()
    expect(screen.queryByText(/\$15\.50/)).not.toBeInTheDocument()
  })

  it('shows £ instead of $ with GBP for component_cost', () => {
    renderWith('GBP')
    expect(screen.getByText(/£15\.50/)).toBeInTheDocument()
    expect(screen.queryByText(/\$15\.50/)).not.toBeInTheDocument()
  })

  it('shows $ with USD for line_cost', () => {
    renderWith('USD')
    expect(screen.getByText('$31.00')).toBeInTheDocument()
  })

  it('shows € instead of $ with EUR for line_cost', () => {
    renderWith('EUR')
    expect(screen.getByText('€31.00')).toBeInTheDocument()
    expect(screen.queryByText('$31.00')).not.toBeInTheDocument()
  })
})

const renderLine = (overrides) =>
  render(
    <MockLocaleProvider currency="USD" locale="en-US">
      <BOMLinesList {...baseProps} lines={[{ ...lines[0], ...overrides }]} />
    </MockLocaleProvider>
  )

describe('BOMLinesList — unit beside the unit cost', () => {
  it('uses the unit the server says the cost is in', () => {
    // A gram-stocked item that is not a material, costed per gram.
    renderLine({
      component_unit: 'G',
      unit: 'G',
      component_cost: '0.02',
      component_cost_unit: 'G',
      is_material: false,
    })
    expect(screen.getByText('$0.02/G')).toBeInTheDocument()
  })

  it('shows a material per KG', () => {
    renderLine({
      component_unit: 'G',
      unit: 'G',
      component_cost: '20.00',
      component_cost_unit: 'KG',
      is_material: true,
    })
    expect(screen.getByText('$20.00/KG')).toBeInTheDocument()
  })

  it('does not label the cost with a line unit it was not converted to', () => {
    // The line is in hours, which cannot be converted; the cost stays per each.
    renderLine({ unit: 'HR', component_unit: 'EA', component_cost_unit: 'EA' })
    expect(screen.getByText('$15.50/EA')).toBeInTheDocument()
  })

  it('shows a line written in boxes per box', () => {
    renderLine({ unit: 'BOX', component_unit: 'EA', component_cost: '24.00', component_cost_unit: 'BOX' })
    expect(screen.getByText('$24.00/BOX')).toBeInTheDocument()
  })
})
