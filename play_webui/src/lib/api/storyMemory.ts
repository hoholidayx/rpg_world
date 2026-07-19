import type { StoryMemoryListOptions, StoryMemoryPage } from '@/types/storyMemory'
import { playApiFetch } from './client'

export function listSessionStoryMemories(
  sessionId: string,
  options: StoryMemoryListOptions = {},
) {
  const params = new URLSearchParams()
  params.set('page', String(options.page ?? 1))
  params.set('pageSize', String(options.pageSize ?? 20))
  if (options.memoryKind) params.set('memoryKind', options.memoryKind)
  if (options.dreamProcessed !== undefined) {
    params.set('dreamProcessed', String(options.dreamProcessed))
  }
  return playApiFetch<StoryMemoryPage>(
    `/sessions/${encodeURIComponent(sessionId)}/story-memories?${params.toString()}`,
  )
}
