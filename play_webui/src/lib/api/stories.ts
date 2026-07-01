import type { StorySummary } from '@/types/story'
import { playApiFetch } from './client'

export function listStories(workspace: string) {
  return playApiFetch<StorySummary[]>(`/workspaces/${encodeURIComponent(workspace)}/stories`)
}
