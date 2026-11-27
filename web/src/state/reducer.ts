import type { Agent, Mood, RunEvent, RunView, TaskCardState } from './types'

export const AGENT_COLORS = ['#FF8A6B', '#4FC7B8', '#F5C451', '#B48CE0', '#7FA6FF', '#F29FC5']
export const ORCHESTRATOR_COLOR = '#9D8CFF'
export const CHECKER_COLOR = '#C9C9CF'
export const TERMINAL = new Set(['finished', 'run_failed', 'run_stopped', 'run_interrupted'])

export function agentColor(index: number) {
  return AGENT_COLORS[index % AGENT_COLORS.length]
}
export function agentAccessory(index: number) {
  return index >= AGENT_COLORS.length ? 'antenna' : 'none'
}

export function emptyRun(id = ''): RunView {
  return {
    id, task: '', title: '', status: 'created', options: {}, authMode: '', repo: null, branch: null,
    parentId: null, startedAt: null, endedAt: null, lastEventAt: null, costUsd: 0, modelCalls: 0,
    assignments: 0, agents: {}, agentOrder: [], tasks: {}, approvals: {}, files: {}, thread: [],
    final: '', giveUp: false, budgetReason: '', error: null, replanning: false, playbook: null, lastSeq: 0, announcements: [],
  }
}

function announce(r: RunView, e: RunEvent, text: string, assertive = false) {
  r.announcements = [...r.announcements.slice(-20), { seq: e.seq, text, assertive }]
}

