import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach } from 'vitest'

const { mocks } = vi.hoisted(() => ({
  mocks: {
    get: vi.fn(),
    post: vi.fn(),
    del: vi.fn(),
    toastSuccess: vi.fn(),
    toastError: vi.fn(),
    // useFeatureFlags + useProInstaller. Defaults represent "PRO already
    // loaded, no install pending" so existing pre-PR-04 tests pass unchanged
    // (the install section is hidden in that state). Install-flow tests
    // override isPro=false and feed their own installState.
    isPro: true,
    startInstall: vi.fn(),
    resetInstall: vi.fn(),
    installState: {
      state: 'idle',
      progress: '',
      error: null,
      installed_version: null,
      started_at: null,
      completed_at: null,
    },
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

vi.mock('../../../hooks/useFeatureFlags', () => ({
  useFeatureFlags: () => ({
    tier: mocks.isPro ? 'professional' : 'community',
    features: [],
    hasFeature: () => false,
    isPro: mocks.isPro,
    isEnterprise: false,
    loading: false,
  }),
}))

vi.mock('../../../hooks/useProInstaller', () => ({
  useProInstaller: () => ({
    installState: mocks.installState,
    startInstall: mocks.startInstall,
    resetInstall: mocks.resetInstall,
    isPolling: false,
  }),
}))

import AdminLicense from '../AdminLicense'

beforeEach(() => {
  mocks.get.mockReset()
  mocks.post.mockReset()
  mocks.del.mockReset()
  mocks.toastSuccess.mockReset()
  mocks.toastError.mockReset()
  mocks.startInstall.mockReset()
  mocks.resetInstall.mockReset()
  // Reset PRO-install mocks to "PRO loaded, idle" defaults so any test that
  // doesn't explicitly opt into the install flow keeps pre-PR-04 behavior.
  mocks.isPro = true
  mocks.installState = {
    state: 'idle',
    progress: '',
    error: null,
    installed_version: null,
    started_at: null,
    completed_at: null,
  }
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

  // ===========================================================================
  // PR-04 — PRO install flow
  // ===========================================================================
  //
  // The install section appears IFF license is activated AND PRO isn't loaded
  // into the running Python process (license.json says professional, but
  // /system/info still reports community because filaops_pro hasn't been
  // imported yet). After restart, useFeatureFlags().isPro flips true and the
  // section disappears — so these tests pin isPro=false explicitly.

  describe('PRO install section (PR-04)', () => {
    const activatedLicense = {
      activated: true,
      tier: 'professional',
      license_key: 'FILAOPS-PRO-X',
      install_uuid: 'install-uuid-123',
      features: ['portal', 'quotes'],
      activated_at: '2026-05-04T12:00:00Z',
    }

    it('hides the install section when license is not activated', async () => {
      mocks.isPro = false
      mocks.get.mockResolvedValue({
        activated: false,
        tier: 'community',
        features: [],
      })
      render(<AdminLicense />)
      await waitFor(() => {
        expect(screen.getByText('COMMUNITY')).toBeInTheDocument()
      })
      expect(screen.queryByTestId('pro-install-section')).not.toBeInTheDocument()
      expect(screen.queryByRole('button', { name: /Install PRO/i })).not.toBeInTheDocument()
    })

    it('hides the install section when PRO is already loaded into the runtime', async () => {
      // License activated AND isPro=true means PRO is loaded → no install needed
      mocks.isPro = true
      mocks.get.mockResolvedValue(activatedLicense)
      render(<AdminLicense />)
      await waitFor(() => {
        expect(screen.getByText('PROFESSIONAL')).toBeInTheDocument()
      })
      expect(screen.queryByTestId('pro-install-section')).not.toBeInTheDocument()
    })

    it('shows the Install PRO button when activated but PRO not loaded yet', async () => {
      mocks.isPro = false
      mocks.get.mockResolvedValue(activatedLicense)
      render(<AdminLicense />)
      await waitFor(() => {
        expect(screen.getByTestId('pro-install-section')).toBeInTheDocument()
      })
      expect(screen.getByRole('button', { name: /^Install PRO$/i })).toBeInTheDocument()
      expect(screen.getByText(/license is active, but the PRO package isn't loaded/i)).toBeInTheDocument()
    })

    it('clicking Install PRO calls startInstall', async () => {
      mocks.isPro = false
      mocks.get.mockResolvedValue(activatedLicense)
      render(<AdminLicense />)
      await waitFor(() => {
        expect(screen.getByRole('button', { name: /^Install PRO$/i })).toBeInTheDocument()
      })
      fireEvent.click(screen.getByRole('button', { name: /^Install PRO$/i }))
      expect(mocks.startInstall).toHaveBeenCalledTimes(1)
    })

    it('shows download progress with a spinner when state is "downloading"', async () => {
      mocks.isPro = false
      mocks.installState = {
        state: 'downloading',
        progress: 'Downloading PRO package from license server...',
        error: null,
        installed_version: null,
        started_at: '2026-05-04T12:00:00Z',
        completed_at: null,
      }
      mocks.get.mockResolvedValue(activatedLicense)
      render(<AdminLicense />)
      await waitFor(() => {
        expect(screen.getByTestId('pro-install-section')).toBeInTheDocument()
      })
      expect(screen.getByRole('status')).toHaveTextContent(/Downloading PRO package/i)
      expect(screen.queryByRole('button', { name: /^Install PRO$/i })).not.toBeInTheDocument()
    })

    it('shows verifying progress when state is "verifying"', async () => {
      mocks.isPro = false
      mocks.installState = {
        state: 'verifying',
        progress: 'Verifying package integrity...',
        error: null,
        installed_version: null,
        started_at: '2026-05-04T12:00:00Z',
        completed_at: null,
      }
      mocks.get.mockResolvedValue(activatedLicense)
      render(<AdminLicense />)
      await waitFor(() => {
        expect(screen.getByTestId('pro-install-section')).toBeInTheDocument()
      })
      expect(screen.getByRole('status')).toHaveTextContent(/Verifying package integrity/i)
    })

    it('shows installing progress when state is "installing"', async () => {
      mocks.isPro = false
      mocks.installState = {
        state: 'installing',
        progress: 'Installing PRO package...',
        error: null,
        installed_version: null,
        started_at: '2026-05-04T12:00:00Z',
        completed_at: null,
      }
      mocks.get.mockResolvedValue(activatedLicense)
      render(<AdminLicense />)
      await waitFor(() => {
        expect(screen.getByTestId('pro-install-section')).toBeInTheDocument()
      })
      expect(screen.getByRole('status')).toHaveTextContent(/Installing PRO package/i)
    })

    it('shows success message and restart instructions when state is "restart_required"', async () => {
      mocks.isPro = false
      mocks.installState = {
        state: 'restart_required',
        progress: 'PRO installed successfully. Restart Core to activate.',
        error: null,
        installed_version: '1.2.3',
        started_at: '2026-05-04T12:00:00Z',
        completed_at: '2026-05-04T12:00:30Z',
      }
      mocks.get.mockResolvedValue(activatedLicense)
      render(<AdminLicense />)
      await waitFor(() => {
        expect(screen.getByTestId('pro-install-section')).toBeInTheDocument()
      })
      expect(screen.getByText(/PRO installed successfully \(v1\.2\.3\)/i)).toBeInTheDocument()
      expect(screen.getByText(/Restart Core to activate/i)).toBeInTheDocument()
      // Deployment-agnostic restart hints
      expect(screen.getByText(/Docker:/i)).toBeInTheDocument()
      expect(screen.getByText(/systemd:/i)).toBeInTheDocument()
    })

    it('shows error and Retry button when state is "error"', async () => {
      mocks.isPro = false
      mocks.installState = {
        state: 'error',
        progress: 'Installation failed: connection refused',
        error: 'Could not reach the license server: connection refused',
        installed_version: null,
        started_at: '2026-05-04T12:00:00Z',
        completed_at: '2026-05-04T12:00:05Z',
      }
      mocks.get.mockResolvedValue(activatedLicense)
      render(<AdminLicense />)
      await waitFor(() => {
        expect(screen.getByTestId('pro-install-section')).toBeInTheDocument()
      })
      const alert = screen.getByRole('alert')
      expect(alert).toHaveTextContent(/Installation failed/i)
      expect(alert).toHaveTextContent(/connection refused/i)
      expect(screen.getByRole('button', { name: /^Retry$/i })).toBeInTheDocument()
      expect(screen.getByRole('button', { name: /^Dismiss$/i })).toBeInTheDocument()
    })

    it('clicking Retry resets state and triggers a new install', async () => {
      mocks.isPro = false
      mocks.installState = {
        state: 'error',
        progress: 'Installation failed',
        error: 'connection refused',
        installed_version: null,
        started_at: '2026-05-04T12:00:00Z',
        completed_at: '2026-05-04T12:00:05Z',
      }
      mocks.get.mockResolvedValue(activatedLicense)
      render(<AdminLicense />)
      await waitFor(() => {
        expect(screen.getByRole('button', { name: /^Retry$/i })).toBeInTheDocument()
      })
      fireEvent.click(screen.getByRole('button', { name: /^Retry$/i }))
      expect(mocks.resetInstall).toHaveBeenCalledTimes(1)
      expect(mocks.startInstall).toHaveBeenCalledTimes(1)
    })

    it('clicking Dismiss in the error state calls resetInstall but not startInstall', async () => {
      mocks.isPro = false
      mocks.installState = {
        state: 'error',
        progress: 'Installation failed',
        error: 'connection refused',
        installed_version: null,
        started_at: '2026-05-04T12:00:00Z',
        completed_at: '2026-05-04T12:00:05Z',
      }
      mocks.get.mockResolvedValue(activatedLicense)
      render(<AdminLicense />)
      await waitFor(() => {
        expect(screen.getByRole('button', { name: /^Dismiss$/i })).toBeInTheDocument()
      })
      fireEvent.click(screen.getByRole('button', { name: /^Dismiss$/i }))
      expect(mocks.resetInstall).toHaveBeenCalledTimes(1)
      expect(mocks.startInstall).not.toHaveBeenCalled()
    })
  })
})
