// Thin client for the ChaCha PA server (docs/ARCHITECTURE.md section 6).

export interface RunSummary {
  id: string
  title: string
  task: string
  status: string
  needs_approval: boolean
  created_at: number
  ended_at: number | null
  duration_s: number
  cost_usd: number
  agents: { name: string; color_index: number }[]
  tasks_total: number
  tasks_passed: number
  repo: string | null
  branch: string | null
  parent_id: string | null
}

export interface CatalogEntry {
  id: string
  kind: 'builtin' | 'mcp' | 'plugin' | 'connector'
  description: string
  risk: 'read' | 'write' | 'shell' | 'outward'
  enabled: boolean
  requires: string | null
  unavailable: string | null
  label?: string | null      // claude.ai connector name, e.g. Figma
}

export interface PlaybookInfo {
  id: string
  title: string
  when: string
}

export interface Health {
  ok: boolean
  auth_mode: 'plan' | 'api_key'
  version: string
  fake_mode: boolean
  auth_required: boolean
}

export interface FileInfo {
  path: string
  size: number
  mtime: number
  agent: string
  versions: number
}

export interface RunOptions {
  allow_bash?: boolean
  repo?: string
  orchestrator_model?: string
  worker_model?: string
  checker_model?: string
  pick_tier?: boolean       // the orchestrator picks a model tier per agent and task
  max_tier?: string         // highest tier a pick or step-up may reach
  max_cost?: number
  max_agents?: number
  max_attempts?: number     // tries per task
  max_steps?: number        // tool-use steps per try
  max_assignments?: number  // tasks per run
  max_parallel?: number     // tasks running at once
  catalog?: string[] | null
  playbook?: string
}

export class ApiError extends Error {
  status: number
  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

export interface TeamMember { name: string; role: string; system_prompt?: string; tools: string[]; wants?: string[]; tier: string }
/** Something a team needs from you before a tool works (M9). */
export interface SetupStep { kind: 'connect' | 'sign_in' | 'missing_tool' | 'option'; tool: string; service: string; text: string }
export interface TeamSlot { cron: string; task: string }
export interface Team {
  id: string
  name: string
  goal: string
  members: TeamMember[]
  schedule: TeamSlot[]
  timezone: string
  enabled: boolean
  hook: { enabled: boolean; task: string; secret?: string }
  options: RunOptions
  memory: string
  outputs?: string[]
  active_run: string | null
  approvals?: string[]
  setup?: SetupStep[]
}
export type TeamInput = Omit<Team, 'id' | 'active_run' | 'hook' | 'approvals' | 'setup'> & { hook: { enabled: boolean; task: string } }
/** A video the team saved for you to post by hand (M10). */
export interface StudioItem {
  id: string; run_id: string; name: string; title: string; caption: string; hashtags: string[]
  video: string | null; script: string | null; created: number; posted_at: number | null
}
/** POST /api/teams/propose: a team to review, edit and save. Nothing is saved yet. */
export interface Proposal {
  team: Omit<TeamInput, 'options' | 'memory'>
  summary: string
  questions: { question: string; options: string[] }[]
  approvals: string[]
  setup: SetupStep[]
  /** tools that could move money; never given to a team */
  refused?: string[]
  cost_usd: number
}
export interface RoomItem {
  t: number
  kind: 'you' | 'agent' | 'handoff' | 'result' | 'system' | 'approval'
  approval_id?: string
  text: string
  from?: string
  to?: string
  run_id?: string
  passed?: boolean
  final?: boolean
}

export const AUTH_EVENT = 'chacha:auth-required'
export const RUNS_CHANGED = 'chacha:runs-changed'
export const TEAMS_CHANGED = 'chacha:teams-changed'

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, {
    ...init,
    headers: { 'Content-Type': 'application/json', ...(init?.headers || {}) },
    credentials: 'same-origin',
  })
  if (res.status === 401) window.dispatchEvent(new Event(AUTH_EVENT))
  if (!res.ok) {
    let msg = res.statusText
    try { msg = (await res.json()).detail || msg } catch { /* not json */ }
    throw new ApiError(res.status, msg)
  }
  if (res.status === 204) return undefined as T
  const type = res.headers.get('content-type') || ''
  return (type.includes('json') ? res.json() : res.text()) as Promise<T>
}

