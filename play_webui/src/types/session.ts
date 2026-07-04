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
  messages: HistoryMessage[]
}

export type HistoryMessage = {
  messageId: number
  turnId: number
  seqInTurn: number
  role: 'user' | 'assistant' | 'tool' | 'system'
  content: string
  metadata: Record<string, unknown>
  createdAt?: string | null
}
