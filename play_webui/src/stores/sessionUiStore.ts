import { create } from 'zustand'

type SessionUiState = {
  workspace: string | null
  storyId: number | null
  sessionId: string | null
  draft: string
  setWorkspace: (workspace: string | null) => void
  setStoryId: (storyId: number | null) => void
  setSessionId: (sessionId: string | null) => void
  setDraft: (draft: string) => void
}

export const useSessionUiStore = create<SessionUiState>((set) => ({
  workspace: null,
  storyId: null,
  sessionId: null,
  draft: '',
  setWorkspace: (workspace) => set({ workspace }),
  setStoryId: (storyId) => set({ storyId }),
  setSessionId: (sessionId) => set({ sessionId }),
  setDraft: (draft) => set({ draft }),
}))
