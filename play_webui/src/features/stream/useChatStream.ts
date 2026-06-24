'use client'

import { useCallback, useRef, useState } from 'react'
import { consumeChatStream } from '@/lib/stream/sse'
import { createInitialStreamState, reduceAgentEvent } from '@/lib/stream/streamReducer'
import type { SendMessagePayload } from '@/types/command'
import type { TimelineItem } from '@/types/stream'

export function useChatStream() {
  const [state, setState] = useState(createInitialStreamState)
  const abortRef = useRef<AbortController | null>(null)

  const sendMessage = useCallback(async (payload: SendMessagePayload) => {
    const userItem: TimelineItem = {
      id: crypto.randomUUID(),
      type: 'user',
      content: payload.text,
      createdAt: new Date().toISOString(),
    }
    const controller = new AbortController()
    abortRef.current = controller
    setState((prev) => ({ ...prev, status: 'connecting', timeline: [...prev.timeline, userItem] }))
    try {
      await consumeChatStream(payload, {
        signal: controller.signal,
        onEvent: (event) => setState((prev) => reduceAgentEvent(prev, event)),
      })
    } catch (error) {
      setState((prev) =>
        reduceAgentEvent(prev, {
          kind: 'error',
          content: error instanceof Error ? error.message : '未知流式错误',
        }),
      )
    }
  }, [])

  const stop = useCallback(() => {
    abortRef.current?.abort()
  }, [])

  return { ...state, sendMessage, stop }
}
