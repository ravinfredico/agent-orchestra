import { useEffect, useMemo, useRef, useState } from 'react'
import { Character } from '../components/Character'
import { Markdown } from '../components/Markdown'
import { Team } from '../components/Icons'
import { Rail } from '../components/RunParts'
import { Item } from '../pages/RunPage'
import { isLive, ORCHESTRATOR_COLOR, reduceAll } from '../state/reducer'
import type { RunEvent, RunView } from '../state/types'
import { holdAfter, SPEEDS } from './clock'

const REPO_URL = 'https://github.com/ravinfredico/agent-orchestra'

/** Plays a recorded log.jsonl with the app's own reducer and components (canvas M6-Replay). No server. */
export function Replay({ events, autoplay = true }: { events: RunEvent[]; autoplay?: boolean }) {
  const [shown, setShown] = useState(1)
  const [playing, setPlaying] = useState(autoplay)
  const [speed, setSpeed] = useState<(typeof SPEEDS)[number]>(2)
  const [railOpen, setRailOpen] = useState(false)
  const bottom = useRef<HTMLDivElement>(null)
  const total = events.length
  const done = shown >= total

  useEffect(() => {
    if (!playing || done) return
    const id = window.setTimeout(() => setShown((n) => Math.min(total, n + 1)), holdAfter(events[shown - 1], speed))
    return () => window.clearTimeout(id)
  }, [playing, shown, speed, done, events, total])
  useEffect(() => { if (done) setPlaying(false) }, [done])
  useEffect(() => { bottom.current?.scrollIntoView?.({ block: 'end' }) }, [shown])

  // the log's own timestamps are from the past: elapsed time is measured up to the last event shown
  const run: RunView = useMemo(() => {
    const r = reduceAll(events.slice(0, shown))
    return { ...r, endedAt: r.endedAt ?? r.lastEventAt }
  }, [events, shown])
  const live = isLive(run)
  const working = Object.values(run.agents).filter((a) => a.currentTask && a.activity)

  return (
    <div className="replay-page">
      <header className="replay-head">
        <span className="sb-brand"><Character color={ORCHESTRATOR_COLOR} accessory="bow" mood="neutral" size={26} animate={false} />ChaCha PA</span>
        <span className="replay-badge">Replay · a recorded run, no live agents</span>
        <a className="replay-src" href={REPO_URL}>Source on GitHub</a>
        <button className="icon-btn rail-toggle" aria-label="Team and usage" aria-expanded={railOpen} onClick={() => setRailOpen(true)}><Team /></button>
      </header>
      <div className="run-page" style={{ display: 'flex', flexDirection: 'row', flex: 1, minWidth: 0 }}>
        <main style={{ flex: 1, minWidth: 0, display: 'flex', flexDirection: 'column', minHeight: 'calc(100vh - 53px)' }}>
          <h1 className="visually-hidden">Replay: {run.title}</h1>
          <div className="thread" style={{ flex: 1 }}>
            {run.thread.map((it, i) => <Item key={`${it.kind}-${it.seq}`} item={it} run={run} last={i === run.thread.length - 1} />)}
            {live && working.map((a) => (
              <div className="activity indent" key={a.name}><span className="typing" aria-hidden><i /><i /><i /></span>{a.name} is {a.activity}</div>
            ))}
            {done && (
              <div className="outcome replay-end enter">
                <h2>Replay finished</h2>
                {run.final && <div className="replay-final"><Markdown source={run.final} /></div>}
                <div className="team-actions">
                  <button className="btn btn-primary" onClick={() => { setShown(1); setPlaying(true) }}>Play again</button>
                  <a className="btn" href={REPO_URL}>See how it works</a>
                </div>
              </div>
            )}
            <div ref={bottom} className="thread-end" />
          </div>
          <div className="runbar-wrap">
            <div className="replay-bar">
              <button className="send-btn" aria-label={playing ? 'Pause' : done ? 'Play again' : 'Play'}
                onClick={() => { if (done) { setShown(1); setPlaying(true) } else setPlaying((p) => !p) }}>
                {playing
                  ? <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor" aria-hidden><rect x="6" y="5" width="4" height="14" rx="1" /><rect x="14" y="5" width="4" height="14" rx="1" /></svg>
                  : <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor" aria-hidden><path d="M8 5v14l11-7z" /></svg>}
              </button>
              <label className="replay-pos">
                <span className="visually-hidden">Position</span>
                <input type="range" min={1} max={total} value={shown} onChange={(e) => setShown(Number(e.target.value))}
                  aria-valuetext={`Event ${shown} of ${total}`} />
              </label>
              <span className="replay-count mono" aria-hidden>{shown} / {total}</span>
              <div className="presets" role="group" aria-label="Speed">
                {SPEEDS.map((s) => <button key={s} className="chip chip-sm" aria-pressed={speed === s} onClick={() => setSpeed(s)}>{s}×</button>)}
              </div>
            </div>
          </div>
        </main>
        <Rail run={run} open={railOpen} onClose={() => setRailOpen(false)} />
        {railOpen && <div className="scrim" onClick={() => setRailOpen(false)} />}
      </div>
    </div>
  )
}
