/**
 * Intake Studio create path: the plate preview is stored through Core's
 * product-image upload and sent to POST /sku as image_url.
 */
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'

const { mocks } = vi.hoisted(() => ({
  mocks: {
    get: vi.fn(),
    post: vi.fn(),
    toastSuccess: vi.fn(),
    toastError: vi.fn(),
    toastWarning: vi.fn(),
  },
}))

vi.mock('../../../hooks/useApi', () => {
  const api = { get: mocks.get, post: mocks.post }
  return { useApi: () => api }
})

vi.mock('../../../components/Toast', () => {
  const toast = {
    success: mocks.toastSuccess,
    error: mocks.toastError,
    warning: mocks.toastWarning,
    info: vi.fn(),
  }
  return { useToast: () => toast }
})

// PRO on, unified-flow gate off: .gcode.3mf parses immediately and step 3 is
// the legacy /match flow.
vi.mock('../../../hooks/useFeatureFlags', () => ({
  useFeatureFlags: () => ({
    isPro: true,
    hasFeature: () => false,
    loading: false,
  }),
}))

vi.mock('../../../config/api', () => ({ API_URL: 'http://api.test' }))

import AdminIntakeStudio from '../AdminIntakeStudio'

// 1x1 PNG
const THUMB_B64 =
  'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=='

const parseResult = (overrides = {}) => ({
  model_name: 'Dragon',
  printer_model: 'A1',
  print_time_seconds: 3600,
  total_weight_g: 10,
  thumbnail_base64: THUMB_B64,
  thumbnail_mime: 'image/png',
  slots: [{ slot_id: 1, filament_type: 'PLA', color_hex: '#FF0000', used_g: 10, used_m: 3 }],
  ...overrides,
})

function jsonResponse(status, body) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

