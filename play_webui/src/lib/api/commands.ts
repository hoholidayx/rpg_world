import type { PlayCommand } from '@/types/command'
import { playApiFetch, withWorkspace } from './client'

export function listCommands(workspace: string, storyId: number, sessionId: string) {
  return playApiFetch<PlayCommand[]>(
    `${withWorkspace('/commands', workspace)}&story_id=${encodeURIComponent(storyId)}&session_id=${encodeURIComponent(sessionId)}`,
  )
}
