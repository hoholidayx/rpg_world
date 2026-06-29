import { getPlayApiBaseUrl } from '@/lib/config/env'
import type { PlayDeleteConfirmationToken, UnindexedRuntimeItem, UnindexedRuntimeScanResponse } from '@/types/ops'
import { playApiFetch } from './client'
import { readApiError } from './errors'

export function scanUnindexedRuntime(workspaceId: string) {
  return playApiFetch<UnindexedRuntimeScanResponse>(
    `/ops/unindexed-runtime?workspace_id=${encodeURIComponent(workspaceId)}`,
  )
}

export function createUnindexedRuntimeDeleteToken(items: UnindexedRuntimeItem[]) {
  return playApiFetch<PlayDeleteConfirmationToken>('/ops/unindexed-runtime/delete-token', {
    method: 'POST',
    body: JSON.stringify({ items }),
  })
}

export async function deleteUnindexedRuntimeItems(items: UnindexedRuntimeItem[], token: string) {
  const response = await fetch(`${getPlayApiBaseUrl()}/ops/unindexed-runtime/delete`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'X-Delete-Confirm-Token': token,
    },
    body: JSON.stringify({ items }),
  })
  if (!response.ok) throw new Error(await readApiError(response))
}
