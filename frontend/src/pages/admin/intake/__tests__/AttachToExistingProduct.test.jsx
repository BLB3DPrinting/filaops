import { render, screen, fireEvent, waitFor, within } from '@testing-library/react'
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

vi.mock('../../../../hooks/useApi', () => {
  const api = { get: mocks.get, post: mocks.post }
  return { useApi: () => api }
})

vi.mock('../../../../components/Toast', () => {
  const toast = {
    success: mocks.toastSuccess,
    error: mocks.toastError,
    warning: mocks.toastWarning,
    info: vi.fn(),
  }
  return { useToast: () => toast }
})

vi.mock('../../../../config/api', () => ({ API_URL: 'http://api.test' }))

import AttachToExistingProduct from '../AttachToExistingProduct'

const DRAGON = { id: 11, sku: 'FG-011', name: 'Crystal Dragon', is_raw_material: false }
const PLA = { id: 90, sku: 'MAT-PLA-RED', name: 'Crystal Red PLA', is_raw_material: true }

const PRE_SLICED_PARSE = { slots: [] }
const SERVER_SLICED_PARSE = {
  slots: [],
  gcode_artifact_id: '0b6d2c4e-1f2a-4b3c-8d4e-5f6a7b8c9d0e',
  gcode_3mf_artifact_id: '9f8e7d6c-5b4a-4c3d-9e2f-1a0b9c8d7e6f',
}

const preSlicedFile = () =>
  new File(['PK-sliced'], 'dragon-v2.gcode.3mf', { type: 'application/octet-stream' })

function jsonResponse(status, body) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

