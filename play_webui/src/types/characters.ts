import type { StorySummary } from './lorebook'

export type { StorySummary }

export type CharacterDetail = {
  id: number
  characterId: number
  name: string
  content: string
  tags: string[]
  sortOrder: number
  version: number
  createdAt?: string | null
  updatedAt?: string | null
}

export type CharacterCard = {
  id: number
  workspaceId: string
  name: string
  personality: string
  content: string
  metadata: Record<string, unknown>
  details: CharacterDetail[]
  version: number
  createdAt?: string | null
  updatedAt?: string | null
  mountId?: number | null
  storyId?: number | null
}

export type CharacterInput = {
  name: string
  personality: string
  content: string
  metadata: Record<string, unknown>
}

export type CharacterDetailInput = {
  name: string
  content: string
  tags: string[]
  sortOrder: number
}
