import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { describe, it, expect, vi, beforeEach } from 'vitest'

const { mocks } = vi.hoisted(() => ({
  mocks: {
    get: vi.fn(),
    post: vi.fn(),
    del: vi.fn(),
    isPro: true,
  },
}))

vi.mock('../../../hooks/useApi', () => {
  const api = {
    get: mocks.get,
    post: mocks.post,
    patch: vi.fn(),
    del: mocks.del,
  }
  return { useApi: () => api }
})

vi.mock('../../../hooks/useFeatureFlags', () => ({
  useFeatureFlags: () => ({
    tier: mocks.isPro ? 'professional' : 'community',
    features: mocks.isPro ? ['bambu_integration'] : [],
    hasFeature: (feature) => mocks.isPro && feature === 'bambu_integration',
    isPro: mocks.isPro,
    isEnterprise: false,
    loading: false,
  }),
}))

vi.mock('../../../components/Toast', () => ({
  useToast: () => ({
    success: vi.fn(),
    error: vi.fn(),
  }),
}))

import AdminBambuddy from '../AdminBambuddy'

function renderPage() {
  return render(
    <MemoryRouter>
      <AdminBambuddy />
    </MemoryRouter>,
  )
}

beforeEach(() => {
  mocks.get.mockReset()
  mocks.post.mockReset()
  mocks.del.mockReset()
  mocks.isPro = true
})

describe('AdminBambuddy', () => {
  it('lists Bambuddy machines with linked FilaOps printer state', async () => {
    mocks.get.mockImplementation((path) => {
      if (path === '/api/v1/pro/integrations/bambuddy/status') {
        return Promise.resolve({
          connected: true,
          base_url: 'http://127.0.0.1:8080',
          health: 'healthy',
        })
      }
      if (path === '/api/v1/pro/printer-providers/bambuddy/machines') {
        return Promise.resolve([
          {
            provider: 'bambuddy',
            external_id: '7',
            name: 'A1 Farm 07',
            model: 'A1',
            ip_address: '192.168.1.77',
            status: 'idle',
            linked_printer_id: 12,
            linked_printer: {
              id: 12,
              code: 'PRN-A1-07',
              name: 'FilaOps A1 07',
            },
          },
        ])
      }
      return Promise.reject(new Error(`unexpected path ${path}`))
    })

    renderPage()

    const row = await screen.findByText('A1 Farm 07')
    const table = row.closest('table')
    expect(within(table).getByText('PRN-A1-07')).toBeInTheDocument()
    expect(within(table).getByText('FilaOps A1 07')).toBeInTheDocument()
    expect(within(table).getByRole('button', { name: /unlink/i })).toBeInTheDocument()
  })

  it('links an unlinked Bambuddy machine to an existing active FilaOps printer', async () => {
    const user = userEvent.setup()
    let linked = false
    mocks.get.mockImplementation((path) => {
      if (path === '/api/v1/pro/integrations/bambuddy/status') {
        return Promise.resolve({ connected: true, base_url: 'http://127.0.0.1:8080' })
      }
      if (path === '/api/v1/pro/printer-providers/bambuddy/machines') {
        return Promise.resolve([
          {
            provider: 'bambuddy',
            external_id: '7',
            name: 'A1 Farm 07',
            model: 'A1',
            ip_address: '192.168.1.77',
            status: 'idle',
            linked_printer_id: linked ? 12 : null,
            linked_printer: linked
              ? { id: 12, code: 'PRN-A1-07', name: 'FilaOps A1 07' }
              : null,
          },
        ])
      }
      if (path === '/api/v1/printers?active_only=true&page_size=200') {
        return Promise.resolve({
          items: [{ id: 12, code: 'PRN-A1-07', name: 'FilaOps A1 07', model: 'A1' }],
        })
      }
      return Promise.reject(new Error(`unexpected path ${path}`))
    })
    mocks.post.mockImplementation((path) => {
      if (path === '/api/v1/pro/printer-providers/bambuddy/printers/7/link') {
        linked = true
        return Promise.resolve({ external_printer_id: '7', filaops_printer_id: 12 })
      }
      return Promise.reject(new Error(`unexpected path ${path}`))
    })

    renderPage()

    await user.click(await screen.findByRole('button', { name: /link printer/i }))
    await user.selectOptions(await screen.findByLabelText(/filaops printer/i), '12')
    const linkButtons = screen.getAllByRole('button', { name: /link printer/i })
    await user.click(linkButtons[linkButtons.length - 1])

    await waitFor(() => {
      expect(mocks.post).toHaveBeenCalledWith(
        '/api/v1/pro/printer-providers/bambuddy/printers/7/link',
        { filaops_printer_id: 12 },
      )
    })
  })

  it('shows create-printer action when there are no existing FilaOps printers to link', async () => {
    const user = userEvent.setup()
    mocks.get.mockImplementation((path) => {
      if (path === '/api/v1/pro/integrations/bambuddy/status') {
        return Promise.resolve({ connected: true, base_url: 'http://127.0.0.1:8080' })
      }
      if (path === '/api/v1/pro/printer-providers/bambuddy/machines') {
        return Promise.resolve([
          {
            provider: 'bambuddy',
            external_id: '7',
            name: 'A1 Farm 07',
            status: 'idle',
            linked_printer_id: null,
            linked_printer: null,
          },
        ])
      }
      if (path === '/api/v1/printers?active_only=true&page_size=200') {
        return Promise.resolve({ items: [] })
      }
      return Promise.reject(new Error(`unexpected path ${path}`))
    })

    renderPage()

    await user.click(await screen.findByRole('button', { name: /link printer/i }))

    expect(
      await screen.findByText(/Create a FilaOps printer before linking/i),
    ).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /create printer/i })).toHaveAttribute(
      'href',
      '/admin/printers',
    )
  })
})
