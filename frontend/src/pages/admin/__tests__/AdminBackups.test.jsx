import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { describe, it, expect, vi, beforeEach } from 'vitest'

const { mocks } = vi.hoisted(() => ({
  mocks: {
    get: vi.fn(),
    post: vi.fn(),
    put: vi.fn(),
    toastSuccess: vi.fn(),
    toastError: vi.fn(),
  },
}))

vi.mock('../../../hooks/useApi', () => {
  const api = { get: mocks.get, post: mocks.post, put: mocks.put, patch: vi.fn(), del: vi.fn() }
  return { useApi: () => api }
})

vi.mock('../../../components/Toast', () => {
  const toast = { success: mocks.toastSuccess, error: mocks.toastError }
  return { useToast: () => toast }
})

import AdminBackups from '../AdminBackups'

const SETTINGS = { enabled: true, time: '03:00', timezone: 'UTC', retention_days: 14 }

const okRun = {
  id: 7,
  status: 'ok',
  trigger: 'scheduled',
  started_at: '2026-10-13T03:00:00+00:00',
  finished_at: '2026-10-13T03:00:09+00:00',
  filename: 'filaops-20261013-030000.sql.gz',
  size_bytes: 2_500_000,
  table_count: 98,
  error: null,
  downloadable: true,
}

function makeStatus(overrides = {}) {
  return {
    settings: SETTINGS,
    settings_problem: null,
    scheduler_enabled: true,
    next_run_at: '2026-10-14T03:00:00+00:00',
    running: false,
    last_run: okRun,
    last_success: okRun,
    tools: {
      pg_dump_path: '/usr/lib/postgresql/16/bin/pg_dump',
      pg_dump_version: 'pg_dump (PostgreSQL) 16.15',
      server_version: '16.4',
      versions_match: true,
      problem: null,
    },
    storage: { path: '/app/backups', problem: null, writable: true, free_bytes: 10e9, file_count: 1, total_bytes: 2_500_000 },
    ...overrides,
  }
}

function routeGets(status, runs) {
  mocks.get.mockImplementation((url) =>
    Promise.resolve(url.startsWith('/api/v1/admin/backups/runs') ? runs : status),
  )
}

function renderPage() {
  return render(
    <MemoryRouter>
      <AdminBackups />
    </MemoryRouter>,
  )
}

beforeEach(() => {
  vi.clearAllMocks()
})

describe('AdminBackups', () => {
  it('shows the last good backup and a download link', async () => {
    routeGets(makeStatus(), [okRun])
    renderPage()

    expect(await screen.findByText(/Last good backup/)).toBeInTheDocument()
    const link = screen.getByRole('link', { name: 'Download' })
    expect(link.getAttribute('href')).toMatch(/\/api\/v1\/admin\/backups\/runs\/7\/download$/)
    expect(screen.getByText(/password hashes/)).toBeInTheDocument()
    expect(screen.getByText('2.4 MB')).toBeInTheDocument()
  })

  it('explains a failed backup and a version mismatch', async () => {
    const failed = { ...okRun, id: 8, status: 'failed', error: 'pg_dump is version 17 but the database server is version 16.', downloadable: false, size_bytes: null, table_count: null }
    routeGets(
      makeStatus({
        last_run: failed,
        last_success: null,
        tools: { ...makeStatus().tools, versions_match: false, problem: 'pg_dump is version 17 but the database is version 16; backups will fail until they match.' },
      }),
      [failed],
    )
    renderPage()

    expect(await screen.findByText('The last backup failed.')).toBeInTheDocument()
    expect(screen.getByRole('alert')).toHaveTextContent('backups will fail until they match')
    expect(screen.queryByRole('link', { name: 'Download' })).not.toBeInTheDocument()
  })

  it('warns and will not start a backup when the folder is not a volume', async () => {
    const problem = 'The backup folder /app/backups is not on a mounted volume, so backups would be deleted whenever the container is recreated.'
    routeGets(makeStatus({ storage: { ...makeStatus().storage, problem } }), [okRun])
    renderPage()

    expect(await screen.findByTestId('storage-warning')).toHaveTextContent('not on a mounted volume')
    expect(screen.getByRole('button', { name: 'Run backup now' })).toBeDisabled()
  })

  it('saves the schedule through the database_backup setting', async () => {
    routeGets(makeStatus(), [okRun])
    mocks.put.mockResolvedValue({})
    renderPage()

    const days = await screen.findByLabelText(/Keep backups for/)
    const save = screen.getByRole('button', { name: 'Save schedule' })
    expect(save).toBeDisabled()

    await userEvent.clear(days)
    await userEvent.type(days, '30')
    await userEvent.click(save)

    await waitFor(() =>
      expect(mocks.put).toHaveBeenCalledWith('/api/v1/system/settings/database_backup', {
        value: { ...SETTINGS, retention_days: 30 },
      }),
    )
    expect(mocks.toastSuccess).toHaveBeenCalledWith('Backup schedule saved.')
  })

  it('starts a backup and disables the button while it runs', async () => {
    routeGets(makeStatus(), [okRun])
    mocks.post.mockResolvedValue({ id: 9, status: 'running' })
    renderPage()

    const button = await screen.findByRole('button', { name: 'Run backup now' })
    routeGets(makeStatus({ running: true }), [{ ...okRun, id: 9, status: 'running', downloadable: false }])
    await userEvent.click(button)

    expect(mocks.post).toHaveBeenCalledWith('/api/v1/admin/backups/runs')
    expect(await screen.findByRole('button', { name: 'Backup running…' })).toBeDisabled()
  })

  it('reports a backup that finishes before the first poll', async () => {
    routeGets(makeStatus(), [okRun])
    mocks.post.mockResolvedValue({ id: 9, status: 'running' })
    renderPage()

    const button = await screen.findByRole('button', { name: 'Run backup now' })
    const done = { ...okRun, id: 9, trigger: 'manual' }
    routeGets(makeStatus({ last_run: done, last_success: done }), [done, okRun])
    await userEvent.click(button)

    await waitFor(() => expect(mocks.toastSuccess).toHaveBeenCalledWith('Backup finished and verified.'))
  })
})
