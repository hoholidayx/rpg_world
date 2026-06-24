import type { PlayCommand } from '@/types/command'
import { playApiFetch, withWorkspace } from './client'

export function listCommands(workspace: string, sessionId: string) {
  return playApiFetch<PlayCommand[]>(
    `${withWorkspace('/commands', workspace)}&session_id=${encodeURIComponent(sessionId)}`,
  )
}
