import type { SendMessagePayload, TurnCancelStatus } from '@/types/command'
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
      narrativeStyleId: payload.narrativeStyleId ?? null,
      requestId: payload.requestId,
    }),
    signal,
  })
}

export async function stopSessionStream(sessionId: string, requestId?: string) {
  const response = await fetch(`${buildStreamUrl()}/sessions/${encodeURIComponent(sessionId)}/stop`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ requestId }),
  })
  if (!response.ok) throw new Error('停止当前生成失败')
  return response.json() as Promise<{
    status: TurnCancelStatus
    sessionId: string
    requestId?: string
  }>
}
