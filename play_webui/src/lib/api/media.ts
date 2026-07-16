import { getPlayApiBaseUrl } from '@/lib/config/env'
import type {
  CreateMediaJobInput,
  MediaBackground,
  MediaBrief,
  MediaGallery,
  MediaGalleryItem,
  MediaJob,
  MediaBackgroundEvaluation,
  MediaLibrary,
  MediaLibraryItem,
  MediaLibraryMetadataInput,
  MediaLibraryReconcileResult,
  MediaProviderCatalog,
  MediaSourceTurns,
} from '@/types/media'
import { playApiFetch } from './client'
import { readApiError } from './errors'

function mediaPath(sessionId: string) {
  return `/sessions/${encodeURIComponent(sessionId)}/media`
}

export function getMediaProviders(sessionId: string) {
  return playApiFetch<MediaProviderCatalog>(`${mediaPath(sessionId)}/providers`)
}

export function getMediaSourceTurns(sessionId: string) {
  return playApiFetch<MediaSourceTurns>(`${mediaPath(sessionId)}/source-turns`)
}

export function createMediaBrief(
  sessionId: string,
  input: { startTurnId: number; endTurnId: number },
) {
  return playApiFetch<MediaBrief>(`${mediaPath(sessionId)}/briefs`, {
    method: 'POST',
    body: JSON.stringify(input),
  })
}

export function createMediaJob(sessionId: string, input: CreateMediaJobInput) {
  return playApiFetch<MediaJob>(`${mediaPath(sessionId)}/jobs`, {
    method: 'POST',
    body: JSON.stringify({ ...input, generationParams: input.generationParams ?? {} }),
  })
}

export function getMediaGallery(sessionId: string) {
  return playApiFetch<MediaGallery>(`${mediaPath(sessionId)}/gallery`)
}

export function getMediaJob(sessionId: string, jobId: string) {
  return playApiFetch<MediaJob>(`${mediaPath(sessionId)}/jobs/${encodeURIComponent(jobId)}`)
}

export function cancelMediaJob(sessionId: string, jobId: string) {
  return playApiFetch<MediaJob>(`${mediaPath(sessionId)}/jobs/${encodeURIComponent(jobId)}/cancel`, {
    method: 'POST',
  })
}

export function retryMediaJob(sessionId: string, jobId: string) {
  return playApiFetch<MediaJob>(`${mediaPath(sessionId)}/jobs/${encodeURIComponent(jobId)}/retry`, {
    method: 'POST',
  })
}

export function getMediaBackground(sessionId: string) {
  return playApiFetch<MediaBackground>(`${mediaPath(sessionId)}/background`)
}

export function setMediaBackground(sessionId: string, assetId: string) {
  return playApiFetch<MediaBackground>(`${mediaPath(sessionId)}/background`, {
    method: 'PUT',
    body: JSON.stringify({ assetId }),
  })
}

export function clearMediaBackground(sessionId: string) {
  return playApiFetch<MediaBackground>(`${mediaPath(sessionId)}/background`, {
    method: 'DELETE',
  })
}

export function queueMediaBackgroundEvaluation(sessionId: string, observedTurnId: number) {
  return playApiFetch<MediaBackgroundEvaluation>(`${mediaPath(sessionId)}/background-evaluations`, {
    method: 'POST',
    body: JSON.stringify({ observedTurnId }),
  })
}

export function getMediaBackgroundEvaluation(sessionId: string, evaluationId: string) {
  return playApiFetch<MediaBackgroundEvaluation>(
    `${mediaPath(sessionId)}/background-evaluations/${encodeURIComponent(evaluationId)}`,
  )
}

export function getMediaAsset(sessionId: string, assetId: string) {
  return playApiFetch<MediaGalleryItem>(`${mediaPath(sessionId)}/assets/${encodeURIComponent(assetId)}`)
}

export function deleteMediaAsset(sessionId: string, assetId: string) {
  return playApiFetch<{ assetId: string; deleted: boolean }>(
    `${mediaPath(sessionId)}/assets/${encodeURIComponent(assetId)}`,
    { method: 'DELETE' },
  )
}

export function mediaAssetContentUrl(sessionId: string, assetId: string) {
  return `${getPlayApiBaseUrl()}${mediaPath(sessionId)}/assets/${encodeURIComponent(assetId)}/content`
}

function mediaLibraryPath(workspaceId: string) {
  return `/workspaces/${encodeURIComponent(workspaceId)}/media/library`
}

export function getMediaLibrary(
  workspaceId: string,
  options: { scope?: MediaLibraryMetadataInput['scope']; storyId?: number } = {},
) {
  const params = new URLSearchParams()
  if (options.scope) params.set('scope', options.scope)
  if (options.storyId !== undefined) params.set('storyId', String(options.storyId))
  const query = params.toString()
  return playApiFetch<MediaLibrary>(`${mediaLibraryPath(workspaceId)}${query ? `?${query}` : ''}`)
}

export function reconcileMediaLibrary(workspaceId: string) {
  return playApiFetch<MediaLibraryReconcileResult>(`${mediaLibraryPath(workspaceId)}/reconcile`, {
    method: 'POST',
  })
}

export async function uploadMediaLibraryItem(
  workspaceId: string,
  file: File,
  input: MediaLibraryMetadataInput,
) {
  const form = new FormData()
  form.set('file', file)
  form.set('scope', input.scope)
  form.set('title', input.title)
  form.set('description', input.description)
  form.set('tags', JSON.stringify(input.tags))
  form.set('isDefault', String(input.isDefault))
  if (input.storyId !== null) form.set('storyId', String(input.storyId))
  const response = await fetch(`${getPlayApiBaseUrl()}${mediaLibraryPath(workspaceId)}`, {
    method: 'POST',
    body: form,
  })
  if (!response.ok) throw new Error(await readApiError(response))
  return response.json() as Promise<MediaLibraryItem>
}

export function updateMediaLibraryItem(
  workspaceId: string,
  itemId: string,
  input: Omit<MediaLibraryMetadataInput, 'scope' | 'storyId'>,
) {
  return playApiFetch<MediaLibraryItem>(
    `${mediaLibraryPath(workspaceId)}/${encodeURIComponent(itemId)}`,
    { method: 'PATCH', body: JSON.stringify(input) },
  )
}

export function deleteMediaLibraryItem(workspaceId: string, itemId: string) {
  return playApiFetch<{ itemId: string; deleted: boolean }>(
    `${mediaLibraryPath(workspaceId)}/${encodeURIComponent(itemId)}`,
    { method: 'DELETE' },
  )
}

export function mediaLibraryContentUrl(workspaceId: string, itemId: string) {
  return `${getPlayApiBaseUrl()}${mediaLibraryPath(workspaceId)}/${encodeURIComponent(itemId)}/content`
}
