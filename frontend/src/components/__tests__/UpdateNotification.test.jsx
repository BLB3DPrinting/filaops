import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'

const { mocks } = vi.hoisted(() => ({
  mocks: {
    checker: {
      updateInfo: {
        update_available: true,
        current_version: '4.1.2',
        latest_version: '4.3.0',
        release_date: '2026-10-14T00:00:00Z',
        release_url: 'https://github.com/BLB3DPrinting/filaops/releases/tag/v4.3.0',
      },
      hasUpdate: true,
      dismissUpdate: vi.fn(),
    },
  },
}))

vi.mock('../../hooks/useUpdateChecker', () => ({
  useUpdateChecker: () => mocks.checker,
}))

vi.mock('../../config/api', () => ({ API_URL: '' }))

import UpdateNotification from '../UpdateNotification'

const DOCS_URL = 'https://blb3dprinting.github.io/filaops/UPGRADE/'

const INSTRUCTIONS = {
  method: 'docker-compose',
  estimated_time: '5-15 minutes',
  downtime: 'FilaOps is unavailable while the containers rebuild and restart',
  instructions: [
    '2. Back up the database, from the filaops folder: docker exec filaops-db pg_dump ...',
    '5. Rebuild and start: docker compose up -d --build',
  ],
  backup_recommendation: 'Back up the database before you start (step 2) and keep the file.',
  documentation_url: DOCS_URL,
  rollback_steps: ['1. Stop the backend: docker compose stop backend'],
  requires_manual_steps: true,
}

let fetchMock
let openMock

beforeEach(() => {
  fetchMock = vi.fn()
  openMock = vi.fn()
  vi.stubGlobal('fetch', fetchMock)
  vi.stubGlobal('open', openMock)
  vi.spyOn(console, 'error').mockImplementation(() => {})
})

afterEach(() => {
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
})

describe('UpdateNotification', () => {
  it('renders nothing when there is no update', () => {
    mocks.checker = { ...mocks.checker, hasUpdate: false }
    const { container } = render(<UpdateNotification />)
    expect(container).toBeEmptyDOMElement()
    mocks.checker = { ...mocks.checker, hasUpdate: true }
  })

  it('offers upgrade steps and release notes but no one-click update', () => {
    render(<UpdateNotification />)

    expect(screen.getByText('FilaOps 4.3.0 Available!')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'How to Upgrade' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Release Notes' })).toHaveAttribute(
      'href',
      mocks.checker.updateInfo.release_url,
    )
    expect(screen.queryByRole('button', { name: /update now/i })).not.toBeInTheDocument()
  })

  it('never calls the removed update/start endpoint', async () => {
    fetchMock.mockResolvedValue({ ok: true, json: async () => INSTRUCTIONS })
    render(<UpdateNotification />)

    fireEvent.click(screen.getByRole('button', { name: 'How to Upgrade' }))
    await screen.findByText('Update to 4.3.0')

    const urls = fetchMock.mock.calls.map(([url]) => url)
    expect(urls).toEqual(['/api/v1/system/updates/instructions'])
    expect(urls.some((url) => url.includes('update/start'))).toBe(false)
  })

  it('shows the instructions from the API with the backup advice and docs link', async () => {
    fetchMock.mockResolvedValue({ ok: true, json: async () => INSTRUCTIONS })
    render(<UpdateNotification />)

    fireEvent.click(screen.getByRole('button', { name: 'How to Upgrade' }))

    expect(await screen.findByText('Update to 4.3.0')).toBeInTheDocument()
    expect(fetchMock).toHaveBeenCalledWith('/api/v1/system/updates/instructions', {
      credentials: 'include',
    })
    expect(screen.getByText(INSTRUCTIONS.instructions[1])).toBeInTheDocument()
    expect(screen.getByText(INSTRUCTIONS.backup_recommendation)).toBeInTheDocument()
    expect(screen.queryByText(/recommended/i)).not.toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Full Documentation' })).toHaveAttribute('href', DOCS_URL)
    expect(screen.queryByRole('button', { name: /ready to update/i })).not.toBeInTheDocument()
  })

  it('opens the docs site when the instructions request is rejected', async () => {
    fetchMock.mockResolvedValue({
      ok: false,
      status: 401,
      statusText: 'Unauthorized',
      json: async () => ({ detail: 'Not authenticated' }),
    })
    render(<UpdateNotification />)

    fireEvent.click(screen.getByRole('button', { name: 'How to Upgrade' }))

    await waitFor(() =>
      expect(openMock).toHaveBeenCalledWith(DOCS_URL, '_blank', 'noopener,noreferrer'),
    )
    expect(screen.queryByText('Update to 4.3.0')).not.toBeInTheDocument()
  })

  it('opens the docs site when the instructions request fails', async () => {
    fetchMock.mockRejectedValue(new Error('network down'))
    render(<UpdateNotification />)

    fireEvent.click(screen.getByRole('button', { name: 'How to Upgrade' }))

    await waitFor(() =>
      expect(openMock).toHaveBeenCalledWith(DOCS_URL, '_blank', 'noopener,noreferrer'),
    )
  })
})
