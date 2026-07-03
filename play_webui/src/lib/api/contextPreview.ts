import type { ContextPreviewPayload } from '@/types/contextPreview'
import { playApiFetch } from './client'

export function getContextPreview(sessionId: string) {
  return playApiFetch<ContextPreviewPayload>(`/sessions/${encodeURIComponent(sessionId)}/context-preview`)
}