function installFetch(parse) {
  const fetchMock = vi.fn(async (url, init = {}) => {
    const method = (init.method || 'GET').toUpperCase()
    if (url.endsWith('/pro/intake/parse')) return jsonResponse(200, parse)
    if (method === 'POST' && url.endsWith('/admin/uploads/product-image')) {
      return jsonResponse(200, { filename: 'abc.png', url: '/static/uploads/products/abc.png', size: 70 })
    }
    if (method === 'DELETE' && url.includes('/admin/uploads/product-image/')) {
      return jsonResponse(200, { message: 'deleted' })
    }
    if (method === 'POST' && /\/products\/\d+\/slice-file$/.test(url)) {
      return jsonResponse(200, { id: 1 })
    }
    throw new Error(`unexpected fetch ${method} ${url}`)
  })
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

function installApi({ skuError = null } = {}) {
  mocks.get.mockImplementation(async (url) => {
    if (url === '/api/v1/pro/intake/context') {
      return {
        printer_work_center_map: { A1: { work_center_id: 3 } },
        work_centers: [{ id: 3, code: 'PRINT', name: 'Printers' }],
      }
    }
    if (url === '/api/v1/items/categories') return []
    throw new Error(`unexpected GET ${url}`)
  })
  mocks.post.mockImplementation(async (url) => {
    if (url === '/api/v1/pro/intake/match') {
      return { results: [{ slot_id: 1, suggestions: [{ product_id: 5, sku: 'MAT-PLA-RED', name: 'PLA Red' }] }] }
    }
    if (url === '/api/v1/pro/intake/preview') return { suggested_price: 12.5 }
    if (url === '/api/v1/pro/intake/sku') {
      if (skuError) throw skuError
      return { product: { id: 42, sku: 'INTAKE-DRAGON' } }
    }
    throw new Error(`unexpected POST ${url}`)
  })
}

async function driveToCreate() {
  const input = document.querySelector('input[type=file]')
  fireEvent.change(input, {
    target: { files: [new File(['PK'], 'Dragon.gcode.3mf')] },
  })
  fireEvent.click(await screen.findByRole('button', { name: /Next: match spools/ }))
  fireEvent.click(await screen.findByRole('button', { name: /Next: finishing/ }))
  const create = await screen.findByRole('button', { name: /Create SKU/ })
  await waitFor(() => expect(create).toBeEnabled())
  fireEvent.click(create)
}

const skuCall = () => mocks.post.mock.calls.find(([url]) => url === '/api/v1/pro/intake/sku')
const uploadCalls = (fetchMock) =>
  fetchMock.mock.calls.filter(([url, init]) =>
    url.endsWith('/admin/uploads/product-image') && init?.method === 'POST')

beforeEach(() => {
  mocks.get.mockReset()
  mocks.post.mockReset()
  mocks.toastSuccess.mockReset()
  mocks.toastError.mockReset()
  mocks.toastWarning.mockReset()
})

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('Intake Studio — plate preview as product image (create path)', () => {
  it('uploads the plate preview and sends its URL to /sku as image_url', async () => {
    const fetchMock = installFetch(parseResult())
    installApi()
    render(<AdminIntakeStudio />)

    await driveToCreate()

    await waitFor(() => expect(skuCall()).toBeTruthy())
    expect(skuCall()[1].image_url).toBe('/static/uploads/products/abc.png')

    const uploads = uploadCalls(fetchMock)
    expect(uploads).toHaveLength(1)
    const file = uploads[0][1].body.get('file')
    expect(file.type).toBe('image/png')
    expect(file.name).toMatch(/\.png$/)
    // the stored image is a URL, never the data itself
    expect(skuCall()[1].image_url).not.toMatch(/^data:/)
  })

  it('creates the product without an image when there is no plate preview', async () => {
    const fetchMock = installFetch(parseResult({ thumbnail_base64: null }))
    installApi()
    render(<AdminIntakeStudio />)

    await driveToCreate()

    await waitFor(() => expect(skuCall()).toBeTruthy())
    expect(skuCall()[1].image_url).toBeUndefined()
    expect(uploadCalls(fetchMock)).toHaveLength(0)
  })

  it('still creates the product when the image upload fails', async () => {
    const fetchMock = installFetch(parseResult())
    // Keep every other route; make only the image upload fail.
    const base = fetchMock.getMockImplementation()
    fetchMock.mockImplementation(async (url, init = {}) => {
      if (url.endsWith('/admin/uploads/product-image') && init.method === 'POST') {
        return jsonResponse(500, { detail: 'Failed to save file' })
      }
      return base(url, init)
    })
    installApi()
    render(<AdminIntakeStudio />)

    await driveToCreate()

    await waitFor(() => expect(skuCall()).toBeTruthy())
    expect(skuCall()[1].image_url).toBeUndefined()
    expect(mocks.toastWarning).toHaveBeenCalledWith(
      expect.stringContaining('Failed to save file')
    )
  })

  it('still creates the product when the upload answers without a URL', async () => {
    const fetchMock = installFetch(parseResult())
    const base = fetchMock.getMockImplementation()
    fetchMock.mockImplementation(async (url, init = {}) => {
      if (url.endsWith('/admin/uploads/product-image') && init.method === 'POST') {
        return new Response('<html>proxy page</html>', { status: 200 })
      }
      return base(url, init)
    })
    installApi()
    render(<AdminIntakeStudio />)

    await driveToCreate()

    await waitFor(() => expect(skuCall()).toBeTruthy())
    expect(skuCall()[1].image_url).toBeUndefined()
    expect(mocks.toastWarning).toHaveBeenCalledWith(
      expect.stringContaining('returned no URL')
    )
  })

  it('removes the uploaded image when /sku refuses the product', async () => {
    const fetchMock = installFetch(parseResult())
    const err = Object.assign(new Error('SKU already exists'), { status: 409 })
    installApi({ skuError: err })
    render(<AdminIntakeStudio />)

    await driveToCreate()

    await waitFor(() =>
      expect(
        fetchMock.mock.calls.some(([url, init]) =>
          url === 'http://api.test/api/v1/admin/uploads/product-image/abc.png' &&
          init?.method === 'DELETE')
      ).toBe(true)
    )
    expect(mocks.toastError).toHaveBeenCalledWith('SKU already exists')
  })
})
