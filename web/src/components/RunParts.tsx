import { useEffect, useRef, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { api } from '../api'
import { clock, money } from '../format'
import { useElapsed } from '../state/hooks'
import {
  agentAccessory, agentColor, agentMood, agentStatusText, CHECKER_COLOR, isLive, needsApproval, ORCHESTRATOR_COLOR,
  orchestratorMood, toolVerb,
} from '../state/reducer'
import type { Approval, RunView } from '../state/types'
import { Character } from './Character'
import { ArrowUp, FileIc, StopSq } from './Icons'

// ---- approval card (DESIGN.md 3.5) ---------------------------------------------------------

export function ApprovalCard({ ap, run }: { ap: Approval; run: RunView }) {
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')
  const a = run.agents[ap.agent]
  const idx = a?.colorIndex ?? 0
  const verb = toolVerb(ap.tool)
  if (ap.decision !== 'pending') {
    const word = ap.decision === 'approved' ? 'Approved' : ap.decision === 'denied' ? 'Denied' : 'Not answered'
    return (
      <div className="approval resolved enter">
        <Character color={agentColor(idx)} accessory={agentAccessory(idx)} mood="neutral" size={22} animate={false} />
        <span>{word} · {ap.agent} wanted to {verb}</span>
      </div>
    )
  }
  const decide = async (yes: boolean) => {
    setBusy(true)
    setErr('')
    try { await api.approve(run.id, ap.approvalId, yes) } catch (e) { setErr((e as Error).message); setBusy(false) }
  }
  return (
    <div className="approval enter" role="group" aria-label={`Approval needed: ${ap.agent} wants to ${verb}`}>
      <div className="approval-head">
        <Character color={agentColor(idx)} accessory={agentAccessory(idx)} mood="waiting" size={32} label={ap.agent} />
        <span><b>{ap.agent}</b> wants to {verb} <span className="muted">({ap.catalogId})</span></span>
      </div>
      <pre>{ap.preview}</pre>
      <div className="acts">
        <button className="btn btn-primary btn-sm" disabled={busy} onClick={() => decide(true)}>Approve</button>
        <button className="btn btn-sm" disabled={busy} onClick={() => decide(false)}>Deny</button>
      </div>
      {err && <span className="form-error">{err}</span>}
    </div>
  )
}

// ---- outcome card (DESIGN.md 3.6) ----------------------------------------------------------

function mainFile(run: RunView): string | null {
  const paths = Object.keys(run.files)
  return paths.find((p) => p === 'report.md') || paths.find((p) => p.endsWith('.md') && !p.includes('/')) || paths[0] || null
}

export function OutcomeCard({ run }: { run: RunView }) {
  const nav = useNavigate()
  const [busy, setBusy] = useState(false)
  const elapsed = useElapsed(run.startedAt, run.endedAt, false)
  const passed = Object.values(run.tasks).filter((t) => t.status === 'done').length
  const main = mainFile(run)
  const rerun = () => nav('/', { state: { task: run.task, options: run.options } })
  const cont = async (extra: number) => {
    setBusy(true)
    try { const r = await api.continueRun(run.id, extra); nav(`/runs/${r.id}`) } finally { setBusy(false) }
  }
  const filesLink = main ? `/runs/${run.id}/files/${main}` : `/runs/${run.id}/files`
  const orch = (mood: 'happy' | 'sad' | 'sleepy') => <Character color={ORCHESTRATOR_COLOR} accessory="bow" mood={mood} size={40} label="orchestrator" />

  if (run.status === 'finished') {
    return (
      <div className="outcome enter">
        <div className="outcome-head">
          <span className="cast" aria-hidden>
            {run.agentOrder.map((n) => {
              const a = run.agents[n]
              return <Character key={n} color={agentColor(a.colorIndex)} accessory={agentAccessory(a.colorIndex)}
                mood={a.passed > 0 ? 'happy' : 'neutral'} size={36} />
            })}
          </span>
        </div>
        <div className="outcome-head">
          <span className="txt">
            <b>All done</b>
            <span>Every task passed the checker · {clock(elapsed)} · {money(run.costUsd)} est.</span>
          </span>
        </div>
        <div className="acts">
          {main && <Link className="btn btn-primary" to={filesLink}>Open {main}</Link>}
          <button className="btn" onClick={rerun}>Run again</button>
        </div>
      </div>
    )
  }
  if (run.status === 'gave_up') {
    return (
      <div className="outcome enter">
        <div className="outcome-head">
          {orch('sad')}
          <span className="txt">
            <b>Out of budget</b>
            <span>Used {money(run.costUsd)} of the {money(run.options?.max_cost)} cap · {passed} of {Object.keys(run.tasks).length} tasks passed</span>
          </span>
        </div>
        <div className="meter hot" role="meter" aria-label="Estimated usage" aria-valuenow={100} aria-valuemin={0} aria-valuemax={100}><i style={{ transform: 'scaleX(1)' }} /></div>
        <div className="acts">
          <button className="btn btn-primary" disabled={busy} onClick={() => cont(2)}>Continue with $2 more</button>
          <Link className="btn" to={`/runs/${run.id}/files`}>See files</Link>
          <button className="btn" onClick={rerun}>Run again</button>
        </div>
        <span className="muted" style={{ fontSize: 12.5 }}>Continue starts a new run that picks up these files and the unfinished tasks.</span>
      </div>
    )
  }
  if (run.status === 'failed') {
    const kind = run.error?.kind
    const title = kind === 'auth' ? 'Your Claude login expired' : kind === 'limit' ? "You've hit your plan's usage limit" : 'The run crashed'
    return (
      <div className="outcome enter" role="alert">
        <div className="outcome-head">
          {orch('sleepy')}
          <span className="txt"><b>{title}</b><span>The run stopped after {clock(elapsed)}.</span></span>
        </div>
        {kind === 'auth' ? (
          <ol>
            <li>Open a terminal and run <code>claude</code></li>
            <li>Type <code>/login</code> and sign in with your Claude account</li>
            <li>Come back and press Try again</li>
          </ol>
        ) : <span>{run.error?.hint}</span>}
        <div className="acts">
          <button className="btn btn-primary" onClick={rerun}>Try again</button>
          <button className="btn" onClick={() => navigator.clipboard?.writeText(run.error?.error || '')}>Copy error details</button>
        </div>
        <details><summary>Technical details</summary><span className="mono">{run.error?.error}</span></details>
      </div>
    )
  }
  const stopped = run.status === 'stopped'
  return (
    <div className="outcome enter">
      <div className="outcome-head">
        {orch('sleepy')}
        <span className="txt">
          <b>{stopped ? 'Stopped by you' : 'Interrupted'}</b>
          <span>{stopped ? `${passed} of ${Object.keys(run.tasks).length} tasks had passed. Files are kept.` : 'The server restarted. Files are kept.'}</span>
        </span>
      </div>
      <div className="acts">
        <button className="btn btn-primary" disabled={busy} onClick={() => cont(Number(run.options?.max_cost) || 2)}>Continue</button>
        <Link className="btn" to={`/runs/${run.id}/files`}>See files</Link>
        <button className="btn" onClick={rerun}>Run again</button>
      </div>
    </div>
  )
}

// ---- run bar / follow-up (DESIGN.md 3.4) --------------------------------------------------

export function RunBar({ run, onStop }: { run: RunView; onStop: () => void }) {
  const nav = useNavigate()
  const live = isLive(run)
  const elapsed = useElapsed(run.startedAt, run.endedAt, live)
  const [follow, setFollow] = useState('')
  const [busy, setBusy] = useState(false)
  const pct = Math.min(100, (run.costUsd / (Number(run.options?.max_cost) || 5)) * 100)

  if (!live) {
    if (run.status !== 'finished') return null
    const submit = async (e: React.FormEvent) => {
      e.preventDefault()
      if (!follow.trim()) return
      setBusy(true)
      try { const r = await api.start(follow.trim(), run.options, { run_id: run.id, mode: 'follow_up' }); nav(`/runs/${r.id}`) }
      finally { setBusy(false) }
    }
    return (
      <div className="runbar-wrap">
        <form className="follow" onSubmit={submit}>
          <label className="visually-hidden" htmlFor="follow">Follow-up task</label>
          <input id="follow" value={follow} onChange={(e) => setFollow(e.target.value)}
            placeholder="Start a follow-up run, e.g. translate the report" />
          <button type="submit" className="send-btn" disabled={!follow.trim() || busy} aria-label="Start follow-up run">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" aria-hidden><path d="M12 19V5" /><path d="M5 12l7-7 7 7" /></svg>
          </button>
        </form>
      </div>
    )
  }

  const label = needsApproval(run) ? 'Needs your approval' : run.replanning ? 'Replanning' : 'Running'
  const steer = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!follow.trim() || busy) return
    setBusy(true)
    try { await api.steer(run.id, follow.trim()); setFollow('') } catch { /* the run just ended */ } finally { setBusy(false) }
  }
  return (
    <div className="runbar-wrap">
      <form className="follow steer" onSubmit={steer}>
        <label className="visually-hidden" htmlFor="steer">Message the orchestrator</label>
        <input id="steer" value={follow} onChange={(e) => setFollow(e.target.value)} autoComplete="off"
          placeholder="Message the orchestrator. It reads this at its next step." />
        <button type="submit" className="send-btn" disabled={!follow.trim() || busy} aria-label="Send message"><ArrowUp /></button>
      </form>
      <div className="runbar">
        <div className="meter meter-mini" role="presentation"><i style={{ transform: `scaleX(${pct / 100})` }} /></div>
        <span className="faces" aria-hidden>
          {run.agentOrder.length === 0 && <Character color={ORCHESTRATOR_COLOR} accessory="bow" mood="working" size={26} />}
          {run.agentOrder.map((n) => {
            const a = run.agents[n]
            return <Character key={n} color={agentColor(a.colorIndex)} accessory={agentAccessory(a.colorIndex)} mood={agentMood(a, run)} size={26} />
          })}
        </span>
        <span className="label">{label}</span>
        <span className="meta">{clock(elapsed)} · {money(run.costUsd)} est.</span>
        <button className="btn btn-sm btn-stop" onClick={onStop}><StopSq />Stop</button>
      </div>
    </div>
  )
}

