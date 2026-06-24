import { create } from 'zustand'

type SessionUiState = {
  workspace: string
  sessionId: string | null
  draft: string
  setWorkspace: (workspace: string) => void
  setSessionId: (sessionId: string | null) => void
  setDraft: (draft: string) => void
}

export const useSessionUiStore = create<SessionUiState>((set) => ({
  workspace: 'default',
  sessionId: null,
  draft: '',
  setWorkspace: (workspace) => set({ workspace }),
  setSessionId: (sessionId) => set({ sessionId }),
  setDraft: (draft) => set({ draft }),
}))
