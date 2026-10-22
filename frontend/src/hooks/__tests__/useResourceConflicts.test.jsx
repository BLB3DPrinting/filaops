/**
 * Tests for useResourceConflicts — the scheduler modal's live conflict check.
 *
 * While editing an already-scheduled operation the modal names that
 * operation (`operationId`) so the SERVER can leave it — and, when it keeps
 * its co-booked block's slot, its block siblings — out of the conflicts.
 * The browser sends one id for the operation being edited and never a list
 * of ids to ignore: the sibling set is derived from the stored window on
 * the server.
 */
import { renderHook, act } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { useResourceConflicts } from '../useResources'

const START = '2026-06-11T10:00'
const END = '2026-06-11T13:00'

function stubConflicts(conflicts = []) {
  const fetchSpy = vi.fn().mockResolvedValue({
    ok: true,
    json: async () => ({ conflicts }),
  })
  vi.stubGlobal('fetch', fetchSpy)
  return fetchSpy
}

async function settle() {
  // Debounce is 300ms
  await act(async () => { await vi.advanceTimersByTimeAsync(400) })
}

function lastRequest(fetchSpy) {
  const [url] = fetchSpy.mock.calls.at(-1)
  return new URL(url, 'http://localhost')
}

beforeEach(() => {
  vi.useFakeTimers({ shouldAdvanceTime: true })
})

afterEach(() => {
  vi.useRealTimers()
  vi.unstubAllGlobals()
})

describe('useResourceConflicts', () => {
  it('queries the live conflict endpoint with the machine and window', async () => {
    const fetchSpy = stubConflicts()
    renderHook(() => useResourceConflicts(7, START, END, true))
    await settle()

    const url = lastRequest(fetchSpy)
    expect(url.pathname).toBe('/api/v1/scheduling/resource-conflicts')
    expect(url.searchParams.get('resource_id')).toBe('7')
    expect(url.searchParams.get('is_printer')).toBe('true')
    expect(url.searchParams.get('start')).toBe(new Date(START).toISOString())
    expect(url.searchParams.get('end')).toBe(new Date(END).toISOString())
  })

  it('names no operation when none is being edited', async () => {
    const fetchSpy = stubConflicts()
    renderHook(() => useResourceConflicts(7, START, END, true))
    await settle()

    expect(lastRequest(fetchSpy).searchParams.has('operation_id')).toBe(false)
  })

  it('names the operation being edited', async () => {
    const fetchSpy = stubConflicts()
    renderHook(() => useResourceConflicts(7, START, END, true, 50))
    await settle()

    expect(lastRequest(fetchSpy).searchParams.get('operation_id')).toBe('50')
  })

  it('never sends a list of ids to exclude', async () => {
    const fetchSpy = stubConflicts()
    renderHook(() => useResourceConflicts(7, START, END, true, 50))
    await settle()

    const names = [...lastRequest(fetchSpy).searchParams.keys()]
    expect(names.filter((n) => /exclude|sibling|block/i.test(n))).toEqual([])
  })

  it('reports whatever the server returns as conflicts', async () => {
    const conflicts = [{ type: 'operation', operation_id: 51, po_code: 'PO-2' }]
    stubConflicts(conflicts)
    const { result } = renderHook(() => useResourceConflicts(7, START, END, true, 50))
    await settle()

    expect(result.current.conflicts).toEqual(conflicts)
    expect(result.current.hasConflicts).toBe(true)
  })

  it('has no conflicts when the server returns none (the unchanged block slot)', async () => {
    stubConflicts([])
    const { result } = renderHook(() => useResourceConflicts(7, START, END, true, 50))
    await settle()

    expect(result.current.conflicts).toEqual([])
    expect(result.current.hasConflicts).toBe(false)
  })

  it('checks again when the edited operation changes', async () => {
    const fetchSpy = stubConflicts()
    const { rerender } = renderHook(
      ({ opId }) => useResourceConflicts(7, START, END, true, opId),
      { initialProps: { opId: 50 } },
    )
    await settle()
    expect(fetchSpy).toHaveBeenCalledTimes(1)

    rerender({ opId: 51 })
    await settle()

    expect(fetchSpy).toHaveBeenCalledTimes(2)
    expect(lastRequest(fetchSpy).searchParams.get('operation_id')).toBe('51')
  })

  it('does not call the server without a machine and window', async () => {
    const fetchSpy = stubConflicts()
    renderHook(() => useResourceConflicts(null, START, END, false, 50))
    await settle()

    expect(fetchSpy).not.toHaveBeenCalled()
  })
})

describe('useResourceConflicts — overlapping requests', () => {
  /** A fetch whose responses the test resolves by hand, in any order. */
  function stubDeferredFetch() {
    const pending = []
    const fetchSpy = vi.fn(() => new Promise((resolve) => { pending.push(resolve) }))
    vi.stubGlobal('fetch', fetchSpy)
    const respond = async (index, conflicts) => {
      await act(async () => {
        pending[index]({ ok: true, json: async () => ({ conflicts }) })
      })
    }
    return { fetchSpy, respond }
  }

  it('ignores a slow response that arrives after a newer request has answered', async () => {
    const { fetchSpy, respond } = stubDeferredFetch()
    const { result, rerender } = renderHook(
      ({ opId }) => useResourceConflicts(7, START, END, true, opId),
      { initialProps: { opId: 50 } },
    )
    await settle()
    rerender({ opId: 51 })
    await settle()
    expect(fetchSpy).toHaveBeenCalledTimes(2)

    const fresh = [{ type: 'operation', operation_id: 61 }]
    const stale = [{ type: 'operation', operation_id: 60 }]
    await respond(1, fresh)
    await respond(0, stale)

    expect(result.current.conflicts).toEqual(fresh)
    expect(result.current.checking).toBe(false)
  })

  it('does not report a response for an older window once the inputs have changed', async () => {
    const { respond, fetchSpy } = stubDeferredFetch()
    const { result, rerender } = renderHook(
      ({ end }) => useResourceConflicts(7, START, end, true, 50),
      { initialProps: { end: END } },
    )
    await settle()
    rerender({ end: '2026-06-11T15:00' })
    await settle()
    expect(fetchSpy).toHaveBeenCalledTimes(2)

    await respond(0, [{ type: 'operation', operation_id: 60 }])

    // The newer request has not answered yet: still checking, nothing stale shown
    expect(result.current.conflicts).toEqual([])
    expect(result.current.checking).toBe(true)
  })

  it('stops reporting "checking" when the inputs are cleared while a request is in flight', async () => {
    const { respond } = stubDeferredFetch()
    const { result, rerender } = renderHook(
      ({ resourceId }) => useResourceConflicts(resourceId, START, END, true, 50),
      { initialProps: { resourceId: 7 } },
    )
    await settle()
    expect(result.current.checking).toBe(true)

    rerender({ resourceId: null })
    await settle()
    await respond(0, [{ type: 'operation', operation_id: 60 }])

    expect(result.current.checking).toBe(false)
    expect(result.current.conflicts).toEqual([])
  })
})
