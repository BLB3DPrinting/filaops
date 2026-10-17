import { describe, it, expect } from 'vitest'
import {
  filenameFromContentDisposition,
  resolveSliceSource,
} from '../sliceFileAttach'

describe('resolveSliceSource', () => {
  const sliced = new File(['PK'], 'Widget.GCODE.3MF')
  const raw = new File(['PK'], 'widget.3mf')

  it('uses the worker artifact for server-sliced inputs', () => {
    const parse = { gcode_artifact_id: 'a', gcode_3mf_artifact_id: 'b' }
    expect(resolveSliceSource(parse, raw)).toEqual({ kind: 'artifact', artifactId: 'b' })
  })

  it('uses the uploaded file for a pre-sliced .gcode.3mf', () => {
    expect(resolveSliceSource({}, sliced)).toEqual({ kind: 'upload', file: sliced })
  })

  it('never treats a raw .3mf source as the slice file', () => {
    expect(resolveSliceSource({}, raw)).toBeNull()
  })

  it('returns nothing for a server-sliced input with no .gcode.3mf export', () => {
    expect(resolveSliceSource({ gcode_artifact_id: 'a' }, sliced)).toBeNull()
  })
})

describe('filenameFromContentDisposition', () => {
  it('reads a quoted filename', () => {
    expect(filenameFromContentDisposition('attachment; filename="Tiny Chick.gcode.3mf"'))
      .toBe('Tiny Chick.gcode.3mf')
  })

  it('prefers the RFC 5987 encoded form', () => {
    expect(
      filenameFromContentDisposition(
        "attachment; filename*=utf-8''Caf%C3%A9.gcode.3mf; filename=\"Cafe.gcode.3mf\""
      )
    ).toBe('Café.gcode.3mf')
  })

  it('returns null without a header', () => {
    expect(filenameFromContentDisposition(null)).toBeNull()
  })
})
