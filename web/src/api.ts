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
  kind: 'builtin' | 'mcp' | 'plugin'
  description: string
  risk: 'read' | 'write' | 'shell' | 'outward'
  enabled: boolean
  requires: string | null
  unavailable: string | null
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
  max_cost?: number
  max_agents?: number
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

export const AUTH_EVENT = 'chacha:auth-required'
export const RUNS_CHANGED = 'chacha:runs-changed'

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
}
