import { getPlayApiBaseUrl } from '@/lib/config/env'
import type {
  CreateMediaJobInput,
  MediaBackground,
  MediaBrief,
  MediaGallery,
  MediaGalleryItem,
  MediaJob,
  MediaProviderCatalog,
  MediaSourceTurns,
} from '@/types/media'
import { playApiFetch } from './client'

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
