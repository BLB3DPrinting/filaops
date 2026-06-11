/**
 * Tests for PR-18 additions to the Onboarding wizard:
 *   - Currency / locale selectors on the account step
 *   - Printer step (add + skip paths)
 *   - Step indicator reflects 8 total steps
 */
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { describe, it, expect, vi, beforeEach } from 'vitest'

// ── Hoisted mocks ────────────────────────────────────────────────────────────
const navigateFn = vi.fn()

vi.mock('react-router-dom', async (importOriginal) => {
  const actual = await importOriginal()
  return {
    ...actual,
    useNavigate: () => navigateFn,
  }
})

// Import the component once — mocks are stable after module-level hoisting
import Onboarding from '../Onboarding'

// ── Helpers ──────────────────────────────────────────────────────────────────
const fetchOk = (body = {}) =>
  Promise.resolve({ ok: true, json: async () => body })

const setupFetch = (overrides = {}) => {
  globalThis.fetch = vi.fn((url, opts) => {
    const u = String(url)
    for (const [pattern, handler] of Object.entries(overrides)) {
      if (u.includes(pattern)) {
        if (typeof handler === 'function') return handler(url, opts)
        return Promise.resolve(handler)
      }
    }
    return fetchOk({})
  })
}

/** Render the wizard and wait for the account step. */
async function renderWizard(fetchOverrides = {}) {
  setupFetch({
    '/setup/status': fetchOk({ needs_setup: true }),
    ...fetchOverrides,
  })

  render(
    <MemoryRouter>
      <Onboarding />
    </MemoryRouter>,
  )

  await waitFor(() =>
    expect(screen.getByRole('heading', { name: 'Create Admin Account' })).toBeInTheDocument(),
  )
}

/** Fill and submit the account form with valid data. */
const fillAndSubmitAccount = async () => {
  fireEvent.change(screen.getByPlaceholderText('John Smith'), {
    target: { value: 'Test User', name: 'full_name' },
  })
  fireEvent.change(screen.getByPlaceholderText('you@yourcompany.com'), {
    target: { value: 'test@example.com', name: 'email' },
  })
  const pwInputs = screen.getAllByPlaceholderText('••••••••')
  fireEvent.change(pwInputs[0], { target: { value: 'Abcdefg1!', name: 'password' } })
  fireEvent.change(pwInputs[1], { target: { value: 'Abcdefg1!', name: 'confirmPassword' } })

  fireEvent.click(screen.getByText('Create Account & Continue'))
  await waitFor(() =>
    expect(screen.queryByText('Creating Account...')).not.toBeInTheDocument(),
  )
}

beforeEach(() => {
  navigateFn.mockReset()
})

// ── Tests ────────────────────────────────────────────────────────────────────

describe('Onboarding — step indicator', () => {
  it('shows "Step 1 of 8" on the account step', async () => {
    await renderWizard()
    expect(screen.getByText('Step 1 of 8')).toBeInTheDocument()
  })
})

