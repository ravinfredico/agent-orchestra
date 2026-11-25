import { useEffect, useRef, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { api } from '../api'
import { Character } from '../components/Character'
import { Book, Team } from '../components/Icons'
import { Announcer, ApprovalCard, ConfirmDialog, OutcomeCard, Rail, RunBar } from '../components/RunParts'
import { MenuButton } from '../components/Shell'
import { TaskCard } from '../components/TaskCard'
import { STATUS_DOT, STATUS_LABEL } from '../format'
import { useRunEvents } from '../state/hooks'
import { agentAccessory, agentColor, agentMood, isLive, needsApproval, ORCHESTRATOR_COLOR, orchestratorMood } from '../state/reducer'
import type { RunView, ThreadItem } from '../state/types'

function Item({ item, run, last }: { item: ThreadItem; run: RunView; last: boolean }) {
  switch (item.kind) {
    case 'task_message':
      return <div className="msg-user enter">{item.text}</div>
    case 'say':
      return (
        <div className="msg-orch enter">
          <Character color={ORCHESTRATOR_COLOR} accessory="bow" mood={last ? orchestratorMood(run) : 'neutral'} size={32} label="orchestrator" />
          <p>{item.text}</p>
        </div>
      )
    case 'playbook':
      return (
        <div className="playbook-line indent enter">
          <Book />
          <span>Using the <b>{item.title}</b> playbook</span>
        </div>
      )
    case 'joined':
      return (
        <div className="joined indent enter">
          {item.names.map((n) => {
            const a = run.agents[n]
            return <Character key={n} color={agentColor(a?.colorIndex ?? 0)} accessory={agentAccessory(a?.colorIndex ?? 0)} mood="happy" size={22} animate={false} />
          })}
          <span>
            {item.names.map((n, i) => (
              <span key={n}><b>{n}</b>{i < item.names.length - 2 ? ', ' : i === item.names.length - 2 ? ' and ' : ''}</span>
            ))} joined
          </span>
        </div>
      )
    case 'task': {
      const t = run.tasks[item.taskId]
      return t ? <div className="indent"><TaskCard task={t} run={run} /></div> : null
    }
    case 'approval': {
      const ap = run.approvals[item.approvalId]
      return ap ? <div className="indent"><ApprovalCard ap={ap} run={run} /></div> : null
    }
  }
}

export function RunPage() {
  const { runId } = useParams()
  const { run, error, historySeq } = useRunEvents(runId)
  const [confirmStop, setConfirmStop] = useState(false)
  const [railOpen, setRailOpen] = useState(false)
  const bottom = useRef<HTMLDivElement>(null)
  const railBtn = useRef<HTMLButtonElement>(null)
  const railWasOpen = useRef(false)
  const stick = useRef(true)
  const live = isLive(run)

  useEffect(() => {
    const onScroll = () => { stick.current = window.innerHeight + window.scrollY >= document.body.scrollHeight - 160 }
    window.addEventListener('scroll', onScroll, { passive: true })
    return () => window.removeEventListener('scroll', onScroll)
  }, [])
  useEffect(() => {
    if (stick.current) bottom.current?.scrollIntoView({ block: 'end' })
  }, [run.lastSeq])
  useEffect(() => { document.title = run.title ? `${run.title} · ChaCha PA` : 'ChaCha PA' }, [run.title])
  // rail drawer (below 1280px): focus moves in on open, Escape closes, focus returns to the toggle
  useEffect(() => {
    if (!railOpen) {
      if (railWasOpen.current) { railWasOpen.current = false; railBtn.current?.focus() }
      return
    }
    railWasOpen.current = true
    document.querySelector<HTMLElement>('.rail .rail-toggle')?.focus()
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') setRailOpen(false) }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [railOpen])

  if (error) {
    return (
      <div className="center-page"><div className="empty"><span>That run doesn't exist.</span><Link className="btn" to="/">New run</Link></div></div>
    )
  }

  const working = run.agentOrder.map((n) => run.agents[n]).filter((a) => a.activity && a.currentTask)
  const stateDot = needsApproval(run) ? 'check' : STATUS_DOT[run.status] || 'border'
  const items = run.thread
  return (
    <div className="run-page" style={{ display: 'flex', flexDirection: 'row', flex: 1, minWidth: 0 }}>
      <Announcer run={run} quietThrough={historySeq} />
      <div style={{ flex: 1, minWidth: 0, display: 'flex', flexDirection: 'column', minHeight: '100vh' }}>
        <header className="run-header">
          <MenuButton />
          <h1>{run.title || 'Loading…'}</h1>
          <span className="state"><span className={`dot dot-${stateDot}${live ? ' live' : ''}`} aria-hidden />
            {needsApproval(run) ? 'Needs approval' : STATUS_LABEL[run.status]}</span>
          {run.branch && <span className="mono muted" title="Git branch">{run.branch}</span>}
          <button ref={railBtn} className="icon-btn rail-toggle" aria-label="Team and usage" aria-expanded={railOpen} onClick={() => setRailOpen(true)}><Team /></button>
        </header>
        <div className="team-strip" role="group" aria-label="Team" tabIndex={0}>
          <div><Character color={ORCHESTRATOR_COLOR} accessory="bow" mood={orchestratorMood(run)} size={40} label="orchestrator" /><span>orchestrator</span></div>
          {run.agentOrder.map((n) => {
            const a = run.agents[n]
            return <div key={n}><Character color={agentColor(a.colorIndex)} accessory={agentAccessory(a.colorIndex)} mood={agentMood(a, run)} size={40} label={n} /><span>{n}</span></div>
          })}
        </div>
        <div className="thread">
          {items.map((it, i) => <Item key={`${it.kind}-${it.seq}`} item={it} run={run} last={i === items.length - 1 || it.kind === 'say' && !items.slice(i + 1).some((x) => x.kind === 'say')} />)}
          {live && working.map((a) => (
            <div className="activity indent" key={a.name}>
              <span className="typing" aria-hidden><i /><i /><i /></span>
              {a.name} is {a.activity}
            </div>
          ))}
          {live && items.length <= 1 && (
            <div className="activity indent"><span className="typing" aria-hidden><i /><i /><i /></span>The orchestrator is planning</div>
          )}
          {!live && run.status !== 'created' && <OutcomeCard run={run} />}
          <div ref={bottom} className="thread-end" />
        </div>
        <RunBar run={run} onStop={() => setConfirmStop(true)} />
      </div>
      <Rail run={run} open={railOpen} onClose={() => setRailOpen(false)} />
      {railOpen && <div className="scrim" onClick={() => setRailOpen(false)} />}
      {confirmStop && (
        <ConfirmDialog title="Stop this run?" body="The current attempt is cancelled. Finished tasks and files are kept."
          confirm="Stop run" cancel="Keep running" danger onConfirm={() => runId && api.stop(runId)} onClose={() => setConfirmStop(false)} />
      )}
    </div>
  )
}
