import type { SummaryDetail, SummaryIndex } from '@/types/summaries'
import { playApiFetch } from './client'

export function listSessionSummaries(sessionId: string) {
  return playApiFetch<SummaryIndex>(
    `/sessions/${encodeURIComponent(sessionId)}/summaries`,
  )
}

export function getSessionSummary(sessionId: string, summaryKey: string) {
  return playApiFetch<SummaryDetail>(
    `/sessions/${encodeURIComponent(sessionId)}/summaries/${encodeURIComponent(summaryKey)}`,
  )
}
