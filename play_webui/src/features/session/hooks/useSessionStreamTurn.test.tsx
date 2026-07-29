// @vitest-environment jsdom

import { act, renderHook, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import React, {
  type ReactNode,
  useEffect,
  useState,
} from 'react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import {
  TURN_CANCEL_STATUS,
} from '@/types/command'
import type { ContextUsageSnapshot } from '@/types/contextUsage'
import {
  PLAY_STREAM_EVENT_TYPE,
  PLAY_STREAM_SCHEMA_VERSION,
  type PlayStreamEvent,
} from '@/types/stream'
import {
  SESSION_MESSAGE_STATUS,
  SESSION_STREAM_SOURCE,
  SESSION_TIMELINE_ROLE,
  type SessionTimelineMessage,
} from '../sessionRoomTypes'
import { createSessionRoomLogger } from '../sessionRoomLogger'
import {
  type StreamLocalTurnOptions,
  useSessionStreamTurn,
} from './useSessionStreamTurn'

const consumeChatStreamMock = vi.hoisted(() => vi.fn())
const stopSessionStreamMock = vi.hoisted(() => vi.fn())

vi.mock('@/lib/stream/sse', () => ({
  consumeChatStream: consumeChatStreamMock,
}))

vi.mock('@/lib/api/chat', () => ({
  stopSessionStream: stopSessionStreamMock,
}))

type StreamHandlers = {
  signal?: AbortSignal
  onEvent: (event: PlayStreamEvent) => void
}

function deferred<T>() {
  let resolve!: (value: T) => void
  let reject!: (reason?: unknown) => void
  const promise = new Promise<T>((settle, fail) => {
    resolve = settle
    reject = fail
  })
  return { promise, resolve, reject }
}

function event(
  type: PlayStreamEvent['type'],
  payload: Record<string, unknown>,
  eventId = 1,
): PlayStreamEvent {
  return {
    schemaVersion: PLAY_STREAM_SCHEMA_VERSION,
    eventId,
    sessionId: 'session_1',
    turnId: 'turn_session_1',
    type,
    payload,
  } as PlayStreamEvent
}

function turnOptions(turnId: number): StreamLocalTurnOptions {
  const userMessage: SessionTimelineMessage = {
    id: `user-${turnId}`,
    turnId,
    seqInTurn: 1,
    role: SESSION_TIMELINE_ROLE.USER,
    mode: 'neutral',
    content: `user ${turnId}`,
    speaker: {
      name: '玩家',
      fallback: '玩',
      tone: 'player',
    },
  }
  const assistantMessage: SessionTimelineMessage = {
    id: `assistant-${turnId}`,
    turnId,
    seqInTurn: 2,
    role: SESSION_TIMELINE_ROLE.ASSISTANT,
    content: '',
    speaker: {
      name: '叙事者',
      fallback: '叙',
      tone: 'assistant',
    },
    status: SESSION_MESSAGE_STATUS.STREAMING,
  }
  return {
    text: userMessage.content,
    turnId,
    timelineAnchorTurnId: Math.max(0, turnId - 1),
    userMessage,
    assistantMessage,
    source: SESSION_STREAM_SOURCE.SEND,
    mode: 'neutral',
    narrativeStyleId: null,
    successToast: '发送完成',
    failureToast: '发送失败',
  }
}

function wrapper() {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  })
  return function TestWrapper({ children }: { children: ReactNode }) {
    return (
      <QueryClientProvider client={queryClient}>
        {children}
      </QueryClientProvider>
    )
  }
}

function createDependencies() {
  const logger = createSessionRoomLogger('test')
  logger.info = vi.fn()
  logger.warn = vi.fn()
  logger.error = vi.fn()
  return {
    refreshSessionData: vi.fn().mockResolvedValue(true),
    refreshContextPreview: vi.fn().mockResolvedValue({
      available: true,
      usage: null,
    }),
    showToast: vi.fn(),
    logger,
    onExit: vi.fn(),
    onActiveSession: vi.fn(),
    onCommittedNarrativeStyle: vi.fn(),
    onTurnCommitted: vi.fn(),
  }
}

