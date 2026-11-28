import type { RunOptions } from './api'

/** Fields a preset sets. Everything else in Options (shell, repo, playbook, tools) is left alone. */
export type PresetFields = Required<Pick<RunOptions,
  'orchestrator_model' | 'worker_model' | 'pick_tier' | 'max_tier' | 'checker_model' |
  'max_cost' | 'max_attempts' | 'max_steps' | 'max_assignments'>>

/** Matches the engine's defaults (orchestra/config.py). */
export const DEFAULT_PRESET: PresetFields = {
  orchestrator_model: 'sonnet', worker_model: 'sonnet', pick_tier: true, max_tier: 'opus', checker_model: 'haiku',
  max_cost: 5, max_attempts: 3, max_steps: 25, max_assignments: 15,
}

/** Haiku-first: workers start on haiku and step up to sonnet at most. */
export const CHEAP_PRESET: PresetFields = {
  orchestrator_model: 'sonnet', worker_model: 'haiku', pick_tier: true, max_tier: 'sonnet', checker_model: 'haiku',
  max_cost: 1, max_attempts: 2, max_steps: 15, max_assignments: 8,
}

export const PRESETS = { default: DEFAULT_PRESET, cheap: CHEAP_PRESET } as const
export type PresetId = keyof typeof PRESETS | 'custom'

export function presetOf(o: Partial<PresetFields>): PresetId {
  for (const [id, p] of Object.entries(PRESETS) as [keyof typeof PRESETS, PresetFields][]) {
    if ((Object.keys(p) as (keyof PresetFields)[]).every((k) => o[k] === p[k])) return id
  }
  return 'custom'
}
