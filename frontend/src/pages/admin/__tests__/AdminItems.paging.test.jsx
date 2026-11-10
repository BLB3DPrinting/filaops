/**
 * AdminItems paging.
 *
 * The Items table has to stay on the page the user moves to. It used to jump
 * back to page 1 about 300 ms after "Next" was clicked, because the search
 * debounce effect re-armed whenever the page changed and reset the page.
 *
 * The page is rendered for real and talks to one fake API that serves 120
 * items. Timers are real: a regression fires its 300 ms timer whatever the
 * machine speed, so waiting longer only makes these checks more reliable.
 */
import { render, screen, waitFor, act, fireEvent } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { MemoryRouter } from 'react-router-dom'
import { MockLocaleProvider } from '../../../test/mockLocaleProvider'

const TOTAL_ITEMS = 120
const PAGE_SIZE = 50
// The page debounces search by 300 ms. Waiting twice that lets any stray timer fire.
const SETTLE_MS = 600
const TEST_TIMEOUT = 15000

const { api, itemRequests } = vi.hoisted(() => ({
  // Every GET /api/v1/items?... the page makes, newest last.
  itemRequests: [],
  api: { get: vi.fn(), post: vi.fn(), patch: vi.fn(), put: vi.fn(), del: vi.fn() },
}))

vi.mock('../../../hooks/useApi', () => ({ useApi: () => api }))
vi.mock('../../../components/Toast', () => ({
  useToast: () => ({ success: vi.fn(), error: vi.fn(), info: vi.fn(), warning: vi.fn() }),
}))

import AdminItems from '../AdminItems'

/** Builds the n-th fake item (SKU-0001, SKU-0002, ...) with the fields the table reads. */
function makeItem(n) {
  return {
    id: n,
    sku: `SKU-${String(n).padStart(4, '0')}`,
    name: `Item ${n}`,
    item_type: 'component',
    category_name: null,
    standard_cost: '1.00',
    selling_price: '2.00',
    unit: 'EA',
    purchase_uom: 'EA',
    material_type_id: null,
    on_hand_qty: 0,
    allocated_qty: 0,
    available_qty: 0,
    stocking_policy: 'on_demand',
    reorder_point: null,
    active: true,
    needs_reorder: false,
    procurement_type: 'buy',
  }
}

const ALL_ITEMS = Array.from({ length: TOTAL_ITEMS }, (_, i) => makeItem(i + 1))

/**
 * Fake `GET /api/v1/items?...`: records the request in `itemRequests` and returns
 * the requested slice of ALL_ITEMS, narrowed by `search` when one is given.
 */
function serveItems(url) {
  const params = new URLSearchParams(url.split('?')[1])
  const offset = Number(params.get('offset') || 0)
  const limit = Number(params.get('limit') || PAGE_SIZE)
  const search = params.get('search') || ''
  itemRequests.push({ offset, limit, search, itemType: params.get('item_type') })

  // The item_type filter is not applied here; these tests only care which page is asked for.
  const needle = search.toLowerCase()
  const matching = needle
    ? ALL_ITEMS.filter((i) => `${i.sku} ${i.name}`.toLowerCase().includes(needle))
    : ALL_ITEMS
  return { items: matching.slice(offset, offset + limit), total: matching.length }
}

/** Lets real timers run for `ms` (inside act), so a stray debounce timer can fire. */
const settle = (ms = SETTLE_MS) => act(() => new Promise((resolve) => setTimeout(resolve, ms)))

/** Renders the real page and waits until page 1 is shown and its timers have settled. */
async function renderItemsPage() {
  render(
    <MemoryRouter>
      <MockLocaleProvider>
        <AdminItems />
      </MockLocaleProvider>
    </MemoryRouter>,
  )
  await screen.findByText('SKU-0001')
  await settle() // let any trailing timer from the first load fire before the test starts
}

/** Clicks Next and checks the table is still on page 2 once the debounce window has passed. */
async function goToPageTwo() {
  fireEvent.click(screen.getByRole('button', { name: 'Next' }))
  await screen.findByText('SKU-0051')
  await settle()
  // Still on page 2 after the debounce window has passed.
  expect(screen.getByText('Page 2 of 3')).toBeInTheDocument()
}

/**
 * Types each value in turn with no pause between them (one debounce window),
 * then waits for the page to react and for any stray timer to fire.
 */
async function typeSearch(values) {
  const before = itemRequests.length
  const box = screen.getByPlaceholderText('Search by SKU, name, or UPC...')
  values.forEach((value) => fireEvent.change(box, { target: { value } }))
  await waitFor(() => expect(itemRequests.length).toBeGreaterThan(before))
  await settle()
}

