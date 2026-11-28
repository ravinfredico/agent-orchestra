import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { api, type StudioItem, type Team } from '../api'
import { MenuButton } from '../components/Shell'

type Filter = 'ready' | 'posted' | 'all'

/** Room and Studio tabs in a team's header. The Studio tab shows for video teams or once it has videos. */
export function TeamTabs({ teamId, current, show }: { teamId: string; current: 'room' | 'studio'; show: boolean }) {
  if (!show) return null
  return (
    <nav className="team-tabs" aria-label="Team views">
      <Link to={`/teams/${teamId}`} aria-current={current === 'room' ? 'page' : undefined}>Room</Link>
      <Link to={`/teams/${teamId}/studio`} aria-current={current === 'studio' ? 'page' : undefined}>Studio</Link>
    </nav>
  )
}

export const isVideoTeam = (t?: Pick<Team, 'name' | 'goal'> | null) => /video|tiktok|reel|shorts|youtube/i.test(`${t?.name ?? ''} ${t?.goal ?? ''}`)

/** The caption you paste into TikTok: caption, a blank line, then the hashtags. */
export const postText = (i: Pick<StudioItem, 'caption' | 'hashtags'>) => [i.caption, i.hashtags.join(' ')].filter(Boolean).join('\n\n')

const day = (t: number) => new Date(t * 1000).toLocaleDateString(undefined, { weekday: 'short', day: 'numeric', month: 'short' })

/** M10 video studio (DESIGN.md T4, canvas M10-Studio): videos the team made, posted by you by hand. */
export function TeamStudio() {
  const { teamId = '' } = useParams()
  const [team, setTeam] = useState<Team | null>(null)
  const [items, setItems] = useState<StudioItem[] | null>(null)
  const [filter, setFilter] = useState<Filter>('ready')
  const [copied, setCopied] = useState('')
  const [error, setError] = useState('')

  useEffect(() => {
    api.team(teamId).then(setTeam).catch((e) => setError((e as Error).message))
    api.studio(teamId).then((r) => setItems(r.items)).catch((e) => setError((e as Error).message))
  }, [teamId])
  useEffect(() => { document.title = `Studio · ${team?.name ?? 'Team'} · ChaCha PA` }, [team])

  const ready = (items ?? []).filter((i) => !i.posted_at)
  const posted = (items ?? []).filter((i) => i.posted_at)
  const shown = filter === 'ready' ? ready : filter === 'posted' ? posted : items ?? []

  const mark = async (i: StudioItem, on: boolean) => {
    try {
      const next = await api.markPosted(teamId, i.run_id, i.name, on)
      setItems((xs) => (xs ?? []).map((x) => (x.id === next.id ? next : x)))
    } catch (e) { setError((e as Error).message) }
  }
  const copy = async (i: StudioItem) => {
    try { await navigator.clipboard.writeText(postText(i)); setCopied(i.id) } catch { setError('Copy failed. Select the caption and copy it by hand.') }
  }
  const videoUrl = (i: StudioItem) => `/api/teams/${teamId}/studio/${i.run_id}/${encodeURIComponent(i.name)}.mp4`

  return (
    <div className="team-studio">
      <header className="run-header">
        <MenuButton />
        <h1>{team?.name ?? 'Studio'}</h1>
        <TeamTabs teamId={teamId} current="studio" show />
        <span className="studio-note muted">You post by hand. Nothing is uploaded.</span>
      </header>
      <div className="studio-body">
        {error && <p className="form-error" role="alert">{error}</p>}
        <div className="connectors" role="group" aria-label="Show">
          <button type="button" className="chip" aria-pressed={filter === 'ready'} onClick={() => setFilter('ready')}>Ready · {ready.length}</button>
          <button type="button" className="chip" aria-pressed={filter === 'posted'} onClick={() => setFilter('posted')}>Posted · {posted.length}</button>
          <button type="button" className="chip" aria-pressed={filter === 'all'} onClick={() => setFilter('all')}>All · {items?.length ?? 0}</button>
        </div>
        {items && items.length === 0 && (
          <div className="studio-empty">
            <b>No videos yet</b>
            <span className="muted">Ask the team in the room ("make 3 videos for this week"){team?.schedule[0] ? ', or wait for its next slot' : ''}.</span>
            <Link to={`/teams/${teamId}`} className="btn btn-sm">Go to the room</Link>
          </div>
        )}
        {items && items.length > 0 && shown.length === 0 && <p className="muted">{filter === 'posted' ? 'Nothing marked posted yet.' : 'Everything is posted.'}</p>}
        <ul className="studio-grid">
          {shown.map((i) => (
            <li key={i.id} className="studio-card">
              <div className="studio-top">
                {i.video
                  ? <video className="studio-video" src={videoUrl(i)} controls preload="metadata" playsInline aria-label={`${i.title}, video`} />
                  : <div className="studio-video studio-video-missing"><span>Script only</span><small>no video rendered yet</small></div>}
                <div className="studio-text">
                  <b>{i.title}</b>
                  <span className="muted studio-when">{day(i.created)}{i.posted_at ? ` · posted ${day(i.posted_at)}` : ''}</span>
                  {i.caption && <p>{i.caption}</p>}
                  {i.hashtags.length > 0 && <span className="muted">{i.hashtags.join(' ')}</span>}
                </div>
              </div>
              <div className="studio-actions">
                <button type="button" className="btn btn-sm" onClick={() => copy(i)} aria-live="polite">{copied === i.id ? 'Copied' : 'Copy caption'}</button>
                {i.video && <a className="btn btn-sm" href={videoUrl(i)} download={`${i.name}.mp4`}>Download</a>}
                {i.script && <Link className="btn btn-sm" to={`/runs/${i.run_id}/files/${i.script}`}>Open script</Link>}
                {i.posted_at
                  ? <button type="button" className="btn btn-sm btn-ghost" onClick={() => mark(i, false)}>Undo posted</button>
                  : <button type="button" className="btn btn-sm btn-primary" onClick={() => mark(i, true)}>Mark posted</button>}
              </div>
            </li>
          ))}
        </ul>
      </div>
    </div>
  )
}
