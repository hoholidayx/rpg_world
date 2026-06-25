import type { SendMessagePayload } from '@/types/command'
import { getPlayApiBaseUrl } from '@/lib/config/env'

export function buildStreamUrl() {
  return `${getPlayApiBaseUrl()}/chat/stream`
}

export function createStreamRequest(payload: SendMessagePayload, signal?: AbortSignal) {
  return fetch(buildStreamUrl(), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      workspace: payload.workspace,
      story_id: payload.storyId,
      session_id: payload.sessionId,
      text: payload.text,
      mode: payload.mode,
    }),
    signal,
  })
}
