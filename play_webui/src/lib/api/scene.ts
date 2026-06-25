import type { Scene } from '@/types/scene'
import { playApiFetch, withWorkspace } from './client'

export function getCurrentScene(workspace: string, storyId: number, sessionId: string) {
  return playApiFetch<Scene>(
    `${withWorkspace('/scene/current', workspace)}&story_id=${encodeURIComponent(storyId)}&session_id=${encodeURIComponent(sessionId)}`,
  )
}