const changed = () => window.dispatchEvent(new Event(RUNS_CHANGED))
const teamsChanged = () => { window.dispatchEvent(new Event(TEAMS_CHANGED)); changed() }

export const api = {
  health: () => request<Health>('/api/health'),
  login: (token: string) => request<{ ok: boolean }>('/api/login', { method: 'POST', body: JSON.stringify({ token }) }),
  catalog: () => request<CatalogEntry[]>('/api/catalog'),
  playbooks: () => request<PlaybookInfo[]>('/api/playbooks'),
  runs: (params: { q?: string; status?: string; repo?: boolean; limit?: number } = {}) => {
    const qs = new URLSearchParams()
    Object.entries(params).forEach(([k, v]) => v !== undefined && v !== '' && qs.set(k, String(v)))
    return request<{ runs: RunSummary[]; next: number | null }>(`/api/runs?${qs}`)
  },
  start: async (task: string, options: RunOptions, parent?: { run_id: string; mode: 'continue' | 'follow_up' }) => {
    const r = await request<{ id: string }>('/api/runs', { method: 'POST', body: JSON.stringify({ task, options, parent }) })
    changed()
    return r
  },
  stop: (id: string) => request(`/api/runs/${id}/stop`, { method: 'POST' }).then(changed),
  approve: (id: string, approvalId: string, approve: boolean) =>
    request(`/api/runs/${id}/approvals/${approvalId}`, { method: 'POST', body: JSON.stringify({ decision: approve ? 'approve' : 'deny' }) }),
  continueRun: async (id: string, extra: number) => {
    const r = await request<{ id: string }>(`/api/runs/${id}/continue`, { method: 'POST', body: JSON.stringify({ extra_budget_usd: extra }) })
    changed()
    return r
  },
  remove: (id: string) => request(`/api/runs/${id}`, { method: 'DELETE' }).then(changed),
  files: (id: string) => request<FileInfo[]>(`/api/runs/${id}/files`),
  file: (id: string, path: string) => request<string>(`/api/runs/${id}/files/${path.split('/').map(encodeURIComponent).join('/')}`),
  fileUrl: (id: string, path: string) => `/api/runs/${id}/files/${path.split('/').map(encodeURIComponent).join('/')}`,
  zipUrl: (id: string) => `/api/runs/${id}/zip`,
  eventsUrl: (id: string) => `/api/runs/${id}/events`,
  steer: (id: string, text: string) => request(`/api/runs/${id}/messages`, { method: 'POST', body: JSON.stringify({ text }) }),
  teams: () => request<Team[]>('/api/teams'),
  studio: (id: string) => request<{ items: StudioItem[] }>(`/api/teams/${id}/studio`),
  markPosted: (id: string, runId: string, name: string, posted: boolean) =>
    request<StudioItem>(`/api/teams/${id}/studio/${runId}/${encodeURIComponent(name)}/posted`, { method: 'POST', body: JSON.stringify({ posted }) }),
  proposeTeam: (goal: string) => request<Proposal>('/api/teams/propose', { method: 'POST', body: JSON.stringify({ goal }) }),
  team: (id: string) => request<Team>(`/api/teams/${id}`),
  createTeam: async (t: TeamInput) => { const r = await request<Team>('/api/teams', { method: 'POST', body: JSON.stringify(t) }); teamsChanged(); return r },
  updateTeam: async (id: string, t: Partial<TeamInput>) => { const r = await request<Team>(`/api/teams/${id}`, { method: 'PUT', body: JSON.stringify(t) }); teamsChanged(); return r },
  deleteTeam: (id: string) => request(`/api/teams/${id}`, { method: 'DELETE' }).then(teamsChanged),
  room: (id: string) => request<{ items: RoomItem[]; active_run: string | null }>(`/api/teams/${id}/room`),
  messageTeam: async (id: string, text: string) => {
    const r = await request<{ run_id: string; steered: boolean }>(`/api/teams/${id}/messages`, { method: 'POST', body: JSON.stringify({ text }) })
    teamsChanged()
    return r
  },
}
