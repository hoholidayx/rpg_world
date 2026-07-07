import type { ReactNode } from 'react'
import { HISTORY_MESSAGE_ROLE } from '@/types/session'

export type SessionInputMode = 'ic' | 'ooc' | 'gm'

export type NarrativeStyleId = 'default' | 'detailed' | 'fast' | 'options'

export type NarrativeStyle = {
  id: NarrativeStyleId
  label: string
  prompt: string
}

export type SpeakerTone = 'player' | 'assistant' | 'tool' | 'system' | 'thinking' | 'error'

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

export const SESSION_TIMELINE_ROLE = {
  ...HISTORY_MESSAGE_ROLE,
  THINKING: 'thinking',
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
  seqInTurn?: number
  role: SessionTimelineRole
  content: string
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
