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

export function getSession(sessionId: string) {
  return playApiFetch<SessionSummary>(`/sessions/${encodeURIComponent(sessionId)}`)
}

export function createSession(workspace: string, storyId: number, title?: string) {
  return playApiFetch<SessionSummary>('/sessions', {
    method: 'POST',
    body: JSON.stringify({ workspaceId: workspace, storyId, title: title ?? '' }),
  })
}

export function getSessionHistory(sessionId: string) {
  return playApiFetch<Turn[]>(`/sessions/${encodeURIComponent(sessionId)}/history`)
}
