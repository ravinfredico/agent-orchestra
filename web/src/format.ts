export const money = (n: number | null | undefined) => '$' + (n || 0).toFixed(2)

export function clock(sec: number): string {
  sec = Math.max(0, Math.floor(sec))
  const h = Math.floor(sec / 3600)
  const m = Math.floor((sec % 3600) / 60)
  const s = sec % 60
  const mm = String(m).padStart(2, '0')
  const ss = String(s).padStart(2, '0')
  return h ? `${h}:${mm}:${ss}` : `${mm}:${ss}`
}

export function duration(sec: number): string {
  sec = Math.max(0, Math.round(sec))
  if (sec < 60) return `${sec}s`
  const m = Math.floor(sec / 60)
  if (m < 60) return `${m}m${sec % 60 ? ` ${String(sec % 60).padStart(2, '0')}s` : ''}`
  return `${Math.floor(m / 60)}h ${m % 60}m`
}

export function ago(ts: number | null | undefined): string {
  if (!ts) return ''
  const m = Math.round((Date.now() / 1000 - ts) / 60)
  if (m < 1) return 'just now'
  if (m < 60) return `${m} min ago`
  const h = Math.round(m / 60)
  if (h < 24) return `${h} h ago`
  const d = Math.round(h / 24)
  return d === 1 ? 'yesterday' : `${d} days ago`
}

export function dayGroup(ts: number): 'Today' | 'Yesterday' | 'Earlier' {
  const d = new Date(ts * 1000)
  const now = new Date()
  const start = new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime() / 1000
  if (d.getTime() / 1000 >= start) return 'Today'
  if (d.getTime() / 1000 >= start - 86400) return 'Yesterday'
  return 'Earlier'
}

export const STATUS_LABEL: Record<string, string> = {
  created: 'Starting', running: 'Running', finished: 'Finished', gave_up: 'Out of budget', failed: 'Crashed',
  stopped: 'Stopped by you', interrupted: 'Interrupted',
}

export const STATUS_DOT: Record<string, string> = {
  created: 'text', running: 'text', finished: 'pass', gave_up: 'check', failed: 'fail', stopped: 'border', interrupted: 'border',
}
