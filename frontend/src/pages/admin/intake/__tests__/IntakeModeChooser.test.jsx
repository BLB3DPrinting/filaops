import { render, screen, fireEvent } from '@testing-library/react'
import { describe, it, expect, vi } from 'vitest'

import IntakeModeChooser from '../IntakeModeChooser'

const plateButton = () => screen.getByRole('button', { name: /intake one plate/i })
const assemblyButton = () => screen.getByRole('button', { name: /intake whole model/i })

describe('IntakeModeChooser', () => {
  it('renders both intake modes, with the plate count in the assembly option', () => {
    render(<IntakeModeChooser mode="plate" onModeChange={vi.fn()} plateCount={4} />)

    expect(
      screen.getByRole('heading', { name: 'How do you want to intake this file?' }),
    ).toBeInTheDocument()
    expect(plateButton()).toBeInTheDocument()
    expect(assemblyButton()).toHaveTextContent('Intake whole model as an assembly (4 plates)')
  })

  it('marks the current mode as pressed', () => {
    const { rerender } = render(
      <IntakeModeChooser mode="plate" onModeChange={vi.fn()} plateCount={4} />,
    )
    expect(plateButton()).toHaveAttribute('aria-pressed', 'true')
    expect(assemblyButton()).toHaveAttribute('aria-pressed', 'false')

    rerender(<IntakeModeChooser mode="assembly" onModeChange={vi.fn()} plateCount={4} />)
    expect(plateButton()).toHaveAttribute('aria-pressed', 'false')
    expect(assemblyButton()).toHaveAttribute('aria-pressed', 'true')
  })

  it('calls the setter with the mode the operator picks', () => {
    const onModeChange = vi.fn()
    render(<IntakeModeChooser mode="plate" onModeChange={onModeChange} plateCount={4} />)

    fireEvent.click(assemblyButton())
    expect(onModeChange).toHaveBeenLastCalledWith('assembly')

    fireEvent.click(plateButton())
    expect(onModeChange).toHaveBeenLastCalledWith('plate')
    expect(onModeChange).toHaveBeenCalledTimes(2)
  })
})
