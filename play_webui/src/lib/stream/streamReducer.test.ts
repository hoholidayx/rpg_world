import { describe, expect, it } from 'vitest'
import {
  PLAY_STREAM_EVENT_TYPE,
  PLAY_STREAM_SCHEMA_VERSION,
  TIMELINE_ITEM_TYPE,
  type PlayStreamEvent,
} from '@/types/stream'
import {
  createInitialStreamState,
  reducePlayStreamEvent,
} from './streamReducer'

function event(
  type: PlayStreamEvent['type'],
  payload: Record<string, unknown>,
): PlayStreamEvent {
  return {
    schemaVersion: PLAY_STREAM_SCHEMA_VERSION,
    eventId: 1,
    sessionId: 'session_1',
    turnId: 'request_1',
    type,
    payload,
  } as PlayStreamEvent
}

describe('reducePlayStreamEvent', () => {
  it('moves a started turn into connecting state', () => {
    const state = reducePlayStreamEvent(
      createInitialStreamState(),
      event(PLAY_STREAM_EVENT_TYPE.TURN_STARTED, { mode: 'ic' }),
    )

    expect(state.status).toBe('connecting')
    expect(state.debugEvents).toHaveLength(1)
  })

  it('coalesces adjacent assistant text deltas', () => {
    const first = reducePlayStreamEvent(
      createInitialStreamState(),
      event(PLAY_STREAM_EVENT_TYPE.TEXT_DELTA, { text: '雨声' }),
    )
    const second = reducePlayStreamEvent(
      first,
      event(PLAY_STREAM_EVENT_TYPE.TEXT_DELTA, { text: '渐近。' }),
    )

    expect(second.status).toBe('streaming')
    expect(second.timeline).toHaveLength(1)
    expect(second.timeline[0]).toMatchObject({
      type: TIMELINE_ITEM_TYPE.ASSISTANT,
      content: '雨声渐近。',
    })
  })

  it('keeps thinking and tool events as distinct timeline items', () => {
    const thinking = reducePlayStreamEvent(
      createInitialStreamState(),
      event(PLAY_STREAM_EVENT_TYPE.THINKING_DELTA, { text: '判断场景' }),
    )
    const tool = reducePlayStreamEvent(
      thinking,
      event(PLAY_STREAM_EVENT_TYPE.TOOL_RESULT, {
        toolName: 'rp_story_outcome',
        resultPreview: '成功',
      }),
    )

    expect(tool.status).toBe('tool_running')
    expect(tool.timeline.map((item) => [item.type, item.content])).toEqual([
      [TIMELINE_ITEM_TYPE.THINKING, '判断场景'],
      [TIMELINE_ITEM_TYPE.TOOL, '成功'],
    ])
  })

  it('uses the completed payload when no assistant delta exists', () => {
    const state = reducePlayStreamEvent(
      createInitialStreamState(),
      event(PLAY_STREAM_EVENT_TYPE.TURN_COMPLETED, {
        text: '最终正文',
        committedTurnId: 7,
      }),
    )

    expect(state.status).toBe('done')
    expect(state.timeline).toHaveLength(1)
    expect(state.timeline[0]).toMatchObject({
      type: TIMELINE_ITEM_TYPE.ASSISTANT,
      content: '最终正文',
    })
  })

  it('formats a business error without replacing it with an HTTP code', () => {
    const state = reducePlayStreamEvent(
      createInitialStreamState(),
      event(PLAY_STREAM_EVENT_TYPE.ERROR, {
        message: '上下文已满',
        errorCode: 'MAIN_CONTEXT_WINDOW_THRESHOLD_EXCEEDED',
        statusCode: 409,
      }),
    )

    expect(state.status).toBe('error')
    expect(state.timeline.at(-1)).toMatchObject({
      type: TIMELINE_ITEM_TYPE.ERROR,
      content: [
        '错误码：MAIN_CONTEXT_WINDOW_THRESHOLD_EXCEEDED',
        '错误内容：上下文已满',
      ].join('\n'),
      metadata: {
        errorCode: 'MAIN_CONTEXT_WINDOW_THRESHOLD_EXCEEDED',
        errorMessage: '上下文已满',
      },
    })
  })
})