/** Apply one event. Pure: returns a new RunView. Events with seq <= lastSeq are ignored (replays). */
export function reduce(prev: RunView, e: RunEvent): RunView {
  if (e.seq <= prev.lastSeq) return prev
  const r: RunView = {
    ...prev, agents: { ...prev.agents }, tasks: { ...prev.tasks }, approvals: { ...prev.approvals },
    files: { ...prev.files }, thread: [...prev.thread], lastSeq: e.seq, lastEventAt: e.t,
  }
  const task = (id: string): TaskCardState | undefined => (r.tasks[id] ? (r.tasks[id] = { ...r.tasks[id] }) : undefined)
  const agent = (name: string): Agent | undefined => (r.agents[name] ? (r.agents[name] = { ...r.agents[name] }) : undefined)

  switch (e.type) {
    case 'run_started':
      Object.assign(r, {
        id: e.run_id, task: e.task ?? '', title: e.title ?? '', status: 'running', options: e.options ?? {},
        authMode: e.auth_mode ?? '', repo: e.repo ?? null, branch: e.branch ?? null, parentId: e.parent_id ?? null,
        startedAt: e.t,
      })
      r.thread.push({ kind: 'task_message', seq: e.seq, text: e.task ?? '' })
      break
    case 'playbook_chosen':
      r.playbook = { id: e.id, title: e.title }
      r.thread.push({ kind: 'playbook', seq: e.seq, id: e.id, title: e.title })
      break
    case 'orchestrator_said':
      r.thread.push({ kind: 'say', seq: e.seq, text: e.text })
      break
    case 'agent_created': {
      r.agents[e.name] = {
        name: e.name, role: e.role ?? '', tools: e.tools ?? [], model: e.model ?? '', tierReason: e.tier_reason ?? '',
        colorIndex: e.color_index ?? r.agentOrder.length, activity: '', currentTask: null, passed: 0, failed: 0,
      }
      r.agentOrder = [...r.agentOrder, e.name]
      const last = r.thread[r.thread.length - 1]
      if (last && last.kind === 'joined') r.thread[r.thread.length - 1] = { ...last, names: [...last.names, e.name] }
      else r.thread.push({ kind: 'joined', seq: e.seq, names: [e.name] })
      r.replanning = false
      announce(r, e, `${e.name} joined the team`)
      break
    }
    case 'task_assigned':
      r.assignments += 1
      r.tasks[e.task_id] = {
        taskId: e.task_id, title: e.title || e.task_id, agent: e.agent, task: e.task ?? '', doneWhen: e.done_when ?? '',
        replaces: e.replaces ?? '', replacedBy: '', status: 'pending', attempts: 0, short: '', history: [],
        tier: e.tier ?? '', tierReason: e.tier_reason ?? '',
      }
      r.thread.push({ kind: 'task', seq: e.seq, taskId: e.task_id })
      r.replanning = false
      break
    case 'attempt_started': {
      const t = task(e.task_id)
      if (t) {
        t.attempts = e.attempt
        if (e.tier) t.tier = e.tier
        t.status = e.attempt > 1 ? 'retrying' : 'running'
        const a = agent(t.agent)
        if (a) { a.currentTask = t.taskId; a.activity = '' }
      }
      break
    }
    case 'worker_activity': {
      const a = agent(e.agent)
      if (a) a.activity = e.summary ?? ''
      break
    }
    case 'file_written': {
      const f = r.files[e.path]
      r.files[e.path] = { path: e.path, agent: e.agent ?? '', versions: f ? f.versions + 1 : 1, t: e.t }
      break
    }
    case 'checker_started': {
      const t = task(e.task_id)
      if (t) {
        t.status = 'checking'
        const a = agent(t.agent)
        if (a) a.activity = ''
      }
      break
    }
    case 'attempt_failed': {
      const t = task(e.task_id)
      if (t) {
        t.status = 'sent_back'
        t.short = e.short ?? ''
        t.history = [...t.history, { attempt: e.attempt, tier: t.tier, passed: false, reason: e.reason ?? '', short: e.short ?? '' }]
        announce(r, e, `${t.title}: try ${e.attempt} sent back. ${e.short || e.reason || ''}`)
      }
      break
    }
    case 'task_passed': {
      const t = task(e.task_id)
      if (t) {
        t.status = 'done'
        t.short = e.short ?? ''
        t.history = [...t.history, { attempt: e.attempt, tier: t.tier, passed: true, reason: e.reason ?? '', short: e.short ?? '' }]
        const a = agent(t.agent)
        if (a) { a.currentTask = null; a.activity = ''; a.passed += 1 }
        announce(r, e, `${t.title} passed`)
      }
      break
    }
    case 'task_failed': {
      const t = task(e.task_id)
      if (t) {
        t.status = 'failed'
        const a = agent(t.agent)
        if (a) { a.currentTask = null; a.activity = ''; a.failed += 1 }
        r.replanning = true
        announce(r, e, `${t.title} failed after ${e.attempts} tries`)
      }
      break
    }
    case 'task_replaced': {
      const t = task(e.task_id)
      if (t) {
        t.status = 'replaced'
        t.replacedBy = e.by ?? ''
        announce(r, e, `${t.title} was replaced`)
      }
      break
    }
    case 'approval_requested':
      r.approvals[e.approval_id] = {
        approvalId: e.approval_id, taskId: e.task_id ?? '', agent: e.agent ?? '', tool: e.tool ?? '',
        catalogId: e.catalog_id ?? '', preview: e.preview ?? '', decision: 'pending',
      }
      r.thread.push({ kind: 'approval', seq: e.seq, approvalId: e.approval_id })
      announce(r, e, `${e.agent} needs your approval to ${toolVerb(e.tool)}`, true)
      break
    case 'approval_resolved': {
      const ap = r.approvals[e.approval_id]
      if (ap) r.approvals[e.approval_id] = { ...ap, decision: e.decision }
      break
    }
    case 'usage':
      r.costUsd = e.cost_usd ?? r.costUsd
      r.modelCalls = e.model_calls ?? r.modelCalls
      break
    case 'budget_exhausted':
      r.budgetReason = e.reason ?? ''
      break
    case 'finished':
      r.status = e.give_up ? 'gave_up' : 'finished'
      r.final = e.result ?? ''
      r.giveUp = !!e.give_up
      announce(r, e, e.give_up ? 'Run ended: out of budget' : 'Run finished. Every task passed.')
      break
    case 'run_failed':
      r.status = 'failed'
      r.error = { error: e.error ?? '', kind: e.kind ?? 'crash', hint: e.hint ?? '' }
      announce(r, e, 'Run crashed. ' + (e.hint ?? ''))
      break
    case 'run_stopped':
      r.status = 'stopped'
      announce(r, e, 'Run stopped')
      break
    case 'run_interrupted':
      r.status = 'interrupted'
      break
  }
  if (TERMINAL.has(e.type)) {
    r.endedAt = e.t
    r.replanning = false
    for (const ap of Object.values(r.approvals)) {
      if (ap.decision === 'pending') r.approvals[ap.approvalId] = { ...ap, decision: 'expired' }
    }
    for (const name of r.agentOrder) {
      const a = r.agents[name]
      if (a.currentTask || a.activity) r.agents[name] = { ...a, currentTask: null, activity: '' }
    }
  }
  return r
}

