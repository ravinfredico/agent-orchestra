// Live event schema: docs/ARCHITECTURE.md section 7. One envelope for every event.
export interface RunEvent {
  seq: number
  run_id: string
  t: number
  type: string
  [key: string]: any
}

export type RunStatus = 'created' | 'running' | 'finished' | 'gave_up' | 'failed' | 'stopped' | 'interrupted'
export type TaskStatus = 'pending' | 'running' | 'checking' | 'retrying' | 'sent_back' | 'done' | 'failed' | 'replaced'
export type Mood = 'neutral' | 'working' | 'waiting' | 'happy' | 'sad' | 'sleepy'

export interface Agent {
  name: string
  role: string
  tools: string[]
  model: string
  tierReason: string
  colorIndex: number
  activity: string          // latest worker_activity summary while working
  currentTask: string | null
  passed: number
  failed: number
}

export interface CheckResult {
  check: string
  passed: boolean
  detail: string
}

export interface Attempt {
  attempt: number
  tier: string
  checkedBy: string         // model | checks | worker
  checks: CheckResult[]
  passed: boolean
  reason: string
  short: string
}

export interface TaskCardState {
  taskId: string
  title: string
  agent: string
  task: string
  doneWhen: string
  replaces: string
  replacedBy: string
  status: TaskStatus
  attempts: number
  short: string
  history: Attempt[]
  tier: string              // model tier of the current attempt
  tierReason: string
  checks: string[]          // cheap check labels, run before the model checker
  checksOnly: boolean
  dependsOn: string[]       // task ids that must pass first (parallel batches)
  notStarted: string        // why it never started (a dependency failed, out of budget), else ''
}

export interface Approval {
  approvalId: string
  taskId: string
  agent: string
  tool: string
  catalogId: string
  preview: string
  decision: 'pending' | 'approved' | 'denied' | 'expired'
}

export interface FileEntry {
  path: string
  agent: string
  versions: number
  t: number
}

export type ThreadItem =
  | { kind: 'task_message'; seq: number; text: string }
  | { kind: 'say'; seq: number; text: string }
  | { kind: 'playbook'; seq: number; id: string; title: string }
  | { kind: 'joined'; seq: number; names: string[] }
  | { kind: 'task'; seq: number; taskId: string }
  | { kind: 'approval'; seq: number; approvalId: string }

export interface RunView {
  id: string
  task: string
  title: string
  status: RunStatus
  options: Record<string, any>
  authMode: string
  repo: string | null
  branch: string | null
  parentId: string | null
  startedAt: number | null
  endedAt: number | null
  lastEventAt: number | null
  costUsd: number
  modelCalls: number
  assignments: number
  agents: Record<string, Agent>
  agentOrder: string[]
  tasks: Record<string, TaskCardState>
  approvals: Record<string, Approval>
  files: Record<string, FileEntry>
  thread: ThreadItem[]
  final: string
  giveUp: boolean
  budgetReason: string
  error: { error: string; kind: string; hint: string } | null
  replanning: boolean
  playbook: { id: string; title: string } | null
  lastSeq: number
  announcements: { seq: number; text: string; assertive?: boolean }[]
}
