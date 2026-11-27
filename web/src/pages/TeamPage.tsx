import { useEffect, useRef, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { api, type RoomItem, type Team } from '../api'
import { Character } from '../components/Character'
import { ArrowUp, Team as TeamIc } from '../components/Icons'
import { MenuButton } from '../components/Shell'
import { useRoom } from '../state/hooks'
import { agentAccessory, agentColor, CHECKER_COLOR, ORCHESTRATOR_COLOR } from '../state/reducer'

/** Plain-words version of the common cron shapes; anything else is shown as written. */
export function cronLabel(cron: string): string {
  const [m, h, dom, mon, dow] = cron.split(/\s+/)
  const time = /^\d+$/.test(m) && /^\d+$/.test(h) ? `${h.padStart(2, '0')}:${m.padStart(2, '0')}` : ''
  if (!time || dom !== '*' || mon !== '*') return cron
  if (dow === '*') return `Every day ${time}`
  if (dow === '1-5') return `Weekdays ${time}`
  if (dow === '0,6' || dow === '6,0') return `Weekends ${time}`
  const days = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat']
  if (/^[0-7]$/.test(dow)) return `${days[Number(dow) % 7]} ${time}`
  return cron
}

function face(name: string | undefined, team: Team | null) {
  if (name === 'orchestrator') return { color: ORCHESTRATOR_COLOR, accessory: 'bow' as const }
  if (name === 'checker') return { color: CHECKER_COLOR, accessory: 'monocle' as const }
  const i = Math.max(0, team?.members.findIndex((m) => m.name === name) ?? 0)
  return { color: agentColor(i), accessory: agentAccessory(i) }
}

function RoomLine({ item, team, answered, onAnswer }: { item: RoomItem; team: Team | null; answered: boolean; onAnswer: () => void }) {
  const [busy, setBusy] = useState(false)
  if (item.kind === 'you') return <div className="msg-user room-you">{item.text}</div>
  if (item.kind === 'system') return <div className="room-system"><span>{item.text}</span></div>
  const who = item.from || 'orchestrator'
  const f = face(who, team)
  if (item.kind === 'approval') {
    const decide = async (yes: boolean) => {
      if (!item.run_id || !item.approval_id) return
      setBusy(true)
      try { await api.approve(item.run_id, item.approval_id, yes); onAnswer() } finally { setBusy(false) }
    }
    return (
      <div className="room-line room-approval" role="group" aria-label={`Approval: ${who} ${item.text}`}>
        <Character color={f.color} accessory={f.accessory} mood={answered ? 'neutral' : 'waiting'} size={28} animate={false} />
        <div>
          <span className="room-from">{who} · needs your approval</span>
          <span className="room-text">{item.text.replace(' Approve it in the run.', '')}</span>
          {!answered && (
            <span className="team-actions room-approve">
              <button className="btn btn-sm btn-primary" disabled={busy} onClick={() => decide(true)}>Approve</button>
              <button className="btn btn-sm" disabled={busy} onClick={() => decide(false)}>Deny</button>
              {item.run_id && <Link to={`/runs/${item.run_id}`}>see details</Link>}
            </span>
          )}
        </div>
      </div>
    )
  }
  return (
    <div className={`room-line${item.kind === 'result' ? (item.passed ? ' room-pass' : ' room-fail') : ''}`}>
      <Character color={f.color} accessory={f.accessory} mood={item.final ? 'happy' : item.kind === 'result' && !item.passed ? 'sad' : 'neutral'} size={28} animate={false} />
      <div>
        <span className="room-from">{who}{item.to ? ` → ${item.to}` : ''}</span>
        <span className="room-text">
          {item.text}
          {item.final && item.run_id && <> · <Link to={`/runs/${item.run_id}`}>open run</Link></>}
        </span>
      </div>
    </div>
  )
}

export function TeamPage() {
  const { teamId = '' } = useParams()
  const nav = useNavigate()
  const { team, items, activeRun, error, reload } = useRoom(teamId)
  const [text, setText] = useState('')
  const [busy, setBusy] = useState(false)
  const [sendErr, setSendErr] = useState('')
  const [panelOpen, setPanelOpen] = useState(false)
  const bottom = useRef<HTMLDivElement>(null)

  useEffect(() => { document.title = team ? `${team.name} · ChaCha PA` : 'ChaCha PA' }, [team])
  useEffect(() => { bottom.current?.scrollIntoView?.({ block: 'end' }) }, [items.length])

  const send = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!text.trim() || busy) return
    setBusy(true)
    setSendErr('')
    try { await api.messageTeam(teamId, text.trim()); setText(''); reload() }
    catch (err) { setSendErr((err as Error).message) }
    finally { setBusy(false) }
  }
  const togglePause = async () => { if (team) { await api.updateTeam(team.id, { enabled: !team.enabled }); reload() } }

  if (error) return <div className="center-page"><p className="form-error" role="alert">{error}</p></div>
  const status = activeRun ? 'Working' : team && !team.enabled ? 'Paused' : 'Asleep until a trigger'
  return (
    <div className="run-page" style={{ display: 'flex', flexDirection: 'row', flex: 1, minWidth: 0 }}>
      <div style={{ flex: 1, minWidth: 0, display: 'flex', flexDirection: 'column', minHeight: '100vh' }}>
        <header className="run-header">
          <MenuButton />
          <h1>{team?.name ?? 'Loading…'}</h1>
          <span className="state">
            <span className={`dot ${activeRun ? 'dot-text live' : 'dot-border'}`} aria-hidden />
            {status}{activeRun && <> · <Link to={`/runs/${activeRun}`}>open run</Link></>}
          </span>
          <button className="icon-btn rail-toggle" aria-label="Team details" aria-expanded={panelOpen} onClick={() => setPanelOpen(true)}><TeamIc /></button>
        </header>
        <div className="thread room" aria-live="off">
          {items.length === 0 && (
            <p className="muted room-empty">No messages yet. Write below to start a run, or wait for the next scheduled slot.</p>
          )}
          {items.map((it, i) => (
            <RoomLine key={`${it.run_id ?? 'team'}-${it.t}-${i}`} item={it} team={team} onAnswer={reload}
              answered={it.kind === 'approval' && (!activeRun || it.run_id !== activeRun
                || items.some((x) => x.kind === 'system' && x.approval_id === it.approval_id))} />
          ))}
          <div ref={bottom} />
        </div>
        <div className="runbar-wrap">
          <form className="follow" onSubmit={send}>
            <label className="visually-hidden" htmlFor="room-msg">Message the team</label>
            <input id="room-msg" value={text} onChange={(e) => setText(e.target.value)} autoComplete="off"
              placeholder={activeRun ? 'Message the team. It reads this at its next step.' : 'Message the team to start a run'} />
            <button type="submit" className="send-btn" disabled={!text.trim() || busy} aria-label="Send"><ArrowUp /></button>
          </form>
          {sendErr && <p className="form-error" role="alert">{sendErr}</p>}
        </div>
      </div>
      <aside className={`rail${panelOpen ? ' open' : ''}`} aria-label="Team details">
        <button className="btn btn-sm rail-toggle" onClick={() => setPanelOpen(false)} style={{ alignSelf: 'flex-end' }}>Close</button>
        {team?.goal && <p className="team-goal">{team.goal}</p>}
        <section>
          <h2 className="caps">Members</h2>
          {team?.members.length === 0 && <span className="muted" style={{ fontSize: 13.5 }}>None yet. The orchestrator hires agents per run.</span>}
          {team?.members.map((m, i) => (
            <div className="team-row" key={m.name}>
              <Character color={agentColor(i)} accessory={agentAccessory(i)} mood="sleepy" size={30} animate={false} />
              <span className="txt"><b>{m.name}</b><span>{m.role}</span></span>
              <span className="tier-chip">{m.tier}</span>
            </div>
          ))}
        </section>
        {(team?.setup ?? []).length > 0 && (
          <section>
            <h2 className="caps">Set up first</h2>
            <ol className="setup-steps">{team!.setup!.map((s) => <li key={s.tool}>{s.text}.</li>)}</ol>
            <small className="muted">Members skip these tools until they are set up.</small>
          </section>
        )}
        <section>
          <h2 className="caps">Triggers</h2>
          <ul className="trigger-list">
            {team?.schedule.map((s, i) => <li key={i}><b>{cronLabel(s.cron)}</b> · <span className="muted">{s.task}</span></li>)}
            <li>Your messages</li>
            {team?.hook.enabled && <li>Webhook · <span className="muted">{team.hook.task || 'new data'}</span></li>}
          </ul>
          <small className="muted">Asleep between triggers. Runs only while this machine is on.</small>
        </section>
        <section>
          <h2 className="caps">Memory</h2>
          <p className="team-memory">{team?.memory.trim() ? team.memory.trim().slice(0, 400) : 'Empty.'}</p>
        </section>
        <div className="team-actions">
          <button className="btn btn-sm" onClick={() => nav(`/teams/${teamId}/edit`)}>Edit team</button>
          <button className="btn btn-sm" onClick={togglePause}>{team?.enabled === false ? 'Resume triggers' : 'Pause triggers'}</button>
        </div>
      </aside>
      {panelOpen && <div className="scrim" onClick={() => setPanelOpen(false)} />}
    </div>
  )
}
