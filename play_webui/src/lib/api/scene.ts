import type { Scene } from '@/types/scene'
import { playApiFetch } from './client'

export function getCurrentScene(sessionId: string) {
  return playApiFetch<Scene>(`/sessions/${encodeURIComponent(sessionId)}/scene`)
}
