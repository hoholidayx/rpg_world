import { playApiFetch } from './client'
import type { NarrativeOutcomeConfig, NarrativeOutcomeWeights } from '@/types/narrativeOutcome'

export function getStoryNarrativeOutcome(workspace: string, storyId: number) {
  return playApiFetch<NarrativeOutcomeConfig>(
    `/workspaces/${encodeURIComponent(workspace)}/stories/${encodeURIComponent(storyId)}/narrative-outcome`,
  )
}

export function setStoryNarrativeOutcome(
  workspace: string,
  storyId: number,
  weights: NarrativeOutcomeWeights | null,
) {
  return playApiFetch<NarrativeOutcomeConfig>(
    `/workspaces/${encodeURIComponent(workspace)}/stories/${encodeURIComponent(storyId)}/narrative-outcome`,
    { method: 'PATCH', body: JSON.stringify({ weights }) },
  )
}

export function getSessionNarrativeOutcome(sessionId: string) {
  return playApiFetch<NarrativeOutcomeConfig>(
    `/sessions/${encodeURIComponent(sessionId)}/narrative-outcome`,
  )
}

export function setSessionNarrativeOutcome(
  sessionId: string,
  weights: NarrativeOutcomeWeights | null,
) {
  return playApiFetch<NarrativeOutcomeConfig>(
    `/sessions/${encodeURIComponent(sessionId)}/narrative-outcome`,
    { method: 'PATCH', body: JSON.stringify({ weights }) },
  )
}
