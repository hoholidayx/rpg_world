export const NARRATIVE_OUTCOME_CODE = {
  CRITICAL_SUCCESS: 'critical_success',
  SUCCESS: 'success',
  SUCCESS_WITH_COST: 'success_with_cost',
  SETBACK: 'setback',
  CRITICAL_FAILURE: 'critical_failure',
} as const

export type NarrativeOutcomeCode = (typeof NARRATIVE_OUTCOME_CODE)[keyof typeof NARRATIVE_OUTCOME_CODE]

export const NARRATIVE_OUTCOME_CODES = Object.values(NARRATIVE_OUTCOME_CODE) as NarrativeOutcomeCode[]

export type NarrativeOutcomeWeights = Record<NarrativeOutcomeCode, number>

export type NarrativeOutcomeDefinition = {
  code: NarrativeOutcomeCode
  label: string
  narrativeGuidance: string
}

export type NarrativeOutcomeConfig = {
  definitions: NarrativeOutcomeDefinition[]
  systemDefault: NarrativeOutcomeWeights
  storyOverride: NarrativeOutcomeWeights | null
  sessionOverride: NarrativeOutcomeWeights | null
  effectiveWeights: NarrativeOutcomeWeights
  effectiveSource: 'config' | 'story' | 'session'
}

export type NarrativeOutcome = {
  outcomeCode: NarrativeOutcomeCode
  label: string
  narrativeGuidance: string
  reason: string
  actor?: string | null
}

export function narrativeOutcomeWeightTotal(weights: NarrativeOutcomeWeights) {
  return NARRATIVE_OUTCOME_CODES.reduce((total, code) => total + weights[code], 0)
}

export function validNarrativeOutcomeWeights(weights: NarrativeOutcomeWeights) {
  return NARRATIVE_OUTCOME_CODES.every((code) => (
    Number.isInteger(weights[code]) && weights[code] >= 0 && weights[code] <= 100
  )) && narrativeOutcomeWeightTotal(weights) === 100
}

export function copyNarrativeOutcomeWeights(weights: NarrativeOutcomeWeights): NarrativeOutcomeWeights {
  return { ...weights }
}
