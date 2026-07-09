import type {
  StatusKind,
  StatusTable,
  StatusTableInput,
  StatusTablePatch,
  StoryStatusMount,
  StoryStatusMountPatch,
  StoryStatusTemplateInput,
} from '@/types/statusTables'
import { getPlayApiBaseUrl } from '@/lib/config/env'
import { playApiFetch } from './client'
import { readApiError } from './errors'

export function listStatusTemplates(workspace: string, statusKind?: StatusKind) {
  const query = statusKind ? `?statusKind=${encodeURIComponent(statusKind)}` : ''
  return playApiFetch<StatusTable[]>(`/workspaces/${encodeURIComponent(workspace)}/status-templates${query}`)
}

export function createStatusTemplate(workspace: string, input: StatusTableInput) {
  return playApiFetch<StatusTable>(`/workspaces/${encodeURIComponent(workspace)}/status-templates`, {
    method: 'POST',
    body: JSON.stringify(input),
  })
}

export function updateStatusTemplate(workspace: string, templateId: number, input: StatusTablePatch) {
  return playApiFetch<StatusTable>(
    `/workspaces/${encodeURIComponent(workspace)}/status-templates/${encodeURIComponent(templateId)}`,
    {
      method: 'PATCH',
      body: JSON.stringify(input),
    },
  )
}

export async function deleteStatusTemplate(workspace: string, templateId: number) {
  const response = await fetch(
    `${getPlayApiBaseUrl()}/workspaces/${encodeURIComponent(workspace)}/status-templates/${encodeURIComponent(templateId)}`,
    { method: 'DELETE' },
  )
  if (!response.ok) throw new Error(await readApiError(response))
}

export function listStoryStatusMounts(workspace: string, storyId: number) {
  return playApiFetch<StoryStatusMount[]>(
    `/workspaces/${encodeURIComponent(workspace)}/stories/${encodeURIComponent(storyId)}/status-mounts`,
  )
}

export function mountStatusTemplate(
  workspace: string,
  storyId: number,
  templateId: number,
  sortOrder = 0,
  characterMountId?: number | null,
) {
  return playApiFetch<StoryStatusMount>(
    `/workspaces/${encodeURIComponent(workspace)}/stories/${encodeURIComponent(storyId)}/status-mounts`,
    {
      method: 'POST',
      body: JSON.stringify({
        templateId,
        sortOrder,
        ...(characterMountId === undefined ? {} : { characterMountId }),
      }),
    },
  )
}

export function createStoryStatusTemplate(workspace: string, storyId: number, input: StoryStatusTemplateInput) {
  return playApiFetch<StoryStatusMount>(
    `/workspaces/${encodeURIComponent(workspace)}/stories/${encodeURIComponent(storyId)}/status-templates`,
    {
      method: 'POST',
      body: JSON.stringify(input),
    },
  )
}

export function updateStoryStatusMount(workspace: string, storyId: number, mountId: number, input: StoryStatusMountPatch) {
  return playApiFetch<StoryStatusMount>(
    `/workspaces/${encodeURIComponent(workspace)}/stories/${encodeURIComponent(storyId)}/status-mounts/${encodeURIComponent(mountId)}`,
    {
      method: 'PATCH',
      body: JSON.stringify(input),
    },
  )
}

export async function unmountStatusTemplate(workspace: string, storyId: number, mountId: number) {
  const response = await fetch(
    `${getPlayApiBaseUrl()}/workspaces/${encodeURIComponent(workspace)}/stories/${encodeURIComponent(storyId)}/status-mounts/${encodeURIComponent(mountId)}`,
    { method: 'DELETE' },
  )
  if (!response.ok) throw new Error(await readApiError(response))
}

export async function deleteStoryStatusTemplate(workspace: string, storyId: number, mountId: number) {
  const response = await fetch(
    `${getPlayApiBaseUrl()}/workspaces/${encodeURIComponent(workspace)}/stories/${encodeURIComponent(storyId)}/status-templates/${encodeURIComponent(mountId)}`,
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
    {
      method: 'PATCH',
      body: JSON.stringify(input),
    },
  )
}

export async function deleteSessionStatusTable(sessionId: string, tableId: number) {
  const response = await fetch(
    `${getPlayApiBaseUrl()}/sessions/${encodeURIComponent(sessionId)}/status-tables/${encodeURIComponent(tableId)}`,
    { method: 'DELETE' },
  )
  if (!response.ok) throw new Error(await readApiError(response))
}