// ---- usage by model and by agent (M7, canvas M7-Cheaper) ------------------------------------

const TIER_ORDER = ['haiku', 'sonnet', 'opus']
const tierRank = (m: string) => (TIER_ORDER.includes(m) ? TIER_ORDER.indexOf(m) : TIER_ORDER.length)

export function UsageBreakdown({ run }: { run: RunView }) {
  const models = Object.entries(run.usageByModel)
    .sort(([a], [b]) => tierRank(a) - tierRank(b))
  const agents = Object.entries(run.usageByAgent).sort(([, a], [, b]) => b.costUsd - a.costUsd)
  if (!agents.length) return null
  const total = Math.max(run.costUsd, 1e-9)
  const color = (name: string) => name === 'orchestrator' ? ORCHESTRATOR_COLOR
    : name === 'checker' ? CHECKER_COLOR : agentColor(run.agents[name]?.colorIndex ?? 0)
  return (
    <>
      <section aria-labelledby="by-model">
        <h3 className="caps" id="by-model">By model</h3>
        <div className="tier-bar" aria-hidden>
          {models.map(([m, u]) => <i key={m} className={`tier-${m}`} style={{ flexGrow: u.costUsd / total }} />)}
        </div>
        <ul className="usage-list">
          {models.map(([m, u]) => (
            <li key={m}><span className={`tier-swatch tier-${m}`} aria-hidden /><span className="n">{m}</span><span className="v">{money(u.costUsd)}</span></li>
          ))}
        </ul>
      </section>
      <section aria-labelledby="by-agent">
        <h3 className="caps" id="by-agent">By agent</h3>
        <ul className="usage-list usage-agents">
          {agents.map(([n, u]) => {
            const tasks = u.tasks.length
            const meta = [u.models.join(' → '),
              u.role === 'checker' ? `${u.calls} ${u.calls === 1 ? 'check' : 'checks'}`
                : u.role === 'orchestrator' ? 'planning' : `${tasks} ${tasks === 1 ? 'task' : 'tasks'}, ${u.calls} ${u.calls === 1 ? 'try' : 'tries'}`]
            return (
              <li key={n}>
                <span className="agent-dot" style={{ background: color(n) }} aria-hidden />
                <span className="n">{n}</span><span className="v">{money(u.costUsd)}</span>
                <span className="meter meter-thin" aria-hidden><i style={{ transform: `scaleX(${Math.min(1, u.costUsd / total)})` }} /></span>
                <span className="meta">{meta.join(' · ')}</span>
              </li>
            )
          })}
        </ul>
      </section>
    </>
  )
}

