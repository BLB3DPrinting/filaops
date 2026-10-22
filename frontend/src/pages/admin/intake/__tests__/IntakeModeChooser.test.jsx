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

describe('IntakeModeChooser plate layouts option', () => {
  const layoutsButton = () =>
    screen.queryByRole('button', { name: /parts and plate layouts/i })

  it('does not show the plate layouts option unless asked to', () => {
    render(<IntakeModeChooser mode="plate" onModeChange={vi.fn()} plateCount={4} />)
    expect(layoutsButton()).not.toBeInTheDocument()
  })

  it('shows it beside the two existing options, whose wording is unchanged', () => {
    render(
      <IntakeModeChooser mode="plate" onModeChange={vi.fn()} plateCount={4} showPlateLayouts />,
    )
    expect(layoutsButton()).toBeInTheDocument()
    expect(plateButton()).toHaveTextContent('Pick a single plate below')
    expect(assemblyButton()).toHaveTextContent('Intake whole model as an assembly (4 plates)')
  })

  it('reports the mode the operator picks and marks it pressed', () => {
    const onModeChange = vi.fn()
    const { rerender } = render(
      <IntakeModeChooser
        mode="plate"
        onModeChange={onModeChange}
        plateCount={4}
        isRaw={false}
        showPlateLayouts
      />,
    )
    fireEvent.click(layoutsButton())
    expect(onModeChange).toHaveBeenLastCalledWith('plateLayouts')

    rerender(
      <IntakeModeChooser
        mode="plateLayouts"
        onModeChange={onModeChange}
        plateCount={4}
        isRaw={false}
        showPlateLayouts
      />,
    )
    expect(layoutsButton()).toHaveAttribute('aria-pressed', 'true')
    expect(plateButton()).toHaveAttribute('aria-pressed', 'false')
  })

  it('leaves out the assembly option for a sliced file, which cannot be sliced again', () => {
    render(
      <IntakeModeChooser
        mode="plate"
        onModeChange={vi.fn()}
        plateCount={4}
        isRaw={false}
        showPlateLayouts
      />,
    )
    expect(screen.queryByRole('button', { name: /intake whole model/i })).not.toBeInTheDocument()
    expect(plateButton()).toBeInTheDocument()
    expect(layoutsButton()).toBeEnabled()
  })

  it('shows the option disabled, with the reason, for a raw file that is not sliced yet', () => {
    const onModeChange = vi.fn()
    render(
      <IntakeModeChooser mode="plate" onModeChange={onModeChange} plateCount={4} showPlateLayouts />,
    )
    // A raw .3mf has no per-plate G-code: PRO only reads a sliced .gcode.3mf.
    // (isRaw defaults to true, which keeps existing callers unchanged.)
    expect(layoutsButton()).toBeDisabled()
    expect(layoutsButton()).toHaveTextContent(/sliced \.gcode\.3mf/i)
    fireEvent.click(layoutsButton())
    expect(onModeChange).not.toHaveBeenCalled()
  })
})
