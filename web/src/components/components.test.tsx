import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import demo from '../test/fixtures/demo.json'
import { NewRun } from '../pages/NewRun'
import { reduce, reduceAll, emptyRun } from '../state/reducer'
import type { RunEvent } from '../state/types'
import { Character } from './Character'
import { Announcer, OutcomeCard } from './RunParts'
import { TaskCard } from './TaskCard'

const events = demo as RunEvent[]
const finished = reduceAll(events)

afterEach(() => vi.restoreAllMocks())

describe('Character', () => {
  it('has a label when given one, and is hidden otherwise', () => {
    const { container, rerender } = render(<Character color="#4FC7B8" mood="waiting" label="analyst, waiting on checker" />)
    expect(screen.getByRole('img', { name: 'analyst, waiting on checker' })).toBeInTheDocument()
    rerender(<Character color="#4FC7B8" mood="happy" />)
    expect(container.querySelector('[aria-hidden]')).toBeInTheDocument()
  })
})

describe('TaskCard', () => {
  it('shows every state with its status line', () => {
    const r = finished
    const { rerender } = render(<TaskCard task={r.tasks['analysis-1']} run={r} />)
    expect(screen.getByText('Passed on try 2')).toBeInTheDocument()
    rerender(<TaskCard task={r.tasks['report-1']} run={r} />)
    expect(screen.getByText('Replaced by Rewrite the report')).toBeInTheDocument()
    rerender(<TaskCard task={{ ...r.tasks['report-1'], status: 'failed' }} run={r} />)
    expect(screen.getByText('Failed · 3 tries')).toBeInTheDocument()
    rerender(<TaskCard task={{ ...r.tasks['report-1'], status: 'pending', history: [], attempts: 0 }} run={{ ...r, status: 'running' }} />)
    expect(screen.getByText('Queued')).toBeInTheDocument()
  })

  it('opens with Enter, shows checker notes, closes with Escape', async () => {
    const user = userEvent.setup()
    render(<TaskCard task={finished.tasks['report-1']} run={finished} />)
    const btn = screen.getByRole('button', { name: /writer/ })
    expect(btn).toHaveAttribute('aria-expanded', 'false')
    btn.focus()
    await user.keyboard('{Enter}')
    expect(btn).toHaveAttribute('aria-expanded', 'true')
    expect(screen.getByText(/Sources list has 6 URLs/)).toBeInTheDocument()
    await user.keyboard('{Escape}')
    expect(btn).toHaveAttribute('aria-expanded', 'false')
  })
})

describe('OutcomeCard', () => {
  it('shows All done with the main file for a finished run', () => {
    render(<MemoryRouter><OutcomeCard run={finished} /></MemoryRouter>)
    expect(screen.getByText('All done')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Open report.md' })).toHaveAttribute('href', `/runs/${finished.id}/files/report.md`)
  })

  it('explains an expired login', () => {
    const crashed = reduce(reduce(emptyRun(), { seq: 1, run_id: 'x', t: 1, type: 'run_started', task: 't' }),
      { seq: 2, run_id: 'x', t: 2, type: 'run_failed', error: 'ProcessError', kind: 'auth', hint: 'login' })
    render(<MemoryRouter><OutcomeCard run={crashed} /></MemoryRouter>)
    expect(screen.getByText('Your Claude login expired')).toBeInTheDocument()
    expect(screen.getByText('/login')).toBeInTheDocument()
  })
})

describe('Announcer', () => {
  it('stays quiet on replay, then announces new events', () => {
    const half = events.slice(0, 30).reduce(reduce, emptyRun())
    const { rerender } = render(<Announcer run={half} />)
    expect(screen.getByRole('status')).toHaveTextContent('')
    const more = events.slice(30).reduce(reduce, half)
    rerender(<Announcer run={more} />)
    expect(screen.getByRole('status').textContent || screen.getByRole('alert').textContent).not.toBe('')
  })
})

describe('NewRun', () => {
  it('starts a run with the chosen options', async () => {
    const calls: { url: string; body?: unknown }[] = []
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
      const url = String(input)
      calls.push({ url, body: init?.body ? JSON.parse(String(init.body)) : undefined })
      if (url.startsWith('/api/catalog')) {
        return new Response(JSON.stringify([
          { id: 'browser', kind: 'mcp', description: 'Browser', risk: 'read', enabled: true, requires: null, unavailable: null },
          { id: 'gmail', kind: 'mcp', description: 'Mail', risk: 'outward', enabled: true, requires: null, unavailable: 'set GMAIL_MCP_URL in .env' },
        ]), { headers: { 'content-type': 'application/json' } })
      }
      return new Response(JSON.stringify({ id: 'new-run' }), { status: 201, headers: { 'content-type': 'application/json' } })
    })
    const user = userEvent.setup()
    render(<MemoryRouter><NewRun /></MemoryRouter>)
    const start = screen.getByRole('button', { name: 'Start run' })
    expect(start).toBeDisabled()
    await user.type(screen.getByLabelText('Task'), 'Write a haiku to haiku.md')
    await user.click(screen.getByRole('button', { name: 'Options' }))
    await user.click(screen.getByLabelText(/Allow shell commands/))
    await waitFor(() => expect(screen.getByRole('button', { name: /gmail/ })).toBeDisabled())
    await act(async () => { fireEvent.click(start) })
    const post = calls.find((c) => c.url === '/api/runs')
    expect(post?.body).toMatchObject({ task: 'Write a haiku to haiku.md', options: { allow_bash: true, max_cost: 5 } })
  })
})
