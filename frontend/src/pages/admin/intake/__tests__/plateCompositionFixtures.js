/**
 * Shared fixtures for the plate-composition intake tests: what PRO's
 * POST /api/v1/pro/intake/compositions answers for a vendor file, and the
 * Core catalog the panel pairs it with.
 */

const BODY_EXISTING = { product_id: 7, sku: 'GOOSE-BODY', name: 'Goose body' }

const bodyGroup = {
  key: 'hash:aaa111bbb222',
  name: 'Body',
  names: ['Body'],
  count: 4,
  identify_ids: [10, 11, 12, 13],
  mesh_hash: 'aaa111bbb222',
  size_mm: { x: 60, y: 40, z: 30 },
  volume_mm3: 40000,
  piece_grams: 25,
  piece_minutes: 30,
  slot: 0,
  slot_grams: { 0: 25 },
  source: 'per_object',
  existing_parts: [BODY_EXISTING],
}

const beakGroup = {
  key: 'hash:ccc333ddd444',
  name: 'Beak',
  names: ['Beak'],
  count: 16,
  identify_ids: [20, 21, 22, 23],
  mesh_hash: 'ccc333ddd444',
  size_mm: { x: 10, y: 8, z: 6 },
  volume_mm3: 300,
  piece_grams: 1.2,
  piece_minutes: 3,
  slot: 1,
  slot_grams: { 1: 1.2 },
  source: 'per_object',
  existing_parts: [],
}

const wingGroup = {
  key: 'name:Wing',
  name: 'Wing',
  names: ['Wing'],
  count: 2,
  identify_ids: [30, 31],
  mesh_hash: null,
  size_mm: null,
  volume_mm3: null,
  piece_grams: 8,
  piece_minutes: 12,
  slot: 0,
  slot_grams: { 0: 8 },
  source: 'volume',
  existing_parts: [],
}

const SLOTS = [
  { slot: 0, grams: 140, material: 'PLA', color_hex: '#FFFFFF' },
  { slot: 1, grams: 19.2, material: 'PLA', color_hex: '#FFA500' },
]

const part = (group, plates, suggested) => ({
  ...group,
  suggested_sku: suggested.sku,
  suggested_name: suggested.name,
  first_plate: plates[0].plate_index,
  plates,
})

/** A two-plate vendor file: plate 1 is 4 bodies + 16 beaks, plate 2 is 4 bodies + 2 wings. */
export const PREVIEW = {
  mode: 'preview',
  filename: 'Goose.gcode.3mf',
  model_name: 'Goose',
  printer: { model: 'A1', nozzle: 0.4, name: 'Bambu Lab A1' },
  plates: [
    {
      plate_index: 1,
      name: 'Plate 1',
      plate_time_minutes: 195,
      total_grams: 124.2,
      outside_grams: 5,
      object_count: 20,
      label_objects: true,
      slots: SLOTS,
      groups: [bodyGroup, beakGroup],
      warnings: [],
    },
    {
      plate_index: 2,
      name: 'Plate 2',
      plate_time_minutes: 144,
      total_grams: 116,
      outside_grams: 0,
      object_count: 6,
      label_objects: false,
      slots: [SLOTS[0]],
      groups: [bodyGroup, wingGroup],
      warnings: ['no object markers in this plate\'s G-code (label objects was off)'],
    },
  ],
  parts: [
    part(bodyGroup, [{ plate_index: 1, count: 4 }, { plate_index: 2, count: 4 }], {
      sku: 'GOOSE-BODY',
      name: 'Body',
    }),
    part(beakGroup, [{ plate_index: 1, count: 16 }], { sku: 'GOOSE-BEAK', name: 'Beak' }),
    part(wingGroup, [{ plate_index: 2, count: 2 }], { sku: 'GOOSE-WING', name: 'Wing' }),
  ],
  warnings: [],
}

/** Core's GET /api/v1/pro/intake/context, trimmed to what the panel reads. */
export const CONTEXT = {
  work_centers: [
    { id: 3, code: 'PRINT', name: 'Printers' },
    { id: 4, code: 'ASSEMBLY', name: 'Assembly bench' },
  ],
  printer_work_center_map: { A1: { work_center_id: 3, work_center_code: 'PRINT' } },
}

/** Core's GET /api/v1/materials/for-bom items. */
export const MATERIALS = {
  items: [
    { id: 90, sku: 'MAT-PLA-WHT', name: 'PLA White', material_code: 'PLA', color_code: 'WHT', color_hex: '#FFFFFF' },
    { id: 91, sku: 'MAT-PLA-ORG', name: 'PLA Orange', material_code: 'PLA', color_code: 'ORG', color_hex: '#FFA500' },
    { id: 92, sku: 'MAT-PLA-BLK', name: 'PLA Black', material_code: 'PLA', color_code: 'BLK', color_hex: '#000000' },
  ],
}

/** What POST /intake/compositions answers once a plan is saved. */
export const COMMITTED = {
  mode: 'committed',
  parts: [
    { key: 'hash:aaa111bbb222', action: 'link', product_id: 7, sku: null },
    { key: 'hash:ccc333ddd444', action: 'create', product_id: 501, sku: 'GOOSE-BEAK' },
    { key: 'name:Wing', action: 'create', product_id: 502, sku: 'GOOSE-WING' },
  ],
  compositions: [
    {
      plate_index: 1,
      composition_id: 61,
      code: 'GOOSE-P01',
      printer_model: 'A1',
      version_id: 71,
      version: 1,
      locked: false,
      plate_time_minutes: 195,
      total_grams: 124.2,
      items: [],
    },
    {
      plate_index: 2,
      composition_id: 62,
      code: 'GOOSE-P02',
      printer_model: 'A1',
      version_id: 72,
      version: 1,
      locked: false,
      plate_time_minutes: 144,
      total_grams: 116,
      items: [],
    },
  ],
  parent: null,
}
