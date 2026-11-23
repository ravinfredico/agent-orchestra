import { useCallback, useEffect, useRef, useState } from 'react'
import { api, RUNS_CHANGED, type Health, type RunSummary } from '../api'
import { emptyRun, reduce, TERMINAL } from './reducer'
import type { RunEvent, RunView } from './types'

/** Live run state from the SSE stream. EventSource resumes from the last seq on its own after a drop. */
export function useRunEvents(runId: string | undefined): { run: RunView; connected: boolean; error: string } {
  const [run, setRun] = useState<RunView>(() => emptyRun(runId))
  const [connected, setConnected] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    if (!runId) return
    setRun(emptyRun(runId))
    setError('')
    const es = new EventSource(api.eventsUrl(runId))
    let ended = false
    const onEvent = (msg: MessageEvent) => {
      try {
        const e = JSON.parse(msg.data) as RunEvent
        setRun((r) => reduce(r, e))
        if (TERMINAL.has(e.type)) ended = true
      } catch { /* ignore malformed */ }
    }
    // the server sends named events (event: <type>), so listen to each type plus the default
    const types = ['run_started', 'playbook_chosen', 'orchestrator_said', 'nudge', 'agent_created', 'task_assigned', 'attempt_started',
      'worker_activity', 'file_written', 'checker_started', 'attempt_failed', 'task_passed', 'task_failed',
      'task_replaced', 'approval_requested', 'approval_resolved', 'usage', 'budget_exhausted', 'finished',
      'run_failed', 'run_stopped', 'run_interrupted']
    types.forEach((t) => es.addEventListener(t, onEvent as EventListener))
    es.onmessage = onEvent
    es.addEventListener('end', () => { ended = true; es.close(); setConnected(false) })
    es.onopen = () => setConnected(true)
    es.onerror = () => {
      setConnected(false)
      if (ended) es.close()
      else fetch(`/api/runs/${runId}`).then((r) => { if (r.status === 404) { setError('Run not found'); es.close() } }).catch(() => {})
    }
    return () => es.close()
  }, [runId])

  return { run, connected, error }
}

/** Run list for the sidebar and history. Refreshes on RUNS_CHANGED and every few seconds while any run is live. */
export function useRuns(params: { q?: string; status?: string; repo?: boolean; limit?: number } = {}) {
  const [runs, setRuns] = useState<RunSummary[]>([])
  const [loaded, setLoaded] = useState(false)
  const key = JSON.stringify(params)
  const timer = useRef<number | undefined>(undefined)

  const load = useCallback(() => {
    api.runs(JSON.parse(key)).then((d) => { setRuns(d.runs); setLoaded(true) }).catch(() => setLoaded(true))
  }, [key])

  useEffect(() => {
    load()
    window.addEventListener(RUNS_CHANGED, load)
    timer.current = window.setInterval(load, 4000)
    return () => { window.removeEventListener(RUNS_CHANGED, load); window.clearInterval(timer.current) }
  }, [load])

  return { runs, loaded, reload: load }
}

export function useHealth(): Health | null {
  const [h, setH] = useState<Health | null>(null)
  useEffect(() => { api.health().then(setH).catch(() => setH(null)) }, [])
  return h
}

/** Seconds since `start`, ticking once a second while `live`. */
export function useElapsed(start: number | null, end: number | null, live: boolean): number {
  const [now, setNow] = useState(() => Date.now() / 1000)
  useEffect(() => {
    if (!live) return
    const id = window.setInterval(() => setNow(Date.now() / 1000), 1000)
    return () => window.clearInterval(id)
  }, [live])
  if (!start) return 0
  return Math.max(0, Math.round((end ?? (live ? now : start)) - start))
}

type Theme = 'dark' | 'light'
export function useTheme(): [Theme, () => void] {
  const [theme, setTheme] = useState<Theme>(() => (document.documentElement.dataset.theme as Theme) || 'dark')
  const toggle = useCallback(() => {
    setTheme((t) => {
      const next = t === 'dark' ? 'light' : 'dark'
      document.documentElement.dataset.theme = next
      try { localStorage.setItem('chacha-theme', next) } catch { /* storage blocked */ }
      document.querySelector('meta[name=theme-color]')?.setAttribute('content', next === 'dark' ? '#0A0A0A' : '#FFFFFF')
      return next
    })
  }, [])
  return [theme, toggle]
}
