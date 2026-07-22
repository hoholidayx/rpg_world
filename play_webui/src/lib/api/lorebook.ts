import type { LorebookEntry, LorebookEntryInput } from '@/types/lorebook'
import { playApiFetch } from './client'
import { getPlayApiBaseUrl } from '@/lib/config/env'
import { readApiError } from './errors'

function storyLorebookPath(workspace: string, storyId: number) {
  return `/workspaces/${encodeURIComponent(workspace)}/stories/${encodeURIComponent(storyId)}/lorebook-entries`
}

export function listLorebookEntries(workspace: string, storyId: number) {
  return playApiFetch<LorebookEntry[]>(storyLorebookPath(workspace, storyId))
}

export function createLorebookEntry(workspace: string, storyId: number, input: LorebookEntryInput) {
  return playApiFetch<LorebookEntry>(storyLorebookPath(workspace, storyId), {
    method: 'POST',
    body: JSON.stringify(input),
  })
}

export function updateLorebookEntry(workspace: string, storyId: number, entryId: number, input: Partial<LorebookEntryInput>) {
  return playApiFetch<LorebookEntry>(`${storyLorebookPath(workspace, storyId)}/${encodeURIComponent(entryId)}`, {
    method: 'PATCH',
    body: JSON.stringify(input),
  })
}

export async function deleteLorebookEntry(workspace: string, storyId: number, entryId: number) {
  const response = await fetch(
    `${getPlayApiBaseUrl()}${storyLorebookPath(workspace, storyId)}/${encodeURIComponent(entryId)}`,
    { method: 'DELETE' },
  )
  if (!response.ok) throw new Error(await readApiError(response))
}