// Routes fetch calls the panel makes. `current` controls the slice-file probe.
function installFetch({ current = 'present', attachStatus = 200, imageStatus = 200, putStatus = 200 } = {}) {
  const fetchMock = vi.fn(async (url, init = {}) => {
    const method = (init.method || 'GET').toUpperCase()
    if (method === 'POST' && url.endsWith('/admin/uploads/product-image')) {
      if (imageStatus !== 200) return jsonResponse(imageStatus, { detail: 'Failed to save file' })
      return jsonResponse(200, { filename: 'thumb.png', url: '/static/uploads/products/thumb.png', size: 70 })
    }
    if (method === 'PUT' && /\/api\/v1\/products\/\d+$/.test(url)) {
      if (putStatus === 'network') throw new TypeError('Failed to fetch')
      if (putStatus !== 200) return jsonResponse(putStatus, { detail: 'Validation failed' })
      return jsonResponse(200, { id: 11 })
    }
    if (method === 'DELETE' && url.includes('/admin/uploads/product-image/')) {
      return jsonResponse(200, { message: 'deleted' })
    }
    if (method === 'GET' && url.endsWith('/slice-file')) {
      if (current === 'present') {
        return new Response('PK-old-bytes', {
          status: 200,
          headers: {
            'Content-Disposition': 'attachment; filename="Crystal Dragon.gcode.3mf"',
            'Last-Modified': 'Wed, 03 Jun 2026 14:05:00 GMT',
          },
        })
      }
      if (current === 'missing') {
        return jsonResponse(404, { detail: 'Slice file content missing for product 11' })
      }
      return jsonResponse(404, { detail: 'No slice file on record for product 11' })
    }
    if (method === 'POST' && /\/slice-file(-from-artifact)?$/.test(url)) {
      if (attachStatus !== 200) {
        return jsonResponse(attachStatus, { detail: 'artifact not found' })
      }
      return jsonResponse(200, {
        id: 7,
        product_id: 11,
        original_filename: 'Crystal Dragon.gcode.3mf',
        download_url: '/api/v1/pro/intake/products/11/slice-file',
      })
    }
    throw new Error(`unexpected fetch ${method} ${url}`)
  })
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

const postCalls = (fetchMock) =>
  fetchMock.mock.calls.filter(([, init]) => (init?.method || 'GET').toUpperCase() === 'POST')

function expectNoSkuCall(fetchMock) {
  const fetchUrls = fetchMock.mock.calls.map(([url]) => url)
  const apiUrls = [...mocks.get.mock.calls, ...mocks.post.mock.calls].map(([url]) => url)
  for (const url of [...fetchUrls, ...apiUrls]) {
    expect(url).not.toMatch(/\/intake\/sku/)
  }
}

async function pickDragon() {
  fireEvent.change(screen.getByLabelText(/find product/i), {
    target: { value: 'dragon' },
  })
  const list = await screen.findByRole('list', { name: /matching products/i })
  fireEvent.click(within(list).getByRole('button', { name: /FG-011/ }))
}

beforeEach(() => {
  mocks.get.mockReset()
  mocks.post.mockReset()
  mocks.toastSuccess.mockReset()
  mocks.toastError.mockReset()
  mocks.toastWarning.mockReset()
  mocks.get.mockResolvedValue({ total: 2, items: [DRAGON, PLA] })
})

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('AttachToExistingProduct — product selection', () => {
  it('searches products by SKU or name and leaves raw materials out', async () => {
    installFetch()
    render(<AttachToExistingProduct parseResult={PRE_SLICED_PARSE} sourceFile={preSlicedFile()} />)

    fireEvent.change(screen.getByLabelText(/find product/i), {
      target: { value: 'crystal' },
    })

    const list = await screen.findByRole('list', { name: /matching products/i })
    expect(mocks.get).toHaveBeenCalledWith('/api/v1/products?search=crystal&limit=20')
    expect(within(list).getByText('Crystal Dragon')).toBeInTheDocument()
    expect(within(list).queryByText('Crystal Red PLA')).not.toBeInTheDocument()
  })

  it('prefills the search from the parsed product name', async () => {
    installFetch()
    render(
      <AttachToExistingProduct
        parseResult={PRE_SLICED_PARSE}
        sourceFile={preSlicedFile()}
        initialQuery="Crystal Dragon"
      />
    )
    await screen.findByRole('list', { name: /matching products/i })
    expect(mocks.get).toHaveBeenCalledWith('/api/v1/products?search=Crystal%20Dragon&limit=20')
  })

  it('shows the current slice file name and date for the chosen product', async () => {
    const fetchMock = installFetch({ current: 'present' })
    render(<AttachToExistingProduct parseResult={PRE_SLICED_PARSE} sourceFile={preSlicedFile()} />)

    await pickDragon()

    const current = await screen.findByTestId('current-slice-file')
    await waitFor(() => expect(current).toHaveTextContent('Crystal Dragon.gcode.3mf'))
    expect(current).toHaveTextContent('2026')
    expect(screen.getByRole('button', { name: 'Replace slice file' })).toBeEnabled()

    // The probe reads headers only; the download is aborted.
    const [, probeInit] = fetchMock.mock.calls.find(([, init]) => !init?.method || init.method === 'GET')
    expect(probeInit.signal.aborted).toBe(true)
  })

  it('says when the product has a slice file record whose file is gone', async () => {
    installFetch({ current: 'missing' })
    render(<AttachToExistingProduct parseResult={PRE_SLICED_PARSE} sourceFile={preSlicedFile()} />)

    await pickDragon()

    await waitFor(() =>
      expect(screen.getByTestId('current-slice-file')).toHaveTextContent(/missing from the server/i)
    )
    expect(screen.getByRole('button', { name: 'Replace slice file' })).toBeInTheDocument()
  })
})

describe('AttachToExistingProduct — attaching', () => {
  it('pre-sliced upload: confirms, then POSTs the file to /slice-file with no /sku call', async () => {
    const fetchMock = installFetch({ current: 'present' })
    const file = preSlicedFile()
    render(<AttachToExistingProduct parseResult={PRE_SLICED_PARSE} sourceFile={file} />)

    await pickDragon()
    const replace = await screen.findByRole('button', { name: 'Replace slice file' })
    await waitFor(() => expect(replace).toBeEnabled())
    fireEvent.click(replace)

    // Nothing is attached until the operator confirms.
    const dialog = screen.getByRole('alertdialog')
    expect(within(dialog).getByText(/Crystal Dragon\.gcode\.3mf/)).toBeInTheDocument()
    expect(postCalls(fetchMock)).toHaveLength(0)

    fireEvent.click(within(dialog).getByRole('button', { name: 'Replace' }))

    await screen.findByText(/Slice file attached to FG-011/)
    const posts = postCalls(fetchMock)
    expect(posts).toHaveLength(1)
    const [url, init] = posts[0]
    expect(url).toBe('http://api.test/api/v1/pro/intake/products/11/slice-file')
    expect(init.body).toBeInstanceOf(FormData)
    expect(init.body.get('file')).toBe(file)
    expect(mocks.toastSuccess).toHaveBeenCalledWith('Slice file attached to FG-011')
    expectNoSkuCall(fetchMock)
  })

  it('server-sliced upload: POSTs the worker artifact id to /slice-file-from-artifact with no /sku call', async () => {
    const fetchMock = installFetch({ current: 'present' })
    // The source of a server-sliced input is a raw .3mf, not the slice file.
    const raw = new File(['raw'], 'dragon.3mf')
    render(<AttachToExistingProduct parseResult={SERVER_SLICED_PARSE} sourceFile={raw} />)

    await pickDragon()
    const replace = await screen.findByRole('button', { name: 'Replace slice file' })
    await waitFor(() => expect(replace).toBeEnabled())
    fireEvent.click(replace)
    fireEvent.click(within(screen.getByRole('alertdialog')).getByRole('button', { name: 'Replace' }))

    await screen.findByText(/Slice file attached to FG-011/)
    const posts = postCalls(fetchMock)
    expect(posts).toHaveLength(1)
    const [url, init] = posts[0]
    expect(url).toBe('http://api.test/api/v1/pro/intake/products/11/slice-file-from-artifact')
    expect(JSON.parse(init.body)).toEqual({
      gcode_artifact_id: SERVER_SLICED_PARSE.gcode_3mf_artifact_id,
      filename: 'Crystal Dragon.gcode.3mf',
    })
    expectNoSkuCall(fetchMock)
  })

  it('cancelling the confirmation attaches nothing', async () => {
    const fetchMock = installFetch({ current: 'present' })
    render(<AttachToExistingProduct parseResult={PRE_SLICED_PARSE} sourceFile={preSlicedFile()} />)

    await pickDragon()
    const replace = await screen.findByRole('button', { name: 'Replace slice file' })
    await waitFor(() => expect(replace).toBeEnabled())
    fireEvent.click(replace)
    fireEvent.click(within(screen.getByRole('alertdialog')).getByRole('button', { name: 'Cancel' }))

    expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument()
    expect(postCalls(fetchMock)).toHaveLength(0)
  })

  it('a product with no slice file gets "Attach", and the confirmation says so', async () => {
    installFetch({ current: 'none' })
    render(<AttachToExistingProduct parseResult={PRE_SLICED_PARSE} sourceFile={preSlicedFile()} />)

    await pickDragon()
    const attach = await screen.findByRole('button', { name: 'Attach slice file' })
    await waitFor(() => expect(attach).toBeEnabled())
    expect(screen.getByTestId('current-slice-file')).toHaveTextContent('No slice file on record')
    fireEvent.click(attach)

    const dialog = screen.getByRole('alertdialog')
    expect(within(dialog).getByText(/has no slice file on record/)).toBeInTheDocument()
    expect(within(dialog).getByRole('button', { name: 'Attach' })).toBeInTheDocument()
  })

  it('reports an attach failure and stays on the form', async () => {
    installFetch({ current: 'present', attachStatus: 404 })
    render(<AttachToExistingProduct parseResult={SERVER_SLICED_PARSE} sourceFile={null} />)

    await pickDragon()
    const replace = await screen.findByRole('button', { name: 'Replace slice file' })
    await waitFor(() => expect(replace).toBeEnabled())
    fireEvent.click(replace)
    fireEvent.click(within(screen.getByRole('alertdialog')).getByRole('button', { name: 'Replace' }))

    await waitFor(() => expect(mocks.toastError).toHaveBeenCalledWith('artifact not found'))
    expect(screen.queryByText(/Slice file attached/)).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Replace slice file' })).toBeInTheDocument()
  })

  it('disables attaching when the upload produced no slice file', async () => {
    installFetch({ current: 'present' })
    // Server-sliced, but the worker exported no .gcode.3mf.
    const parse = { slots: [], gcode_artifact_id: SERVER_SLICED_PARSE.gcode_artifact_id }
    render(<AttachToExistingProduct parseResult={parse} sourceFile={new File(['x'], 'm.stl')} />)

    expect(screen.getByText(/nothing to attach/i)).toBeInTheDocument()
    await pickDragon()
    await waitFor(() =>
      expect(screen.getByTestId('current-slice-file')).toHaveTextContent('Crystal Dragon.gcode.3mf')
    )
    expect(screen.getByRole('button', { name: 'Replace slice file' })).toBeDisabled()
  })
})

describe('AttachToExistingProduct — plate preview as product image', () => {
  // 1x1 PNG
  const THUMB_B64 =
    'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=='
  const WITH_THUMB = { ...SERVER_SLICED_PARSE, thumbnail_base64: THUMB_B64, thumbnail_mime: 'image/png' }

  const imageUploads = (fetchMock) =>
    fetchMock.mock.calls.filter(([url, init]) =>
      url.endsWith('/admin/uploads/product-image') && init?.method === 'POST')
  const productPuts = (fetchMock) =>
    fetchMock.mock.calls.filter(([, init]) => init?.method === 'PUT')

  async function replaceAndConfirm() {
    const replace = await screen.findByRole('button', { name: 'Replace slice file' })
    await waitFor(() => expect(replace).toBeEnabled())
    fireEvent.click(replace)
    const dialog = screen.getByRole('alertdialog')
    const message = dialog.textContent
    fireEvent.click(within(dialog).getByRole('button', { name: 'Replace' }))
    return message
  }

  it('is offered and on by default, and notes it replaces an existing image', async () => {
    installFetch()
    mocks.get.mockResolvedValue({
      total: 1,
      items: [{ ...DRAGON, image_url: '/static/uploads/products/old.png' }],
    })
    render(<AttachToExistingProduct parseResult={WITH_THUMB} sourceFile={null} />)

    const box = screen.getByRole('checkbox', { name: /plate preview as the product image/i })
    expect(box).toBeChecked()
    await pickDragon()
    expect(screen.getByText(/Replaces the product's current image/)).toBeInTheDocument()
  })

  it('uploads the preview and sets only image_url on the product after attaching', async () => {
    const fetchMock = installFetch()
    mocks.get.mockResolvedValue({
      total: 1,
      items: [{ ...DRAGON, image_url: '/static/uploads/products/old.png' }],
    })
    render(<AttachToExistingProduct parseResult={WITH_THUMB} sourceFile={null} />)

    await pickDragon()
    const message = await replaceAndConfirm()
    expect(message).toMatch(/plate preview replaces the product image/i)

    await screen.findByText(/plate preview is now the product image/i)
    const uploads = imageUploads(fetchMock)
    expect(uploads).toHaveLength(1)
    expect(uploads[0][1].body.get('file').type).toBe('image/png')

    const puts = productPuts(fetchMock)
    expect(puts).toHaveLength(1)
    expect(puts[0][0]).toBe('http://api.test/api/v1/products/11')
    expect(JSON.parse(puts[0][1].body)).toEqual({ image_url: '/static/uploads/products/thumb.png' })
    expectNoSkuCall(fetchMock)
  })

  it('leaves the image alone when unticked', async () => {
    const fetchMock = installFetch()
    render(<AttachToExistingProduct parseResult={WITH_THUMB} sourceFile={null} />)

    fireEvent.click(screen.getByRole('checkbox', { name: /plate preview as the product image/i }))
    await pickDragon()
    const message = await replaceAndConfirm()
    expect(message).not.toMatch(/product image/i)

    await screen.findByText(/Slice file attached to FG-011/)
    expect(imageUploads(fetchMock)).toHaveLength(0)
    expect(productPuts(fetchMock)).toHaveLength(0)
  })

  it('keeps the attached slice file and warns when the image fails', async () => {
    const fetchMock = installFetch({ imageStatus: 500 })
    render(<AttachToExistingProduct parseResult={WITH_THUMB} sourceFile={null} />)

    await pickDragon()
    await replaceAndConfirm()

    await screen.findByText(/Slice file attached to FG-011/)
    expect(screen.getByText(/product image was not updated/i)).toBeInTheDocument()
    expect(mocks.toastWarning).toHaveBeenCalledWith('Product image not updated: Failed to save file')
    expect(productPuts(fetchMock)).toHaveLength(0)
  })

  const imageDeletes = (fetchMock) =>
    fetchMock.mock.calls.filter(([, init]) => init?.method === 'DELETE')

  it('removes the uploaded preview when the product update is refused', async () => {
    const fetchMock = installFetch({ putStatus: 422 })
    render(<AttachToExistingProduct parseResult={WITH_THUMB} sourceFile={null} />)

    await pickDragon()
    await replaceAndConfirm()

    await screen.findByText(/product image was not updated/i)
    await waitFor(() => expect(imageDeletes(fetchMock)).toHaveLength(1))
    expect(imageDeletes(fetchMock)[0][0]).toBe(
      'http://api.test/api/v1/admin/uploads/product-image/thumb.png'
    )
    expect(mocks.toastWarning).toHaveBeenCalledWith('Product image not updated: Validation failed')
  })

  it('keeps the uploaded preview when the product update hits a network error', async () => {
    const fetchMock = installFetch({ putStatus: 'network' })
    render(<AttachToExistingProduct parseResult={WITH_THUMB} sourceFile={null} />)

    await pickDragon()
    await replaceAndConfirm()

    await screen.findByText(/product image was not updated/i)
    expect(imageDeletes(fetchMock)).toHaveLength(0)
  })

  it('is not offered when the upload has no plate preview', () => {
    installFetch()
    render(<AttachToExistingProduct parseResult={SERVER_SLICED_PARSE} sourceFile={null} />)
    expect(screen.queryByRole('checkbox')).not.toBeInTheDocument()
  })
})
