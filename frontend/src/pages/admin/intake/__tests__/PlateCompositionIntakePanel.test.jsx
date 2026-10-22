import { render, screen, fireEvent, waitFor, within } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach } from 'vitest'

const { mocks } = vi.hoisted(() => ({
  mocks: { get: vi.fn(), post: vi.fn(), toastSuccess: vi.fn(), toastError: vi.fn() },
}))

vi.mock('../../../../hooks/useApi', () => {
  const api = { get: mocks.get, post: mocks.post }
  return { useApi: () => api }
})

vi.mock('../../../../components/Toast', () => {
  const toast = { success: mocks.toastSuccess, error: mocks.toastError, warning: vi.fn(), info: vi.fn() }
  return { useToast: () => toast }
})

import { ApiError } from '../../../../lib/apiClient'
import PlateCompositionIntakePanel from '../PlateCompositionIntakePanel'
import { COMMITTED, CONTEXT, MATERIALS, PREVIEW } from './plateCompositionFixtures'

const URL = '/api/v1/pro/intake/compositions'
const BODY = 'hash:aaa111bbb222'
const BEAK = 'hash:ccc333ddd444'
const WING = 'name:Wing'
const FILE = new File(['PK-vendor'], 'Goose.gcode.3mf', { type: 'application/octet-stream' })

// What the API client throws for an answer PRO gave with `detail`.
const refused = (status, detail) =>
  new ApiError(typeof detail === 'string' ? detail : `HTTP ${status}`, status, { detail })

/**
 * Answers the three calls the panel makes. `post` tells the preview from the
 * commit by whether the form carries a plan.
 */
function installApi({
  preview = PREVIEW,
  previewError = null,
  commit = COMMITTED,
  commitError = null,
  context = CONTEXT,
  materials = MATERIALS,
  products = { items: [] },
  contextError = null,
} = {}) {
  mocks.get.mockImplementation(async (url) => {
    if (url === '/api/v1/pro/intake/context') {
      if (contextError) throw contextError
      return context
    }
    if (url === '/api/v1/materials/for-bom') return materials
    if (url.startsWith('/api/v1/products?search=')) return products
    throw new Error(`unexpected GET ${url}`)
  })
  mocks.post.mockImplementation(async (url, _json, init) => {
    if (url !== URL) throw new Error(`unexpected POST ${url}`)
    if (init.body.has('plan')) {
      if (commitError) throw commitError
      return commit
    }
    if (previewError) throw previewError
    return preview
  })
}

const posts = () => mocks.post.mock.calls
const commitCall = () => posts().find(([, , init]) => init.body.has('plan'))
const sentPlan = () => JSON.parse(commitCall()[2].body.get('plan'))

const createButton = () => screen.getByRole('button', { name: /create parts and plate layouts/i })
const part = (name) => screen.getByRole('group', { name: `Part: ${name}` })

async function openPanel(props = {}) {
  const onStartOver = vi.fn()
  render(<PlateCompositionIntakePanel file={FILE} onStartOver={onStartOver} {...props} />)
  await screen.findByRole('region', { name: 'Plate 1' })
  return { onStartOver }
}

/** Open the panel and wait for the work centres and spools to load. */
async function openReadyPanel() {
  const opened = await openPanel()
  await waitFor(() => expect(createButton()).toBeEnabled())
  return opened
}

beforeEach(() => {
  mocks.get.mockReset()
  mocks.post.mockReset()
  mocks.toastSuccess.mockReset()
  mocks.toastError.mockReset()
  installApi()
})