// ---- right rail (DESIGN.md 3.7, team, files) ----------------------------------------------

export function Rail({ run, open, onClose }: { run: RunView; open: boolean; onClose: () => void }) {
  const live = isLive(run)
  const elapsed = useElapsed(run.startedAt, run.endedAt, live)
  const cap = Number(run.options?.max_cost) || 5
  const pct = Math.min(100, (run.costUsd / cap) * 100)
  const hot = pct >= 85
  const files = Object.values(run.files).sort((a, b) => a.path.localeCompare(b.path))
  return (
    <aside className={`rail${open ? ' open' : ''}`} aria-label="Run details">
      <button className="btn btn-sm rail-toggle" onClick={onClose} style={{ alignSelf: 'flex-end' }}>Close</button>
      <section>
        <h2 className="caps">Usage</h2>
        <div className={`usage-top${hot ? ' hot' : ''}`}>
          <b>{money(run.costUsd)}</b>
          <span className="muted" style={{ fontSize: 13 }}>{hot && live ? 'almost out · ' : ''}est. of {money(cap)}</span>
        </div>
        <div className={`meter${hot ? ' hot' : ''}`} role="meter" aria-label="Estimated plan usage"
          aria-valuenow={Math.round(pct)} aria-valuemin={0} aria-valuemax={100}
          aria-valuetext={`${money(run.costUsd)} of ${money(cap)} estimated`}>
          <i style={{ transform: `scaleX(${pct / 100})` }} />
        </div>
        <div className="stats">
          <div><b>{clock(elapsed)}</b><span>elapsed</span></div>
          <div><b>{run.agentOrder.length}/{run.options?.max_agents ?? 6}</b><span>agents</span></div>
          <div><b>{run.assignments}/{run.options?.max_assignments ?? 15}</b><span>tasks</span></div>
        </div>
      </section>
      <UsageBreakdown run={run} />
      <section>
        <h2 className="caps">Team</h2>
        <div className="team-row">
          <Character color={ORCHESTRATOR_COLOR} accessory="bow" mood={orchestratorMood(run)} size={34} label="orchestrator" />
          <span className="txt"><b>Orchestrator</b><span>{live ? (run.replanning ? 'Replanning' : 'Watching the board') : run.status === 'finished' ? 'Finished' : 'Stopped'}</span></span>
        </div>
        {run.agentOrder.map((n) => {
          const a = run.agents[n]
          const status = agentStatusText(a, run)
          return (
            <div className="team-row" key={n}>
              <Character color={agentColor(a.colorIndex)} accessory={agentAccessory(a.colorIndex)} mood={agentMood(a, run)} size={34} label={`${n}, ${status}`} />
              <span className="txt"><b>{n}</b><span title={a.role}>{status}</span></span>
            </div>
          )
        })}
      </section>
      <section>
        <h2 className="caps">Files</h2>
        {files.length === 0 && <span className="muted" style={{ fontSize: 13.5 }}>Files appear here as agents write them.</span>}
        {files.map((f) => (
          <Link key={f.path} className="file-row" to={`/runs/${run.id}/files/${f.path}`}>
            <FileIc /><span className="p">{f.path}</span><span className="a">{f.agent}</span>
          </Link>
        ))}
      </section>
    </aside>
  )
}

