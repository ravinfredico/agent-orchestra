/// <reference types="node" />
// The iPhone widget (widgets/scriptable.js) runs in Scriptable, not here. Its data logic is pure,
// so load the file with no Scriptable globals and test describe() against /api/status shapes.
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { runInNewContext } from 'node:vm'
import { describe as group, expect, it } from 'vitest'

type Model = { label: string; title: string; detail: string; dot: string; url: string; more?: string; live?: boolean }
const src = readFileSync(resolve(__dirname, '../../../widgets/scriptable.js'), 'utf8')
const mod: { exports: { describe: (s: unknown, e: unknown, base: string, now: number) => Model } } = { exports: {} as never }
// wrap in an async function: Scriptable allows top-level await, a plain script does not
await runInNewContext(`(async (module) => {\n${src}\n})(module)`, { module: mod })
const describe = mod.exports.describe
const BASE = 'https://pa.example.com'
const NOW = 1_795_500_000_000

group('iPhone widget', () => {
  it('shows the running task with team, time and usage', () => {
    const m = describe({ running: [{ id: 'r1', title: 'Build a todo app', status: 'running', elapsed_s: 754, cost_usd: 1.2, agents: 2, needs_approval: false }], last: null }, null, BASE, NOW)
    expect(m).toMatchObject({ label: 'Running', title: 'Build a todo app', detail: '2 agents · 12:34 · $1.20 est.', dot: 'text', live: true, url: `${BASE}/runs/r1` })
  })

  it('puts a run that needs approval first, and counts the others', () => {
    const m = describe({ running: [
      { id: 'a', title: 'A', elapsed_s: 1, cost_usd: 0, agents: 1, needs_approval: false },
      { id: 'b', title: 'B', elapsed_s: 1, cost_usd: 0, agents: 3, needs_approval: true },
    ] }, null, BASE, NOW)
    expect(m).toMatchObject({ label: 'Needs your approval', title: 'B', dot: 'check', more: '+1 more running', url: `${BASE}/runs/b` })
  })

  it('shows the last result when nothing is running', () => {
    const m = describe({ running: [], last: { id: 'r9', title: 'Report', status: 'gave_up', ended_at: NOW / 1000 - 7200 } }, null, BASE, NOW)
    expect(m).toMatchObject({ label: 'Out of budget', title: 'Report', detail: '2 h ago', dot: 'check', url: `${BASE}/runs/r9` })
  })

  it('handles no runs and an unreachable server', () => {
    expect(describe({ running: [], last: null }, null, BASE, NOW).title).toBe('No runs yet')
    expect(describe(null, 'The request timed out.', BASE, NOW)).toMatchObject({ title: "Can't reach ChaCha PA", dot: 'fail' })
  })
})