beforeEach(() => {
  itemRequests.length = 0
  api.get.mockReset()
  api.get.mockImplementation(async (url) => {
    if (url.startsWith('/api/v1/items?')) return serveItems(url)
    if (url.includes('/categories')) return []
    return {}
  })
})

describe('AdminItems paging', () => {
  it('loads the first page once', async () => {
    await renderItemsPage()

    expect(itemRequests).toEqual([{ offset: 0, limit: 50, search: '', itemType: null }])
  }, TEST_TIMEOUT)

  it('stays on page 2 after Next is clicked', async () => {
    await renderItemsPage()
    const before = itemRequests.length

    await goToPageTwo()

    expect(screen.getByText('SKU-0051')).toBeInTheDocument()
    expect(screen.queryByText('SKU-0001')).not.toBeInTheDocument()
    expect(screen.getByText('Page 2 of 3')).toBeInTheDocument()
    // One request for page 2, and nothing sent the page back to offset 0.
    expect(itemRequests.slice(before).map((r) => r.offset)).toEqual([50])
  }, TEST_TIMEOUT)

  it('stays on page 1 after Previous is clicked', async () => {
    await renderItemsPage()
    await goToPageTwo()
    const before = itemRequests.length

    fireEvent.click(screen.getByRole('button', { name: 'Previous' }))
    await screen.findByText('SKU-0001')
    await settle()

    expect(screen.getByText('Page 1 of 3')).toBeInTheDocument()
    expect(itemRequests.slice(before).map((r) => r.offset)).toEqual([0])
  }, TEST_TIMEOUT)

  it('searches once, for the final term, when typing pauses', async () => {
    await renderItemsPage()
    const before = itemRequests.length

    await typeSearch(['I', 'Item'])

    expect(itemRequests.slice(before)).toEqual([
      { offset: 0, limit: 50, search: 'Item', itemType: null },
    ])
  }, TEST_TIMEOUT)

  it('goes back to page 1 with the search term when typed on page 2', async () => {
    await renderItemsPage()
    await goToPageTwo()
    const before = itemRequests.length

    await typeSearch(['I', 'Item'])

    expect(itemRequests.slice(before)).toEqual([
      { offset: 0, limit: 50, search: 'Item', itemType: null },
    ])
    expect(screen.getByText('SKU-0001')).toBeInTheDocument()
    expect(screen.getByText('Page 1 of 3')).toBeInTheDocument()
  }, TEST_TIMEOUT)

  it('keeps the search term when paging through search results', async () => {
    await renderItemsPage()

    // "SKU-00" matches SKU-0001 to SKU-0099 (two pages) and not SKU-0100 to SKU-0120.
    await typeSearch(['SKU-00'])
    expect(screen.getByText('Page 1 of 2')).toBeInTheDocument()
    const before = itemRequests.length

    fireEvent.click(screen.getByRole('button', { name: 'Next' }))
    await screen.findByText('SKU-0099')
    await settle()

    expect(screen.getByText('Page 2 of 2')).toBeInTheDocument()
    // SKU-0100 is on page 2 of the unfiltered list, so it shows only if the term was dropped.
    expect(screen.queryByText('SKU-0100')).not.toBeInTheDocument()
    expect(itemRequests.slice(before)).toEqual([
      { offset: 50, limit: 50, search: 'SKU-00', itemType: null },
    ])
  }, TEST_TIMEOUT)

  it('goes back to page 1 when the page size changes', async () => {
    await renderItemsPage()
    await goToPageTwo()

    fireEvent.change(screen.getByDisplayValue('50 per page'), { target: { value: '25' } })
    await screen.findByText('Page 1 of 5')
    await settle()

    expect(screen.getByText('SKU-0001')).toBeInTheDocument()
    expect(screen.queryByText('SKU-0026')).not.toBeInTheDocument()
    expect(itemRequests.at(-1)).toMatchObject({ offset: 0, limit: 25 })
  }, TEST_TIMEOUT)

  it('goes back to page 1 when the item type filter changes', async () => {
    await renderItemsPage()
    await goToPageTwo()

    fireEvent.change(screen.getByDisplayValue('All Types'), { target: { value: 'finished_good' } })
    await settle()

    expect(itemRequests.at(-1)).toMatchObject({ offset: 0, itemType: 'finished_good' })
    expect(screen.getByText('Page 1 of 3')).toBeInTheDocument()
    expect(screen.getByText('SKU-0001')).toBeInTheDocument()
  }, TEST_TIMEOUT)
})
