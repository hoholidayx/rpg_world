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

export type LorebookEntry = {
  id: number
  workspaceId: string
  name: string
  content: string
  description: string
  tags: string[]
  metadata: Record<string, unknown>
  version: number
  createdAt?: string | null
  updatedAt?: string | null
  mountId?: number | null
  storyId?: number | null
}

export type LorebookEntryInput = {
  name: string
  content: string
  description: string
  tags: string[]
  metadata: Record<string, unknown>
}
