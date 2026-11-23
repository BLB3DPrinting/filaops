import { render, screen } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach } from 'vitest'

const reloadForNewBuild = vi.fn()
vi.mock('../../lib/staleBuild', async (importOriginal) => ({
  ...(await importOriginal()),
  reloadForNewBuild: (...args) => reloadForNewBuild(...args),
}))

const { default: ErrorBoundary } = await import('../ErrorBoundary')

function Throw({ message }) {
  throw new TypeError(message)
}

const STALE = 'Failed to fetch dynamically imported module: http://localhost/assets/CommandCenter-CAG0geRE.js'

describe('ErrorBoundary after an app update', () => {
  beforeEach(() => {
    reloadForNewBuild.mockReset()
    vi.spyOn(console, 'error').mockImplementation(() => {})
  })

  it('reloads onto the new build instead of showing the error', () => {
    reloadForNewBuild.mockReturnValue(true)
    render(<ErrorBoundary><Throw message={STALE} /></ErrorBoundary>)
    expect(reloadForNewBuild).toHaveBeenCalledTimes(1)
    expect(screen.getByText(/Loading the new version/)).toBeInTheDocument()
    expect(screen.queryByText('Something broke')).not.toBeInTheDocument()
  })

  it('shows the normal error screen when it already reloaded once', () => {
    reloadForNewBuild.mockReturnValue(false)
    render(<ErrorBoundary><Throw message={STALE} /></ErrorBoundary>)
    expect(screen.getByText('Something broke')).toBeInTheDocument()
  })

  it('does not reload for other errors', () => {
    render(<ErrorBoundary><Throw message="Cannot read properties of undefined" /></ErrorBoundary>)
    expect(reloadForNewBuild).not.toHaveBeenCalled()
    expect(screen.getByText('Something broke')).toBeInTheDocument()
  })
})
