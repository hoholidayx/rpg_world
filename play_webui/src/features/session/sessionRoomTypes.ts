import type { ReactNode } from 'react'
import type { ContextUsageSnapshot } from '@/types/contextUsage'
import { HISTORY_MESSAGE_ROLE } from '@/types/session'
import type { NarrativeOutcome } from '@/types/narrativeOutcome'

export type SessionInputMode = 'ic' | 'ooc' | 'gm'

export type NarrativeStyleId = 'default' | 'detailed' | 'fast' | 'options'

export type NarrativeStyle = {
  id: NarrativeStyleId
  label: string
  prompt: string
}

export type SpeakerTone = 'player' | 'assistant' | 'tool' | 'outcome' | 'system' | 'thinking' | 'error'

export const SESSION_MESSAGE_STATUS = {
  DONE: 'done',
  STREAMING: 'streaming',
  LOCAL: 'local',
  ERROR: 'error',
} as const

export type SessionMessageStatus = (typeof SESSION_MESSAGE_STATUS)[keyof typeof SESSION_MESSAGE_STATUS]

export const SESSION_STREAM_SOURCE = {
  SEND: 'send',
  RETRY: 'retry',
  EDIT: 'edit',
} as const

export type SessionStreamSource = (typeof SESSION_STREAM_SOURCE)[keyof typeof SESSION_STREAM_SOURCE]

export const HISTORY_LOAD_DIRECTION = {
  BEFORE: 'before',
  AFTER: 'after',
} as const

export type HistoryLoadDirection = (typeof HISTORY_LOAD_DIRECTION)[keyof typeof HISTORY_LOAD_DIRECTION]

export const HISTORY_REFRESH_MODE = {
  ACTIVE: 'active',
  LATEST: 'latest',
} as const

export type HistoryRefreshMode = (typeof HISTORY_REFRESH_MODE)[keyof typeof HISTORY_REFRESH_MODE]

export type RefreshSessionDataOptions = {
  silent?: boolean
  clearLastTurnUsage?: boolean
  preserveDiagnostics?: boolean
  preserveCommandMessages?: boolean
  historyMode?: HistoryRefreshMode
  scrollToBottom?: boolean
}

export type SessionRailDrawerState =
  | { kind: 'characters' }
  | { kind: 'status-manager' }
  | { kind: 'summary'; summaryKey: string }
  | null

export const SESSION_HISTORY_MESSAGES = {
  LATEST_LOAD_FAILED: '加载最新历史失败，请稍后再试',
} as const

export const SESSION_TIMELINE_ROLE = {
  ...HISTORY_MESSAGE_ROLE,
  THINKING: 'thinking',
  OUTCOME: 'outcome',
  ERROR: 'error',
} as const

export type SessionTimelineRole = (typeof SESSION_TIMELINE_ROLE)[keyof typeof SESSION_TIMELINE_ROLE]

export type SessionSpeaker = {
  name: string
  label?: string
  avatarUrl?: string
  fallback: string
  tone: SpeakerTone
}

export type SessionTimelineMessage = {
  id: string
  messageId?: number
  turnId: number
  timelineGroupId?: string
  timelineAnchorTurnId?: number
  timelineGroupOrder?: number
  timelineItemOrder?: number
  seqInTurn?: number
  role: SessionTimelineRole
  content: string
  usage?: ContextUsageSnapshot | null
  outcome?: NarrativeOutcome
  metadata?: Record<string, unknown>
  createdAt?: string | null
  speaker: SessionSpeaker
  status?: SessionMessageStatus
  hiddenPrompt?: string
  canCopy?: boolean
  canRetry?: boolean
  canEdit?: boolean
  canDelete?: boolean
}

export type ConfirmRequest = {
  title: string
  heading: string
  body: ReactNode
  confirmLabel: string
  onConfirm: () => void
}
