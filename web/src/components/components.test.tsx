import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import demo from '../test/fixtures/demo.json'
import { NewRun } from '../pages/NewRun'
import { reduce, reduceAll, emptyRun } from '../state/reducer'
import type { RunEvent } from '../state/types'
import { Character } from './Character'
import { Announcer, ConfirmDialog, OutcomeCard } from './RunParts'
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

  it('names the card once: agent, title, status', () => {
    render(<TaskCard task={finished.tasks['analysis-1']} run={finished} />)
    const name = screen.getByRole('button').textContent?.replace(/\s+/g, ' ').trim()
    expect(name).toBe(`${finished.tasks['analysis-1'].agent}: ${finished.tasks['analysis-1'].title}, Passed on try 2, model sonnet ↑, stepped up`)
    expect(screen.queryByRole('img')).toBeNull()
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
  it('stays quiet for history, however many batches it arrives in, then announces new events', () => {
    const historyEnd = events[29].seq
    const a = events.slice(0, 10).reduce(reduce, emptyRun())
    const { rerender } = render(<Announcer run={a} quietThrough={null} />)    // last_seq not known yet
    const b = events.slice(10, 20).reduce(reduce, a)
    rerender(<Announcer run={b} quietThrough={historyEnd} />)
    const c = events.slice(20, 30).reduce(reduce, b)
    rerender(<Announcer run={c} quietThrough={historyEnd} />)
    expect(screen.getByRole('status')).toHaveTextContent('')
    expect(screen.getByRole('alert')).toHaveTextContent('')
    const more = events.slice(30).reduce(reduce, c)
    rerender(<Announcer run={more} quietThrough={historyEnd} />)
    expect((screen.getByRole('status').textContent || '') + (screen.getByRole('alert').textContent || '')).not.toBe('')
  })

  it('reads every item of a batch, not only the last one', () => {
    const base = emptyRun()
    const { rerender } = render(<Announcer run={base} quietThrough={0} />)
    rerender(<Announcer run={{ ...base, announcements: [{ seq: 5, text: 'Rewrite the report passed' }, { seq: 6, text: 'Run finished' }] }} quietThrough={0} />)
    expect(screen.getByRole('status')).toHaveTextContent('Rewrite the report passed. Run finished')
  })
})

describe('ConfirmDialog', () => {
  it('moves focus in, keeps Tab inside, and closes on Escape', async () => {
    const user = userEvent.setup()
    const onClose = vi.fn()
    render(<><button>outside</button><ConfirmDialog title="Stop this run?" body="b" confirm="Stop run" cancel="Keep running" danger onConfirm={() => {}} onClose={onClose} /></>)
    expect(screen.getByRole('button', { name: 'Keep running' })).toHaveFocus()
    await user.tab()
    expect(screen.getByRole('button', { name: 'Stop run' })).toHaveFocus()
    await user.tab()
    expect(screen.getByRole('button', { name: 'Keep running' })).toHaveFocus()
    await user.tab({ shift: true })
    expect(screen.getByRole('button', { name: 'Stop run' })).toHaveFocus()
    await user.keyboard('{Escape}')
    expect(onClose).toHaveBeenCalled()
  })
})

describe('NewRun', () => {
  it('starts a run with the chosen options', async () => {
    const calls: { url: string; body?: unknown }[] = []
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
      const url = String(input)
      calls.push({ url, body: init?.body ? JSON.parse(String(init.body)) : undefined })
      if (url.startsWith('/api/playbooks')) {
        return new Response(JSON.stringify([{ id: 'writing', title: 'Writing', when: 'Draft text' }]), { headers: { 'content-type': 'application/json' } })
      }
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
    await waitFor(() => expect(screen.getByRole('option', { name: 'Writing' })).toBeInTheDocument())
    await user.selectOptions(screen.getByLabelText(/^Playbook/), 'writing')
    await act(async () => { fireEvent.click(start) })
    const post = calls.find((c) => c.url === '/api/runs')
    expect(post?.body).toMatchObject({ task: 'Write a haiku to haiku.md', options: { allow_bash: true, max_cost: 5, playbook: 'writing' } })
  })

  it('posts the Cheap preset, and an edited field makes it Custom', async () => {
    const calls: { url: string; body?: unknown }[] = []
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
      const url = String(input)
      calls.push({ url, body: init?.body ? JSON.parse(String(init.body)) : undefined })
      const body = url === '/api/runs' ? { id: 'r' } : []
      return new Response(JSON.stringify(body), { status: url === '/api/runs' ? 201 : 200, headers: { 'content-type': 'application/json' } })
    })
    const user = userEvent.setup()
    render(<MemoryRouter><NewRun /></MemoryRouter>)
    await user.type(screen.getByLabelText('Task'), 'Summarise a page')
    await user.click(screen.getByRole('button', { name: 'Options' }))
    await user.click(screen.getByRole('button', { name: 'Cheap' }))
    expect(screen.getByRole('button', { name: 'Cheap' })).toHaveAttribute('aria-pressed', 'true')
    expect(screen.getByText(/^Cheap · \$1 cap/)).toBeInTheDocument()
    const tries = screen.getByLabelText('Tries per task')
    await user.clear(tries)
    await user.type(tries, '3')
    expect(screen.getByText('Custom')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Cheap' }))
    await act(async () => { fireEvent.click(screen.getByRole('button', { name: 'Start run' })) })
    const post = calls.find((c) => c.url === '/api/runs')
    expect(post?.body).toMatchObject({ options: {
      orchestrator_model: 'sonnet', worker_model: 'haiku', pick_tier: true, max_tier: 'sonnet', checker_model: 'haiku',
      max_cost: 1, max_attempts: 2, max_steps: 15, max_assignments: 8,
    } })
  })
})
