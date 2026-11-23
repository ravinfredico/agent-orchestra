import { useState } from 'react'
import { agentAccessory, agentColor, cardLook, CHECKER_COLOR } from '../state/reducer'
import type { RunView, TaskCardState } from '../state/types'
import { Character } from './Character'

/** A face, a short title, one status line, attempt dots. Opens in place for details (DESIGN.md 3.2). */
export function TaskCard({ task, run }: { task: TaskCardState; run: RunView }) {
  const [open, setOpen] = useState(false)
  const look = cardLook(task, run, Number(run.options?.max_attempts) || 3)
  const agent = run.agents[task.agent]
  const idx = agent?.colorIndex ?? 0
  const bodyId = `card-${task.taskId}`
  return (
    <div className={`card enter${task.status === 'replaced' ? ' replaced' : ''}`}>
      <button
        type="button"
        className="card-head"
        aria-expanded={open}
        aria-controls={bodyId}
        onClick={() => setOpen((o) => !o)}
        onKeyDown={(e) => { if (e.key === 'Escape') setOpen(false) }}
      >
        <Character color={agentColor(idx)} accessory={agentAccessory(idx)} mood={look.mood} size={36}
          label={`${task.agent}, ${look.line}`} />
        <span className="txt">
          <span className="ttl">{task.title}</span>
          <span className="line"><span className={`dot dot-${look.dot}`} /><span key={look.line}>{look.line}</span></span>
        </span>
        {look.pips.length > 0 && (
          <span className="pips" aria-hidden>
            {look.pips.map((p, i) => <span key={i} className={`pip pip-${p}`} />)}
          </span>
        )}
      </button>
      {open && (
        <div className="card-body" id={bodyId}>
          <span className="dw"><b>{task.agent}</b> · Done when: {task.doneWhen}</span>
          {task.history.map((h) => (
            <div className="note" key={h.attempt}>
              <Character color={CHECKER_COLOR} accessory="monocle" mood={h.passed ? 'happy' : 'sad'} size={22} animate={false} />
              <span><span className="muted">Try {h.attempt}</span>{h.reason || h.short}</span>
            </div>
          ))}
          {task.history.length === 0 && <span className="muted" style={{ fontSize: 13.5 }}>No checker notes yet.</span>}
        </div>
      )}
    </div>
  )
}
