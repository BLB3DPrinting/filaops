import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach } from 'vitest'

const { mocks } = vi.hoisted(() => ({
  mocks: {
    get: vi.fn(),
    post: vi.fn(),
    del: vi.fn(),
    toastSuccess: vi.fn(),
    toastError: vi.fn(),
  },
}))

vi.mock('../../../hooks/useApi', () => {
  const api = { get: mocks.get, post: mocks.post, del: mocks.del }
  return { useApi: () => api }
})

vi.mock('../../../components/Toast', () => {
  const toast = {
    success: mocks.toastSuccess,
    error: mocks.toastError,
    warning: vi.fn(),
    info: vi.fn(),
  }
  return { useToast: () => toast }
})

import AdminLicense from '../AdminLicense'

beforeEach(() => {
  mocks.get.mockReset()
  mocks.post.mockReset()
  mocks.del.mockReset()
  mocks.toastSuccess.mockReset()
  mocks.toastError.mockReset()
})

describe('AdminLicense', () => {
  it('renders loading spinner while initial license fetch is pending (no header)', () => {
    mocks.get.mockReturnValue(new Promise(() => {}))
    const { container } = render(<AdminLicense />)
    expect(container.querySelector('.animate-spin')).toBeInTheDocument()
    expect(screen.queryByText(/License & PRO Activation/i)).not.toBeInTheDocument()
    expect(screen.queryByLabelText(/License Key/i)).not.toBeInTheDocument()
  })

  it('renders error panel under the header when the initial GET fails', async () => {
    mocks.get.mockRejectedValue(new Error('Internal Server Error'))
    render(<AdminLicense />)
    await waitFor(() => {
      expect(screen.getByText('Internal Server Error')).toBeInTheDocument()
    })
    expect(screen.getByText(/License & PRO Activation/i)).toBeInTheDocument()
    expect(screen.queryByLabelText(/License Key/i)).not.toBeInTheDocument()
  })

  it('renders Community / not-activated state with the activate form visible', async () => {
    mocks.get.mockResolvedValue({
      activated: false,
      tier: 'community',
      features: [],
    })
    render(<AdminLicense />)
    await waitFor(() => {
      expect(screen.getByText('COMMUNITY')).toBeInTheDocument()
    })
    expect(screen.getByText(/Not activated/i)).toBeInTheDocument()
    expect(screen.getByLabelText(/License Key/i)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /^Activate$/i })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Remove license/i })).not.toBeInTheDocument()
  })

  it('renders activated PRO state with features, install id, and no activate form', async () => {
    mocks.get.mockResolvedValue({
      activated: true,
      tier: 'professional',
      license_key: 'FILAOPS-PRO-ABCDEF',
      install_uuid: 'install-uuid-123',
      features: ['portal', 'quotes', 'gl'],
      expires_at: '2027-01-01T00:00:00Z',
      activated_at: '2026-04-01T12:00:00Z',
    })
    render(<AdminLicense />)
    await waitFor(() => {
      expect(screen.getByText('PROFESSIONAL')).toBeInTheDocument()
    })
    expect(screen.getByText('FILAOPS-PRO-ABCDEF')).toBeInTheDocument()
    expect(screen.getByText('install-uuid-123')).toBeInTheDocument()
    expect(screen.getByText(/Enabled Features \(3\)/i)).toBeInTheDocument()
    expect(screen.getByText('portal')).toBeInTheDocument()
    expect(screen.getByText('quotes')).toBeInTheDocument()
    expect(screen.getByText('gl')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Remove license/i })).toBeInTheDocument()
    expect(screen.queryByLabelText(/License Key/i)).not.toBeInTheDocument()
  })

  it('activates a license — submits trimmed key, swaps to PRO state, fires success toast', async () => {
    mocks.get.mockResolvedValue({
      activated: false,
      tier: 'community',
      features: [],
    })
    mocks.post.mockResolvedValue({
      activated: true,
      tier: 'professional',
      license_key: 'FILAOPS-PRO-NEW',
      install_uuid: 'install-uuid-123',
      features: ['portal'],
      activated_at: '2026-05-04T12:00:00Z',
    })

    render(<AdminLicense />)
    await waitFor(() => {
      expect(screen.getByLabelText(/License Key/i)).toBeInTheDocument()
    })

    fireEvent.change(screen.getByLabelText(/License Key/i), {
      target: { value: '  FILAOPS-PRO-NEW  ' },
    })
    fireEvent.click(screen.getByRole('button', { name: /^Activate$/i }))

    await waitFor(() => {
      expect(mocks.post).toHaveBeenCalledWith('/api/v1/system/license/activate', {
        license_key: 'FILAOPS-PRO-NEW',
      })
    })
    await waitFor(() => {
      expect(screen.getByText('PROFESSIONAL')).toBeInTheDocument()
    })
    expect(mocks.toastSuccess).toHaveBeenCalledWith(
      expect.stringContaining('Activated PROFESSIONAL'),
    )
    expect(mocks.toastError).not.toHaveBeenCalled()
  })

  it('shows activation error in role="alert" when POST rejects', async () => {
    mocks.get.mockResolvedValue({
      activated: false,
      tier: 'community',
      features: [],
    })
    mocks.post.mockRejectedValue(new Error('License key not found'))

    render(<AdminLicense />)
    await waitFor(() => {
      expect(screen.getByLabelText(/License Key/i)).toBeInTheDocument()
    })

    fireEvent.change(screen.getByLabelText(/License Key/i), {
      target: { value: 'BAD-KEY' },
    })
    fireEvent.click(screen.getByRole('button', { name: /^Activate$/i }))

    await waitFor(() => {
      const alert = screen.getByRole('alert')
      expect(alert).toHaveTextContent('License key not found')
    })
    expect(mocks.toastSuccess).not.toHaveBeenCalled()
    expect(screen.getByLabelText(/License Key/i)).toBeInTheDocument()
  })

  it('deactivates a license — confirm prompt, DELETE, re-fetch, success toast', async () => {
    mocks.get
      .mockResolvedValueOnce({
        activated: true,
        tier: 'professional',
        license_key: 'FILAOPS-PRO-X',
        install_uuid: 'install-uuid-123',
        features: ['portal'],
      })
      .mockResolvedValueOnce({
        activated: false,
        tier: 'community',
        features: [],
      })
    mocks.del.mockResolvedValue(undefined)

    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(true)
    try {
      render(<AdminLicense />)
      await waitFor(() => {
        expect(screen.getByText('PROFESSIONAL')).toBeInTheDocument()
      })

      fireEvent.click(screen.getByRole('button', { name: /Remove license/i }))

      await waitFor(() => {
        expect(mocks.del).toHaveBeenCalledWith('/api/v1/system/license/')
      })
      await waitFor(() => {
        expect(screen.getByText('COMMUNITY')).toBeInTheDocument()
      })
      expect(confirmSpy).toHaveBeenCalledTimes(1)
      expect(mocks.get).toHaveBeenCalledTimes(2)
      expect(mocks.toastSuccess).toHaveBeenCalledWith(
        expect.stringContaining('License removed locally'),
      )
    } finally {
      confirmSpy.mockRestore()
    }
  })

  it('shows error toast and keeps PRO state when deactivate DELETE rejects', async () => {
    mocks.get.mockResolvedValue({
      activated: true,
      tier: 'professional',
      license_key: 'FILAOPS-PRO-X',
      install_uuid: 'install-uuid-123',
      features: ['portal'],
    })
    mocks.del.mockRejectedValue(new Error('Could not reach the license server'))

    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(true)
    try {
      render(<AdminLicense />)
      await waitFor(() => {
        expect(screen.getByText('PROFESSIONAL')).toBeInTheDocument()
      })

      fireEvent.click(screen.getByRole('button', { name: /Remove license/i }))

      await waitFor(() => {
        expect(mocks.toastError).toHaveBeenCalledWith(
          'Could not reach the license server',
        )
      })
      expect(mocks.del).toHaveBeenCalledWith('/api/v1/system/license/')
      expect(screen.getByText('PROFESSIONAL')).toBeInTheDocument()
      expect(mocks.toastSuccess).not.toHaveBeenCalled()
      expect(mocks.get).toHaveBeenCalledTimes(1)
    } finally {
      confirmSpy.mockRestore()
    }
  })

  it('does not call DELETE when the user cancels the confirm dialog', async () => {
    mocks.get.mockResolvedValue({
      activated: true,
      tier: 'professional',
      license_key: 'FILAOPS-PRO-X',
      install_uuid: 'install-uuid-123',
      features: ['portal'],
    })

    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(false)
    try {
      render(<AdminLicense />)
      await waitFor(() => {
        expect(screen.getByText('PROFESSIONAL')).toBeInTheDocument()
      })

      fireEvent.click(screen.getByRole('button', { name: /Remove license/i }))

      expect(confirmSpy).toHaveBeenCalledTimes(1)
      expect(mocks.del).not.toHaveBeenCalled()
      expect(screen.getByText('PROFESSIONAL')).toBeInTheDocument()
      expect(mocks.toastSuccess).not.toHaveBeenCalled()
      expect(mocks.toastError).not.toHaveBeenCalled()
    } finally {
      confirmSpy.mockRestore()
    }
  })

  it('Header external link to filaops.blb3dprinting.com uses target="_blank" and rel="noopener noreferrer"', async () => {
    mocks.get.mockResolvedValue({
      activated: false,
      tier: 'community',
      features: [],
    })
    render(<AdminLicense />)
    await waitFor(() => {
      expect(screen.getByText(/License & PRO Activation/i)).toBeInTheDocument()
    })

    const link = screen.getByRole('link', { name: /filaops\.blb3dprinting\.com/i })
    expect(link).toHaveAttribute('href', 'https://filaops.blb3dprinting.com/')
    expect(link).toHaveAttribute('target', '_blank')
    expect(link).toHaveAttribute('rel', 'noopener noreferrer')
  })
})
