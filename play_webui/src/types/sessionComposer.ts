import type { InputMode } from './command'

export type WorkspaceTurnMode = {
  mode: InputMode
  shortName: string
  prompt: string
  sortOrder: number
  version: number
}

export type NarrativeStyle = {
  id: number
  workspaceId: string
  name: string
  prompt: string
  sortOrder: number
  version: number
  createdAt?: string | null
  updatedAt?: string | null
}

export type StoryNarrativeStyle = {
  mountId: number
  narrativeStyleId: number
  name: string
  prompt: string
  isBase: boolean
  sortOrder: number
  version: number
}

export type StoryQuickReply = {
  id: number
  title: string
  message: string
  sortOrder: number
  enabled: boolean
  version: number
  createdAt?: string | null
  updatedAt?: string | null
}

export type SessionComposerConfig = {
  sessionId: string
  workspaceId: string
  storyId: number
  modes: WorkspaceTurnMode[]
  narrativeStyles: StoryNarrativeStyle[]
  baseNarrativeStyleId: number | null
  quickReplies: StoryQuickReply[]
}

export type NarrativeStyleInput = {
  name: string
  prompt: string
  sortOrder: number
}

export type QuickReplyInput = {
  title: string
  message: string
  sortOrder: number
  enabled: boolean
}
