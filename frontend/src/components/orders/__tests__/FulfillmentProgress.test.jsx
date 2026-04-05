/**
 * Unit tests for FulfillmentProgress — closedShort prop behavior.
 */
import { render, screen } from '@testing-library/react'
import { describe, it, expect, vi } from 'vitest'
import FulfillmentProgress from '../FulfillmentProgress'

const makeFulfillmentStatus = (state, lines = []) => ({
  summary: {
    state,
    fulfillment_percent: 0,
    lines_ready: 0,
    lines_total: lines.length,
  },
  lines,
})

const shortLine = {
  line_id: 1,
  line_number: 1,
  product_sku: 'FG-TEST-01',
  quantity_remaining: 12,
  shortage: 3,
  is_ready: false,
}

const readyLine = {
  line_id: 2,
  line_number: 2,
  product_sku: 'FG-TEST-02',
  quantity_remaining: 10,
  shortage: 0,
  is_ready: true,
}

describe('FulfillmentProgress — closedShort=false (baseline)', () => {
  it('shows Blocked badge for blocked state', () => {
    render(
      <FulfillmentProgress
        fulfillmentStatus={makeFulfillmentStatus('blocked', [shortLine])}
        loading={false}
        error={null}
        onRefresh={vi.fn()}
        closedShort={false}
      />
    )
    expect(screen.getByText('Blocked')).toBeTruthy()
  })

  it('shows "Short X" label for non-ready lines', () => {
    render(
      <FulfillmentProgress
        fulfillmentStatus={makeFulfillmentStatus('blocked', [shortLine])}
        loading={false}
        error={null}
        onRefresh={vi.fn()}
        closedShort={false}
      />
    )
    expect(screen.getByText('Short 3')).toBeTruthy()
  })
})

describe('FulfillmentProgress — closedShort=true', () => {
  it('shows amber "Closed Short — Ready to Ship" badge when rawState is blocked', () => {
    render(
      <FulfillmentProgress
        fulfillmentStatus={makeFulfillmentStatus('blocked', [shortLine])}
        loading={false}
        error={null}
        onRefresh={vi.fn()}
        closedShort={true}
      />
    )
    expect(screen.getByText('Closed Short — Ready to Ship')).toBeTruthy()
    expect(screen.queryByText('Blocked')).toBeNull()
  })

  it('shows amber "Closed Short — Ready to Ship" badge when rawState is ready_to_ship', () => {
    render(
      <FulfillmentProgress
        fulfillmentStatus={makeFulfillmentStatus('ready_to_ship', [shortLine])}
        loading={false}
        error={null}
        onRefresh={vi.fn()}
        closedShort={true}
      />
    )
    expect(screen.getByText('Closed Short — Ready to Ship')).toBeTruthy()
    expect(screen.queryByText('Ready to Ship')).toBeNull()
  })

  it('shows amber "Closed Short — Ready to Ship" badge when rawState is partially_ready', () => {
    render(
      <FulfillmentProgress
        fulfillmentStatus={makeFulfillmentStatus('partially_ready', [shortLine])}
        loading={false}
        error={null}
        onRefresh={vi.fn()}
        closedShort={true}
      />
    )
    expect(screen.getByText('Closed Short — Ready to Ship')).toBeTruthy()
  })

  it('shows "Short Closed" label (not "Short X") for non-ready lines', () => {
    render(
      <FulfillmentProgress
        fulfillmentStatus={makeFulfillmentStatus('blocked', [shortLine])}
        loading={false}
        error={null}
        onRefresh={vi.fn()}
        closedShort={true}
      />
    )
    expect(screen.getByText('Short Closed')).toBeTruthy()
    expect(screen.queryByText('Short 3')).toBeNull()
  })

  it('keeps "Ready" label for lines that are already ready', () => {
    render(
      <FulfillmentProgress
        fulfillmentStatus={makeFulfillmentStatus('blocked', [readyLine])}
        loading={false}
        error={null}
        onRefresh={vi.fn()}
        closedShort={true}
      />
    )
    expect(screen.getByText('Ready')).toBeTruthy()
  })

  it('does not override terminal state "shipped"', () => {
    render(
      <FulfillmentProgress
        fulfillmentStatus={makeFulfillmentStatus('shipped', [])}
        loading={false}
        error={null}
        onRefresh={vi.fn()}
        closedShort={true}
      />
    )
    expect(screen.getByText('Shipped')).toBeTruthy()
    expect(screen.queryByText('Closed Short — Ready to Ship')).toBeNull()
  })

  it('does not override terminal state "cancelled"', () => {
    render(
      <FulfillmentProgress
        fulfillmentStatus={makeFulfillmentStatus('cancelled', [])}
        loading={false}
        error={null}
        onRefresh={vi.fn()}
        closedShort={true}
      />
    )
    expect(screen.getByText('Cancelled')).toBeTruthy()
    expect(screen.queryByText('Closed Short — Ready to Ship')).toBeNull()
  })
})
