import type { SessionSummary } from './session'

export type StorySummary = {
  id: number
  workspace: string
  title: string
  summary?: string | null
  storyPrompt: string
  firstMessage: string
  createdAt?: string | null
  updatedAt?: string | null
}

export type StoryInput = {
  title: string
  summary: string
  storyPrompt: string
  firstMessage: string
}

export type StoryComputedStatus = 'live' | 'draft'

export type StoryLibraryItem = StorySummary & {
  characterCount: number
  lorebookCount: number
  statusTableCount: number
  sceneStatusCount: number
  sessions: SessionSummary[]
  latestSession?: SessionSummary | null
  computedStatus: StoryComputedStatus
  searchText: string
}
