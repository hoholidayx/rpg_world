import type { StoryInput, StorySummary } from '@/types/story'
import { playApiFetch } from './client'

export function listStories(workspace: string) {
  return playApiFetch<StorySummary[]>(`/workspaces/${encodeURIComponent(workspace)}/stories`)
}

export function createStory(workspace: string, input: StoryInput) {
  return playApiFetch<StorySummary>(`/workspaces/${encodeURIComponent(workspace)}/stories`, {
    method: 'POST',
    body: JSON.stringify(input),
  })
}

export function updateStory(workspace: string, storyId: number, input: Partial<StoryInput>) {
  return playApiFetch<StorySummary>(`/workspaces/${encodeURIComponent(workspace)}/stories/${encodeURIComponent(storyId)}`, {
    method: 'PATCH',
    body: JSON.stringify(input),
  })
}
