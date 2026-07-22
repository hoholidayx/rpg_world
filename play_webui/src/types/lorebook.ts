export type LorebookEntry = {
  id: number
  workspaceId: string
  storyId: number
  name: string
  content: string
  description: string
  tags: string[]
  metadata: Record<string, unknown>
  version: number
  createdAt?: string | null
  updatedAt?: string | null
  sortOrder: number
}

export type LorebookEntryInput = {
  name: string
  content: string
  description: string
  tags: string[]
  sortOrder?: number
  metadata: Record<string, unknown>
}
