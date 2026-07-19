import type { DreamEpistemicStatus, DreamMemoryKind } from './dream'

export type StoryMemoryEvidence = {
  messageId: number
  turnId: number
}

export type StoryMemoryItem = {
  id: number
  text: string
  memoryKind: DreamMemoryKind
  epistemicStatus: DreamEpistemicStatus
  salience: number
  sourceTurnStart: number
  sourceTurnEnd: number
  dreamProcessed: boolean
  evidence: StoryMemoryEvidence[]
  version: number
  createdAt: string
  updatedAt: string
}

export type StoryMemoryStats = {
  totalFacts: number
  dreamProcessedFacts: number
  pendingDreamFacts: number
  unprocessedSourceTurns: number
  latestUpdatedAt: string | null
}

export type StoryMemoryPage = {
  items: StoryMemoryItem[]
  page: number
  pageSize: number
  total: number
  stats: StoryMemoryStats
}

export type StoryMemoryListOptions = {
  page?: number
  pageSize?: number
  memoryKind?: DreamMemoryKind
  dreamProcessed?: boolean
}
