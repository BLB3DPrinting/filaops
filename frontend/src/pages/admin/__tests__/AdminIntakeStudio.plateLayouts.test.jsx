/**
 * Intake Studio's third mode for a multi-plate file: parts and plate layouts
 * (PRO). The Studio only decides when the choice shows and hands the dropped
 * file to the panel; the panel itself is tested beside it.
 */
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'

const { mocks } = vi.hoisted(() => ({
  mocks: { get: vi.fn(), post: vi.fn(), flags: { isPro: true } },
}))

vi.mock('../../../hooks/useApi', () => {
  const api = { get: mocks.get, post: mocks.post }
  return { useApi: () => api }
})

vi.mock('../../../components/Toast', () => {
  const toast = { success: vi.fn(), error: vi.fn(), warning: vi.fn(), info: vi.fn() }
  return { useToast: () => toast }
})

// The unified flow (which is what detects multi-plate files) is on.
vi.mock('../../../hooks/useFeatureFlags', () => ({
  useFeatureFlags: () => ({
    isPro: mocks.flags.isPro,
    hasFeature: (feature) => feature === 'intake_unified_flow',
    loading: false,
  }),
}))

vi.mock('../../../config/api', () => ({ API_URL: 'http://api.test' }))

import AdminIntakeStudio from '../AdminIntakeStudio'
import { MATERIALS, PREVIEW, CONTEXT } from '../intake/__tests__/plateCompositionFixtures'

const preparse = (overrides = {}) => ({
  kind: 'sliced',
  model_name: 'Goose',
  plate_count: 2,
  slot_count: 2,
  slots: [],
  plates: [
    { plate_index: 1, total_weight_g: 124.2, print_time_seconds: 11700, slots: [] },
    { plate_index: 2, total_weight_g: 116, print_time_seconds: 8640, slots: [] },
  ],
  ...overrides,
})

function jsonResponse(status, body) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

function installFetch(pre) {
  const fetchMock = vi.fn(async (url) => {
    if (url.endsWith('/pro/intake/preparse')) return jsonResponse(200, pre)
    if (url.endsWith('/pro/intake/parse')) return jsonResponse(200, { slots: [] })
    throw new Error(`unexpected fetch ${url}`)
  })
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

/** Open the Studio and drop `name`, which /preparse describes as `pre`. */
function dropFile(name, pre) {
  const fetchMock = installFetch(pre)
  render(<AdminIntakeStudio />)
  const file = new File(['PK'], name)
  fireEvent.change(document.querySelector('input[type=file]'), { target: { files: [file] } })
  return { file, fetchMock }
}

const layoutsButton = () => screen.queryByRole('button', { name: /parts and plate layouts/i })

beforeEach(() => {
  mocks.flags.isPro = true
  mocks.get.mockReset()
  mocks.post.mockReset()
  mocks.get.mockImplementation(async (url) => {
    if (url === '/api/v1/materials/for-bom') return MATERIALS
    if (url === '/api/v1/pro/intake/context') return CONTEXT
    throw new Error(`unexpected GET ${url}`)
  })
  mocks.post.mockResolvedValue(PREVIEW)
})

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('Intake Studio plate layouts mode', () => {
  it('offers parts and plate layouts for a sliced multi-plate file, and no assembly', async () => {
    dropFile('Goose.gcode.3mf', preparse())

    expect(await screen.findByRole('button', { name: /parts and plate layouts/i })).toBeEnabled()
    expect(screen.getByRole('button', { name: /intake one plate/i })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /intake whole model/i })).not.toBeInTheDocument()
  })

  it('shows it disabled, beside the assembly option, for a raw multi-plate file', async () => {
    dropFile('Goose.3mf', preparse({ kind: 'raw3mf' }))

    expect(await screen.findByRole('button', { name: /intake whole model/i })).toBeInTheDocument()
    expect(layoutsButton()).toBeDisabled()
  })

  it('does not offer it for a single-plate file, which goes straight to parsing', async () => {
    const { fetchMock } = dropFile('Goose.gcode.3mf', preparse({ plate_count: 1, plates: [] }))

    await waitFor(() =>
      expect(fetchMock).toHaveBeenCalledWith(
        'http://api.test/api/v1/pro/intake/parse',
        expect.anything(),
      ),
    )
    expect(layoutsButton()).not.toBeInTheDocument()
  })

  it('hands the dropped file to the panel when the mode is chosen', async () => {
    const { file } = dropFile('Goose.gcode.3mf', preparse())

    fireEvent.click(await screen.findByRole('button', { name: /parts and plate layouts/i }))

    expect(await screen.findByRole('region', { name: 'Plate 1' })).toBeInTheDocument()
    const [url, , init] = mocks.post.mock.calls.find(([u]) => u === '/api/v1/pro/intake/compositions')
    expect(url).toBe('/api/v1/pro/intake/compositions')
    expect(init.body.get('file')).toBe(file)
    // The plate picker of the single-plate flow is not shown beside it.
    expect(screen.queryByText('Choose a plate')).not.toBeInTheDocument()
  })

  it('goes back to the drop zone from the panel', async () => {
    dropFile('Goose.gcode.3mf', preparse())
    fireEvent.click(await screen.findByRole('button', { name: /parts and plate layouts/i }))
    await screen.findByRole('region', { name: 'Plate 1' })

    fireEvent.click(screen.getByRole('button', { name: /choose a different file/i }))
    expect(document.querySelector('input[type=file]')).toBeInTheDocument()
    expect(layoutsButton()).not.toBeInTheDocument()
  })

  it('is part of the PRO-only Intake Studio: without PRO there is no file drop at all', () => {
    mocks.flags.isPro = false
    render(<AdminIntakeStudio />)
    expect(screen.getByText('PRO Feature')).toBeInTheDocument()
    expect(document.querySelector('input[type=file]')).not.toBeInTheDocument()
  })
})
