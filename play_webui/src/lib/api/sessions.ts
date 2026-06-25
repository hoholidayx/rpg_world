import type { SessionSummary, Turn, WorkspaceSummary } from '@/types/session'
import { playApiFetch, withWorkspace } from './client'

export function listWorkspaces() {
  return playApiFetch<WorkspaceSummary[]>('/workspaces')
}

export function listSessions(workspace: string, storyId: number) {
  return playApiFetch<SessionSummary[]>(
    `${withWorkspace('/sessions', workspace)}&story_id=${encodeURIComponent(storyId)}`,
  )
}

export function getSessionHistory(workspace: string, storyId: number, sessionId: string) {
  return playApiFetch<Turn[]>(
    `${withWorkspace(`/sessions/${sessionId}/history`, workspace)}&story_id=${encodeURIComponent(storyId)}`,
  )
}