describe('PlateCompositionIntakePanel preview', () => {
  it('sends only the file first, to get the preview', async () => {
    await openPanel()
    const [url, json, init] = posts()[0]
    expect(url).toBe(URL)
    expect(json).toBeUndefined()
    expect(init.body.get('file')).toBe(FILE)
    expect(init.body.has('plan')).toBe(false)
    // A failed save is not retried behind the operator's back.
    expect(init.retry).toBe(0)
  })

  it('shows a manifest card per plate with each kind of object, its count and its numbers', async () => {
    await openPanel()
    const one = screen.getByRole('region', { name: 'Plate 1' })
    expect(within(one).getByText('Body × 4')).toBeInTheDocument()
    expect(within(one).getByText('Beak × 16')).toBeInTheDocument()
    expect(within(one).getByText(/25 g · 30m each/)).toBeInTheDocument()
    expect(within(one).getByText(/1\.2 g · 3m each/)).toBeInTheDocument()
    expect(within(one).getByText(/3h 15m/)).toBeInTheDocument()

    const two = screen.getByRole('region', { name: 'Plate 2' })
    expect(within(two).getByText('Wing × 2')).toBeInTheDocument()
    // Wing's numbers are a share of the plate, not measured; the card says so.
    expect(within(two).getByText(/estimated from volume/i)).toBeInTheDocument()
    expect(within(two).getByText(/label objects was off/i)).toBeInTheDocument()
  })

  it('groups a plate of 4 bodies and 16 beaks into two kinds of object, and each kind into one part', async () => {
    await openPanel()
    const one = screen.getByRole('region', { name: 'Plate 1' })
    expect(within(one).getAllByRole('listitem')).toHaveLength(2)

    // The body is on both plates and is still one row.
    const rows = screen.getAllByRole('group', { name: /^Part: / })
    expect(rows.map((row) => row.getAttribute('aria-label'))).toEqual([
      'Part: Body',
      'Part: Beak',
      'Part: Wing',
    ])
    expect(within(part('Body')).getByText(/plate 1 × 4.*plate 2 × 4/i)).toBeInTheDocument()
  })

  it('pre-selects the existing part PRO proposes by mesh hash, and creates the others', async () => {
    await openPanel()
    const body = part('Body')
    expect(within(body).getByRole('radio', { name: /link to an existing part/i })).toBeChecked()
    expect(within(body).getByText(/GOOSE-BODY/)).toBeInTheDocument()

    const beak = part('Beak')
    expect(within(beak).getByRole('radio', { name: /create a new part/i })).toBeChecked()
    expect(within(beak).getByLabelText('SKU')).toHaveValue('GOOSE-BEAK')
    expect(within(beak).getByLabelText('Name')).toHaveValue('Beak')
  })

  it('makes a new part a component unless the operator says it is also sold loose', async () => {
    await openPanel()
    const itemType = within(part('Beak')).getByLabelText('Item type')
    expect(itemType).toHaveValue('component')
    fireEvent.change(itemType, { target: { value: 'finished_good' } })
    expect(itemType).toHaveValue('finished_good')
    // The other new part is untouched.
    expect(within(part('Wing')).getByLabelText('Item type')).toHaveValue('component')
  })

  it('suggests the print work centre for the file\'s printer and the spool for a slot\'s colour', async () => {
    await openPanel()
    await waitFor(() => expect(screen.getByLabelText(/print work centre/i)).toHaveValue('3'))
    expect(screen.getByLabelText(/spool for slot 1/i)).toHaveValue('90')
    expect(screen.getByLabelText(/spool for slot 2/i)).toHaveValue('91')
  })
})

