import type { StatusKind, StatusTable, StatusTableInput, StatusTablePatch } from '@/types/statusTables'
import { getPlayApiBaseUrl } from '@/lib/config/env'
import { playApiFetch } from './client'
import { readApiError } from './errors'

function storyStatusPath(workspace: string, storyId: number) {
  return `/workspaces/${encodeURIComponent(workspace)}/stories/${encodeURIComponent(storyId)}/status-tables`
}

export function listStoryStatusTables(workspace: string, storyId: number, statusKind?: StatusKind) {
  const query = statusKind ? `?statusKind=${encodeURIComponent(statusKind)}` : ''
  return playApiFetch<StatusTable[]>(`${storyStatusPath(workspace, storyId)}${query}`)
}

export function createStoryStatusTable(workspace: string, storyId: number, input: StatusTableInput) {
  return playApiFetch<StatusTable>(storyStatusPath(workspace, storyId), {
    method: 'POST',
    body: JSON.stringify(input),
  })
}

export function updateStoryStatusTable(workspace: string, storyId: number, tableId: number, input: StatusTablePatch) {
  return playApiFetch<StatusTable>(`${storyStatusPath(workspace, storyId)}/${encodeURIComponent(tableId)}`, {
    method: 'PATCH',
    body: JSON.stringify(input),
  })
}

export async function deleteStoryStatusTable(workspace: string, storyId: number, tableId: number) {
  const response = await fetch(
    `${getPlayApiBaseUrl()}${storyStatusPath(workspace, storyId)}/${encodeURIComponent(tableId)}`,
    { method: 'DELETE' },
  )
  if (!response.ok) throw new Error(await readApiError(response))
}

export function listSessionStatusTables(sessionId: string, statusKind?: StatusKind) {
  const query = statusKind ? `?statusKind=${encodeURIComponent(statusKind)}` : ''
  return playApiFetch<StatusTable[]>(`/sessions/${encodeURIComponent(sessionId)}/status-tables${query}`)
}

export function createSessionStatusTable(sessionId: string, input: StatusTableInput) {
  return playApiFetch<StatusTable>(`/sessions/${encodeURIComponent(sessionId)}/status-tables`, {
    method: 'POST',
    body: JSON.stringify(input),
  })
}

export function updateSessionStatusTable(sessionId: string, tableId: number, input: StatusTablePatch) {
  return playApiFetch<StatusTable>(
    `/sessions/${encodeURIComponent(sessionId)}/status-tables/${encodeURIComponent(tableId)}`,
    { method: 'PATCH', body: JSON.stringify(input) },
  )
}

export async function deleteSessionStatusTable(sessionId: string, tableId: number) {
  const response = await fetch(
    `${getPlayApiBaseUrl()}/sessions/${encodeURIComponent(sessionId)}/status-tables/${encodeURIComponent(tableId)}`,
    { method: 'DELETE' },
  )
  if (!response.ok) throw new Error(await readApiError(response))
}
