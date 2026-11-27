import { describe, expect, it } from 'vitest'
import demo from '../test/fixtures/demo.json'
import budget from '../test/fixtures/budget.json'
import { agentMood, cardLook, emptyRun, reduce, reduceAll } from './reducer'
import type { RunEvent } from './types'

const demoEvents = demo as RunEvent[]

describe('reducer', () => {
  it('replays the demo run to a finished state', () => {
    const r = reduceAll(demoEvents)
    expect(r.status).toBe('finished')
    expect(r.agentOrder).toEqual(['researcher', 'analyst', 'writer', 'editor'])
    expect(r.tasks['report-1'].status).toBe('replaced')
    expect(r.tasks['report-1'].replacedBy).toBe('report-2')
    expect(r.tasks['analysis-1'].history.map((h) => h.passed)).toEqual([false, true])
    expect(r.files['report.md'].versions).toBeGreaterThan(1)
    expect(r.files['report.md'].agent).toBe('editor')
    expect(Object.values(r.approvals)[0].decision).toBe('approved')
    expect(r.costUsd).toBeGreaterThan(0)
    expect(r.final).toMatch(/report\.md/)
  })

  it('tracks the model tier and the step-up after a failed attempt', () => {
    const r = reduceAll(demoEvents)
    const a = r.tasks['analysis-1']
    expect(a.tierReason).toBe('tables from notes')
    expect(a.history.map((h) => h.tier)).toEqual(['haiku', 'sonnet'])
    expect(a.tier).toBe('sonnet')
    expect(r.agents.writer.model).toBe('sonnet')
  })

  it('shows what a queued task waits for, and why a blocked one never started', () => {
    const at = demoEvents.findIndex((e) => e.type === 'task_assigned' && e.task_id === 'report-1')
    const mid = reduceAll(demoEvents.slice(0, at + 1))
    expect(mid.tasks['report-1'].dependsOn).toEqual(['analysis-1'])
    expect(cardLook(mid.tasks['report-1'], mid).line).toBe('Queued · waits for Compare fees')

    const base = { run_id: 'x', t: 1 }
    const evs = [
      { ...base, seq: 1, type: 'run_started', task: 't', title: 't', options: {} },
      { ...base, seq: 2, type: 'agent_created', name: 'a', role: '', tools: [], model: 'haiku', color_index: 0 },
      { ...base, seq: 3, type: 'task_assigned', task_id: 'r1', title: 'Research', agent: 'a', done_when: 'x' },
      { ...base, seq: 4, type: 'task_assigned', task_id: 'rep', title: 'Report', agent: 'a', done_when: 'x', depends_on: ['r1'] },
      { ...base, seq: 5, type: 'task_failed', task_id: 'r1', attempts: 2 },
      { ...base, seq: 6, type: 'task_failed', task_id: 'rep', attempts: 0, reason: 'depends on r1, which did not pass' },
    ] as RunEvent[]
    const r = reduceAll(evs)
    expect(cardLook(r.tasks.rep, r).line).toBe('Not started · Research failed')
    expect(r.agents.a.failed).toBe(1)                 // the blocked task is not the agent's failure
  })

  it('keeps cheap check results on the attempt', () => {
    const t = reduceAll(demoEvents).tasks['research-1']
    expect(t.checks).toEqual(['5+ files match research/*.md'])
    expect(t.history[0].checks[0]).toMatchObject({ passed: true, detail: '5 found' })
    expect(t.history[0].checkedBy).toBe('model')
  })

  it('builds the thread in event order with joined lines grouped', () => {
    const r = reduceAll(demoEvents)
    const kinds = r.thread.map((i) => i.kind)
    expect(kinds[0]).toBe('task_message')
    expect(r.thread[1]).toMatchObject({ kind: 'playbook', id: 'research-report', title: 'Research report' })
    expect(kinds[2]).toBe('say')
    expect(r.thread[3]).toMatchObject({ kind: 'joined', names: ['researcher', 'analyst', 'writer'] })
    expect(r.playbook?.id).toBe('research-report')
    expect(kinds.filter((k) => k === 'task')).toHaveLength(4)
    expect(kinds).toContain('approval')
  })

  it('ignores replayed events (seq <= lastSeq)', () => {
    const once = reduceAll(demoEvents)
    const twice = demoEvents.reduce(reduce, once)
    expect(twice).toBe(once)
  })

  it('handles out of budget and denied approvals', () => {
    const r = reduceAll(budget as RunEvent[])
    expect(r.status).toBe('gave_up')
    expect(r.giveUp).toBe(true)
    expect(r.budgetReason).toMatch(/cost limit/)
  })

  it('shows retries on the card', () => {
    let r = emptyRun()
    let i = 0
    const upTo = (pred: (e: RunEvent) => boolean) => {
      while (i < demoEvents.length) { const e = demoEvents[i++]; r = reduce(r, e); if (pred(e)) break }
    }
    upTo((e) => e.type === 'attempt_failed' && e.task_id === 'analysis-1')
    expect(cardLook(r.tasks['analysis-1'], r)).toMatchObject({ mood: 'sad', line: 'Sent back · 2 wallets missing fees' })
    upTo((e) => e.type === 'attempt_started' && e.task_id === 'analysis-1')
    const look = cardLook(r.tasks['analysis-1'], r)
    expect(look.line).toBe('Try 2 · 2 wallets missing fees')
    expect(look.pips).toEqual(['fail', 'current', 'empty'])
    expect(agentMood(r.agents.analyst, r)).toBe('working')
    upTo((e) => e.type === 'checker_started' && e.task_id === 'analysis-1')
    expect(cardLook(r.tasks['analysis-1'], r).mood).toBe('waiting')
    upTo((e) => e.type === 'task_passed' && e.task_id === 'analysis-1')
    expect(cardLook(r.tasks['analysis-1'], r).line).toBe('Passed on try 2')
  })

  it('announces only the important events', () => {
    const r = reduceAll(demoEvents)
    const texts = r.announcements.map((a) => a.text).join('\n')
    expect(texts).toMatch(/Run finished/)
    expect(texts).not.toMatch(/reading/)
    expect(r.announcements.some((a) => a.assertive)).toBe(true)
  })
})