function useHarness(
  sessionId: string,
  dependencies: ReturnType<typeof createDependencies>,
) {
  const [lastTurnUsage, setLastTurnUsage] = useState<ContextUsageSnapshot | null>(null)
  const [localTurnUsageByTurn, setLocalTurnUsageByTurn] = useState<Record<number, ContextUsageSnapshot>>({})
  const [composerText, setComposerText] = useState('')
  const [messages, setMessages] = useState<SessionTimelineMessage[]>([])
  const [forceScrollKey, setForceScrollKey] = useState(0)

  useEffect(() => {
    setMessages([])
  }, [sessionId])

  const stream = useSessionStreamTurn({
    sessionId,
    contextPreviewUsage: null,
    setLastTurnUsage,
    setLocalTurnUsageByTurn,
    setComposerText,
    setLocalMessages: setMessages,
    setForceScrollKey,
    ...dependencies,
  })

  return {
    stream,
    messages,
    composerText,
    lastTurnUsage,
    localTurnUsageByTurn,
    forceScrollKey,
  }
}

describe('useSessionStreamTurn request ownership', () => {
  beforeEach(() => {
    consumeChatStreamMock.mockReset()
    stopSessionStreamMock.mockReset()
    stopSessionStreamMock.mockResolvedValue({
      status: TURN_CANCEL_STATUS.CANCELLED,
      sessionId: 'session_1',
      requestId: 'request_1',
    })
  })

  it('defensively rejects a second direct stream start', async () => {
    const running = deferred<void>()
    consumeChatStreamMock.mockReturnValue(running.promise)
    const dependencies = createDependencies()
    const { result } = renderHook(
      () => useHarness('session_1', dependencies),
      { wrapper: wrapper() },
    )

    let first!: Promise<void>
    await act(async () => {
      first = result.current.stream.streamLocalTurn(turnOptions(1))
      await result.current.stream.streamLocalTurn(turnOptions(2))
    })

    expect(consumeChatStreamMock).toHaveBeenCalledTimes(1)
    expect(dependencies.showToast).toHaveBeenCalledWith('当前仍在生成，请稍后再试')

    await act(async () => {
      running.resolve()
      await first
    })
  })

  it('does not let an old session event or finally mutate a new stream', async () => {
    const calls: Array<{
      handlers: StreamHandlers
      completion: ReturnType<typeof deferred<void>>
    }> = []
    consumeChatStreamMock.mockImplementation((
      _payload: unknown,
      handlers: StreamHandlers,
    ) => {
      const completion = deferred<void>()
      calls.push({ handlers, completion })
      return completion.promise
    })
    const dependencies = createDependencies()
    const { result, rerender } = renderHook(
      ({ sessionId }) => useHarness(sessionId, dependencies),
      {
        initialProps: { sessionId: 'session_1' },
        wrapper: wrapper(),
      },
    )

    let oldStream!: Promise<void>
    await act(async () => {
      oldStream = result.current.stream.streamLocalTurn(turnOptions(1))
    })
    await waitFor(() => expect(calls).toHaveLength(1))

    await act(async () => {
      rerender({ sessionId: 'session_2' })
    })

    let newStream!: Promise<void>
    await act(async () => {
      newStream = result.current.stream.streamLocalTurn(turnOptions(2))
    })
    await waitFor(() => expect(calls).toHaveLength(2))

    await act(async () => {
      calls[0].handlers.onEvent(event(
        PLAY_STREAM_EVENT_TYPE.TEXT_DELTA,
        { text: '旧会话正文' },
      ))
      calls[0].completion.resolve()
      await oldStream
    })

    expect(result.current.stream.sending).toBe(true)
    expect(result.current.messages.some((message) => (
      message.content.includes('旧会话正文')
    ))).toBe(false)

    await act(async () => {
      calls[1].handlers.onEvent(event(
        PLAY_STREAM_EVENT_TYPE.TEXT_DELTA,
        { text: '新会话正文' },
      ))
      calls[1].completion.resolve()
      await newStream
    })

    expect(result.current.stream.sending).toBe(false)
    expect(result.current.messages.some((message) => (
      message.content.includes('新会话正文')
    ))).toBe(true)
  })

  it('keeps partial assistant text when cancellation is confirmed', async () => {
    const running = deferred<void>()
    let handlers!: StreamHandlers
    consumeChatStreamMock.mockImplementation((
      _payload: unknown,
      nextHandlers: StreamHandlers,
    ) => {
      handlers = nextHandlers
      return running.promise
    })
    const dependencies = createDependencies()
    const { result } = renderHook(
      () => useHarness('session_1', dependencies),
      { wrapper: wrapper() },
    )

    let streamPromise!: Promise<void>
    await act(async () => {
      streamPromise = result.current.stream.streamLocalTurn(turnOptions(1))
    })
    await act(async () => {
      handlers.onEvent(event(
        PLAY_STREAM_EVENT_TYPE.TEXT_DELTA,
        { text: '已经生成的部分正文' },
      ))
      await result.current.stream.stopActiveStream()
    })

    const assistant = result.current.messages.find(
      (message) => message.id === 'assistant-1',
    )
    expect(assistant).toMatchObject({
      content: '已经生成的部分正文',
      status: SESSION_MESSAGE_STATUS.DONE,
    })

    await act(async () => {
      running.resolve()
      await streamPromise
    })
  })

  it('renders stopped when the stream settles before cancellation confirmation arrives', async () => {
    const running = deferred<void>()
    const stopResult = deferred<{
      status: typeof TURN_CANCEL_STATUS.CANCELLED
      sessionId: string
      requestId: string
    }>()
    consumeChatStreamMock.mockReturnValue(running.promise)
    stopSessionStreamMock.mockReturnValue(stopResult.promise)
    const dependencies = createDependencies()
    const { result } = renderHook(
      () => useHarness('session_1', dependencies),
      { wrapper: wrapper() },
    )

    let streamPromise!: Promise<void>
    let stopPromise!: Promise<boolean>
    await act(async () => {
      streamPromise = result.current.stream.streamLocalTurn(turnOptions(1))
      stopPromise = result.current.stream.stopActiveStream()
    })
    await act(async () => {
      running.resolve()
      await streamPromise
    })

    expect(result.current.messages.find(
      (message) => message.id === 'assistant-1',
    )?.status).toBe(SESSION_MESSAGE_STATUS.STREAMING)

    await act(async () => {
      stopResult.resolve({
        status: TURN_CANCEL_STATUS.CANCELLED,
        sessionId: 'session_1',
        requestId: 'request_1',
      })
      await stopPromise
    })

    expect(result.current.messages.find(
      (message) => message.id === 'assistant-1',
    )).toMatchObject({
      content: '已停止当前流式响应。',
      status: SESSION_MESSAGE_STATUS.DONE,
    })
    expect(dependencies.showToast).toHaveBeenCalledWith('已停止当前流式响应')
  })

  it('keeps the active stream running when the stop request is stale', async () => {
    const running = deferred<void>()
    let handlers!: StreamHandlers
    consumeChatStreamMock.mockImplementation((
      _payload: unknown,
      nextHandlers: StreamHandlers,
    ) => {
      handlers = nextHandlers
      return running.promise
    })
    stopSessionStreamMock.mockResolvedValue({
      status: TURN_CANCEL_STATUS.STALE,
      sessionId: 'session_1',
      requestId: 'another_request',
    })
    const dependencies = createDependencies()
    const { result } = renderHook(
      () => useHarness('session_1', dependencies),
      { wrapper: wrapper() },
    )

    let streamPromise!: Promise<void>
    await act(async () => {
      streamPromise = result.current.stream.streamLocalTurn(turnOptions(1))
    })
    await act(async () => {
      handlers.onEvent(event(
        PLAY_STREAM_EVENT_TYPE.TEXT_DELTA,
        { text: '生成继续' },
      ))
      await result.current.stream.stopActiveStream()
    })

    expect(handlers.signal?.aborted).toBe(false)
    expect(result.current.stream.sending).toBe(true)
    expect(result.current.messages.find(
      (message) => message.id === 'assistant-1',
    )?.content).toBe('生成继续')
    expect(dependencies.showToast).toHaveBeenCalledWith('当前生成状态已变化，未停止')

    await act(async () => {
      running.resolve()
      await streamPromise
    })
  })

  it('refreshes authoritative state without showing stopped when generation is not running', async () => {
    const running = deferred<void>()
    consumeChatStreamMock.mockReturnValue(running.promise)
    stopSessionStreamMock.mockResolvedValue({
      status: TURN_CANCEL_STATUS.NOT_RUNNING,
      sessionId: 'session_1',
      requestId: 'request_1',
    })
    const dependencies = createDependencies()
    const { result } = renderHook(
      () => useHarness('session_1', dependencies),
      { wrapper: wrapper() },
    )

    let streamPromise!: Promise<void>
    await act(async () => {
      streamPromise = result.current.stream.streamLocalTurn(turnOptions(1))
    })
    await act(async () => {
      await result.current.stream.stopActiveStream()
    })

    expect(dependencies.refreshSessionData).toHaveBeenCalledWith({
      silent: true,
      preserveLocalMessages: true,
    })
    expect(dependencies.showToast).toHaveBeenCalledWith('生成已结束，已刷新状态')
    expect(result.current.messages.find(
      (message) => message.id === 'assistant-1',
    )?.content).not.toBe('已停止当前流式响应。')

    await act(async () => {
      running.resolve()
      await streamPromise
    })
  })

  it('retains received text when a tolerant stream ends without a terminal event', async () => {
    consumeChatStreamMock.mockImplementation(async (
      _payload: unknown,
      handlers: StreamHandlers,
    ) => {
      handlers.onEvent(event(
        PLAY_STREAM_EVENT_TYPE.TEXT_DELTA,
        { text: '没有终态事件也不能丢失' },
      ))
    })
    const dependencies = createDependencies()
    const { result } = renderHook(
      () => useHarness('session_1', dependencies),
      { wrapper: wrapper() },
    )

    await act(async () => {
      await result.current.stream.streamLocalTurn(turnOptions(1))
    })

    expect(dependencies.refreshSessionData).toHaveBeenCalledWith(expect.objectContaining({
      preserveLocalMessages: true,
    }))
    expect(result.current.messages.find(
      (message) => message.id === 'assistant-1',
    )?.content).toBe('没有终态事件也不能丢失')
  })

  it('keeps partial text and reports a provider error without a success refresh', async () => {
    consumeChatStreamMock.mockImplementation(async (
      _payload: unknown,
      handlers: StreamHandlers,
    ) => {
      handlers.onEvent(event(
        PLAY_STREAM_EVENT_TYPE.TEXT_DELTA,
        { text: 'Provider 失败前的正文' },
      ))
      handlers.onEvent(event(
        PLAY_STREAM_EVENT_TYPE.ERROR,
        {
          message: 'Provider 暂时不可用',
          errorCode: 'provider_error',
        },
        2,
      ))
    })
    const dependencies = createDependencies()
    const { result } = renderHook(
      () => useHarness('session_1', dependencies),
      { wrapper: wrapper() },
    )

    await act(async () => {
      await result.current.stream.streamLocalTurn(turnOptions(1))
    })

    expect(dependencies.refreshSessionData).not.toHaveBeenCalled()
    expect(result.current.stream.sending).toBe(false)
    expect(result.current.messages.find(
      (message) => message.id === 'assistant-1',
    )).toMatchObject({
      content: 'Provider 失败前的正文',
      status: SESSION_MESSAGE_STATUS.ERROR,
    })
    expect(result.current.messages.some(
      (message) => message.role === SESSION_TIMELINE_ROLE.ERROR,
    )).toBe(true)
    expect(dependencies.showToast).not.toHaveBeenCalledWith('发送完成')
  })

  it('keeps partial text and unlocks sending after a network interruption', async () => {
    consumeChatStreamMock.mockImplementation(async (
      _payload: unknown,
      handlers: StreamHandlers,
    ) => {
      handlers.onEvent(event(
        PLAY_STREAM_EVENT_TYPE.TEXT_DELTA,
        { text: '断流前已经收到' },
      ))
      throw new Error('网络连接中断')
    })
    const dependencies = createDependencies()
    const { result } = renderHook(
      () => useHarness('session_1', dependencies),
      { wrapper: wrapper() },
    )

    await act(async () => {
      await result.current.stream.streamLocalTurn(turnOptions(1))
    })

    expect(result.current.stream.sending).toBe(false)
    expect(result.current.messages.find(
      (message) => message.id === 'assistant-1',
    )).toMatchObject({
      content: '断流前已经收到',
      status: SESSION_MESSAGE_STATUS.ERROR,
    })
    expect(dependencies.refreshSessionData).not.toHaveBeenCalled()
    expect(dependencies.showToast).toHaveBeenCalledWith('网络连接中断')
  })

  it('preserves partial text when leaving the session view', async () => {
    const running = deferred<void>()
    let handlers!: StreamHandlers
    consumeChatStreamMock.mockImplementation((
      _payload: unknown,
      nextHandlers: StreamHandlers,
    ) => {
      handlers = nextHandlers
      return running.promise
    })
    const dependencies = createDependencies()
    const { result } = renderHook(
      () => useHarness('session_1', dependencies),
      { wrapper: wrapper() },
    )

    let streamPromise!: Promise<void>
    await act(async () => {
      streamPromise = result.current.stream.streamLocalTurn(turnOptions(1))
    })
    await act(async () => {
      handlers.onEvent(event(
        PLAY_STREAM_EVENT_TYPE.TEXT_DELTA,
        { text: '离开前已经收到的正文' },
      ))
      result.current.stream.handleExitSession()
    })

    expect(handlers.signal?.aborted).toBe(true)
    expect(result.current.messages.find(
      (message) => message.id === 'assistant-1',
    )).toMatchObject({
      content: '离开前已经收到的正文',
      status: SESSION_MESSAGE_STATUS.STREAMING,
    })
    expect(dependencies.onExit).toHaveBeenCalledTimes(1)

    await act(async () => {
      running.resolve()
      await streamPromise
    })
  })

  it('retains local content and offers retry when completion refresh fails', async () => {
    consumeChatStreamMock.mockImplementation(async (
      _payload: unknown,
      handlers: StreamHandlers,
    ) => {
      handlers.onEvent(event(
        PLAY_STREAM_EVENT_TYPE.TEXT_DELTA,
        { text: '不会因刷新失败而丢失' },
      ))
      handlers.onEvent(event(
        PLAY_STREAM_EVENT_TYPE.TURN_COMPLETED,
        {
          text: '不会因刷新失败而丢失',
          committedTurnId: 1,
        },
        2,
      ))
    })
    const dependencies = createDependencies()
    dependencies.refreshSessionData
      .mockResolvedValueOnce(false)
      .mockResolvedValueOnce(true)
    const { result } = renderHook(
      () => useHarness('session_1', dependencies),
      { wrapper: wrapper() },
    )

    await act(async () => {
      await result.current.stream.streamLocalTurn(turnOptions(1))
    })

    expect(result.current.stream.refreshRecoveryPending).toBe(true)
    expect(result.current.messages.find(
      (message) => message.id === 'assistant-1',
    )?.content).toBe('不会因刷新失败而丢失')

    await act(async () => {
      await result.current.stream.retryCompletionRefresh()
    })

    expect(result.current.stream.refreshRecoveryPending).toBe(false)
    expect(dependencies.refreshSessionData).toHaveBeenCalledTimes(2)
    expect(dependencies.showToast).toHaveBeenCalledWith('历史已刷新')
  })
})
