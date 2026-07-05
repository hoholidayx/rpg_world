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

export function bindSessionPlayerCharacter(sessionId: string, playerCharacterId: number) {
  return playApiFetch<SessionSummary>(`/sessions/${encodeURIComponent(sessionId)}/player-character`, {
    method: 'PATCH',
    body: JSON.stringify({ playerCharacterId }),
  })
}

export function getSessionHistory(sessionId: string) {
  return playApiFetch<Turn[]>(`/sessions/${encodeURIComponent(sessionId)}/history`)
}

export function truncateSessionTurn(sessionId: string, turnId: number) {
  return playApiFetch<{ status: string; turnId: number; removed: number }>(
    `/sessions/${encodeURIComponent(sessionId)}/turns/${encodeURIComponent(turnId)}/truncate`,
    { method: 'POST' },
  )
}

export function deleteSessionMessage(sessionId: string, messageId: number) {
  return playApiFetch<{ status: string }>(
    `/sessions/${encodeURIComponent(sessionId)}/messages/${encodeURIComponent(messageId)}`,
    { method: 'DELETE' },
  )
}
