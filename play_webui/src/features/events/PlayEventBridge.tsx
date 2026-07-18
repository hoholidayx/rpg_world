'use client'

import { useEffect } from 'react'
import { getPlayApiBaseUrl } from '@/lib/config/env'
import { usePlayEventStore } from '@/stores/playEventStore'
import { parsePlayEvent } from './playEvents'

export function PlayEventBridge() {
  useEffect(() => {
    const development = process.env.NODE_ENV !== 'production'
    const store = usePlayEventStore.getState()
    store.setConnectionStatus('connecting')
    const baseUrl = getPlayApiBaseUrl().replace(/\/$/, '')
    const source = new EventSource(`${baseUrl}/events/stream`)

    source.onopen = () => {
      usePlayEventStore.getState().setConnectionStatus('open')
      if (development) console.info('[PlayEvents] stream opened')
    }
    source.onerror = () => {
      const connectionStatus = source.readyState === EventSource.CONNECTING
        ? 'connecting'
        : 'disconnected'
      usePlayEventStore.getState().setConnectionStatus(connectionStatus)
      if (development) {
        console.warn('[PlayEvents] stream error', {
          connectionStatus,
          readyState: source.readyState,
        })
      }
    }
    source.onmessage = (message) => {
      try {
        const event = parsePlayEvent(JSON.parse(message.data) as unknown)
        if (event !== null) {
          usePlayEventStore.getState().receive(event)
          if (development) {
            console.info('[PlayEvents] terminal event stored', {
              eventId: event.eventId,
              eventType: event.eventType,
              sessionId: event.sessionId,
              status: event.payload.status,
            })
          }
        } else if (development) {
          console.warn('Ignored invalid Play event payload')
        }
      } catch (error) {
        if (development) {
          console.warn(
            'Ignored malformed Play event JSON',
            error instanceof Error ? error.message : String(error),
          )
        }
      }
    }

    return () => {
      source.close()
      usePlayEventStore.getState().setConnectionStatus('disconnected')
      if (development) console.info('[PlayEvents] stream closed')
    }
  }, [])

  return null
}
