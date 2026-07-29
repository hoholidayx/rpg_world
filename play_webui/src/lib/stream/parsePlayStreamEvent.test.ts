import { describe, expect, it } from 'vitest'
import {
  PLAY_STREAM_EVENT_TYPE,
  PLAY_STREAM_SCHEMA_VERSION,
} from '@/types/stream'
import { DEFAULT_STREAM_ERROR_MESSAGE } from './formatStreamError'
import { parsePlayStreamEvent } from './parsePlayStreamEvent'

function rawEvent(
  type: string,
  payload: Record<string, unknown>,
  overrides: Record<string, unknown> = {},
) {
  return JSON.stringify({
    schemaVersion: PLAY_STREAM_SCHEMA_VERSION,
    eventId: 1,
    sessionId: 'session_1',
    turnId: 'request_1',
    type,
    payload,
    ...overrides,
  })
}

describe('parsePlayStreamEvent', () => {
  it.each(['', '   ', '[DONE]', '  [DONE]  '])(
    'ignores stream sentinel %j',
    (raw) => {
      expect(parsePlayStreamEvent(raw)).toBeNull()
    },
  )

  it('parses a valid text delta', () => {
    const parsed = parsePlayStreamEvent(rawEvent(
      PLAY_STREAM_EVENT_TYPE.TEXT_DELTA,
      { text: '新的正文' },
    ))

    expect(parsed).toMatchObject({
      schemaVersion: PLAY_STREAM_SCHEMA_VERSION,
      eventId: 1,
      sessionId: 'session_1',
      turnId: 'request_1',
      type: PLAY_STREAM_EVENT_TYPE.TEXT_DELTA,
      payload: { text: '新的正文' },
    })
  })

  it('normalizes error fields without mixing business and HTTP codes', () => {
    const parsed = parsePlayStreamEvent(rawEvent(
      PLAY_STREAM_EVENT_TYPE.ERROR,
      {
        message: null,
        errorCode: 42,
        statusCode: '503',
      },
    ))

    expect(parsed).toMatchObject({
      type: PLAY_STREAM_EVENT_TYPE.ERROR,
      payload: {
        message: DEFAULT_STREAM_ERROR_MESSAGE,
        errorCode: '42',
        statusCode: 503,
      },
    })
  })

  it('drops invalid optional error fields', () => {
    const parsed = parsePlayStreamEvent(rawEvent(
      PLAY_STREAM_EVENT_TYPE.ERROR,
      {
        message: 'provider unavailable',
        errorCode: '',
        statusCode: 'not-a-number',
      },
    ))

    expect(parsed?.payload).toEqual({ message: 'provider unavailable' })
  })

  it.each([
    ['malformed JSON', '{', '无法解析 Play SSE 事件'],
    [
      'schema mismatch',
      rawEvent(PLAY_STREAM_EVENT_TYPE.TEXT_DELTA, { text: 'x' }, { schemaVersion: 'future' }),
      '协议版本不匹配',
    ],
    ['unknown type', rawEvent('unknown', {}), 'type 缺失或无效'],
    [
      'missing required text',
      rawEvent(PLAY_STREAM_EVENT_TYPE.TEXT_DELTA, {}),
      'payload.text 缺失或无效',
    ],
    [
      'invalid committed turn',
      rawEvent(PLAY_STREAM_EVENT_TYPE.TURN_COMPLETED, {
        text: 'done',
        committedTurnId: 0,
      }),
      'committedTurnId 必须是正整数',
    ],
  ])('rejects %s', (_label, raw, expectedMessage) => {
    expect(() => parsePlayStreamEvent(raw)).toThrow(expectedMessage)
  })
})
