export type CharacterDetail = {
  id: number
  storyCharacterId: number
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
  storyId: number
  name: string
  description: string
  metadata: Record<string, unknown>
  details: CharacterDetail[]
  version: number
  createdAt?: string | null
  updatedAt?: string | null
  sortOrder: number
}

export type CharacterInput = {
  name: string
  description: string
  sortOrder?: number
  metadata: Record<string, unknown>
}

export type CharacterDetailInput = {
  name: string
  content: string
  tags: string[]
  sortOrder: number
}
