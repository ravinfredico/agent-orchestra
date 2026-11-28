import { useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { api, type CatalogEntry, type Proposal, type TeamInput } from '../api'
import { Character } from '../components/Character'
import { Lock } from '../components/Icons'
import { MenuButton } from '../components/Shell'
import { CHEAP_PRESET } from '../presets'
import { agentAccessory, agentColor, ORCHESTRATOR_COLOR } from '../state/reducer'
import { cronLabel } from './TeamPage'

const EXAMPLES = [
  ['Marketing team', 'I want a marketing team that plans our posts every week and drafts the newsletter'],
  ['TikTok studio', 'A TikTok team that makes 3 videos a week and learns from the stats'],
  ['Stocks desk', 'A team that writes a daily brief on my watchlist. It never trades.'],
]

/** "connector.google-drive" -> "Google Drive"; catalog labels win. */
export function toolLabel(id: string, catalog: CatalogEntry[]): string {
  const e = catalog.find((x) => x.id === id)
  if (e?.label) return e.label
  if (id.startsWith('connector.')) return id.slice(10).split('-').map((w) => w[0]?.toUpperCase() + w.slice(1)).join(' ')
  return id
}

/** Your answers to the builder's questions become notes the team reads before every run. */
export function draftFrom(p: Proposal, answers: Record<number, string>): TeamInput {
  const notes = p.questions.map((q, i) => (answers[i] ? `- ${q.question} ${answers[i]}` : '')).filter(Boolean)
  return { ...p.team, options: { ...CHEAP_PRESET }, memory: `## Notes\n${notes.join('\n')}${notes.length ? '\n' : ''}\n## Past runs\n` }
}

/** M9 team builder (DESIGN.md, canvas M9-Builder): describe, review the proposal, save or edit. */
export function TeamBuilder() {
  const nav = useNavigate()
  const [goal, setGoal] = useState('')
  const [asked, setAsked] = useState('')
  const [p, setP] = useState<Proposal | null>(null)
  const [answers, setAnswers] = useState<Record<number, string>>({})
  const [catalog, setCatalog] = useState<CatalogEntry[]>([])
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => { api.catalog().then(setCatalog).catch(() => {}) }, [])
  useEffect(() => { document.title = 'New team · ChaCha PA' }, [])

  const propose = async (text: string) => {
    if (!text.trim() || busy) return
    setBusy(true); setError(''); setAsked(text.trim())
    try {
      const res = await api.proposeTeam(text.trim())
      setP(res)
      setAnswers(Object.fromEntries(res.questions.map((q, i) => [i, q.options[0] ?? ''])))
    } catch (err) {
      setError((err as Error).message)
    } finally {
      setBusy(false)
    }
  }
  const save = async () => {
    if (!p) return
    setBusy(true); setError('')
    try {
      const saved = await api.createTeam(draftFrom(p, answers))
      nav(`/teams/${saved.id}`)
    } catch (err) {
      setError((err as Error).message); setBusy(false)
    }
  }
  const asks = (id: string) => catalog.find((e) => e.id === id)?.risk === 'outward'
  const connectors = catalog.filter((e) => e.kind === 'connector').length

  if (!p) {
    return (
      <div className="team-builder">
        <header className="run-header"><MenuButton /><h1>New team</h1></header>
        <div className="new-run builder-start">
          <h2 className="builder-title">What should the team do?</h2>
          {!busy ? (
            <>
              <form className="composer" onSubmit={(e) => { e.preventDefault(); propose(goal) }}>
                <label className="visually-hidden" htmlFor="team-goal">Describe the team</label>
                <textarea id="team-goal" rows={3} value={goal} onChange={(e) => setGoal(e.target.value)} autoFocus
                  placeholder="I want a marketing team that plans posts weekly and drafts our newsletter"
                  onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); propose(goal) } }} />
                <div className="composer-row">
                  <span className="summary">One model call. Nothing runs until you save.</span>
                  <button type="submit" className="btn btn-primary btn-sm send-btn" disabled={!goal.trim()}>Propose team</button>
                </div>
              </form>
              <div className="suggestions" role="group" aria-label="Examples">
                {EXAMPLES.map(([label, text]) => <button key={label} type="button" className="chip" onClick={() => { setGoal(text); propose(text) }}>{label}</button>)}
              </div>
              {error && <p className="form-error builder-error" role="alert">{error} <button type="button" className="btn btn-sm" onClick={() => propose(asked || goal)}>Try again</button></p>}
              <Link to="/teams/new/edit" className="muted builder-manual">Or set it up by hand</Link>
            </>
          ) : (
            <div className="builder-thinking" role="status">
              <Character color={ORCHESTRATOR_COLOR} accessory="bow" mood="working" size={28} />
              <span className="muted">Designing your team from the catalog{connectors ? ` and your ${connectors} connectors` : ''}…</span>
            </div>
          )}
        </div>
      </div>
    )
  }

  const t = p.team
  return (
    <div className="team-builder">
      <header className="run-header">
        <MenuButton /><h1>New team</h1>
        <span className="builder-badge">Proposal · not saved</span>
      </header>
      <div className="builder-body">
        <section className="builder-main" aria-label="Proposed team">
          <div className="bubble-you">{asked}</div>
          <div className="builder-say">
            <Character color={ORCHESTRATOR_COLOR} accessory="bow" mood="happy" size={28} animate={false} />
            <div><span className="muted builder-from">orchestrator</span><p>{p.summary || `Here is ${t.name}. Check it, then save.`}</p></div>
          </div>
          <h2 className="caps">Members</h2>
          <ul className="builder-members">
            {t.members.map((m, i) => (
              <li key={m.name} className="builder-member">
                <div className="team-row">
                  <Character color={agentColor(i)} accessory={agentAccessory(i)} size={32} animate={false} />
                  <span className="txt"><b className="mono">{m.name}</b><span>{m.role}</span></span>
                  <span className="tier-chip">{m.tier}</span>
                </div>
                <ul className="builder-tools" aria-label={`Tools for ${m.name}`}>
                  {m.tools.map((id) => (
                    <li key={id} className="tool-pill">{toolLabel(id, catalog)}{asks(id) && <span className="tool-pill-asks" title="Asks you first"><Lock /><span className="visually-hidden">, asks first</span></span>}</li>
                  ))}
                  {(m.wants ?? []).map((id) => <li key={id} className="tool-pill tool-pill-missing">{toolLabel(id, catalog)} <span>· set up</span></li>)}
                </ul>
              </li>
            ))}
          </ul>
          <small className="muted builder-legend"><Lock /> asks you before it sends, posts or edits. Tools come only from the catalog and your claude.ai connectors.</small>
        </section>

        <aside className="builder-side" aria-label="Proposal details">
          {p.setup.length > 0 && (
            <section>
              <h2 className="caps">Set up first</h2>
              <ol className="setup-steps">
                {p.setup.map((s) => <li key={s.tool}>{s.text}.</li>)}
              </ol>
              <small className="muted">You can save now. Members skip a tool until it is set up.</small>
            </section>
          )}
          <section>
            <h2 className="caps">Schedule</h2>
            {t.schedule.length === 0 && !t.hook.enabled ? <span className="muted">Only when you message the team.</span> : (
              <ul className="trigger-list">
                {t.schedule.map((s, i) => <li key={i}><b>{cronLabel(s.cron)}</b> · <span className="muted">{s.task}</span></li>)}
                {t.hook.enabled && <li><b>New data</b> · <span className="muted">{t.hook.task}</span></li>}
              </ul>
            )}
            {t.hook.enabled && <small className="muted">New data comes in on the team's webhook. Its URL appears after you save.</small>}
          </section>
          {(t.outputs ?? []).length > 0 && (
            <section><h2 className="caps">Outputs</h2><ul className="trigger-list">{t.outputs!.map((o) => <li key={o}>{o}</li>)}</ul></section>
          )}
          <section>
            <h2 className="caps">Asks you first</h2>
            {p.approvals.length === 0 ? <span className="muted">Nothing: this team only reads and writes files.</span>
              : <ul className="trigger-list">{p.approvals.map((a) => <li key={a}>{a}</li>)}</ul>}
            {(p.refused ?? []).length > 0 && (
              <small className="muted">Left out: {p.refused!.map((id) => toolLabel(id, catalog)).join(', ')}. Anything that moves money stays outside the app.</small>
            )}
          </section>
          {p.questions.map((q, i) => (
            <fieldset key={i} className="builder-question">
              <legend className="caps">{p.questions.length > 1 ? `Question ${i + 1}` : 'One question'}</legend>
              <p>{q.question}</p>
              <div className="connectors">
                {q.options.map((o) => <button key={o} type="button" className="chip" aria-pressed={answers[i] === o} onClick={() => setAnswers({ ...answers, [i]: o })}>{o}</button>)}
              </div>
              <label className="visually-hidden" htmlFor={`q-${i}`}>Other answer</label>
              <input id={`q-${i}`} className="builder-other" placeholder="Other…" value={q.options.includes(answers[i]) ? '' : answers[i] ?? ''}
                onChange={(e) => setAnswers({ ...answers, [i]: e.target.value })} />
              <small className="muted">Answers go into the team's notes. No extra model call.</small>
            </fieldset>
          ))}
        </aside>
      </div>
      <footer className="builder-actions">
        {error && <p className="form-error" role="alert">{error}</p>}
        <button type="button" className="btn btn-primary" onClick={save} disabled={busy}>Save team</button>
        <button type="button" className="btn" onClick={() => nav('/teams/new/edit', { state: { draft: draftFrom(p, answers) } })}>Edit before saving</button>
        <button type="button" className="btn btn-ghost" onClick={() => { setP(null); setGoal(asked) }}>Start over</button>
        <small className="muted builder-note">Cheap preset · runs only on schedule, your messages or the webhook</small>
      </footer>
    </div>
  )
}

