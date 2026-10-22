import { describe, it, expect } from 'vitest'

import { ApiError } from '../../../../lib/apiClient'
import {
  buildPlan,
  buildRows,
  describeIntakeError,
  formatMinutes,
  neededSlots,
  planProblems,
  slotMeta,
  suggestSpool,
} from '../plateCompositionPlan'
import { MATERIALS, PREVIEW } from './plateCompositionFixtures'

const BODY = 'hash:aaa111bbb222'
const BEAK = 'hash:ccc333ddd444'
const WING = 'name:Wing'

const form = (overrides = {}) => ({
  name: 'Goose',
  workCenterId: '3',
  rows: buildRows(PREVIEW, {}),
  spoolIds: { 0: 90, 1: 91 },
  meta: slotMeta(PREVIEW),
  parent: null,
  ...overrides,
})

describe('buildRows', () => {
  it('makes one row per kind of object across all plates, not one per plate', () => {
    const rows = buildRows(PREVIEW, {})
    // The body is on both plates and is still one part.
    expect(rows.map((row) => row.key)).toEqual([BODY, BEAK, WING])
  })

  it('pre-selects the part the API proposes by mesh hash, and creates the rest', () => {
    const [body, beak, wing] = buildRows(PREVIEW, {})
    expect(body.action).toBe('link')
    expect(body.linked).toEqual({ product_id: 7, sku: 'GOOSE-BODY', name: 'Goose body' })
    expect(beak.action).toBe('create')
    expect(beak.linked).toBeNull()
    expect(wing.action).toBe('create')
  })

  it('starts new parts as components, with the API\'s suggested name and SKU', () => {
    const beak = buildRows(PREVIEW, {})[1]
    expect(beak.itemType).toBe('component')
    expect(beak.name).toBe('Beak')
    expect(beak.sku).toBe('GOOSE-BEAK')
  })

  it('lets an edit win over the default', () => {
    const rows = buildRows(PREVIEW, { [BODY]: { action: 'create' }, [BEAK]: { itemType: 'finished_good' } })
    expect(rows[0].action).toBe('create')
    expect(rows[1].itemType).toBe('finished_good')
    expect(rows[2].itemType).toBe('component')
  })
})

describe('neededSlots', () => {
  it('lists the filament slots of the parts being created, and nothing for linked parts', () => {
    expect(neededSlots(buildRows(PREVIEW, {}))).toEqual([0, 1])
    const onlyBodyAndBeak = buildRows(PREVIEW, { [WING]: { action: 'link' } })
    expect(neededSlots(onlyBodyAndBeak)).toEqual([1])
  })
})

describe('suggestSpool', () => {
  const meta = slotMeta(PREVIEW)

  it('reads each slot\'s material and colour from the plates', () => {
    expect(meta[0]).toEqual({ material: 'PLA', colorHex: '#FFFFFF' })
    expect(meta[1]).toEqual({ material: 'PLA', colorHex: '#FFA500' })
  })

  it('suggests the one spool with the same material and colour', () => {
    expect(suggestSpool(meta[1], MATERIALS.items)?.id).toBe(91)
    expect(suggestSpool({ material: 'pla', colorHex: '#ffa500' }, MATERIALS.items)?.id).toBe(91)
  })

  it('suggests nothing when no spool, or more than one, matches', () => {
    expect(suggestSpool({ material: 'PETG', colorHex: '#FFA500' }, MATERIALS.items)).toBeNull()
    const twins = [...MATERIALS.items, { ...MATERIALS.items[1], id: 99 }]
    expect(suggestSpool(meta[1], twins)).toBeNull()
    expect(suggestSpool({ material: null, colorHex: null }, MATERIALS.items)).toBeNull()
  })
})

