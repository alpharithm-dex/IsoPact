import { describe, expect, it } from 'vitest'
import data from '../public/data/stage11-data.json'
import { assertAuthoritativeScenario, currentStep, initialReplay, replayReducer } from './model'
import type { Scenario } from './types'

const scenarios = data.scenarios as unknown as Scenario[]
const byId = (id: string) => scenarios.find(s => s.id === id)!

describe('authoritative replay model', () => {
  it('applies backend snapshots without deriving lifecycle or economics', () => {
    const scenario = byId('protected'); assertAuthoritativeScenario(scenario)
    const next = replayReducer(initialReplay, { type: 'STEP', max: scenario.steps.length - 1 })
    expect(currentStep(scenario, next)).toBe(scenario.steps[1])
    expect(currentStep(scenario, next).economics).toEqual(scenario.steps[1].economics)
  })

  it('supports deterministic controls and bounds', () => {
    let state = replayReducer(initialReplay, { type: 'PLAY' })
    state = replayReducer(state, { type: 'SPEED', speed: 2 })
    state = replayReducer(state, { type: 'GOTO', index: 99, max: 2 })
    expect(state).toEqual({ index: 2, playing: false, speed: 2 })
    expect(replayReducer(state, { type: 'RESET' })).toEqual(initialReplay)
  })

  it('renders unmanaged/protected economics from provenance-backed data', () => {
    const unmanaged = byId('unmanaged').steps.at(-1)!.economics
    const protectedOutcome = byId('protected').steps.at(-1)!.economics
    expect(unmanaged).toEqual(expect.arrayContaining([
      expect.objectContaining({ label: 'Projected compensation', value: '$650' }),
      expect.objectContaining({ label: 'Projected excess exposure', value: '$450' })
    ]))
    expect(protectedOutcome).toEqual(expect.arrayContaining([
      expect.objectContaining({ label: 'Final authorized compensation', value: '$250' }),
      expect.objectContaining({ label: 'Projected invalid value prevented', value: '$400' })
    ]))
    expect(JSON.stringify(protectedOutcome).toLowerCase()).not.toContain('cash saved')
  })

  it('keeps Rank 4 unsettled and Rank 1 causally before settlement', () => {
    const steps = byId('protected').steps
    expect(steps.find(s => s.id === 'agent-complete-unsettled')).toMatchObject({ lifecycle: 'PENDING', businessOutcome: 'NOT SETTLED' })
    expect(steps.findIndex(s => s.id === 'rank1-evidence')).toBeLessThan(steps.findIndex(s => s.id === 'settled'))
  })

  it('contains visible blocked actions and goodwill', () => {
    const text = JSON.stringify(byId('protected'))
    expect(text).toContain('EXCLUSIVE_RESOLUTION_CONFLICT')
    expect(text).toContain('DUPLICATE_OPERATION')
    expect(text).toContain('$50')
  })

  it('contains reconciliation, TOCTOU and outcome-unknown guarantees', () => {
    expect(JSON.stringify(byId('reconciliation'))).toContain('$0')
    expect(JSON.stringify(byId('reconciliation'))).toContain('$200 RECOVERED')
    expect(JSON.stringify(byId('toctou'))).toContain('0 external calls')
    expect(JSON.stringify(byId('unknown'))).toContain('External executions')
    expect(JSON.stringify(byId('unknown'))).toContain('DEFER')
  })

  it('distinguishes receipt and tamper verification', () => {
    expect(data.receiptBundle.verification.overall_integrity_valid).toBe(true)
    expect(data.receiptBundle.tamperedVerification.overall_integrity_valid).toBe(false)
  })

  it('labels evidence modes explicitly', () => {
    expect(byId('protected').evidenceMode).toBe('LIVE')
    expect(byId('unmanaged').evidenceMode).toBe('VERIFIED REPLAY')
  })
})
