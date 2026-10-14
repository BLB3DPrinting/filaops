import { render, screen } from '@testing-library/react'
import { describe, it, expect, vi } from 'vitest'

// 4.3.1 lifted the community staff-seat cap. The page no longer keeps its own
// copy of the cap: the backend (app/core/seat_limits.py) is the only gate, and
// a refused add shows the server's message in a toast. So the page never
// shows a seat banner or disables Add User.

vi.mock('../../../hooks/useApi', () => ({
  useApi: () => ({ get: vi.fn(), post: vi.fn(), patch: vi.fn(), del: vi.fn() }),
}))

vi.mock('../../../components/Toast', () => ({
  useToast: () => ({ error: vi.fn(), success: vi.fn(), warning: vi.fn(), info: vi.fn() }),
}))

vi.mock('../../../components/Modal', () => ({
  default: ({ children }) => <div role="dialog">{children}</div>,
}))

const staff = [
  { id: 1, email: 'owner@example.com', full_name: 'Owner', account_type: 'admin', status: 'active' },
  { id: 2, email: 'op@example.com', full_name: 'Operator', account_type: 'operator', status: 'active' },
]

vi.mock('../../../hooks/useCRUD', () => ({
  useCRUD: () => ({
    items: staff,
    loading: false,
    error: null,
    fetchAll: vi.fn(() => Promise.resolve()),
    refresh: vi.fn(() => Promise.resolve()),
  }),
}))

import AdminUsers from '../AdminUsers'

describe('AdminUsers staff seats', () => {
  it('keeps Add User enabled with more than one active staff account', () => {
    render(<AdminUsers />)
    const add = screen.getByRole('button', { name: /add user/i })
    expect(add).toBeEnabled()
    expect(add).not.toHaveAttribute('title')
  })

  it('shows no seat banner or PRO upsell', () => {
    render(<AdminUsers />)
    expect(screen.queryByText(/staff seat/i)).not.toBeInTheDocument()
    expect(screen.queryByText(/upgrade to pro/i)).not.toBeInTheDocument()
  })
})
