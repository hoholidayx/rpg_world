'use client'

import { create } from 'zustand'

type NotificationState = {
  readEventIds: string[]
  dismissedEventIds: string[]
  markRead: (eventIds: string[]) => void
  dismiss: (eventId: string) => void
  dismissAll: (eventIds: string[]) => void
  reconcile: (retainedEventIds: string[]) => void
}

export const useNotificationStore = create<NotificationState>((set) => ({
  readEventIds: [],
  dismissedEventIds: [],
  markRead: (eventIds) => set((state) => {
    const readEventIds = mergeUnique(state.readEventIds, eventIds)
    return arraysEqual(readEventIds, state.readEventIds) ? state : { readEventIds }
  }),
  dismiss: (eventId) => set((state) => {
    if (state.dismissedEventIds.includes(eventId)) return state
    return { dismissedEventIds: [...state.dismissedEventIds, eventId] }
  }),
  dismissAll: (eventIds) => set((state) => {
    const dismissedEventIds = mergeUnique(state.dismissedEventIds, eventIds)
    return arraysEqual(dismissedEventIds, state.dismissedEventIds)
      ? state
      : { dismissedEventIds }
  }),
  reconcile: (retainedEventIds) => set((state) => {
    const retained = new Set(retainedEventIds)
    const readEventIds = state.readEventIds.filter((eventId) => retained.has(eventId))
    const dismissedEventIds = state.dismissedEventIds.filter((eventId) => retained.has(eventId))
    if (
      arraysEqual(readEventIds, state.readEventIds)
      && arraysEqual(dismissedEventIds, state.dismissedEventIds)
    ) return state
    return { readEventIds, dismissedEventIds }
  }),
}))

function mergeUnique(current: string[], incoming: string[]) {
  if (incoming.length === 0) return current
  return Array.from(new Set([...current, ...incoming]))
}

function arraysEqual(left: string[], right: string[]) {
  return left.length === right.length && left.every((value, index) => value === right[index])
}
