import { describe, it, expect } from 'vitest'
import { hasStorableThumbnail, thumbnailToFile } from '../productImage'

// 1x1 PNG
const THUMB_B64 =
  'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=='

describe('thumbnailToFile', () => {
  it('decodes the base64 thumbnail into an image file', async () => {
    const file = thumbnailToFile(
      { thumbnail_base64: THUMB_B64, thumbnail_mime: 'image/png' },
      'FG-011'
    )
    expect(file.name).toBe('FG-011.png')
    expect(file.type).toBe('image/png')
    const bytes = new Uint8Array(await file.arrayBuffer())
    // PNG signature
    expect(Array.from(bytes.slice(0, 4))).toEqual([0x89, 0x50, 0x4e, 0x47])
  })

  it('defaults to PNG when the mime type is missing', () => {
    expect(thumbnailToFile({ thumbnail_base64: THUMB_B64 }).type).toBe('image/png')
  })

  it('uses the extension for the mime type', () => {
    const file = thumbnailToFile({ thumbnail_base64: THUMB_B64, thumbnail_mime: 'image/jpeg' })
    expect(file.name).toMatch(/\.jpg$/)
  })

  it('makes the base name safe for a filename', () => {
    const file = thumbnailToFile({ thumbnail_base64: THUMB_B64 }, 'Crystal Dragon/v2')
    expect(file.name).toBe('Crystal-Dragon-v2.png')
  })

  it('returns null without a thumbnail, for bad base64, or an unsupported type', () => {
    expect(thumbnailToFile({})).toBeNull()
    expect(thumbnailToFile({ thumbnail_base64: '%%%not-base64' })).toBeNull()
    expect(thumbnailToFile({ thumbnail_base64: THUMB_B64, thumbnail_mime: 'image/svg+xml' })).toBeNull()
  })
})

describe('hasStorableThumbnail', () => {
  it('needs a thumbnail of an upload-allowed image type', () => {
    expect(hasStorableThumbnail({ thumbnail_base64: THUMB_B64 })).toBe(true)
    expect(hasStorableThumbnail({ thumbnail_base64: THUMB_B64, thumbnail_mime: 'image/bmp' })).toBe(false)
    expect(hasStorableThumbnail(null)).toBe(false)
  })
})
