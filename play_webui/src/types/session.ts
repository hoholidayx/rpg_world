export type WorkspaceSummary = {
  id: string
  name: string
  description?: string | null
}

export type SessionSummary = {
  id: string
  workspace: string
  storyId: number
  title?: string | null
  description?: string | null
  createdAt?: string | null
  updatedAt?: string | null
}

export type Turn = {
  turnId: number
  userMessage: string
  assistantMessage?: string | null
  source?: 'play_webui' | 'telegram' | 'cli'
  createdAt?: string | null
}
