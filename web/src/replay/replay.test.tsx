import { act, fireEvent, render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import recorded from './run.json'
import type { RunEvent } from '../state/types'
import { holdAfter, scrub } from './clock'
import { Replay } from './Replay'

const events = recorded as RunEvent[]
afterEach(() => { vi.useRealTimers(); vi.restoreAllMocks() })

describe('replay clock', () => {
  it('paces by event type and speed', () => {
    const said = { seq: 1, run_id: 'x', t: 0, type: 'orchestrator_said' } as RunEvent
    expect(holdAfter(said, 1)).toBe(1600)
    expect(holdAfter(said, 4)).toBe(400)
    expect(holdAfter({ ...said, type: 'usage' }, 1)).toBe(0)
    expect(holdAfter(undefined)).toBe(0)
  })

  it('scrubs machine paths and secrets', () => {
    const out = scrub([{ seq: 1, run_id: 'x', t: 0, type: 'run_started', workspace: '/home/me/runs/w', repo: 'C:\\code',
      task: 'see /Users/me/secret.txt and sk-ant-abc123' } as RunEvent])[0]
    expect(out.workspace).toBeNull()
    expect(out.repo).toBeNull()
    expect(out.task).toBe('see … and [secret]')
  })

  it('the bundled run has no machine paths left after scrubbing', () => {
    expect(JSON.stringify(scrub(events))).not.toMatch(/\/tmp\/|\/home\/|\/Users\//)
  })
})

describe('Replay', () => {
  it('plays the whole run with no network calls, then offers Play again', async () => {
    vi.useFakeTimers()
    const fetchSpy = vi.spyOn(globalThis, 'fetch')
    render(<MemoryRouter><Replay events={scrub(events)} /></MemoryRouter>)
    expect(screen.getByText(`1 / ${events.length}`)).toBeInTheDocument()
    for (let i = 0; i < events.length; i++) await act(async () => { vi.advanceTimersByTime(2000) })
    expect(screen.getByRole('heading', { name: 'Replay finished' })).toBeInTheDocument()
    expect(screen.getByText(`${events.length} / ${events.length}`)).toBeInTheDocument()
    expect(fetchSpy).not.toHaveBeenCalled()
    fireEvent.click(screen.getAllByRole('button', { name: 'Play again' })[0])
    expect(screen.getByText(`1 / ${events.length}`)).toBeInTheDocument()
  })

  it('pauses, changes speed, and jumps with the position slider', async () => {
    vi.useFakeTimers()
    render(<MemoryRouter><Replay events={scrub(events)} /></MemoryRouter>)
    fireEvent.click(screen.getByRole('button', { name: 'Pause' }))
    await act(async () => { vi.advanceTimersByTime(10000) })
    expect(screen.getByText(`1 / ${events.length}`)).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: '4×' }))
    expect(screen.getByRole('button', { name: '4×' })).toHaveAttribute('aria-pressed', 'true')
    fireEvent.change(screen.getByLabelText('Position'), { target: { value: '40' } })
    expect(screen.getByText(`40 / ${events.length}`)).toBeInTheDocument()
    expect(screen.getByText('Research wallets')).toBeInTheDocument()
  })
})
