import type { ContextPreviewPayload } from '@/types/contextPreview'
import { playApiFetch } from './client'

export function getContextPreview(
  sessionId: string,
  options: { mode?: string; narrativeStyleId?: number | null } = {},
) {
  const params = new URLSearchParams()
  if (options.mode) params.set('mode', options.mode)
  if (options.narrativeStyleId !== undefined && options.narrativeStyleId !== null) {
    params.set('narrativeStyleId', String(options.narrativeStyleId))
  }
  const query = params.toString()
  return playApiFetch<ContextPreviewPayload>(
    `/sessions/${encodeURIComponent(sessionId)}/context-preview${query ? `?${query}` : ''}`,
  )
}
