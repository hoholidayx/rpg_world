import type { PlayCommand } from '@/types/command'
import { playApiFetch } from './client'

export function listCommands() {
  return playApiFetch<PlayCommand[]>('/commands')
}
