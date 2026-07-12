'use client'

import { create } from 'zustand'

export type SessionFontScale =
  | 90
  | 95
  | 100
  | 105
  | 110
  | 115
  | 120
  | 125
  | 130
  | 135
  | 140
  | 145
  | 150
  | 155
  | 160
  | 165
  | 170
  | 175
  | 180
  | 185
  | 190
  | 195
  | 200

export const SESSION_FONT_SCALE_MIN = 90
export const SESSION_FONT_SCALE_MAX = 200
export const SESSION_FONT_SCALE_STEP = 5
export const SESSION_FONT_SCALE_DEFAULT: SessionFontScale = 125

const SESSION_FONT_SCALE_STORAGE_KEY = 'rpg-world-session-font-scale'
const SESSION_SHOW_THINKING_STORAGE_KEY = 'rpg-world-session-show-thinking'
const SESSION_SHOW_TOOLS_STORAGE_KEY = 'rpg-world-session-show-tools'

function normalizeSessionFontScale(value: number): SessionFontScale {
  const rounded = Math.round(value / SESSION_FONT_SCALE_STEP) * SESSION_FONT_SCALE_STEP
  const clamped = Math.min(SESSION_FONT_SCALE_MAX, Math.max(SESSION_FONT_SCALE_MIN, rounded))
  return clamped as SessionFontScale
}

function readStoredFontScale(): SessionFontScale {
  if (typeof window === 'undefined') return SESSION_FONT_SCALE_DEFAULT

  const stored = window.localStorage.getItem(SESSION_FONT_SCALE_STORAGE_KEY)
  if (stored === null) return SESSION_FONT_SCALE_DEFAULT
  const parsed = Number(stored)
  if (!Number.isFinite(parsed)) return SESSION_FONT_SCALE_DEFAULT
  return normalizeSessionFontScale(parsed)
}

function storeFontScale(fontScale: SessionFontScale) {
  if (typeof window === 'undefined') return
  window.localStorage.setItem(SESSION_FONT_SCALE_STORAGE_KEY, String(fontScale))
}

function readStoredBoolean(key: string, fallback = false): boolean {
  if (typeof window === 'undefined') return fallback

  const stored = window.localStorage.getItem(key)
  if (stored === null) return fallback
  return stored === 'true'
}

function storeBoolean(key: string, value: boolean) {
  if (typeof window === 'undefined') return
  window.localStorage.setItem(key, String(value))
}

type SessionUiState = {
  workspace: string | null
  storyId: number | null
  sessionId: string | null
  draft: string
  fontScale: SessionFontScale
  showThinking: boolean
  showTools: boolean
  setWorkspace: (workspace: string | null) => void
  setStoryId: (storyId: number | null) => void
  setSessionId: (sessionId: string | null) => void
  setDraft: (draft: string) => void
  setFontScale: (fontScale: number) => void
  setShowThinking: (show: boolean) => void
  setShowTools: (show: boolean) => void
  syncFontScale: () => void
  syncDiagnosticsDisplay: () => void
}

export const useSessionUiStore = create<SessionUiState>((set) => ({
  workspace: null,
  storyId: null,
  sessionId: null,
  draft: '',
  fontScale: SESSION_FONT_SCALE_DEFAULT,
  showThinking: false,
  showTools: false,
  setWorkspace: (workspace) => set({ workspace }),
  setStoryId: (storyId) => set({ storyId }),
  setSessionId: (sessionId) => set({ sessionId }),
  setDraft: (draft) => set({ draft }),
  setFontScale: (value) => {
    const fontScale = normalizeSessionFontScale(value)
    storeFontScale(fontScale)
    set({ fontScale })
  },
  setShowThinking: (showThinking) => {
    storeBoolean(SESSION_SHOW_THINKING_STORAGE_KEY, showThinking)
    set({ showThinking })
  },
  setShowTools: (showTools) => {
    storeBoolean(SESSION_SHOW_TOOLS_STORAGE_KEY, showTools)
    set({ showTools })
  },
  syncFontScale: () => set({ fontScale: readStoredFontScale() }),
  syncDiagnosticsDisplay: () => set({
    showThinking: readStoredBoolean(SESSION_SHOW_THINKING_STORAGE_KEY),
    showTools: readStoredBoolean(SESSION_SHOW_TOOLS_STORAGE_KEY),
  }),
}))
