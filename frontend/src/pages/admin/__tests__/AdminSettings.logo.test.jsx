import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const { mocks } = vi.hoisted(() => ({
  mocks: {
    api: {
      get: vi.fn(),
      patch: vi.fn(),
      post: vi.fn(),
      delete: vi.fn(),
      del: vi.fn(),
    },
    toastSuccess: vi.fn(),
    toastError: vi.fn(),
  },
}))

vi.mock('../../../hooks/useApi', () => ({ useApi: () => mocks.api }))
vi.mock('../../../components/Toast', () => ({
  useToast: () => ({ success: mocks.toastSuccess, error: mocks.toastError }),
}))
vi.mock('../../../hooks/useVersionCheck', () => ({
  useVersionCheck: () => ({
    latestVersion: null,
    installMethod: 'docker',
    updateAvailable: false,
    loading: false,
    checkForUpdates: vi.fn(),
  }),
}))
vi.mock('../../../utils/version', () => ({
  getCurrentVersion: vi.fn().mockResolvedValue('4.1.0'),
  getCurrentVersionSync: vi.fn().mockReturnValue('4.1.0'),
  formatVersion: (version) => version,
}))
vi.mock('../../../contexts/LocaleContext', () => ({
  useLocale: () => ({ updateLocaleSettings: vi.fn() }),
}))
vi.mock('../../../contexts/AppContext', () => ({
  useApp: () => ({ smtpConfigured: true }),
}))
vi.mock('../../../components/LicenseSection', () => ({ default: () => null }))
vi.mock('../../../components/settings/QualitySettingsSection', () => ({ default: () => null }))

import AdminSettings from '../AdminSettings'

const companySettings = {
  company_name: 'FilaOps Test Farm',
  has_logo: true,
  updated_at: '2026-07-28T00:00:00Z',
}

let currentSettings

describe('AdminSettings company logo cache revision', () => {
  beforeEach(() => {
    currentSettings = companySettings
    mocks.api.get.mockReset()
    mocks.api.get.mockImplementation((path) => {
      if (path === '/api/v1/settings/company') return Promise.resolve(currentSettings)
      if (path === '/api/v1/tax-rates') return Promise.resolve([])
      return Promise.reject(new Error(`Unexpected GET ${path}`))
    })
    mocks.toastSuccess.mockReset()
    mocks.toastError.mockReset()
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('keeps the logo URL stable across renders and revises it only after a successful replacement', async () => {
    const failedUpload = {
      ok: false,
      json: vi.fn().mockResolvedValue({ detail: 'Invalid logo' }),
    }
    const successfulUpload = { ok: true }
    const uploadFetch = vi.fn()
      .mockResolvedValueOnce(failedUpload)
      .mockResolvedValueOnce(successfulUpload)
    vi.stubGlobal('fetch', uploadFetch)

    const { container, rerender, unmount } = render(
      <MemoryRouter>
        <AdminSettings />
      </MemoryRouter>,
    )

    const logo = await screen.findByAltText('Company Logo')
    const initialUrl = logo.getAttribute('src')
    expect(initialUrl).toMatch(
      new RegExp(`\\?revision=${encodeURIComponent(companySettings.updated_at)}$`),
    )

    rerender(
      <MemoryRouter>
        <AdminSettings />
      </MemoryRouter>,
    )
    expect(screen.getByAltText('Company Logo')).toHaveAttribute('src', initialUrl)

    const fileInput = container.querySelector('input[type="file"]')
    fireEvent.change(fileInput, {
      target: { files: [new File(['bad'], 'bad.png', { type: 'image/png' })] },
    })
    await waitFor(() => expect(mocks.toastError).toHaveBeenCalledWith('Invalid logo'))
    expect(screen.getByAltText('Company Logo')).toHaveAttribute('src', initialUrl)

    currentSettings = {
      ...companySettings,
      updated_at: '2026-07-28T00:05:00Z',
    }
    fireEvent.change(fileInput, {
      target: { files: [new File(['good'], 'good.png', { type: 'image/png' })] },
    })
    await waitFor(() => expect(mocks.toastSuccess).toHaveBeenCalledWith('Logo uploaded successfully!'))
    const replacedUrl = initialUrl.replace(
      encodeURIComponent(companySettings.updated_at),
      encodeURIComponent(currentSettings.updated_at),
    )
    await waitFor(() => {
      expect(screen.getByAltText('Company Logo')).toHaveAttribute('src', replacedUrl)
    })

    unmount()
    render(
      <MemoryRouter>
        <AdminSettings />
      </MemoryRouter>,
    )
    expect(await screen.findByAltText('Company Logo')).toHaveAttribute('src', replacedUrl)
  })
})
