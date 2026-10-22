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