describe('Onboarding — account step currency/locale', () => {
  it('renders currency and locale selectors with USD / en-US pre-selected', async () => {
    await renderWizard()

    // The currency select shows the USD option label
    expect(screen.getByDisplayValue(/USD/)).toBeInTheDocument()
    // The locale select shows the en-US label
    expect(screen.getByDisplayValue('English (United States)')).toBeInTheDocument()
  })

  it('updates currency when user selects a different option', async () => {
    await renderWizard()

    const currencySelect = screen.getByDisplayValue(/USD/)
    fireEvent.change(currencySelect, { target: { value: 'CAD' } })

    // Label for CAD is "CAD — Canadian Dollar"
    expect(screen.getByDisplayValue(/CAD/)).toBeInTheDocument()
  })

  it('PATCHes company settings with chosen currency + locale after account creation', async () => {
    const patchedBodies = []

    await renderWizard({
      '/setup/initial-admin': fetchOk({ access_token: 'tok-abc', setup_token: 'tok-abc' }),
      '/auth/me': fetchOk({ id: 1, email: 'test@example.com', is_admin: true }),
      '/settings/company': (url, opts) => {
        if (opts?.method === 'PATCH') {
          patchedBodies.push(JSON.parse(opts.body))
        }
        return fetchOk({})
      },
    })

    // Change currency to EUR
    fireEvent.change(screen.getByDisplayValue(/USD/), { target: { value: 'EUR' } })
    // Change locale to fr-FR
    fireEvent.change(screen.getByDisplayValue('English (United States)'), {
      target: { value: 'fr-FR' },
    })

    // Fill required fields
    fireEvent.change(screen.getByPlaceholderText('John Smith'), {
      target: { value: 'Alice', name: 'full_name' },
    })
    fireEvent.change(screen.getByPlaceholderText('you@yourcompany.com'), {
      target: { value: 'alice@example.com', name: 'email' },
    })
    const pwInputs = screen.getAllByPlaceholderText('••••••••')
    fireEvent.change(pwInputs[0], { target: { value: 'Abcdefg1!', name: 'password' } })
    fireEvent.change(pwInputs[1], { target: { value: 'Abcdefg1!', name: 'confirmPassword' } })

    fireEvent.click(screen.getByText('Create Account & Continue'))

    // Wait for the step to advance (account step heading gone)
    await waitFor(() =>
      expect(screen.getByRole('heading', { name: 'Load Example Data' })).toBeInTheDocument(),
    )

    expect(patchedBodies).toHaveLength(1)
    expect(patchedBodies[0]).toMatchObject({ currency_code: 'EUR', locale: 'fr-FR' })
  })
})

