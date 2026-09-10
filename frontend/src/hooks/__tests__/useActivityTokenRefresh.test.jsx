import { act, renderHook } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import useActivityTokenRefresh from '../useActivityTokenRefresh'

describe('useActivityTokenRefresh', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date('2026-07-28T00:00:00Z'))
    localStorage.setItem('adminUser', JSON.stringify({ id: 1 }))
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true }))
  })

  afterEach(() => {
    localStorage.clear()
    vi.unstubAllGlobals()
    vi.useRealTimers()
  })

  it('initializes activity on mount so the first interval refreshes an active session', async () => {
    renderHook(() => useActivityTokenRefresh())

    await act(async () => {
      vi.advanceTimersByTime(10 * 60 * 1000)
      await Promise.resolve()
    })

    expect(fetch).toHaveBeenCalledWith(
      expect.stringMatching(/\/api\/v1\/auth\/refresh$/),
      expect.objectContaining({ method: 'POST', credentials: 'include' }),
    )
  })
})
