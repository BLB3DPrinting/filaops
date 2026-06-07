import { render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { describe, it, expect, vi, beforeEach } from 'vitest'

const { mocks } = vi.hoisted(() => {
  const mocks = {
    get: vi.fn(),
    post: vi.fn(),
    patch: vi.fn(),
    del: vi.fn(),
    toastError: vi.fn(),
    toastSuccess: vi.fn(),
    toastInfo: vi.fn(),
  }
  mocks.api = {
    get: mocks.get,
    post: mocks.post,
    patch: mocks.patch,
    del: mocks.del,
  }
  mocks.toast = {
    error: mocks.toastError,
    success: mocks.toastSuccess,
    info: mocks.toastInfo,
  }
  return { mocks }
})

vi.mock('../../../hooks/useApi', () => ({
  useApi: () => mocks.api,
}))

vi.mock('../../../components/Toast', () => ({
  useToast: () => mocks.toast,
}))

import AdminQuotes from '../AdminQuotes'

function renderPage() {
  return render(
    <MemoryRouter>
      <AdminQuotes />
    </MemoryRouter>,
  )
}

beforeEach(() => {
  mocks.get.mockReset()
  mocks.toastError.mockReset()
  mocks.toastSuccess.mockReset()
  mocks.get.mockImplementation((path) => {
    if (path === '/api/v1/quotes/stats') {
      return Promise.resolve({
        total: 3,
        pending: 1,
        approved: 1,
        accepted: 0,
        rejected: 0,
        converted: 1,
        expired: 0,
        total_value: '1250.00',
        pending_value: '500.00',
      })
    }
    if (path.startsWith('/api/v1/quotes?')) {
      return Promise.resolve([])
    }
    return Promise.reject(new Error(`unexpected path ${path}`))
  })
})

describe('AdminQuotes', () => {
  it('labels quote total stats as pipeline value, not revenue', async () => {
    renderPage()

    expect(await screen.findByText('Quote Pipeline')).toBeInTheDocument()
    expect(screen.getByText('$1,250')).toBeInTheDocument()
    expect(screen.getByText('3 quotes, not revenue')).toBeInTheDocument()
    expect(screen.queryByText('Total Value')).not.toBeInTheDocument()

    await waitFor(() => {
      expect(mocks.get).toHaveBeenCalledWith('/api/v1/quotes/stats')
    })
  })
})