describe('PlateCompositionIntakePanel save', () => {
  it('sends the file again with the plan as JSON', async () => {
    await openReadyPanel()
    fireEvent.change(within(part('Beak')).getByLabelText('Item type'), {
      target: { value: 'finished_good' },
    })
    fireEvent.click(createButton())

    await waitFor(() => expect(commitCall()).toBeDefined())
    const [url, json, init] = commitCall()
    expect(url).toBe(URL)
    expect(json).toBeUndefined()
    expect(init.body.get('file')).toBe(FILE)
    expect(init.retry).toBe(0)
    expect(sentPlan()).toEqual({
      name: 'Goose',
      print_work_center_id: 3,
      slot_spools: [
        { slot: 0, spool_product_id: 90, filament_type: 'PLA', color_hex: '#FFFFFF' },
        { slot: 1, spool_product_id: 91, filament_type: 'PLA', color_hex: '#FFA500' },
      ],
      parts: [
        { key: BODY, action: 'link', product_id: 7 },
        { key: BEAK, action: 'create', name: 'Beak', sku: 'GOOSE-BEAK', item_type: 'finished_good' },
        { key: WING, action: 'create', name: 'Wing', sku: 'GOOSE-WING', item_type: 'component' },
      ],
    })
  })

  it('renames a part and sends the new name', async () => {
    await openReadyPanel()
    fireEvent.change(within(part('Wing')).getByLabelText('Name'), { target: { value: 'Left wing' } })
    fireEvent.click(createButton())
    await waitFor(() => expect(commitCall()).toBeDefined())
    expect(sentPlan().parts.find((p) => p.key === WING).name).toBe('Left wing')
  })

  it('links a part to an existing product found by search', async () => {
    installApi({
      products: {
        items: [
          { id: 55, sku: 'FG-BEAK', name: 'Old beak', is_raw_material: false },
          { id: 56, sku: 'MAT-BEAK', name: 'Beak filament', is_raw_material: true },
        ],
      },
    })
    await openReadyPanel()
    const beak = part('Beak')
    fireEvent.click(within(beak).getByRole('radio', { name: /link to an existing part/i }))
    fireEvent.change(within(beak).getByLabelText(/find part/i), { target: { value: 'beak' } })

    const found = await within(beak).findByRole('button', { name: /FG-BEAK/ })
    // Raw materials are not parts and are not offered.
    expect(within(beak).queryByRole('button', { name: /MAT-BEAK/ })).not.toBeInTheDocument()
    expect(mocks.get).toHaveBeenCalledWith('/api/v1/products?search=beak&limit=20')
    fireEvent.click(found)
    expect(within(beak).getByText(/FG-BEAK/)).toBeInTheDocument()

    fireEvent.click(createButton())
    await waitFor(() => expect(commitCall()).toBeDefined())
    expect(sentPlan().parts.find((p) => p.key === BEAK)).toEqual({
      key: BEAK,
      action: 'link',
      product_id: 55,
    })
  })

  it('merges two kinds of object into one existing part by linking both to it', async () => {
    // PRO has no "merge into a new part"; linking two groups to the same
    // existing part is how two kinds of object become one part.
    installApi({ products: { items: [{ id: 7, sku: 'GOOSE-BODY', name: 'Goose body', is_raw_material: false }] } })
    await openReadyPanel()
    const wing = part('Wing')
    fireEvent.click(within(wing).getByRole('radio', { name: /link to an existing part/i }))
    fireEvent.change(within(wing).getByLabelText(/find part/i), { target: { value: 'goose' } })
    fireEvent.click(await within(wing).findByRole('button', { name: /GOOSE-BODY/ }))

    fireEvent.click(createButton())
    await waitFor(() => expect(commitCall()).toBeDefined())
    const { parts, slot_spools: spools } = sentPlan()
    expect(parts.filter((p) => p.action === 'link').map((p) => [p.key, p.product_id])).toEqual([
      [BODY, 7],
      [WING, 7],
    ])
    // Only the beak is still being made, so only its slot needs a spool.
    expect(spools.map((spool) => spool.slot)).toEqual([1])
  })

  it('adds an assembly parent with a quantity per part', async () => {
    await openReadyPanel()
    expect(screen.queryByLabelText('Per parent')).not.toBeInTheDocument()
    fireEvent.click(screen.getByLabelText(/also create an assembly parent/i))

    expect(createButton()).toBeDisabled()
    fireEvent.change(screen.getByLabelText(/assembly work centre/i), { target: { value: '4' } })
    fireEvent.change(screen.getByLabelText('Parent SKU (optional)'), { target: { value: 'GOOSE-ASM' } })
    fireEvent.change(screen.getByLabelText(/run minutes/i), { target: { value: '15' } })
    fireEvent.change(within(part('Beak')).getByLabelText('Per parent'), { target: { value: '2' } })
    fireEvent.change(within(part('Wing')).getByLabelText('Per parent'), { target: { value: '0' } })
    expect(createButton()).toBeEnabled()

    fireEvent.click(createButton())
    await waitFor(() => expect(commitCall()).toBeDefined())
    expect(sentPlan().parent).toEqual({
      name: 'Goose',
      sku: 'GOOSE-ASM',
      assembly_work_center_id: 4,
      assembly_run_time_minutes: 15,
      assembly_setup_minutes: 0,
      quantities: { [BODY]: 1, [BEAK]: 2 },
    })
  })

  it('will not save until every slot has a spool, and says which is missing', async () => {
    installApi({ materials: { items: [MATERIALS.items[0]] } })
    await openPanel()
    await waitFor(() => expect(screen.getByLabelText(/spool for slot 1/i)).toHaveValue('90'))
    expect(createButton()).toBeDisabled()
    expect(screen.getByText(/choose a spool for slot 2/i)).toBeInTheDocument()

    fireEvent.change(screen.getByLabelText(/spool for slot 2/i), { target: { value: '90' } })
    expect(createButton()).toBeEnabled()
  })

  it('shows what was created and linked, with links to the parts', async () => {
    await openReadyPanel()
    fireEvent.click(createButton())

    expect(await screen.findByRole('heading', { name: /plate layouts saved/i })).toBeInTheDocument()
    expect(screen.getByText(/created 2 parts/i)).toBeInTheDocument()
    expect(screen.getByText(/linked 1/i)).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /GOOSE-BEAK/ })).toHaveAttribute('href', '/admin/items')
    expect(screen.getByText('GOOSE-P01')).toBeInTheDocument()
    expect(screen.getByText('GOOSE-P02')).toBeInTheDocument()
    expect(mocks.toastSuccess).toHaveBeenCalled()
  })
})

