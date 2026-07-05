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

export const STORY_COMPUTED_STATUS = {
  LIVE: 'live',
  DRAFT: 'draft',
} as const

export type StoryComputedStatus = (typeof STORY_COMPUTED_STATUS)[keyof typeof STORY_COMPUTED_STATUS]

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
