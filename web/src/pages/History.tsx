import { useEffect, useRef, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { api, type RunSummary } from '../api'
import { Character } from '../components/Character'
import { More, Search } from '../components/Icons'
import { ConfirmDialog } from '../components/RunParts'
import { MenuButton } from '../components/Shell'
import { ago, dayGroup, duration, money, STATUS_DOT, STATUS_LABEL } from '../format'
import { useRuns } from '../state/hooks'
import { agentAccessory, agentColor, ORCHESTRATOR_COLOR } from '../state/reducer'

const FILTERS = [
  { id: '', label: 'All' },
  { id: 'finished', label: 'Finished' },
  { id: 'gave_up', label: 'Out of budget' },
  { id: 'failed', label: 'Crashed' },
  { id: 'repo', label: 'In a repo' },
]

function moodFor(status: string) {
  return status === 'finished' ? 'happy' : status === 'running' ? 'working' : status === 'gave_up' ? 'sad' : 'sleepy'
}

function RowMenu({ run, onDelete }: { run: RunSummary; onDelete: () => void }) {
  const nav = useNavigate()
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLDivElement>(null)
  useEffect(() => {
    if (!open) return
    const close = (e: MouseEvent) => { if (!ref.current?.contains(e.target as Node)) setOpen(false) }
    const key = (e: KeyboardEvent) => { if (e.key === 'Escape') setOpen(false) }
    document.addEventListener('mousedown', close)
    document.addEventListener('keydown', key)
    return () => { document.removeEventListener('mousedown', close); document.removeEventListener('keydown', key) }
  }, [open])
  const rerun = async () => {
    const d = await fetch(`/api/runs/${run.id}`).then((r) => r.json())
    nav('/', { state: { task: d.task, options: d.options } })
  }
  return (
    <div className="menu-wrap" ref={ref}>
      <button className="icon-btn" aria-label={`Actions for ${run.title}`} aria-haspopup="menu" aria-expanded={open} onClick={() => setOpen((o) => !o)}><More /></button>
      {open && (
        <div className="menu" role="menu">
          <button role="menuitem" onClick={rerun}>Rerun with edits</button>
          <a role="menuitem" href={api.zipUrl(run.id)} download>Download files (.zip)</a>
          <button role="menuitem" className="danger" disabled={run.status === 'running'} onClick={() => { setOpen(false); onDelete() }}>
            {run.status === 'running' ? 'Delete (stop it first)' : 'Delete run'}
          </button>
        </div>
      )}
    </div>
  )
}

export function History() {
  const [q, setQ] = useState('')
  const [debounced, setDebounced] = useState('')
  const [filter, setFilter] = useState('')
  const [toDelete, setToDelete] = useState<RunSummary | null>(null)
  useEffect(() => { const id = setTimeout(() => setDebounced(q), 200); return () => clearTimeout(id) }, [q])
  const { runs, loaded, reload } = useRuns({
    q: debounced, limit: 100,
    status: filter && filter !== 'repo' ? filter : undefined,
    repo: filter === 'repo' ? true : undefined,
  })
  useEffect(() => { document.title = 'All runs · ChaCha PA' }, [])
  const total = runs.reduce((s, r) => s + (r.cost_usd || 0), 0)
  const groups = (['Today', 'Yesterday', 'Earlier'] as const).map((g) => ({ g, runs: runs.filter((r) => dayGroup(r.created_at) === g) })).filter((x) => x.runs.length)

  return (
    <div className="history">
      <div className="history-head">
        <MenuButton />
        <div className="grow">
          <h1>All runs</h1>
          <span className="muted" style={{ fontSize: 14 }}>{runs.length} {runs.length === 1 ? 'run' : 'runs'} · {money(total)} est. usage</span>
        </div>
        <label className="search">
          <Search />
          <span className="visually-hidden">Search runs</span>
          <input type="search" value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search tasks" />
        </label>
      </div>
      <div className="filters" role="group" aria-label="Filter by outcome">
        {FILTERS.map((f) => (
          <button key={f.id} className="chip" aria-pressed={filter === f.id} onClick={() => setFilter(f.id)}>{f.label}</button>
        ))}
      </div>
      {loaded && runs.length === 0 && (
        <div className="empty">
          <Character color={ORCHESTRATOR_COLOR} accessory="bow" mood="sleepy" size={56} />
          <span>{q || filter ? 'No runs match.' : 'No runs yet. Start one and it will show up here.'}</span>
          {!q && !filter && <Link className="btn btn-primary" to="/">New run</Link>}
        </div>
      )}
      {groups.map(({ g, runs: rs }) => (
        <section className="run-group" key={g}>
          <h2>{g}</h2>
          {rs.map((r) => {
            const dot = r.needs_approval ? 'check' : STATUS_DOT[r.status] || 'border'
            return (
              <div className="run-row" key={r.id}>
                <Link className="main-link" to={`/runs/${r.id}`}>
                  <span className="faces" aria-hidden>
                    {(r.agents.length ? r.agents.slice(0, 4) : [{ name: 'o', color_index: -1 }]).map((a) => (
                      <Character key={a.name} color={a.color_index < 0 ? ORCHESTRATOR_COLOR : agentColor(a.color_index)}
                        accessory={a.color_index < 0 ? 'bow' : agentAccessory(a.color_index)} mood={moodFor(r.status)} size={30} animate={false} />
                    ))}
                  </span>
                  <span className="txt">
                    <span className="ttl">{r.title}</span>
                    <span className="meta">
                      {ago(r.created_at)} · {duration(r.duration_s)} · {r.agents.length} {r.agents.length === 1 ? 'agent' : 'agents'}
                      {r.repo ? ` · ${r.repo.split('/').pop()}` : ''}
                    </span>
                  </span>
                  <span className="st"><span className={`dot dot-${dot}`} aria-hidden />{r.needs_approval ? 'Needs approval' : STATUS_LABEL[r.status] || r.status}</span>
                  <span className="cost">{money(r.cost_usd)}</span>
                </Link>
                <RowMenu run={r} onDelete={() => setToDelete(r)} />
              </div>
            )
          })}
        </section>
      ))}
      {toDelete && (
        <ConfirmDialog title="Delete this run?" body={`"${toDelete.title}" and its files will be removed. This can't be undone.`}
          confirm="Delete run" danger onConfirm={() => api.remove(toDelete.id).then(reload)} onClose={() => setToDelete(null)} />
      )}
    </div>
  )
}
