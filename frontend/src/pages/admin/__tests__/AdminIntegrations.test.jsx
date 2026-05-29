import { render, screen, waitFor, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { describe, it, expect, vi, beforeEach } from 'vitest'

const { mocks } = vi.hoisted(() => ({
  mocks: {
    get: vi.fn(),
    isPro: true,
    features: ['bambu_integration'],
  },
}))

vi.mock('../../../hooks/useApi', () => {
  const api = { get: mocks.get, post: vi.fn(), patch: vi.fn(), del: vi.fn() }
  return { useApi: () => api }
})

// Stub AiSettingsSection — its internals (provider selector, API key input,
// save/test buttons) are exercised by its own tests. AdminIntegrations only
// cares that the section is rendered inside the AI IntegrationCard.
vi.mock('../../../components/settings/AiSettingsSection', () => ({
  default: () => (
    <div data-testid="ai-settings-section-stub">AI Settings Section</div>
  ),
}))

vi.mock('../../../hooks/useFeatureFlags', () => ({
  useFeatureFlags: () => ({
    tier: mocks.isPro ? 'professional' : 'community',
    features: mocks.features,
    hasFeature: (feature) => mocks.features.includes(feature),
    isPro: mocks.isPro,
    isEnterprise: false,
    loading: false,
  }),
}))

import AdminIntegrations, { IntegrationCard } from '../AdminIntegrations'

function renderIntegrations() {
  return render(
    <MemoryRouter>
      <AdminIntegrations />
    </MemoryRouter>,
  )
}

beforeEach(() => {
  mocks.get.mockReset()
  mocks.isPro = true
  mocks.features = ['bambu_integration']
})

describe('AdminIntegrations', () => {
  it('renders header and all three integration cards', async () => {
    mocks.get.mockResolvedValue({ ai_provider: null, ai_api_key_set: false })
    renderIntegrations()

    await waitFor(() => {
      expect(screen.getByText(/Integrations & Connections/i)).toBeInTheDocument()
    })

    expect(screen.getByTestId('integration-card-ai')).toBeInTheDocument()
    expect(screen.getByTestId('integration-card-shopify')).toBeInTheDocument()
    expect(screen.getByTestId('integration-card-qbo')).toBeInTheDocument()
  })

  it('AI card embeds the AiSettingsSection', async () => {
    mocks.get.mockResolvedValue({ ai_provider: null, ai_api_key_set: false })
    renderIntegrations()

    const aiCard = await screen.findByTestId('integration-card-ai')
    expect(
      within(aiCard).getByTestId('ai-settings-section-stub'),
    ).toBeInTheDocument()
  })

  it('AI card status reads "Configured" when ai_api_key_set is true', async () => {
    mocks.get.mockResolvedValue({
      ai_provider: 'anthropic',
      ai_api_key_set: true,
      ai_status: 'configured',
    })
    renderIntegrations()

    const aiCard = await screen.findByTestId('integration-card-ai')
    await waitFor(() => {
      expect(within(aiCard).getByText('Configured')).toBeInTheDocument()
    })
  })

  it('AI card status reads "Not configured" when no provider/key is set', async () => {
    mocks.get.mockResolvedValue({
      ai_provider: null,
      ai_api_key_set: false,
      ai_status: 'not_configured',
    })
    renderIntegrations()

    const aiCard = await screen.findByTestId('integration-card-ai')
    await waitFor(() => {
      expect(within(aiCard).getByText('Not configured')).toBeInTheDocument()
    })
  })

  it('AI card status reads "Error" when backend reports ai_status=error', async () => {
    mocks.get.mockResolvedValue({
      ai_provider: 'anthropic',
      ai_api_key_set: true,
      ai_status: 'error',
    })
    renderIntegrations()

    const aiCard = await screen.findByTestId('integration-card-ai')
    await waitFor(() => {
      expect(within(aiCard).getByText('Error')).toBeInTheDocument()
    })
  })

  it('AI card surfaces "Error" badge when the GET fails (not silently "not configured")', async () => {
    // Suppress the deliberate console.error from the catch block so the test
    // log stays clean — we still assert the error was logged below.
    const errSpy = vi.spyOn(console, 'error').mockImplementation(() => {})
    mocks.get.mockRejectedValue(new Error('boom'))
    renderIntegrations()

    const aiCard = await screen.findByTestId('integration-card-ai')
    await waitFor(() => {
      expect(within(aiCard).getByText('Error')).toBeInTheDocument()
    })
    expect(within(aiCard).queryByText('Not configured')).not.toBeInTheDocument()
    expect(errSpy).toHaveBeenCalled()
    errSpy.mockRestore()
  })

  it('Shopify card renders coming-soon placeholder with feature bullets', async () => {
    mocks.get.mockResolvedValue({ ai_provider: null, ai_api_key_set: false })
    renderIntegrations()

    const shopifyCard = await screen.findByTestId('integration-card-shopify')
    expect(within(shopifyCard).getByText('Shopify')).toBeInTheDocument()
    expect(
      within(shopifyCard).getByText(/Coming in a future update/i),
    ).toBeInTheDocument()
    expect(
      within(shopifyCard).getByText(/Pull paid Shopify orders/i),
    ).toBeInTheDocument()
    expect(within(shopifyCard).getByText('Not configured')).toBeInTheDocument()
  })

  it('QuickBooks card renders coming-soon placeholder with feature bullets', async () => {
    mocks.get.mockResolvedValue({ ai_provider: null, ai_api_key_set: false })
    renderIntegrations()

    const qboCard = await screen.findByTestId('integration-card-qbo')
    expect(within(qboCard).getByText('QuickBooks Online')).toBeInTheDocument()
    expect(
      within(qboCard).getByText(/Coming in a future update/i),
    ).toBeInTheDocument()
    expect(
      within(qboCard).getByText(/Push FilaOps invoices to QuickBooks/i),
    ).toBeInTheDocument()
    expect(within(qboCard).getByText('Not configured')).toBeInTheDocument()
  })

  it('only fires one GET on mount (no fetch storm from re-renders)', async () => {
    mocks.isPro = false
    mocks.features = []
    mocks.get.mockResolvedValue({ ai_provider: null, ai_api_key_set: false })
    renderIntegrations()

    await waitFor(() => {
      expect(screen.getByTestId('integration-card-ai')).toBeInTheDocument()
    })
    // Community users should not call PRO-only Bambuddy endpoints.
    expect(mocks.get).toHaveBeenCalledTimes(1)
    expect(mocks.get).toHaveBeenCalledWith('/api/v1/settings/ai')
  })

  it('renders Bambuddy as a locked PRO card for Community without calling PRO APIs', async () => {
    mocks.isPro = false
    mocks.features = []
    mocks.get.mockResolvedValue({ ai_provider: null, ai_api_key_set: false })

    renderIntegrations()

    const bambuddyCard = await screen.findByTestId('integration-card-bambuddy')
    expect(within(bambuddyCard).getByText('PRO feature')).toBeInTheDocument()
    expect(
      within(bambuddyCard).getByText(/Bambu printer support is included with FilaOps PRO/i),
    ).toBeInTheDocument()
    expect(mocks.get).not.toHaveBeenCalledWith('/api/v1/pro/integrations/bambuddy/status')
  })

  it('checks Bambuddy status only for PRO users with bambu_integration', async () => {
    mocks.get.mockImplementation((path) => {
      if (path === '/api/v1/settings/ai') {
        return Promise.resolve({ ai_provider: null, ai_api_key_set: false })
      }
      if (path === '/api/v1/pro/integrations/bambuddy/status') {
        return Promise.resolve({ connected: true })
      }
      return Promise.reject(new Error(`unexpected path ${path}`))
    })

    renderIntegrations()

    const bambuddyCard = await screen.findByTestId('integration-card-bambuddy')
    await waitFor(() => {
      expect(within(bambuddyCard).getByText('Configured')).toBeInTheDocument()
    })
    expect(mocks.get).toHaveBeenCalledWith('/api/v1/pro/integrations/bambuddy/status')
  })
})

describe('IntegrationCard (status badge variants)', () => {
  it.each([
    ['configured', 'Configured'],
    ['not_configured', 'Not configured'],
    ['error', 'Error'],
    ['loading', 'Loading…'],
  ])('renders %s badge with label %s', (status, label) => {
    render(
      <IntegrationCard
        title="Test"
        description="desc"
        status={status}
        testId="card-under-test"
      >
        <span>body</span>
      </IntegrationCard>,
    )
    const card = screen.getByTestId('card-under-test')
    expect(within(card).getByText(label)).toBeInTheDocument()
    expect(within(card).getByText('Test')).toBeInTheDocument()
    expect(within(card).getByText('body')).toBeInTheDocument()
  })

  it('falls back to "Not configured" badge for an unknown status string', () => {
    render(
      <IntegrationCard
        title="Test"
        description="desc"
        status="some-future-state"
        testId="card-under-test"
      >
        <span>body</span>
      </IntegrationCard>,
    )
    const card = screen.getByTestId('card-under-test')
    expect(within(card).getByText('Not configured')).toBeInTheDocument()
  })
})
