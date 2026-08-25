import type { DemoStep, Scenario } from './types'

export interface ReplayState { index: number; playing: boolean; speed: 1 | 2 }
export type ReplayAction = { type: 'RESET' } | { type: 'PLAY' } | { type: 'PAUSE' } | { type: 'STEP'; max: number } | { type: 'TICK'; max: number } | { type: 'SPEED'; speed: 1 | 2 } | { type: 'GOTO'; index: number; max: number }

export const initialReplay: ReplayState = { index: 0, playing: false, speed: 1 }

export function replayReducer(state: ReplayState, action: ReplayAction): ReplayState {
  if (action.type === 'RESET') return initialReplay
  if (action.type === 'PLAY') return { ...state, playing: true }
  if (action.type === 'PAUSE') return { ...state, playing: false }
  if (action.type === 'SPEED') return { ...state, speed: action.speed }
  if (action.type === 'GOTO') return { ...state, index: Math.max(0, Math.min(action.index, action.max)), playing: false }
  const next = Math.min(state.index + 1, action.max)
  return { ...state, index: next, playing: next < action.max && action.type === 'TICK' ? state.playing : false }
}

export function currentStep(scenario: Scenario, state: ReplayState): DemoStep {
  if (!scenario.steps.length) throw new Error('Backend scenario contains no snapshots')
  return scenario.steps[Math.min(state.index, scenario.steps.length - 1)]
}

export function assertAuthoritativeScenario(scenario: Scenario): void {
  if (!scenario.sourceArtifacts.length) throw new Error('Scenario lacks authoritative provenance')
  for (const step of scenario.steps) {
    if (!step.lifecycle || !step.businessOutcome || !step.economics.length) {
      throw new Error(`Backend snapshot ${step.id} is incomplete`)
    }
  }
}
