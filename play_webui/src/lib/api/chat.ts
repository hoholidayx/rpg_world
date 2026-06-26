import type { SendMessagePayload } from '@/types/command'
import { getPlayApiBaseUrl } from '@/lib/config/env'

export function buildStreamUrl() {
  return getPlayApiBaseUrl()
}

export function createStreamRequest(payload: SendMessagePayload, signal?: AbortSignal) {
  return fetch(`${buildStreamUrl()}/sessions/${encodeURIComponent(payload.sessionId)}/stream`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      text: payload.text,
      mode: payload.mode,
    }),
    signal,
  })
}
