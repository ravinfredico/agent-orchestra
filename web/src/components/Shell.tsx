import { createContext, useContext, useEffect, useRef, useState } from 'react'
import { Link, NavLink, Outlet, useLocation, useParams } from 'react-router-dom'
import { dayGroup, STATUS_DOT } from '../format'
import { useHealth, useRuns, useTeams, useTheme } from '../state/hooks'
import { ORCHESTRATOR_COLOR } from '../state/reducer'
import { Character } from './Character'
import { Menu, Moon, Plus, Sun } from './Icons'

const DrawerCtx = createContext<{ open: () => void }>({ open: () => {} })
export const useSidebarDrawer = () => useContext(DrawerCtx)

/** Hamburger shown below 1100px (CSS decides visibility). */
export function MenuButton() {
  const { open } = useSidebarDrawer()
  return <button className="icon-btn menu-btn" aria-label="Open runs menu" onClick={open}><Menu /></button>
}

function Sidebar({ open, onNavigate }: { open: boolean; onNavigate: () => void }) {
  const { runs } = useRuns({ limit: 30 })
  const health = useHealth()
  const [theme, toggle] = useTheme()
  const teams = useTeams()
  const { runId, teamId } = useParams()
  const loc = useLocation()
  const today = runs.filter((r) => dayGroup(r.created_at) === 'Today').slice(0, 8)
  const earlier = runs.filter((r) => dayGroup(r.created_at) !== 'Today').slice(0, 5)
  const plan = health?.auth_mode === 'api_key'
  const item = (r: (typeof runs)[number], dim = false) => {
    const live = r.status === 'running'
    const dot = r.needs_approval ? 'check' : STATUS_DOT[r.status] || 'border'
    return (
      <Link key={r.id} to={`/runs/${r.id}`} onClick={onNavigate} className={`sb-item${dim ? ' dim' : ''}`}
        aria-current={runId === r.id ? 'page' : undefined}>
        <span className={`dot dot-${dot}${live ? ' live' : ''}`} aria-hidden />
        <span>{r.title}</span>
      </Link>
    )
  }
  return (
    <nav className={`sidebar${open ? ' open' : ''}`} aria-label="Runs">
      <Link to="/" className="sb-brand" onClick={onNavigate}>
        <Character color={ORCHESTRATOR_COLOR} accessory="bow" mood="neutral" size={26} animate={false} />
        ChaCha PA
      </Link>
      <NavLink to="/" end className="btn sb-new" onClick={onNavigate} aria-current={loc.pathname === '/' ? 'page' : undefined}>
        <Plus s={16} />New run
      </NavLink>
      <div className="sb-list">
        <span className="sb-label">Teams</span>
        {teams.map((t) => (
          <Link key={t.id} to={`/teams/${t.id}`} onClick={onNavigate} className="sb-item" aria-current={teamId === t.id ? 'page' : undefined}>
            <span className={`dot ${t.active_run ? 'dot-text live' : 'dot-border'}`} aria-hidden />
            <span>{t.name}</span>
            <span className="sb-meta">{t.active_run ? 'working' : t.enabled ? '' : 'paused'}</span>
          </Link>
        ))}
        <NavLink to="/teams/new" className="sb-all" onClick={onNavigate}>+ New team</NavLink>
        <span className="sb-label">Today</span>
        {today.length === 0 && <span className="sb-label" style={{ paddingTop: 0 }}>No runs yet</span>}
        {today.map((r) => item(r))}
        {earlier.length > 0 && <span className="sb-label">Earlier</span>}
        {earlier.map((r) => item(r, true))}
        <NavLink to="/history" className="sb-all" onClick={onNavigate}>All runs →</NavLink>
      </div>
      <div className="sb-foot">
        <span className={`dot ${plan ? 'dot-check' : 'dot-pass'}`} aria-hidden />
        <span className="sb-plan" title={plan ? 'ANTHROPIC_API_KEY is set, so runs are billed per use.' : 'Runs use your Claude plan login.'}>
          <b>{health ? (plan ? 'API key' : 'Claude plan') : '…'}</b>
          <span>{health ? (plan ? 'billed per use' : 'plan login · no API key') : ''}{health?.fake_mode ? ' · demo mode' : ''}</span>
        </span>
        <button className="icon-btn bordered" onClick={toggle} aria-label={`Switch to ${theme === 'dark' ? 'light' : 'dark'} theme`}>
          {theme === 'dark' ? <Sun /> : <Moon />}
        </button>
      </div>
    </nav>
  )
}

export function Shell() {
  const [open, setOpen] = useState(false)
  const opener = useRef<HTMLElement | null>(null)
  const loc = useLocation()
  useEffect(() => setOpen(false), [loc.pathname])
  // sidebar drawer (below 1100px): focus moves in on open and back to the menu button on close
  useEffect(() => {
    if (!open) {
      if (opener.current?.isConnected) opener.current.focus()
      opener.current = null
      return
    }
    document.querySelector<HTMLElement>('.sidebar a')?.focus()
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') setOpen(false) }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [open])
  return (
    <DrawerCtx.Provider value={{ open: () => { opener.current = document.activeElement as HTMLElement; setOpen(true) } }}>
      <div className="app">
        <a className="skip-link" href="#content"
          onClick={(e) => { e.preventDefault(); document.getElementById('content')?.focus() }}>Skip to content</a>
        <Sidebar open={open} onNavigate={() => setOpen(false)} />
        {open && <div className="scrim" onClick={() => setOpen(false)} />}
        <main className="main" id="content" tabIndex={-1}><Outlet /></main>
      </div>
    </DrawerCtx.Provider>
  )
}
