import { create } from 'zustand'
import type { InputMode } from '@/types/command'

type PlayUiState = {
  inputMode: InputMode
  sceneOpen: boolean
  debugOpen: boolean
  setInputMode: (mode: InputMode) => void
  toggleScene: () => void
  toggleDebug: () => void
}

export const usePlayUiStore = create<PlayUiState>((set) => ({
  inputMode: 'ic',
  sceneOpen: false,
  debugOpen: false,
  setInputMode: (inputMode) => set({ inputMode }),
  toggleScene: () => set((state) => ({ sceneOpen: !state.sceneOpen })),
  toggleDebug: () => set((state) => ({ debugOpen: !state.debugOpen })),
}))
