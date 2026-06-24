import type { SessionSummary, Turn, WorkspaceSummary } from '@/types/session'
import { playApiFetch, withWorkspace } from './client'

export function listWorkspaces() {
  return playApiFetch<WorkspaceSummary[]>('/workspaces')
}

export function listSessions(workspace: string) {
  return playApiFetch<SessionSummary[]>(withWorkspace('/sessions', workspace))
}

export function getSessionHistory(workspace: string, sessionId: string) {
  return playApiFetch<Turn[]>(withWorkspace(`/sessions/${sessionId}/history`, workspace))
}
