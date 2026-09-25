import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const { mocks } = vi.hoisted(() => ({
  mocks: {
    toastSuccess: vi.fn(),
    toastError: vi.fn(),
  },
}))

vi.mock('../../../components/Toast', () => ({
  useToast: () => ({ success: mocks.toastSuccess, error: mocks.toastError }),
}))

import ForgotPassword from '../ForgotPassword'

function submitEmail(email) {
  fireEvent.change(screen.getByLabelText(/email address/i), { target: { value: email } })
  fireEvent.click(screen.getByRole('button', { name: /submit request/i }))
}

describe('ForgotPassword', () => {
  beforeEach(() => {
    mocks.toastSuccess.mockReset()
    mocks.toastError.mockReset()
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('tells the user an administrator must approve the reset', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      json: vi.fn().mockResolvedValue({
        message: 'If an account exists with this email, a password reset request has been submitted for review.',
      }),
    }))

    render(<MemoryRouter><ForgotPassword /></MemoryRouter>)
    submitEmail('someone@example.com')

    expect(await screen.findByText(/request submitted/i)).toBeInTheDocument()
    expect(screen.getByText(/an administrator must approve the reset/i)).toBeInTheDocument()
    expect(mocks.toastSuccess).toHaveBeenCalledWith('Password reset request submitted')
  })

  it('never renders a reset link, even if a response carries one', async () => {
    // An older backend returned reset_url/reset_token. The page must ignore them.
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      json: vi.fn().mockResolvedValue({
        message: 'ignored',
        reset_url: '/reset-password/leaked-token-value',
        reset_token: 'leaked-token-value',
      }),
    }))

    const { container } = render(<MemoryRouter><ForgotPassword /></MemoryRouter>)
    submitEmail('someone@example.com')

    await waitFor(() => expect(screen.getByText(/request submitted/i)).toBeInTheDocument())
    expect(container.innerHTML).not.toContain('leaked-token-value')
    expect(screen.queryByRole('link', { name: /reset my password/i })).not.toBeInTheDocument()
    const hrefs = Array.from(container.querySelectorAll('a')).map((a) => a.getAttribute('href'))
    expect(hrefs.some((href) => href && href.includes('/reset-password'))).toBe(false)
  })
})
