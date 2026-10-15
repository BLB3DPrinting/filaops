import { render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'

const { mocks } = vi.hoisted(() => ({
  mocks: {
    flags: { tier: 'community', features: [], isPro: false, loading: false, hasFeature: () => false },
    get: vi.fn(() => Promise.resolve({})),
    buyerUrl: null,
  },
}))

vi.mock('../../hooks/useApi', () => ({
  useApi: () => ({ get: mocks.get, post: vi.fn() }),
}))
vi.mock('../../hooks/useFeatureFlags', () => ({
  useFeatureFlags: () => mocks.flags,
}))
vi.mock('../../hooks/useActivityTokenRefresh', () => ({ default: () => {} }))
vi.mock('../../utils/version', () => ({
  getCurrentVersion: () => Promise.resolve('4.3.1'),
  getCurrentVersionSync: () => '4.3.1',
  formatVersion: (v) => `v${v}`,
}))
vi.mock('../../config/api', () => ({ API_URL: '' }))

import AdminLayout from '../AdminLayout'

function jsonResponse(body, status = 200) {
  return Promise.resolve({ ok: status < 400, status, json: () => Promise.resolve(body) })
}

let fetchMock

beforeEach(() => {
  localStorage.setItem(
    'adminUser',
    JSON.stringify({ first_name: 'Ada', last_name: 'Admin', account_type: 'admin' }),
  )
  fetchMock = vi.fn((url) => {
    if (String(url).includes('/pro/portal/admin-link')) {
      return jsonResponse({ url: '/portal/admin/dashboard', mode: 'local', buyer_url: mocks.buyerUrl })
    }
    return jsonResponse({}, 404)
  })
  vi.stubGlobal('fetch', fetchMock)
})

afterEach(() => {
  vi.unstubAllGlobals()
  localStorage.clear()
})

function renderLayout() {
  return render(
    <MemoryRouter initialEntries={['/admin']}>
      <AdminLayout />
    </MemoryRouter>,
  )
}

const adminLinkCalls = () =>
  fetchMock.mock.calls.filter(([url]) => String(url).includes('/pro/portal/admin-link'))

describe('AdminLayout portal links', () => {
  it('on PRO, asks for the admin link once and shows Buyer Portal when a buyer_url comes back', async () => {
    mocks.flags = { ...mocks.flags, tier: 'professional', isPro: true }
    mocks.buyerUrl = 'https://shop.portal.example.test'
    renderLayout()

    expect(await screen.findByRole('button', { name: /Portal Admin/i })).toBeInTheDocument()
    const buyer = await screen.findByRole('link', { name: /Buyer Portal/i })
    expect(buyer).toHaveAttribute('href', 'https://shop.portal.example.test')
    expect(buyer).toHaveAttribute('target', '_blank')
    expect(adminLinkCalls()).toHaveLength(1)
  })

  it('on PRO without a hosted tenant, shows Portal Admin but no Buyer Portal', async () => {
    mocks.flags = { ...mocks.flags, tier: 'professional', isPro: true }
    mocks.buyerUrl = null
    renderLayout()

    expect(await screen.findByRole('button', { name: /Portal Admin/i })).toBeInTheDocument()
    await waitFor(() => expect(adminLinkCalls()).toHaveLength(1))
    expect(screen.queryByRole('link', { name: /Buyer Portal/i })).not.toBeInTheDocument()
  })

  it('on Community, shows neither link and never requests the admin link', async () => {
    mocks.flags = { ...mocks.flags, tier: 'community', isPro: false }
    mocks.buyerUrl = 'https://shop.portal.example.test'
    renderLayout()

    expect(await screen.findByText(/Ada Admin|Ada/)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Portal Admin/i })).not.toBeInTheDocument()
    expect(screen.queryByRole('link', { name: /Buyer Portal/i })).not.toBeInTheDocument()
    expect(adminLinkCalls()).toHaveLength(0)
  })
})
