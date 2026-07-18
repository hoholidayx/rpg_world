'use client'

import { create } from 'zustand'
import type { PlayEvent, PlayEventConnectionStatus } from '@/features/events/playEvents'

const RECENT_EVENT_LIMIT = 50

type PlayEventState = {
  connectionStatus: PlayEventConnectionStatus
  events: PlayEvent[]
  setConnectionStatus: (connectionStatus: PlayEventConnectionStatus) => void
  receive: (event: PlayEvent) => void
}

export const usePlayEventStore = create<PlayEventState>((set) => ({
  connectionStatus: 'disconnected',
  events: [],
  setConnectionStatus: (connectionStatus) => set({ connectionStatus }),
  receive: (event) => set((state) => {
    if (state.events.some((existing) => existing.eventId === event.eventId)) {
      return state
    }
    return { events: [event, ...state.events].slice(0, RECENT_EVENT_LIMIT) }
  }),
}))
