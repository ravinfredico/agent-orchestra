import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import demo from '../test/fixtures/demo.json'
import { TeamEdit } from '../pages/TeamEdit'
import { cronLabel, TeamPage } from '../pages/TeamPage'
import { reduceAll } from '../state/reducer'
import type { RunEvent } from '../state/types'
import { RunBar } from './RunParts'

afterEach(() => vi.restoreAllMocks())

const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { 'content-type': 'application/json' } })

const TEAM = {
  id: 'desk', name: 'Stocks desk', goal: 'Daily brief', timezone: '', enabled: true, memory: '## Notes\nno crypto',
  members: [{ name: 'scout', role: 'Finds news', tools: ['web'], tier: 'haiku' }],
  schedule: [{ cron: '0 9 * * 1-5', task: "Write today's brief" }],
  hook: { enabled: false, task: '' }, options: {}, active_run: null,
}

function mockApi(calls: { url: string; method: string; body?: any }[], room: unknown[] = []) {
  vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
    const url = String(input)
    const method = init?.method || 'GET'
    calls.push({ url, method, body: init?.body ? JSON.parse(String(init.body)) : undefined })
    if (url === '/api/teams/desk/room') return json({ items: room, active_run: null })
    if (url === '/api/teams/desk/messages') return json({ run_id: 'r1', steered: false }, 202)
    if (url === '/api/teams/desk' && method === 'GET') return json(TEAM)
    if (url.startsWith('/api/teams')) return json({ ...TEAM, ...(init?.body ? JSON.parse(String(init.body)) : {}) }, method === 'POST' ? 201 : 200)
    if (url.startsWith('/api/catalog')) return json([{ id: 'web', kind: 'builtin', enabled: true }, { id: 'files.write', kind: 'builtin', enabled: true }])
    return json({ ok: true }, 202)
  })
}

describe('cronLabel', () => {
  it('says common schedules in words and leaves the rest as written', () => {
    expect(cronLabel('0 9 * * 1-5')).toBe('Weekdays 09:00')
    expect(cronLabel('30 18 * * *')).toBe('Every day 18:30')
    expect(cronLabel('0 8 * * 1')).toBe('Mon 08:00')
    expect(cronLabel('*/15 * * * *')).toBe('*/15 * * * *')
  })
})

describe('TeamPage', () => {
  it('shows the room and sends a message that starts a run', async () => {
    const calls: { url: string; method: string; body?: any }[] = []
    mockApi(calls, [
      { t: 1, kind: 'system', text: 'Scheduled run: Brief' },
      { t: 2, kind: 'handoff', from: 'orchestrator', to: 'scout', text: 'Find news', run_id: 'r0' },
      { t: 3, kind: 'result', from: 'checker', passed: true, text: 'Find news passed: 6 sources', run_id: 'r0' },
      { t: 4, kind: 'agent', from: 'orchestrator', final: true, text: 'Brief ready', run_id: 'r0' },
    ])
    const user = userEvent.setup()
    render(<MemoryRouter initialEntries={['/teams/desk']}><Routes><Route path="/teams/:teamId" element={<TeamPage />} /></Routes></MemoryRouter>)
    expect(await screen.findByRole('heading', { name: 'Stocks desk' })).toBeInTheDocument()
    expect(await screen.findByText('orchestrator → scout')).toBeInTheDocument()
    expect(screen.getByText('Weekdays 09:00')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'open run' })).toHaveAttribute('href', '/runs/r0')
    await user.type(screen.getByLabelText('Message the team'), 'Add BBRI')
    await act(async () => { fireEvent.click(screen.getByRole('button', { name: 'Send' })) })
    expect(calls.find((c) => c.url === '/api/teams/desk/messages')?.body).toEqual({ text: 'Add BBRI' })
  })
})

describe('TeamEdit', () => {
  it('creates a team with a member and a schedule slot, on the Cheap preset', async () => {
    const calls: { url: string; method: string; body?: any }[] = []
    mockApi(calls)
    const user = userEvent.setup()
    render(<MemoryRouter initialEntries={['/teams/new']}><Routes><Route path="/teams/new" element={<TeamEdit />} /><Route path="/teams/:teamId" element={<p>team page</p>} /></Routes></MemoryRouter>)
    await user.type(screen.getByLabelText('Name'), 'Stocks desk')
    await user.click(screen.getByRole('button', { name: '+ Add member' }))
    await user.type(screen.getAllByLabelText('Name')[1], 'scout')
    await waitFor(() => expect(screen.getByRole('button', { name: 'web' })).toBeInTheDocument())
    await user.click(screen.getByRole('button', { name: 'web' }))
    await user.click(screen.getByRole('button', { name: '+ Add slot' }))
    await user.type(screen.getByLabelText('Task'), 'Morning brief')
    await act(async () => { fireEvent.click(screen.getByRole('button', { name: 'Create team' })) })
    const post = calls.find((c) => c.url === '/api/teams' && c.method === 'POST')
    expect(post?.body).toMatchObject({
      name: 'Stocks desk',
      members: [{ name: 'scout', tools: ['files.read', 'files.write', 'web'], tier: 'haiku' }],
      schedule: [{ cron: '0 9 * * *', task: 'Morning brief' }],
      options: { worker_model: 'haiku', max_tier: 'sonnet', max_cost: 1 },
    })
    expect(await screen.findByText('team page')).toBeInTheDocument()
  })
})

describe('steering', () => {
  it('shows your mid-run message in the thread', () => {
    const evs = demo as RunEvent[]
    const at = evs.findIndex((e) => e.type === 'task_assigned')
    const extra = { seq: 999, run_id: 'x', t: evs[at].t, type: 'user_message', text: 'Add BBRI too' } as RunEvent
    const r = reduceAll([...evs.slice(0, at + 1), extra])
    expect(r.thread.at(-1)).toMatchObject({ kind: 'user_message', text: 'Add BBRI too' })
  })

  it('sends a message from the run bar while the run is live', async () => {
    const calls: { url: string; method: string; body?: any }[] = []
    mockApi(calls)
    const evs = demo as RunEvent[]
    const live = reduceAll(evs.slice(0, 10))
    const user = userEvent.setup()
    render(<MemoryRouter><RunBar run={live} onStop={() => {}} /></MemoryRouter>)
    await user.type(screen.getByLabelText('Message the orchestrator'), 'Shorter please')
    await act(async () => { fireEvent.click(screen.getByRole('button', { name: 'Send message' })) })
    expect(calls.find((c) => c.url.endsWith('/messages'))?.body).toEqual({ text: 'Shorter please' })
  })
})