describe('buildPlan', () => {
  it('builds the CompositionPlan PRO expects', () => {
    expect(buildPlan(form())).toEqual({
      name: 'Goose',
      print_work_center_id: 3,
      slot_spools: [
        { slot: 0, spool_product_id: 90, filament_type: 'PLA', color_hex: '#FFFFFF' },
        { slot: 1, spool_product_id: 91, filament_type: 'PLA', color_hex: '#FFA500' },
      ],
      parts: [
        { key: BODY, action: 'link', product_id: 7 },
        { key: BEAK, action: 'create', name: 'Beak', sku: 'GOOSE-BEAK', item_type: 'component' },
        { key: WING, action: 'create', name: 'Wing', sku: 'GOOSE-WING', item_type: 'component' },
      ],
    })
  })

  it('sends the item type chosen for a new part', () => {
    const rows = buildRows(PREVIEW, { [BEAK]: { itemType: 'finished_good' } })
    const beak = buildPlan(form({ rows })).parts.find((part) => part.key === BEAK)
    expect(beak.item_type).toBe('finished_good')
  })

  it('leaves the SKU out when it is blank, so PRO makes one', () => {
    const rows = buildRows(PREVIEW, { [BEAK]: { sku: '  ' } })
    const beak = buildPlan(form({ rows })).parts.find((part) => part.key === BEAK)
    expect(beak).not.toHaveProperty('sku')
  })

  it('only sends spools for the slots a new part uses', () => {
    const rows = buildRows(PREVIEW, { [WING]: { action: 'link', linked: { product_id: 8 } } })
    expect(buildPlan(form({ rows })).slot_spools.map((spool) => spool.slot)).toEqual([1])
  })

  it('adds the assembly parent, with a quantity only for parts that go in it', () => {
    const rows = buildRows(PREVIEW, { [BEAK]: { perParent: '2' }, [WING]: { perParent: '0' } })
    const parent = {
      name: 'Goose (assembled)',
      sku: 'GOOSE-ASM',
      workCenterId: '4',
      runMinutes: '15',
      setupMinutes: '',
    }
    expect(buildPlan(form({ rows, parent })).parent).toEqual({
      name: 'Goose (assembled)',
      sku: 'GOOSE-ASM',
      assembly_work_center_id: 4,
      assembly_run_time_minutes: 15,
      assembly_setup_minutes: 0,
      quantities: { [BODY]: 1, [BEAK]: 2 },
    })
  })

  it('has no parent unless one was asked for', () => {
    expect(buildPlan(form())).not.toHaveProperty('parent')
  })
})

describe('planProblems', () => {
  const problems = (overrides) => planProblems(form(overrides))

  it('finds nothing wrong with a complete form', () => {
    expect(problems({})).toEqual([])
  })

  it('wants a plan name and a print work centre', () => {
    expect(problems({ name: ' ' })).toEqual([expect.stringMatching(/name/i)])
    expect(problems({ workCenterId: '' })).toEqual([expect.stringMatching(/print work cent/i)])
  })

  it('wants a spool for every slot a new part uses', () => {
    expect(problems({ spoolIds: { 0: 90 } })).toEqual([expect.stringMatching(/spool.*slot 2/i)])
  })

  it('wants a name for a new part and a part for a link', () => {
    const rows = buildRows(PREVIEW, { [BEAK]: { name: '' }, [BODY]: { linked: null } })
    expect(problems({ rows })).toEqual([
      expect.stringMatching(/Body.*existing part/i),
      expect.stringMatching(/Beak.*name/i),
    ])
  })

  it('wants an assembly work centre and at least one part for a parent', () => {
    const none = buildRows(PREVIEW, {
      [BODY]: { perParent: '0' },
      [BEAK]: { perParent: '' },
      [WING]: { perParent: '0' },
    })
    const parent = { name: 'Goose', sku: '', workCenterId: '', runMinutes: '', setupMinutes: '' }
    expect(problems({ parent })).toEqual([expect.stringMatching(/assembly work cent/i)])
    expect(problems({ parent: { ...parent, workCenterId: '4' }, rows: none })).toEqual([
      expect.stringMatching(/at least one part/i),
    ])
  })
})

describe('describeIntakeError', () => {
  it('uses the text PRO answered with', () => {
    const error = new ApiError('x', 409, { detail: "SKU 'GOOSE-BEAK' already exists." })
    expect(describeIntakeError(error)).toEqual({ status: 409, message: "SKU 'GOOSE-BEAK' already exists." })
  })

  it('reads a validation error list, one line per problem', () => {
    const error = new ApiError('HTTP 422', 422, {
      detail: [
        { type: 'value_error', loc: ['parts', 1], msg: 'Value error, link needs a product_id' },
        { type: 'missing', loc: ['print_work_center_id'], msg: 'Field required' },
      ],
    })
    expect(describeIntakeError(error).message).toBe(
      'parts.1: link needs a product_id; print_work_center_id: Field required',
    )
  })

  it('points at the PRO update when the route is not there', () => {
    const error = new ApiError('Not Found', 404, { detail: 'Not Found' })
    expect(describeIntakeError(error).message).toMatch(/update.*PRO|PRO.*update/i)
  })

  it('keeps a real "part not found" 404 as it is', () => {
    const error = new ApiError('x', 404, { detail: 'part(s) 99 not found' })
    expect(describeIntakeError(error).message).toBe('part(s) 99 not found')
  })

  it('says so when the server could not be reached', () => {
    const error = new ApiError('HTTP 0', 0, 'Failed to fetch')
    expect(describeIntakeError(error)).toEqual({
      status: 0,
      message: expect.stringMatching(/reach the server/i),
    })
  })

  it('falls back to the error\'s own message', () => {
    expect(describeIntakeError(new Error('boom'))).toEqual({ status: 0, message: 'boom' })
  })
})

describe('formatMinutes', () => {
  it('writes hours and minutes', () => {
    expect(formatMinutes(195)).toBe('3h 15m')
    expect(formatMinutes(60)).toBe('1h')
    expect(formatMinutes(3)).toBe('3m')
    expect(formatMinutes(0.4)).toBe('<1m')
    expect(formatMinutes(null)).toBe('')
  })
})
