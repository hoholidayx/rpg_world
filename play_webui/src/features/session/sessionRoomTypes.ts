import type { ReactNode } from 'react'

export type SessionInputMode = 'ic' | 'ooc' | 'gm'

export type NarrativeStyleId = 'default' | 'detailed' | 'fast' | 'options'

export type NarrativeStyle = {
  id: NarrativeStyleId
  label: string
  prompt: string
}

export type SpeakerTone = 'player' | 'assistant' | 'tool' | 'thinking' | 'error'

export type SessionSpeaker = {
  name: string
  label?: string
  avatarUrl?: string
  fallback: string
  tone: SpeakerTone
}

export type SessionTimelineMessage = {
  id: string
  turnId: number
  role: 'user' | 'assistant' | 'tool' | 'thinking' | 'error'
  content: string
  createdAt?: string | null
  speaker: SessionSpeaker
  status?: 'done' | 'streaming' | 'local' | 'error'
  hiddenPrompt?: string
}

export type ConfirmRequest = {
  title: string
  heading: string
  body: ReactNode
  confirmLabel: string
  onConfirm: () => void
}