export function reduceAll(events: RunEvent[], id = ''): RunView {
  return events.reduce(reduce, emptyRun(id))
}

export function toolVerb(tool: string): string {
  const name = (tool || '').split('__').pop() || tool
  return name.replace(/_/g, ' ')
}

export const isLive = (r: RunView) => r.status === 'running' || r.status === 'created'
export const needsApproval = (r: RunView) => Object.values(r.approvals).some((a) => a.decision === 'pending')

// ---- presentation helpers (used by components, tested here) ---------------------------

export interface CardLook {
  mood: Mood
  line: string
  dot: 'border' | 'text' | 'check' | 'pass' | 'fail'
  pips: ('empty' | 'current' | 'done' | 'fail')[]
}

export function cardLook(t: TaskCardState, r?: RunView, maxAttempts = 3): CardLook {
  const fails = t.history.filter((h) => !h.passed).length
  const pips: CardLook['pips'] = []
  for (let i = 0; i < maxAttempts; i++) {
    const h = t.history[i]
    if (h) pips.push(h.passed ? 'done' : 'fail')
    else if (i === t.attempts - 1 && ['running', 'checking', 'retrying'].includes(t.status)) pips.push('current')
    else pips.push('empty')
  }
  const stopped = r && !isLive(r)
  switch (t.status) {
    case 'pending':
      return { mood: 'sleepy', line: stopped ? 'Not started' : 'Queued', dot: 'border', pips }
    case 'running':
      return { mood: stopped ? 'sleepy' : 'working', line: stopped ? `Interrupted · try ${t.attempts}` : `Working · try ${t.attempts}`, dot: 'text', pips }
    case 'retrying':
      return { mood: stopped ? 'sleepy' : 'working', line: stopped ? `Interrupted · try ${t.attempts}` : `Try ${t.attempts} · ${t.short || 'retrying'}`, dot: 'check', pips }
    case 'checking':
      return { mood: stopped ? 'sleepy' : 'waiting', line: stopped ? `Interrupted · try ${t.attempts}` : `Checking · try ${t.attempts}`, dot: 'check', pips }
    case 'sent_back':
      return { mood: 'sad', line: `Sent back · ${t.short || 'see notes'}`, dot: 'check', pips }
    case 'done':
      return { mood: 'happy', line: fails ? `Passed on try ${t.attempts}` : 'Passed', dot: 'pass', pips }
    case 'failed':
      return { mood: 'sad', line: `Failed · ${t.attempts} ${t.attempts === 1 ? 'try' : 'tries'}`, dot: 'fail', pips }
    case 'replaced': {
      const by = r?.tasks[t.replacedBy]?.title || t.replacedBy
      return { mood: 'sleepy', line: `Replaced by ${by}`, dot: 'border', pips: [] }
    }
  }
}

export function agentMood(a: Agent, r: RunView): Mood {
  if (!isLive(r)) {
    if (r.status === 'finished') return a.passed > 0 ? 'happy' : 'neutral'
    if (r.status === 'gave_up' || r.status === 'failed') return a.failed > 0 ? 'sad' : 'sleepy'
    return 'sleepy'
  }
  const t = a.currentTask ? r.tasks[a.currentTask] : undefined
  if (t) {
    if (t.status === 'checking') return 'waiting'
    if (t.status === 'sent_back') return 'sad'
    return 'working'
  }
  return Object.values(r.tasks).some((x) => x.agent === a.name) ? 'sleepy' : 'neutral'
}

export function agentStatusText(a: Agent, r: RunView): string {
  const t = a.currentTask ? r.tasks[a.currentTask] : undefined
  if (t && isLive(r)) {
    if (t.status === 'checking') return `Waiting on checker · ${t.title}`
    if (t.status === 'sent_back') return `Sent back · ${t.title}`
    return `Working · ${t.title}${t.attempts > 1 ? `, try ${t.attempts}` : ''}`
  }
  const parts = []
  if (a.passed) parts.push(`${a.passed} passed`)
  if (a.failed) parts.push(`${a.failed} failed`)
  return parts.length ? parts.join(' · ') : isLive(r) ? 'Idle' : 'No tasks'
}

export function orchestratorMood(r: RunView): Mood {
  switch (r.status) {
    case 'finished': return 'happy'
    case 'gave_up': return 'sad'
    case 'failed': case 'stopped': case 'interrupted': return 'sleepy'
    default: return r.replanning ? 'working' : needsApproval(r) ? 'waiting' : 'neutral'
  }
}