describe('PlateCompositionIntakePanel errors', () => {
  const refuseCommit = async (error) => {
    installApi({ commitError: error })
    await openReadyPanel()
    fireEvent.click(createButton())
    return screen.findByRole('alert')
  }

  it('shows a 409 as PRO worded it, and keeps the form so it can be fixed', async () => {
    const alert = await refuseCommit(refused(409, "SKU 'GOOSE-BEAK' already exists. Provide a unique sku."))
    expect(alert).toHaveTextContent(/409/)
    expect(alert).toHaveTextContent("SKU 'GOOSE-BEAK' already exists")
    // Nothing was lost and the operator can try again.
    expect(within(part('Beak')).getByLabelText('SKU')).toHaveValue('GOOSE-BEAK')
    expect(createButton()).toBeEnabled()
  })

  it('shows a 422 validation list line by line', async () => {
    const alert = await refuseCommit(
      refused(422, [{ type: 'value_error', loc: ['parts', 1], msg: 'Value error, link needs a product_id' }]),
    )
    expect(alert).toHaveTextContent(/422/)
    expect(alert).toHaveTextContent('parts.1: link needs a product_id')
  })

  it('shows a 404 for a missing part or work centre', async () => {
    const alert = await refuseCommit(refused(404, 'part(s) 7 not found'))
    expect(alert).toHaveTextContent(/404/)
    expect(alert).toHaveTextContent('part(s) 7 not found')
  })

  it.each([
    [400, 'File is empty'],
    [413, 'File too large. Maximum size is 100MB'],
    [502, 'slicer-worker returned plate data PRO could not read'],
  ])('shows a %i too', async (status, detail) => {
    const alert = await refuseCommit(refused(status, detail))
    expect(alert).toHaveTextContent(String(status))
    expect(alert).toHaveTextContent(detail)
  })

  it('does not take a second click while the save is in flight', async () => {
    let finish
    mocks.post.mockImplementation(
      (url, _json, init) =>
        init.body.has('plan') ? new Promise((resolve) => { finish = resolve }) : Promise.resolve(PREVIEW),
    )
    await openReadyPanel()
    fireEvent.click(createButton())
    await waitFor(() => expect(createButton()).toBeDisabled())
    fireEvent.click(createButton())
    expect(posts().filter(([, , init]) => init.body.has('plan'))).toHaveLength(1)
    finish(COMMITTED)
    await screen.findByRole('heading', { name: /plate layouts saved/i })
  })

  it('reports a refused preview and offers another file', async () => {
    installApi({
      previewError: refused(415, 'Only a sliced .gcode.3mf is accepted (got "Goose.3mf").'),
    })
    const onStartOver = vi.fn()
    render(<PlateCompositionIntakePanel file={FILE} onStartOver={onStartOver} />)
    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent(/415/)
    expect(alert).toHaveTextContent('Only a sliced .gcode.3mf is accepted')
    expect(screen.queryByRole('button', { name: /create parts and plate layouts/i })).not.toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: /choose a different file/i }))
    expect(onStartOver).toHaveBeenCalledTimes(1)
  })

  it('tells the operator to update PRO when the server has no such route', async () => {
    installApi({ previewError: refused(404, 'Not Found') })
    render(<PlateCompositionIntakePanel file={FILE} onStartOver={vi.fn()} />)
    expect(await screen.findByRole('alert')).toHaveTextContent(/update PRO/i)
  })

  it('can try the preview again', async () => {
    installApi({ previewError: refused(503, 'The slicer is busy') })
    render(<PlateCompositionIntakePanel file={FILE} onStartOver={vi.fn()} />)
    expect(await screen.findByRole('alert')).toHaveTextContent('The slicer is busy')

    installApi()
    fireEvent.click(screen.getByRole('button', { name: /try again/i }))
    expect(await screen.findByRole('region', { name: 'Plate 1' })).toBeInTheDocument()
  })

  it('says when the work centres and spools could not be loaded, and loads them again on request', async () => {
    installApi({ contextError: refused(500, 'boom') })
    await openPanel()
    expect(await screen.findByText(/couldn.t load work centres and spools/i)).toBeInTheDocument()
    expect(createButton()).toBeDisabled()

    installApi()
    fireEvent.click(screen.getByRole('button', { name: /reload/i }))
    await waitFor(() => expect(createButton()).toBeEnabled())
  })
})
