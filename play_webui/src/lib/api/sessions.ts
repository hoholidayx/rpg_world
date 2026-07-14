import type { HistoryPage, SessionDeleteResult, SessionSummary, Turn, WorkspaceSummary } from '@/types/session'
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

export function deleteSession(sessionId: string) {
  return playApiFetch<SessionDeleteResult>(`/sessions/${encodeURIComponent(sessionId)}`, {
    method: 'DELETE',
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

export function getSessionHistoryPage(
  sessionId: string,
  options: {
    limit?: number
    beforeTurnId?: number
    afterTurnId?: number
  } = {},
) {
  const params = new URLSearchParams()
  if (options.limit !== undefined) params.set('limit', String(options.limit))
  if (options.beforeTurnId !== undefined) params.set('beforeTurnId', String(options.beforeTurnId))
  if (options.afterTurnId !== undefined) params.set('afterTurnId', String(options.afterTurnId))
  const query = params.toString()
  return playApiFetch<HistoryPage>(
    `/sessions/${encodeURIComponent(sessionId)}/history-page${query ? `?${query}` : ''}`,
  )
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
