import { beforeEach, describe, expect, it, vi } from 'vitest'
import {
  PLAY_STREAM_EVENT_TYPE,
  PLAY_STREAM_SCHEMA_VERSION,
  type PlayStreamEvent,
} from '@/types/stream'

const createStreamRequestMock = vi.hoisted(() => vi.fn())

vi.mock('@/lib/api/chat', () => ({
  createStreamRequest: createStreamRequestMock,
}))

import { consumeChatStream } from './sse'

function streamResponse(chunks: string[]) {
  const encoder = new TextEncoder()
  return new Response(new ReadableStream({
    start(controller) {
      chunks.forEach((chunk) => controller.enqueue(encoder.encode(chunk)))
      controller.close()
    },
  }))
}

function structuredFrame(
  type: PlayStreamEvent['type'],
  payload: Record<string, unknown>,
) {
  return `data: ${JSON.stringify({
    schemaVersion: PLAY_STREAM_SCHEMA_VERSION,
    eventId: 1,
    sessionId: 'session_1',
    turnId: 'turn_session_1',
    type,
    payload,
  })}\n\n`
}

function eventText(event: PlayStreamEvent) {
  return 'text' in event.payload && typeof event.payload.text === 'string'
    ? event.payload.text
    : undefined
}

describe('consumeChatStream fallback compatibility', () => {
  beforeEach(() => {
    createStreamRequestMock.mockReset()
  })

  it('emits a malformed SSE frame as raw assistant text without dropping bytes', async () => {
    const malformedFrame = 'data: {"schemaVersion":"broken"'
    createStreamRequestMock.mockResolvedValue(streamResponse([
      `${malformedFrame}\n\n`,
    ]))
    const events: PlayStreamEvent[] = []

    await consumeChatStream(
      { sessionId: 'session_1', text: 'hello', mode: 'neutral' },
      { onEvent: (event) => events.push(event) },
    )

    expect(events).toHaveLength(1)
    expect(events[0]).toMatchObject({
      eventId: -1,
      sessionId: 'session_1',
      turnId: 'raw_session_1',
      type: PLAY_STREAM_EVENT_TYPE.TEXT_DELTA,
      payload: { text: malformedFrame },
    })
  })

  it('keeps valid and fallback events in their received order', async () => {
    const malformedFrame = 'data: 不是 JSON，但必须展示'
    createStreamRequestMock.mockResolvedValue(streamResponse([
      structuredFrame(PLAY_STREAM_EVENT_TYPE.TEXT_DELTA, { text: '前半段' }),
      `${malformedFrame}\n\n`,
      structuredFrame(PLAY_STREAM_EVENT_TYPE.TEXT_DELTA, { text: '后半段' }),
    ]))
    const events: PlayStreamEvent[] = []

    await consumeChatStream(
      { sessionId: 'session_1', text: 'hello', mode: 'neutral' },
      { onEvent: (event) => events.push(event) },
    )

    expect(events.map(eventText)).toEqual([
      '前半段',
      malformedFrame,
      '后半段',
    ])
  })

  it('keeps the existing tolerant EOF behavior without requiring a terminal event', async () => {
    createStreamRequestMock.mockResolvedValue(streamResponse([
      structuredFrame(PLAY_STREAM_EVENT_TYPE.TEXT_DELTA, { text: '仅有正文' }),
      'data: [DONE]\n\n',
    ]))
    const events: PlayStreamEvent[] = []

    await expect(consumeChatStream(
      { sessionId: 'session_1', text: 'hello', mode: 'neutral' },
      { onEvent: (event) => events.push(event) },
    )).resolves.toBeUndefined()

    expect(events.map(eventText)).toEqual(['仅有正文'])
  })

  it('preserves a malformed frame split across network chunks', async () => {
    createStreamRequestMock.mockResolvedValue(streamResponse([
      'data: 原始',
      '片段不能丢失\n\n',
    ]))
    const events: PlayStreamEvent[] = []

    await consumeChatStream(
      { sessionId: 'session_1', text: 'hello', mode: 'neutral' },
      { onEvent: (event) => events.push(event) },
    )

    expect(events[0] && eventText(events[0])).toBe('data: 原始片段不能丢失')
  })
})
