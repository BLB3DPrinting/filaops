import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach } from 'vitest'

const { mocks } = vi.hoisted(() => ({
  mocks: {
    flags: { tier: 'community', features: [], isPro: false, loading: false },
    post: vi.fn(),
    toastError: vi.fn(),
  },
}))

vi.mock('../../hooks/useApi', () => ({
  useApi: () => ({ post: mocks.post }),
}))

vi.mock('../Toast', () => ({
  useToast: () => ({ error: mocks.toastError, success: vi.fn(), warning: vi.fn(), info: vi.fn() }),
}))

vi.mock('../../hooks/useFeatureFlags', () => ({
  useFeatureFlags: () => mocks.flags,
}))

import LicenseSection from '../LicenseSection'

beforeEach(() => {
  mocks.flags = { tier: 'community', features: [], isPro: false, loading: false }
  mocks.post.mockReset()
  mocks.toastError.mockReset()
})

describe('LicenseSection', () => {
  it('renders loading skeleton while feature flags load', () => {
    mocks.flags = { ...mocks.flags, loading: true }
    render(<LicenseSection />)
    expect(screen.getByText(/Loading license info/i)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Manage Subscription/i })).not.toBeInTheDocument()
    expect(screen.queryByRole('link', { name: /Upgrade to PRO/i })).not.toBeInTheDocument()
  })

  it('renders Community tier with upgrade pitch and pricing link', () => {
    render(<LicenseSection />)
    expect(screen.getByText('Community')).toBeInTheDocument()
    const upgradeLink = screen.getByRole('link', { name: /Upgrade to PRO/i })
    expect(upgradeLink).toHaveAttribute('href', 'https://blb3dprinting.com/pro/pricing/')
    expect(upgradeLink).toHaveAttribute('rel', 'noopener noreferrer')
    expect(screen.getByText(/\$49 \/ month/)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Manage Subscription/i })).not.toBeInTheDocument()
  })

  it('renders Professional tier with feature count badge and Manage button', () => {
    mocks.flags = { tier: 'professional', features: ['portal', 'quotes', 'gl'], isPro: true, loading: false }
    render(<LicenseSection />)
    expect(screen.getByText('Professional')).toBeInTheDocument()
    expect(screen.getByText(/3 features enabled/i)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Manage Subscription/i })).toBeInTheDocument()
    expect(screen.queryByRole('link', { name: /Upgrade to PRO/i })).not.toBeInTheDocument()
  })

  it('renders Enterprise tier and uses singular "feature" copy when count is 1', () => {
    mocks.flags = { tier: 'enterprise', features: ['portal'], isPro: true, loading: false }
    render(<LicenseSection />)
    expect(screen.getByText('Enterprise')).toBeInTheDocument()
    expect(screen.getByText(/1 feature enabled/i)).toBeInTheDocument()
  })

  it('opens the Stripe portal URL in a new tab when Manage Subscription is clicked', async () => {
    mocks.flags = { tier: 'professional', features: ['portal'], isPro: true, loading: false }
    mocks.post.mockResolvedValue({ url: 'https://billing.stripe.com/session/abc' })
    const openSpy = vi.spyOn(window, 'open').mockImplementation(() => null)
    try {
      render(<LicenseSection />)
      fireEvent.click(screen.getByRole('button', { name: /Manage Subscription/i }))
      await waitFor(() => {
        expect(mocks.post).toHaveBeenCalledWith('/api/v1/pro/system/manage-subscription', {
          return_url: window.location.href,
        })
      })
      expect(openSpy).toHaveBeenCalledWith(
        'https://billing.stripe.com/session/abc',
        '_blank',
        'noopener,noreferrer',
      )
      expect(mocks.toastError).not.toHaveBeenCalled()
    } finally {
      openSpy.mockRestore()
    }
  })

  it('shows an error toast when the portal endpoint returns no url', async () => {
    mocks.flags = { tier: 'professional', features: [], isPro: true, loading: false }
    mocks.post.mockResolvedValue({ url: null })
    render(<LicenseSection />)
    fireEvent.click(screen.getByRole('button', { name: /Manage Subscription/i }))
    await waitFor(() => {
      expect(mocks.toastError).toHaveBeenCalledWith('Could not open subscription portal')
    })
  })

  it('shows an error toast when the portal endpoint rejects', async () => {
    mocks.flags = { tier: 'professional', features: [], isPro: true, loading: false }
    mocks.post.mockRejectedValue(new Error('network down'))
    render(<LicenseSection />)
    fireEvent.click(screen.getByRole('button', { name: /Manage Subscription/i }))
    await waitFor(() => {
      expect(mocks.toastError).toHaveBeenCalledWith(expect.stringContaining('network down'))
    })
  })
})