describe('Onboarding — printer step navigation', () => {
  /**
   * Navigate from step 1 all the way to step 7 (printer).
   * Steps 2-6 are skipped by interacting with skip controls.
   */
  async function navigateToPrinterStep() {
    await renderWizard({
      '/setup/initial-admin': fetchOk({ access_token: 'tok-xyz', setup_token: 'tok-xyz' }),
      '/auth/me': fetchOk({ id: 1, email: 'test@example.com', is_admin: true }),
      '/settings/company': fetchOk({}),
      '/setup/seed-example-data': fetchOk({
        items_created: 0, materials_created: 0, colors_created: 0, links_created: 0,
      }),
      '/printers/generate-code': fetchOk({ code: 'PRT-001' }),
      '/printers/': (url, opts) => {
        if (opts?.method === 'POST') {
          return fetchOk({ id: 1, code: 'PRT-001', name: 'Test Printer', brand: 'generic', model: 'Ender 3' })
        }
        return fetchOk({})
      },
    })

    // Step 1: fill account form
    fireEvent.change(screen.getByPlaceholderText('John Smith'), {
      target: { value: 'Bob', name: 'full_name' },
    })
    fireEvent.change(screen.getByPlaceholderText('you@yourcompany.com'), {
      target: { value: 'bob@example.com', name: 'email' },
    })
    const pwInputs = screen.getAllByPlaceholderText('••••••••')
    fireEvent.change(pwInputs[0], { target: { value: 'Abcdefg1!', name: 'password' } })
    fireEvent.change(pwInputs[1], { target: { value: 'Abcdefg1!', name: 'confirmPassword' } })
    fireEvent.click(screen.getByText('Create Account & Continue'))

    // Step 2: Skip example data (uncheck → Skip This Step)
    await waitFor(() =>
      expect(screen.getByRole('heading', { name: 'Load Example Data' })).toBeInTheDocument(),
    )
    const checkbox = screen.getByRole('checkbox')
    fireEvent.click(checkbox) // uncheck
    // After unchecking the button text changes to "Skip This Step"
    await waitFor(() =>
      expect(screen.getByRole('button', { name: 'Skip This Step' })).toBeInTheDocument(),
    )
    fireEvent.click(screen.getByRole('button', { name: 'Skip This Step' }))

    // Steps 3-6: no file selected → Skip This Step
    for (const title of [
      'Import Products',
      'Import Customers',
      'Import Orders',
      'Import Inventory (Optional)',
    ]) {
      await waitFor(() =>
        expect(screen.getByRole('heading', { name: title })).toBeInTheDocument(),
      )
      fireEvent.click(screen.getByRole('button', { name: 'Skip This Step' }))
    }

    // Now on printer step
    await waitFor(() =>
      expect(screen.getByRole('heading', { name: 'Connect Your First Printer' })).toBeInTheDocument(),
    )
  }

  it('shows step 7 of 8 on the printer step', async () => {
    await navigateToPrinterStep()
    expect(screen.getByText('Step 7 of 8')).toBeInTheDocument()
  })

  it('Skip button advances directly to the Complete step', async () => {
    await navigateToPrinterStep()
    fireEvent.click(screen.getByText('Skip'))
    await waitFor(() =>
      expect(screen.getByText('Setup Complete!')).toBeInTheDocument(),
    )
    expect(screen.getByText('Step 8 of 8')).toBeInTheDocument()
  })

  it('Add Printer button is disabled when name or model is empty', async () => {
    await navigateToPrinterStep()
    const addBtn = screen.getByRole('button', { name: 'Add Printer' })
    expect(addBtn).toBeDisabled()

    // Fill name only — still disabled (model empty for generic brand)
    fireEvent.change(screen.getByPlaceholderText('X1C Bay 1'), {
      target: { value: 'My Printer' },
    })
    expect(addBtn).toBeDisabled()

    // Fill model — now enabled
    fireEvent.change(screen.getByPlaceholderText('e.g. Ender 3 Pro'), {
      target: { value: 'Ender 3 Pro' },
    })
    expect(addBtn).not.toBeDisabled()
  })

  it('submits the correct minimal payload for a generic printer', async () => {
    await navigateToPrinterStep()

    fireEvent.change(screen.getByPlaceholderText('X1C Bay 1'), {
      target: { value: 'Bay 1' },
    })
    fireEvent.change(screen.getByPlaceholderText('e.g. Ender 3 Pro'), {
      target: { value: 'Ender 3 Pro' },
    })

    fireEvent.click(screen.getByRole('button', { name: 'Add Printer' }))

    await waitFor(() =>
      expect(screen.getByText(/Printer added/)).toBeInTheDocument(),
    )

    const postCall = globalThis.fetch.mock.calls.find(
      ([url, opts]) =>
        String(url).includes('/printers/') && opts?.method === 'POST',
    )
    expect(postCall).toBeDefined()
    const body = JSON.parse(postCall[1].body)
    expect(body.name).toBe('Bay 1')
    expect(body.model).toBe('Ender 3 Pro')
    expect(body.brand).toBe('generic')
    expect(body.code).toBe('PRT-001')
    expect(body.active).toBe(true)
  })

  it('shows success card with Continue button after printer is added', async () => {
    await navigateToPrinterStep()

    fireEvent.change(screen.getByPlaceholderText('X1C Bay 1'), {
      target: { value: 'Bay 1' },
    })
    fireEvent.change(screen.getByPlaceholderText('e.g. Ender 3 Pro'), {
      target: { value: 'Ender 3 Pro' },
    })

    fireEvent.click(screen.getByRole('button', { name: 'Add Printer' }))

    await waitFor(() => expect(screen.getByText(/Printer added/)).toBeInTheDocument())
    expect(screen.getByRole('button', { name: 'Continue' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Skip' })).not.toBeInTheDocument()
  })

  it('Continue after adding a printer leads to the Complete step', async () => {
    await navigateToPrinterStep()

    fireEvent.change(screen.getByPlaceholderText('X1C Bay 1'), {
      target: { value: 'Bay 1' },
    })
    fireEvent.change(screen.getByPlaceholderText('e.g. Ender 3 Pro'), {
      target: { value: 'Ender 3 Pro' },
    })

    fireEvent.click(screen.getByRole('button', { name: 'Add Printer' }))
    await waitFor(() => expect(screen.getByRole('button', { name: 'Continue' })).toBeInTheDocument())
    fireEvent.click(screen.getByRole('button', { name: 'Continue' }))

    await waitFor(() =>
      expect(screen.getByText('Setup Complete!')).toBeInTheDocument(),
    )
  })
})
