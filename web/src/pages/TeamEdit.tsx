import { useEffect, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { api, type CatalogEntry, type TeamInput, type TeamMember } from '../api'
import { MenuButton } from '../components/Shell'
import { CHEAP_PRESET } from '../presets'

const TIERS = ['haiku', 'sonnet', 'opus']

export const EMPTY_TEAM: TeamInput = {
  name: '', goal: '', members: [], schedule: [], timezone: '', enabled: true,
  hook: { enabled: false, task: '' }, options: { ...CHEAP_PRESET }, memory: '',
}

/** New team and edit team (DESIGN.md, canvas M8-Teams). Team builder from one message is M9. */
export function TeamEdit() {
  const { teamId } = useParams()
  const nav = useNavigate()
  const [t, setT] = useState<TeamInput>(EMPTY_TEAM)
  const [secret, setSecret] = useState('')
  const [catalog, setCatalog] = useState<CatalogEntry[]>([])
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const [confirmDelete, setConfirmDelete] = useState(false)

  useEffect(() => { api.catalog().then(setCatalog).catch(() => {}) }, [])
  useEffect(() => {
    if (!teamId) return
    api.team(teamId).then((x) => {
      setT({ name: x.name, goal: x.goal, members: x.members, schedule: x.schedule, timezone: x.timezone,
        enabled: x.enabled, hook: { enabled: x.hook.enabled, task: x.hook.task }, options: x.options, memory: x.memory })
      setSecret(x.hook.secret || '')
    }).catch((e) => setError((e as Error).message))
  }, [teamId])
  useEffect(() => { document.title = `${teamId ? 'Edit team' : 'New team'} · ChaCha PA` }, [teamId])

  const tools = catalog.filter((e) => e.enabled).map((e) => e.id)
  const setMember = (i: number, m: Partial<TeamMember>) => setT({ ...t, members: t.members.map((x, j) => (j === i ? { ...x, ...m } : x)) })
  const setSlot = (i: number, k: 'cron' | 'task', v: string) => setT({ ...t, schedule: t.schedule.map((x, j) => (j === i ? { ...x, [k]: v } : x)) })

  const save = async (e: React.FormEvent) => {
    e.preventDefault()
    setBusy(true)
    setError('')
    try {
      const saved = teamId ? await api.updateTeam(teamId, t) : await api.createTeam(t)
      nav(`/teams/${saved.id}`)
    } catch (err) {
      setError((err as Error).message)
      setBusy(false)
    }
  }
  const hookUrl = teamId && secret ? `${window.location.origin}/api/hooks/${teamId}/${secret}` : ''

  return (
    <div className="team-edit">
      <header className="run-header"><MenuButton /><h1>{teamId ? 'Edit team' : 'New team'}</h1></header>
      <form className="options team-form" onSubmit={save} aria-label={teamId ? 'Edit team' : 'New team'}>
        <label className="field">
          <span>Name</span>
          <input value={t.name} onChange={(e) => setT({ ...t, name: e.target.value })} required placeholder="Stocks desk" />
        </label>
        <label className="field">
          <span>Time zone</span>
          <input className="mono" value={t.timezone} onChange={(e) => setT({ ...t, timezone: e.target.value })} placeholder="Asia/Jakarta" spellCheck={false} />
          <small>Empty: this machine's time zone.</small>
        </label>
        <label className="field wide">
          <span>Goal</span>
          <input value={t.goal} onChange={(e) => setT({ ...t, goal: e.target.value })} placeholder="Daily brief on my watchlist. Never trade." />
        </label>

        <fieldset className="field wide team-fieldset">
          <legend>Members</legend>
          {t.members.length === 0 && <small>No members: the orchestrator hires agents for each run.</small>}
          {t.members.map((m, i) => (
            <div className="member-row" key={i} role="group" aria-label={`Member ${i + 1}`}>
              <label className="field"><span>Name</span>
                <input className="mono" value={m.name} onChange={(e) => setMember(i, { name: e.target.value })} required />
              </label>
              <label className="field"><span>Role</span>
                <input value={m.role} onChange={(e) => setMember(i, { role: e.target.value })} />
              </label>
              <label className="field"><span>Model</span>
                <select value={m.tier} onChange={(e) => setMember(i, { tier: e.target.value })}>
                  {TIERS.map((x) => <option key={x}>{x}</option>)}
                </select>
              </label>
              <button type="button" className="icon-btn bordered" aria-label={`Remove ${m.name || 'member'}`}
                onClick={() => setT({ ...t, members: t.members.filter((_, j) => j !== i) })}>×</button>
              <div className="connectors member-tools" role="group" aria-label={`Tools for ${m.name || 'member'}`}>
                {tools.map((id) => (
                  <button key={id} type="button" className="chip" aria-pressed={m.tools.includes(id)}
                    onClick={() => setMember(i, { tools: m.tools.includes(id) ? m.tools.filter((x) => x !== id) : [...m.tools, id] })}>{id}</button>
                ))}
              </div>
            </div>
          ))}
          <button type="button" className="chip add-row" onClick={() => setT({ ...t, members: [...t.members, { name: '', role: '', tools: ['files.read', 'files.write'], tier: 'haiku' }] })}>+ Add member</button>
        </fieldset>

        <fieldset className="field wide team-fieldset">
          <legend>Schedule</legend>
          <small>Cron: minute hour day month weekday. "0 9 * * 1-5" is weekdays at 09:00.</small>
          {t.schedule.map((s, i) => (
            <div className="slot-row" key={i} role="group" aria-label={`Slot ${i + 1}`}>
              <label className="field"><span>When</span>
                <input className="mono" value={s.cron} onChange={(e) => setSlot(i, 'cron', e.target.value)} placeholder="0 9 * * 1-5" required />
              </label>
              <label className="field"><span>Task</span>
                <input value={s.task} onChange={(e) => setSlot(i, 'task', e.target.value)} placeholder="Write today's brief" required />
              </label>
              <button type="button" className="icon-btn bordered" aria-label={`Remove slot ${i + 1}`}
                onClick={() => setT({ ...t, schedule: t.schedule.filter((_, j) => j !== i) })}>×</button>
            </div>
          ))}
          <button type="button" className="chip add-row" onClick={() => setT({ ...t, schedule: [...t.schedule, { cron: '0 9 * * *', task: '' }] })}>+ Add slot</button>
        </fieldset>

        <label className="toggle wide">
          <input type="checkbox" checked={t.hook.enabled} onChange={(e) => setT({ ...t, hook: { ...t.hook, enabled: e.target.checked } })} />
          <span className="switch" aria-hidden />
          <span><b>Webhook for new data</b><small>A POST to the team's secret URL starts a run with the data.</small></span>
        </label>
        {t.hook.enabled && (
          <label className="field wide">
            <span>What to do with new data</span>
            <input value={t.hook.task} onChange={(e) => setT({ ...t, hook: { ...t.hook, task: e.target.value } })} placeholder="Check the new prices and alert me on big moves" />
            <small>{hookUrl ? <>URL: <span className="mono">{hookUrl}</span></> : 'The URL appears after you save.'}</small>
          </label>
        )}
        <label className="field wide">
          <span>Memory</span>
          <textarea className="mono" rows={6} value={t.memory} onChange={(e) => setT({ ...t, memory: e.target.value })}
            placeholder={'## Notes\nNo crypto. Keep briefs under 300 words.'} />
          <small>Read before every run. The app adds a line under "Past runs" after each one.</small>
        </label>

        {error && <p className="form-error wide" role="alert">{error}</p>}
        <div className="wide team-actions">
          <button type="submit" className="btn btn-primary" disabled={busy || !t.name.trim()}>{teamId ? 'Save team' : 'Create team'}</button>
          <button type="button" className="btn" onClick={() => nav(teamId ? `/teams/${teamId}` : '/')}>Cancel</button>
          {teamId && (confirmDelete
            ? <button type="button" className="btn btn-danger" onClick={async () => { await api.deleteTeam(teamId); nav('/') }}>Really delete</button>
            : <button type="button" className="btn" onClick={() => setConfirmDelete(true)}>Delete team</button>)}
        </div>
        <small className="wide muted">New teams use the Cheap preset. Runs start only from the schedule, your messages or the webhook.</small>
      </form>
    </div>
  )
}
