import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { StudioItem } from '../api'
import { isVideoTeam, postText, TeamStudio } from '../pages/TeamStudio'

afterEach(() => vi.restoreAllMocks())

const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { 'content-type': 'application/json' } })

const ITEMS: StudioItem[] = [
  { id: 'r1/01-kos', run_id: 'r1', name: '01-kos', title: 'Kos room tour', caption: 'Would you live here?', hashtags: ['#anakkos', '#fyp'],
    video: 'videos/01-kos.mp4', script: 'videos/01-kos.md', created: 1795800000, posted_at: null },
  { id: 'r1/02-krl', run_id: 'r1', name: '02-krl', title: 'KRL rush', caption: 'POV: the 7:04', hashtags: [],
    video: null, script: 'videos/02-krl.md', created: 1795800000, posted_at: 1795900000 },
]
const TEAM = { id: 'tt', name: 'TikTok studio', goal: 'Videos', members: [], schedule: [], timezone: '', enabled: true,
  hook: { enabled: false, task: '' }, options: {}, memory: '', active_run: null }

function mockApi(calls: { url: string; body?: any }[], items = ITEMS) {
  vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
    const url = String(input)
    const body = init?.body ? JSON.parse(String(init.body)) : undefined
    calls.push({ url, body })
    if (url === '/api/teams/tt/studio') return json({ items })
    if (url.endsWith('/posted')) return json({ ...items[0], posted_at: body.posted ? 1795990000 : null })
    return json(TEAM)
  })
}

const renderStudio = () => render(
  <MemoryRouter initialEntries={['/teams/tt/studio']}>
    <Routes><Route path="/teams/:teamId/studio" element={<TeamStudio />} /></Routes>
  </MemoryRouter>,
)

describe('video studio', () => {
  it('builds the text you paste and spots video teams', () => {
    expect(postText(ITEMS[0])).toBe('Would you live here?\n\n#anakkos #fyp')
    expect(postText(ITEMS[1])).toBe('POV: the 7:04')
    expect(isVideoTeam({ name: 'TikTok studio', goal: '' })).toBe(true)
    expect(isVideoTeam({ name: 'Stocks desk', goal: 'Daily brief' })).toBe(false)
  })

  it('shows ready videos, copies the caption and marks one posted', async () => {
    const calls: { url: string; body?: any }[] = []
    mockApi(calls)
    const write = vi.fn().mockResolvedValue(undefined)
    Object.defineProperty(navigator, 'clipboard', { value: { writeText: write }, configurable: true })
    renderStudio()
    expect(await screen.findByText('Kos room tour')).toBeInTheDocument()
    expect(screen.queryByText('KRL rush')).not.toBeInTheDocument()            // posted: hidden under Ready
    expect(screen.getByRole('button', { name: 'Ready · 1' })).toHaveAttribute('aria-pressed', 'true')
    expect(screen.getByRole('link', { name: 'Download' })).toHaveAttribute('href', '/api/teams/tt/studio/r1/01-kos.mp4')
    await userEvent.click(screen.getByRole('button', { name: 'Copy caption' }))
    expect(write).toHaveBeenCalledWith('Would you live here?\n\n#anakkos #fyp')
    expect(screen.getByRole('button', { name: 'Copied' })).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Mark posted' }))
    expect(calls.find((c) => c.url.endsWith('/posted'))).toEqual({ url: '/api/teams/tt/studio/r1/01-kos/posted', body: { posted: true } })
    expect(await screen.findByText('Everything is posted.')).toBeInTheDocument()
  })

  it('shows script-only videos and the empty state', async () => {
    mockApi([])
    renderStudio()
    await userEvent.click(await screen.findByRole('button', { name: 'Posted · 1' }))
    expect(screen.getByText('Script only')).toBeInTheDocument()
    expect(screen.queryByRole('link', { name: 'Download' })).not.toBeInTheDocument()
  })

  it('says what to do when there are no videos', async () => {
    mockApi([], [])
    renderStudio()
    expect(await screen.findByText('No videos yet')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Go to the room' })).toHaveAttribute('href', '/teams/tt')
  })
})
