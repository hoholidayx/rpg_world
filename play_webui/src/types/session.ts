import type { NarrativeOutcome } from './narrativeOutcome'
import type { InputMode } from './command'

export const PLAYER_CHARACTER_STATUS = {
  BOUND: 'bound',
  INVALID: 'invalid',
} as const

export type PlayerCharacterStatus = (typeof PLAYER_CHARACTER_STATUS)[keyof typeof PLAYER_CHARACTER_STATUS]

export const HISTORY_MESSAGE_ROLE = {
  SYSTEM: 'system',
  USER: 'user',
  ASSISTANT: 'assistant',
  TOOL: 'tool',
} as const

export type HistoryMessageRole = (typeof HISTORY_MESSAGE_ROLE)[keyof typeof HISTORY_MESSAGE_ROLE]

export const SESSION_ACTIVITY = {
  RECENT: 'recent',
  STALE: 'stale',
} as const

export type SessionComputedActivity = (typeof SESSION_ACTIVITY)[keyof typeof SESSION_ACTIVITY]

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
  playerCharacter?: SessionPlayerCharacter | null
  playerCharacterStatus: PlayerCharacterStatus
  createdAt?: string | null
  updatedAt?: string | null
}

export type SessionDeleteResult = {
  status: 'deleted'
  sessionId: string
  runtimeCleanup: 'deleted' | 'absent' | 'pending'
}

export type SessionDerivationStatus = 'queued' | 'running' | 'ready' | 'failed' | 'interrupted'

export type SessionDerivationJob = {
  jobId: string
  sourceSessionId: string
  targetSessionId: string | null
  turnId: number
  status: SessionDerivationStatus
  stage: string
  errorCode: string
  errorMessage: string
  contextUsage: Record<string, unknown> | null
  contextThresholdExceeded: boolean
  createdAt: string
  startedAt: string
  finishedAt: string
  updatedAt: string
}

export type SessionPlayerCharacter = {
  characterId: number
  mountId: number
  storyId: number
  name: string
  avatarUrl: string
  roleLabel: string
  updatedAt: string
}

export type Turn = {
  turnId: number
  messages: HistoryMessage[]
  outcome?: NarrativeOutcome | null
}

export type HistoryPage = {
  turns: Turn[]
  startTurnId: number | null
  endTurnId: number | null
  latestTurnId: number
  hasBefore: boolean
  hasAfter: boolean
  limit: number
}

export type HistoryMessage = {
  messageId: number
  turnId: number
  seqInTurn: number
  role: HistoryMessageRole
  content: string
  mode: InputMode
  metadata: Record<string, unknown>
  createdAt?: string | null
}
