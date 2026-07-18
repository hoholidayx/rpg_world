'use client'

import { useEffect } from 'react'
import { getPlayApiBaseUrl } from '@/lib/config/env'
import { usePlayEventStore } from '@/stores/playEventStore'
import { parsePlayEvent } from './playEvents'

export function PlayEventBridge() {
  useEffect(() => {
    const store = usePlayEventStore.getState()
    store.setConnectionStatus('connecting')
    const baseUrl = getPlayApiBaseUrl().replace(/\/$/, '')
    const source = new EventSource(`${baseUrl}/events/stream`)

    source.onopen = () => {
      usePlayEventStore.getState().setConnectionStatus('open')
    }
    source.onerror = () => {
      usePlayEventStore.getState().setConnectionStatus(
        source.readyState === EventSource.CONNECTING ? 'connecting' : 'disconnected',
      )
    }
    source.onmessage = (message) => {
      try {
        const event = parsePlayEvent(JSON.parse(message.data) as unknown)
        if (event !== null) {
          usePlayEventStore.getState().receive(event)
        } else if (process.env.NODE_ENV !== 'production') {
          console.warn('Ignored invalid Play event payload')
        }
      } catch {
        if (process.env.NODE_ENV !== 'production') {
          console.warn('Ignored malformed Play event JSON')
        }
      }
    }

    return () => {
      source.close()
      usePlayEventStore.getState().setConnectionStatus('disconnected')
    }
  }, [])

  return null
}
