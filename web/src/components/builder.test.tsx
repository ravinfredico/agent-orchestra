import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { Proposal } from '../api'
import { draftFrom, TeamBuilder, toolLabel } from '../pages/TeamBuilder'
import { TeamEdit } from '../pages/TeamEdit'

afterEach(() => vi.restoreAllMocks())

const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { 'content-type': 'application/json' } })

const PROPOSAL: Proposal = {
  team: {
    name: 'Marketing team', goal: 'Plan posts', timezone: '', enabled: true, hook: { enabled: false, task: '' },
    outputs: ['Weekly content plan (plan.md)'],
    schedule: [{ cron: '0 9 * * 1', task: "Plan this week's posts" }],
    members: [
      { name: 'designer', role: 'Builds visuals in Figma', tools: ['connector.figma'], wants: [], tier: 'sonnet' },
      { name: 'coordinator', role: 'Slack and Gmail', tools: ['files.read'], wants: ['connector.gmail'], tier: 'haiku' },
    ],
  },
  summary: 'Here is a team of 2.',
  questions: [{ question: 'Which Slack channel gets the plan?', options: ['#marketing', '#general'] }],
  approvals: ['designer asks before it sends, posts or changes anything in Figma'],
  setup: [{ kind: 'connect', tool: 'connector.gmail', service: 'Gmail', text: 'Connect Gmail at claude.ai, Settings, Connectors' }],
  cost_usd: 0,
}
const CATALOG = [
  { id: 'files.read', kind: 'builtin', enabled: true, risk: 'read' },
  { id: 'connector.figma', kind: 'connector', enabled: true, risk: 'outward', label: 'Figma' },
]

function mockApi(calls: { url: string; method: string; body?: any }[], propose = () => json(PROPOSAL)) {
  vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
    const url = String(input)
    const method = init?.method || 'GET'
    calls.push({ url, method, body: init?.body ? JSON.parse(String(init.body)) : undefined })
    if (url === '/api/teams/propose') return propose()
    if (url === '/api/teams' && method === 'POST') return json({ id: 'marketing-team', ...JSON.parse(String(init!.body)) }, 201)
    if (url.startsWith('/api/catalog')) return json(CATALOG)
    return json({ items: [], active_run: null })
  })
}

const renderAt = (path: string) => render(
  <MemoryRouter initialEntries={[path]}>
    <Routes>
      <Route path="/teams/new" element={<TeamBuilder />} />
      <Route path="/teams/new/edit" element={<TeamEdit />} />
      <Route path="/teams/:teamId" element={<p>team page</p>} />
    </Routes>
  </MemoryRouter>,
)

describe('team builder', () => {
  it('labels connectors and missing ones', () => {
    expect(toolLabel('connector.figma', CATALOG as any)).toBe('Figma')
    expect(toolLabel('connector.google-drive', [])).toBe('Google Drive')
    expect(toolLabel('web', [])).toBe('web')
  })

  it('puts answers in the notes and uses the Cheap preset', () => {
    const d = draftFrom(PROPOSAL, { 0: '#marketing' })
    expect(d.memory).toContain('- Which Slack channel gets the plan? #marketing')
    expect(d.memory).toContain('## Past runs')
    expect(d.options.max_tier).toBeDefined()
  })

  it('proposes from one message, shows setup and approvals, and saves with the answer', async () => {
    const calls: { url: string; method: string; body?: any }[] = []
    mockApi(calls)
    renderAt('/teams/new')
    await userEvent.type(screen.getByLabelText('Describe the team'), 'I want a marketing team')
    await userEvent.click(screen.getByRole('button', { name: 'Propose team' }))
    expect(await screen.findByText('Here is a team of 2.')).toBeInTheDocument()
    expect(screen.getByText('Connect Gmail at claude.ai, Settings, Connectors.')).toBeInTheDocument()
    expect(screen.getByText(/designer asks before/)).toBeInTheDocument()
    expect(screen.getByText('Gmail')).toBeInTheDocument()
    expect(calls.some((c) => c.url === '/api/teams' && c.method === 'POST')).toBe(false)   // nothing saved yet
    await userEvent.click(screen.getByRole('button', { name: '#general' }))
    await userEvent.click(screen.getByRole('button', { name: 'Save team' }))
    expect(await screen.findByText('team page')).toBeInTheDocument()
    const saved = calls.find((c) => c.url === '/api/teams' && c.method === 'POST')!.body
    expect(saved.members[1].wants).toEqual(['connector.gmail'])
    expect(saved.memory).toContain('#general')
  })

  it('opens the editor prefilled, with missing tools marked', async () => {
    mockApi([])
    renderAt('/teams/new')
    await userEvent.click(screen.getByRole('button', { name: 'Marketing team' }))
    await userEvent.click(await screen.findByRole('button', { name: 'Edit before saving' }))
    await waitFor(() => expect(screen.getByDisplayValue('Marketing team')).toBeInTheDocument())
    expect(screen.getByRole('button', { name: 'Gmail, not set up yet. Remove' })).toBeInTheDocument()
  })

  it('keeps the message and offers a retry when it fails', async () => {
    mockApi([], () => json({ detail: "Couldn't design a team: the answer had no members. Your message is kept." }, 422))
    renderAt('/teams/new')
    await userEvent.type(screen.getByLabelText('Describe the team'), 'a team')
    await userEvent.click(screen.getByRole('button', { name: 'Propose team' }))
    expect(await screen.findByRole('alert')).toHaveTextContent("Couldn't design a team")
    expect(screen.getByLabelText('Describe the team')).toHaveValue('a team')
    expect(screen.getByRole('button', { name: 'Try again' })).toBeInTheDocument()
  })
})