// ---- announcer: one polite status region (DESIGN.md section 8) ---------------------------

/** quietThrough: the run's last seq when the page opened (null until known). Events up to it are
 *  history, so they are never read out, however many batches the replay arrives in. */
export function Announcer({ run, quietThrough }: { run: RunView; quietThrough: number | null }) {
  const [polite, setPolite] = useState('')
  const [assertive, setAssertive] = useState('')
  const seen = useRef(0)
  useEffect(() => {
    if (quietThrough === null) return
    const from = Math.max(seen.current, quietThrough)
    const items = run.announcements.filter((a) => a.seq > from)
    seen.current = Math.max(from, run.announcements.at(-1)?.seq ?? 0)
    if (!items.length) return
    const urgent = items.filter((a) => a.assertive)
    const calm = items.filter((a) => !a.assertive).slice(-3)
    if (urgent.length) setAssertive(urgent.map((a) => a.text).join('. '))
    if (calm.length) setPolite(calm.map((a) => a.text).join('. '))
  }, [run.announcements, quietThrough])
  return (
    <>
      <div role="status" aria-live="polite" aria-atomic="true" className="visually-hidden">{polite}</div>
      <div role="alert" aria-atomic="true" className="visually-hidden">{assertive}</div>
    </>
  )
}

// ---- confirm dialog ------------------------------------------------------------------------

