import type { LorebookEntry, LorebookEntryInput, StorySummary } from '@/types/lorebook'
import { playApiFetch } from './client'
import { getPlayApiBaseUrl } from '@/lib/config/env'
import { readApiError } from './errors'

export function listStories(workspace: string) {
  return playApiFetch<StorySummary[]>(`/workspaces/${encodeURIComponent(workspace)}/stories`)
}

export function listLorebookEntries(workspace: string) {
  return playApiFetch<LorebookEntry[]>(`/workspaces/${encodeURIComponent(workspace)}/lorebook-entries`)
}

export function createLorebookEntry(workspace: string, input: LorebookEntryInput) {
  return playApiFetch<LorebookEntry>(`/workspaces/${encodeURIComponent(workspace)}/lorebook-entries`, {
    method: 'POST',
    body: JSON.stringify(input),
  })
}

export function updateLorebookEntry(workspace: string, entryId: number, input: Partial<LorebookEntryInput>) {
  return playApiFetch<LorebookEntry>(`/workspaces/${encodeURIComponent(workspace)}/lorebook-entries/${encodeURIComponent(entryId)}`, {
    method: 'PATCH',
    body: JSON.stringify(input),
  })
}

export async function deleteLorebookEntry(workspace: string, entryId: number) {
  const response = await fetch(
    `${getPlayApiBaseUrl()}/workspaces/${encodeURIComponent(workspace)}/lorebook-entries/${encodeURIComponent(entryId)}`,
    { method: 'DELETE' },
  )
  if (!response.ok) throw new Error(await readApiError(response))
}

export function listStoryLorebookEntries(workspace: string, storyId: number) {
  return playApiFetch<LorebookEntry[]>(
    `/workspaces/${encodeURIComponent(workspace)}/stories/${encodeURIComponent(storyId)}/lorebook-entries`,
  )
}

export function mountLorebookEntry(workspace: string, storyId: number, entryId: number) {
  return playApiFetch<LorebookEntry>(
    `/workspaces/${encodeURIComponent(workspace)}/stories/${encodeURIComponent(storyId)}/lorebook-entries/${encodeURIComponent(entryId)}/mount`,
    { method: 'POST' },
  )
}

export async function unmountLorebookEntry(workspace: string, storyId: number, mountId: number) {
  const response = await fetch(
    `${getPlayApiBaseUrl()}/workspaces/${encodeURIComponent(workspace)}/stories/${encodeURIComponent(storyId)}/lorebook-mounts/${encodeURIComponent(mountId)}`,
    { method: 'DELETE' },
  )
  if (!response.ok) throw new Error(await readApiError(response))
}
