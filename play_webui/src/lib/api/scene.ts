import type { Scene } from '@/types/scene'
import { playApiFetch, withWorkspace } from './client'

export function getCurrentScene(workspace: string, sessionId: string) {
  return playApiFetch<Scene>(
    `${withWorkspace('/scene/current', workspace)}&sessionId=${encodeURIComponent(sessionId)}`,
  )
}
