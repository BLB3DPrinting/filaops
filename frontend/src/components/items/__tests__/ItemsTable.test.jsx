import { render, screen } from '@testing-library/react'
import { describe, it, expect, vi } from 'vitest'
import ItemsTable from '../ItemsTable'
import { MockLocaleProvider } from '../../../test/mockLocaleProvider'

// Minimal props — only what ItemsTable needs to render currency fields
const item = {
  id: 1,
  sku: 'MAT-001',
  name: 'Test Filament',
  item_type: 'material',
  category_name: 'Plastics',
  standard_cost: '22.00',
  selling_price: '35.00',
  unit: 'G',
  purchase_uom: 'KG',
  material_type_id: null,
  on_hand_qty: 1000,
  allocated_qty: 0,
  available_qty: 1000,
  stocking_policy: 'mrp',
  reorder_point: null,
  active: true,
  needs_reorder: false,
  procurement_type: 'buy',
}

const baseProps = {
  items: [item],
  loading: false,
  selectedItems: new Set(),
  onSelectAll: vi.fn(),
  onSelectItem: vi.fn(),
  isAllSelected: false,
  isIndeterminate: false,
  sortConfig: { key: 'name', direction: 'asc' },
  onSort: vi.fn(),
  editingQtyItem: null,
  editingQtyValue: '',
  onEditingQtyValueChange: vi.fn(),
  adjustmentReason: '',
  adjustingQty: false,
  onStartEditQty: vi.fn(),
  onSaveQtyAdjustment: vi.fn(),
  onCancelEditQty: vi.fn(),
  onShowAdjustmentModal: vi.fn(),
  pagination: { page: 1, pageSize: 25, total: 1 },
  onPageChange: vi.fn(),
  onPageSizeChange: vi.fn(),
  totalPages: 1,
  canGoPrev: false,
  canGoNext: false,
  onEditItem: vi.fn(),
  onEditRouting: vi.fn(),
}

const renderWith = (currency, locale = 'en-US') =>
  render(
    <MockLocaleProvider currency={currency} locale={locale}>
      <ItemsTable {...baseProps} />
    </MockLocaleProvider>
  )

describe('ItemsTable — currency display', () => {
  it('shows $ with USD for standard_cost', () => {
    renderWith('USD')
    expect(screen.getByText('$22.00')).toBeInTheDocument()
  })

  it('shows € instead of $ with EUR for standard_cost', () => {
    renderWith('EUR')
    expect(screen.getByText('€22.00')).toBeInTheDocument()
    expect(screen.queryByText('$22.00')).not.toBeInTheDocument()
  })

  it('shows £ instead of $ with GBP for standard_cost', () => {
    renderWith('GBP')
    expect(screen.getByText('£22.00')).toBeInTheDocument()
    expect(screen.queryByText('$22.00')).not.toBeInTheDocument()
  })

  it('shows $ with USD for selling_price', () => {
    renderWith('USD')
    expect(screen.getByText('$35.00')).toBeInTheDocument()
  })

  it('shows € instead of $ with EUR for selling_price', () => {
    renderWith('EUR')
    expect(screen.getByText('€35.00')).toBeInTheDocument()
    expect(screen.queryByText('$35.00')).not.toBeInTheDocument()
  })
})

describe('ItemsTable — variant inventory rollup (Workstream A)', () => {
  const templateRow = {
    ...item,
    id: 99,
    sku: 'FG-TMPL-X',
    name: 'Zorble Template',
    item_type: 'finished_good',
    material_type_id: null,
    unit: 'EA',
    on_hand_qty: 0,
    available_qty: 0,
    is_template: true,
    variant_count: 3,
    variants_on_hand_qty: 12,
    variants_available_qty: 9,
  }

  const renderTemplate = () =>
    render(
      <MockLocaleProvider currency="USD" locale="en-US">
        <ItemsTable {...baseProps} items={[templateRow]} />
      </MockLocaleProvider>
    )

  it('renders the rollup on-hand value (12) instead of the templates own 0', () => {
    renderTemplate()
    expect(screen.getByText('12')).toBeInTheDocument()
    // Template own-qty is always 0, but the cell should now show the rollup
    expect(screen.queryByText('0', { selector: 'button' })).not.toBeInTheDocument()
  })

  it('renders the rollup available value (9)', () => {
    renderTemplate()
    expect(screen.getByText('9')).toBeInTheDocument()
  })

  it('exposes an accessible aria-label that names the variant count', () => {
    renderTemplate()
    // On-hand rollup indicator
    expect(
      screen.getByLabelText(/on-hand rolled up from 3 variants/i),
    ).toBeInTheDocument()
    // Available rollup indicator
    expect(
      screen.getByLabelText(/available rolled up from 3 variants/i),
    ).toBeInTheDocument()
  })

  it('does not render rollup indicator for non-template rows', () => {
    render(
      <MockLocaleProvider currency="USD" locale="en-US">
        <ItemsTable {...baseProps} />
      </MockLocaleProvider>
    )
    expect(screen.queryByLabelText(/rolled up from/i)).not.toBeInTheDocument()
  })
})
