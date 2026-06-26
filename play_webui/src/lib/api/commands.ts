import type { PlayCommand } from '@/types/command'
import { playApiFetch } from './client'

export function listCommands(sessionId: string) {
  return playApiFetch<PlayCommand[]>(`/sessions/${encodeURIComponent(sessionId)}/commands`)
}
