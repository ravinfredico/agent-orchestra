import { useEffect, useRef, useState } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import { api, type CatalogEntry, type PlaybookInfo, type RunOptions } from '../api'
import { Character } from '../components/Character'
import { ArrowUp, Folder, Sliders } from '../components/Icons'
import { MenuButton } from '../components/Shell'
import { CHECKER_COLOR, ORCHESTRATOR_COLOR } from '../state/reducer'

const DEFAULTS: Required<Omit<RunOptions, 'catalog'>> & { catalog: string[] | null } = {
  allow_bash: false, repo: '', orchestrator_model: 'sonnet', worker_model: 'sonnet', checker_model: 'haiku',
  max_cost: 5, max_agents: 6, catalog: null, playbook: 'auto',
}

const SUGGESTIONS = [
  { label: 'Research report with sources', task: 'Research the top 5 Indonesian e-wallets and write a comparison report as report.md with a fee table and at least 10 source URLs' },
  { label: 'Small app with passing tests', task: 'Build a Python CLI todo app with pytest tests that all pass', bash: true },
  { label: 'Feature in my repo', task: 'Add <feature> to this project. Include tests. All existing and new tests must pass.', bash: true, repo: true },
]

export function NewRun() {
  const nav = useNavigate()
  const loc = useLocation()
  const prefill = (loc.state || {}) as { task?: string; options?: RunOptions }
  const [task, setTask] = useState(prefill.task || '')
  const [opts, setOpts] = useState({ ...DEFAULTS, ...(prefill.options || {}), repo: prefill.options?.repo || '' })
  const [showOpts, setShowOpts] = useState(false)
  const [catalog, setCatalog] = useState<CatalogEntry[]>([])
  const [playbooks, setPlaybooks] = useState<PlaybookInfo[]>([])
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const ta = useRef<HTMLTextAreaElement>(null)

  useEffect(() => { api.catalog().then(setCatalog).catch(() => {}) }, [])
  useEffect(() => { api.playbooks().then(setPlaybooks).catch(() => {}) }, [])
  useEffect(() => { ta.current?.focus() }, [])
  useEffect(() => {
    const el = ta.current
    if (el) { el.style.height = 'auto'; el.style.height = Math.min(el.scrollHeight, 280) + 'px' }
  }, [task])

  const extras = catalog.filter((e) => e.kind !== 'builtin')
  const selected = opts.catalog ?? extras.filter((e) => e.enabled && !e.unavailable).map((e) => e.id)
  const toggleTool = (id: string) => {
    const next = selected.includes(id) ? selected.filter((x) => x !== id) : [...selected, id]
    setOpts({ ...opts, catalog: next })
  }
  const set = <K extends keyof typeof opts>(k: K, v: (typeof opts)[K]) => setOpts({ ...opts, [k]: v })

  const submit = async (e?: React.FormEvent) => {
    e?.preventDefault()
    if (!task.trim() || busy) return
    setBusy(true)
    setError('')
    try {
      const options: RunOptions = { ...opts, repo: opts.repo?.trim() || undefined, catalog: opts.catalog }
      const r = await api.start(task.trim(), options)
      nav(`/runs/${r.id}`)
    } catch (err) {
      setError((err as Error).message)
      setBusy(false)
    }
  }

  const summary = `$${opts.max_cost} cap · shell ${opts.allow_bash ? 'on' : 'off'}${opts.repo ? ' · repo' : ''}`
  return (
    <div className="new-run">
      <div style={{ position: 'absolute', top: 12, left: 12 }}><MenuButton /></div>
      <div className="hero" style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 16 }}>
        <div className="duo" aria-hidden>
          <Character color={ORCHESTRATOR_COLOR} accessory="bow" mood={task ? 'neutral' : 'sleepy'} size={56} />
          <Character color={CHECKER_COLOR} accessory="monocle" mood={task ? 'neutral' : 'sleepy'} size={56} />
        </div>
        <h1>What should the team do?</h1>
        <p className="lede">The orchestrator plans it, hires agents, and keeps going until the checker passes every task.</p>
      </div>

      <form className="composer" onSubmit={submit}>
        <label className="visually-hidden" htmlFor="task">Task</label>
        <textarea id="task" ref={ta} rows={2} value={task} onChange={(e) => setTask(e.target.value)}
          placeholder="Give the team a task, and say how to tell it's done"
          onKeyDown={(e) => { if (e.key === 'Enter' && (e.metaKey || e.ctrlKey) && !e.nativeEvent.isComposing) { e.preventDefault(); submit() } }} />
        <div className="composer-row">
          <button type="button" className="icon-btn bordered" aria-label="Work in a repository"
            onClick={() => { setShowOpts(true); setTimeout(() => document.getElementById('opt-repo')?.focus(), 50) }}>
            <Folder s={17} />
          </button>
          <button type="button" className="chip" aria-expanded={showOpts} aria-controls="run-options" aria-pressed={showOpts}
            onClick={() => setShowOpts((s) => !s)}>
            <Sliders />Options
          </button>
          <span className="summary">{summary}</span>
          <button type="submit" className="send-btn" disabled={!task.trim() || busy} aria-label="Start run"><ArrowUp /></button>
        </div>
      </form>
      {error && <p className="form-error" role="alert">{error}</p>}

      {showOpts && (
        <section id="run-options" className="options" aria-label="Run options">
          <label className="toggle wide">
            <input type="checkbox" checked={opts.allow_bash} onChange={(e) => set('allow_bash', e.target.checked)} />
            <span className="switch" aria-hidden />
            <span><b>Allow shell commands</b><small>Needed for code and tests. Commands run in a sandbox on this machine.</small></span>
          </label>
          <label className="field wide">
            <span>Playbook</span>
            <select value={opts.playbook} onChange={(e) => set('playbook', e.target.value)}>
              <option value="auto">Auto: the orchestrator picks</option>
              {playbooks.map((p) => <option key={p.id} value={p.id}>{p.title}</option>)}
            </select>
            <small>{playbooks.find((p) => p.id === opts.playbook)?.when || 'Proven steps and pitfalls for the kind of task. Agents are still invented for each run.'}</small>
          </label>
          <label className="field wide">
            <span>Work in a repository (optional)</span>
            <input id="opt-repo" className="mono" value={opts.repo || ''} onChange={(e) => set('repo', e.target.value)}
              placeholder="~/code/my-app" autoComplete="off" spellCheck={false} />
            <small>Needs a clean git tree. The team works on a new branch, so your main branch is never touched.</small>
          </label>
          {extras.length > 0 && (
            <div className="field wide">
              <span>Connectors and plugins this run may use</span>
              <div className="connectors" role="group" aria-label="Connectors and plugins">
                {extras.map((e) => {
                  const off = !e.enabled || !!e.unavailable
                  return (
                    <button key={e.id} type="button" className="chip" disabled={off} aria-pressed={!off && selected.includes(e.id)}
                      title={e.unavailable ? `Not set up: ${e.unavailable}` : e.description} onClick={() => toggleTool(e.id)}>
                      {e.id}{e.risk === 'outward' ? ' · asks first' : ''}
                    </button>
                  )
                })}
              </div>
              <small>Actions that send or change things (email, calendar) always ask you first. Greyed out ones need setup in .env.</small>
            </div>
          )}
          <label className="field">
            <span>Orchestrator and workers</span>
            <select value={opts.worker_model} onChange={(e) => setOpts({ ...opts, worker_model: e.target.value, orchestrator_model: e.target.value })}>
              <option>sonnet</option><option>opus</option><option>haiku</option>
            </select>
          </label>
          <label className="field">
            <span>Checker</span>
            <select value={opts.checker_model} onChange={(e) => set('checker_model', e.target.value)}>
              <option>haiku</option><option>sonnet</option>
            </select>
          </label>
          <label className="field">
            <span>Usage cap (est. $)</span>
            <input type="number" className="mono" min={0.5} step={0.5} value={opts.max_cost}
              onChange={(e) => set('max_cost', Number(e.target.value))} inputMode="decimal" />
          </label>
          <label className="field">
            <span>Max agents</span>
            <input type="number" className="mono" min={1} max={12} value={opts.max_agents}
              onChange={(e) => set('max_agents', Number(e.target.value))} inputMode="numeric" />
          </label>
        </section>
      )}

      <div className="suggestions">
        {SUGGESTIONS.map((s) => (
          <button key={s.label} type="button" className="chip" onClick={() => {
            setTask(s.task)
            setOpts({ ...opts, allow_bash: !!s.bash || opts.allow_bash })
            if (s.repo) setShowOpts(true)
            ta.current?.focus()
          }}>{s.label}</button>
        ))}
      </div>
    </div>
  )
}
