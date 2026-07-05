import { createStreamRequest } from '@/lib/api/chat'
import type { SendMessagePayload } from '@/types/command'
import { PLAY_STREAM_EVENT_TYPE, PLAY_STREAM_SCHEMA_VERSION, type PlayStreamEvent } from '@/types/stream'
import { parsePlayStreamEvent } from './parsePlayStreamEvent'

function sseDataPayload(chunk: string): string | null {
  const dataLines = chunk
    .split('\n')
    .filter((line) => line.startsWith('data:'))
    .map((line) => line.slice(5))

  if (dataLines.length > 0) return dataLines.join('\n')
  return null
}

function rawTextEvent(raw: string, sessionId: string, eventId: number): PlayStreamEvent {
  return {
    schemaVersion: PLAY_STREAM_SCHEMA_VERSION,
    eventId,
    sessionId,
    turnId: `raw_${sessionId}`,
    type: PLAY_STREAM_EVENT_TYPE.TEXT_DELTA,
    payload: { text: raw },
  }
}

export async function consumeChatStream(
  payload: SendMessagePayload,
  handlers: {
    signal?: AbortSignal
    onEvent: (event: PlayStreamEvent) => void
  },
) {
  const response = await createStreamRequest(payload, handlers.signal)
  if (!response.ok || !response.body) throw new Error('无法建立 Play API 流式连接')

  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  let rawEventId = -1

  function emitChunk(chunk: string) {
    const data = sseDataPayload(chunk)
    const parseTarget = data ?? chunk
    if (!parseTarget || parseTarget.trim() === '[DONE]') return
    try {
      const event = parsePlayStreamEvent(parseTarget)
      if (event) handlers.onEvent(event)
    } catch {
      handlers.onEvent(rawTextEvent(chunk, payload.sessionId, rawEventId--))
    }
  }

  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })
    const chunks = buffer.split('\n\n')
    buffer = chunks.pop() ?? ''
    for (const chunk of chunks) {
      emitChunk(chunk)
    }
  }

  if (buffer) emitChunk(buffer)
}
