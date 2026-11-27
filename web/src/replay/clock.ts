import type { RunEvent } from '../state/types'

/** How long to hold after each event at 1× speed (ms). Real gaps are ignored: a recorded run can sit
 *  for minutes on one model call, and demo logs have none. Pacing by event type reads like a live run. */
const HOLD: Record<string, number> = {
  run_started: 900, playbook_chosen: 700, orchestrator_said: 1600, agent_created: 350, task_assigned: 700,
  attempt_started: 400, worker_activity: 450, file_written: 250, checker_started: 700, attempt_failed: 1300,
  task_passed: 900, task_failed: 1300, task_replaced: 600, approval_requested: 1500, approval_resolved: 700,
  user_message: 1200, finished: 0,
}

export const SPEEDS = [1, 2, 4] as const

export function holdAfter(e: RunEvent | undefined, speed = 1): number {
  if (!e) return 0
  return Math.round((HOLD[e.type] ?? 0) / speed)
}

/** Drop machine paths and anything secret-looking before a log goes on a public page. */
export function scrub(events: RunEvent[]): RunEvent[] {
  const pathLike = /(?:[A-Za-z]:\\|\/(?:home|Users|tmp|var|private)\/)[^\s"']*/g
  return events.map((e) => {
    const out: RunEvent = { ...e }
    for (const k of ['workspace', 'repo', 'branch'] as const) if (k in out) out[k] = null
    for (const [k, v] of Object.entries(out)) {
      if (typeof v === 'string') out[k] = v.replace(pathLike, '…').replace(/(sk-ant-|ghp_|xox[bp]-)[A-Za-z0-9_-]+/g, '[secret]')
    }
    return out
  })
}