export function ConfirmDialog({ title, body, confirm, cancel = 'Cancel', danger, onConfirm, onClose }: {
  title: string; body: string; confirm: string; cancel?: string; danger?: boolean; onConfirm: () => void; onClose: () => void
}) {
  const ref = useRef<HTMLButtonElement>(null)
  const box = useRef<HTMLDivElement>(null)
  useEffect(() => {
    const prev = document.activeElement as HTMLElement | null
    ref.current?.focus()
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
      if (e.key !== 'Tab' || !box.current) return
      const items = [...box.current.querySelectorAll<HTMLElement>('button:not(:disabled), a[href], input, select, textarea')]
      if (!items.length) return
      const first = items[0], last = items[items.length - 1]
      const inside = box.current.contains(document.activeElement)
      if (e.shiftKey && (document.activeElement === first || !inside)) { e.preventDefault(); last.focus() }
      else if (!e.shiftKey && (document.activeElement === last || !inside)) { e.preventDefault(); first.focus() }
    }
    window.addEventListener('keydown', onKey)
    return () => { window.removeEventListener('keydown', onKey); prev?.focus() }
  }, [onClose])
  return (
    <div className="dialog-backdrop" onMouseDown={(e) => { if (e.target === e.currentTarget) onClose() }}>
      <div className="dialog" ref={box} role="dialog" aria-modal="true" aria-labelledby="dlg-title" aria-describedby="dlg-body">
        <h2 id="dlg-title">{title}</h2>
        <p id="dlg-body">{body}</p>
        <div className="acts">
          <button className="btn btn-sm" ref={ref} onClick={onClose}>{cancel}</button>
          <button className={`btn btn-sm ${danger ? 'btn-danger' : 'btn-primary'}`} onClick={() => { onConfirm(); onClose() }}>{confirm}</button>
        </div>
      </div>
    </div>
  )
}
