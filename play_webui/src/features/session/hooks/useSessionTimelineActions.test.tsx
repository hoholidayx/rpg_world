// @vitest-environment jsdom

import { act, renderHook } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import React, { type ReactNode } from 'react'
import { describe, expect, it, vi } from 'vitest'
import { PLAYER_CHARACTER_STATUS, type SessionSummary } from '@/types/session'
import { createSessionRoomLogger } from '../sessionRoomLogger'
import {
  SESSION_TIMELINE_ROLE,
  type SessionTimelineMessage,
} from '../sessionRoomTypes'
import { useSessionTimelineActions } from './useSessionTimelineActions'

function deferred<T>() {
  let resolve!: (value: T) => void
  const promise = new Promise<T>((settle) => {
    resolve = settle
  })
  return { promise, resolve }
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

function session(id: string): SessionSummary {
  return {
    id,
    workspace: 'workspace_1',
    storyId: 1,
    title: id,
    playerCharacterStatus: PLAYER_CHARACTER_STATUS.BOUND,
  }
}

function baseDependencies() {
  return {
    playerCharacter: {
      characterId: 1,
      storyId: 1,
      name: '言琴',
      avatarUrl: '',
      roleLabel: 'PLAYER',
      updatedAt: '2026-07-29T00:00:00Z',
    },
    playerCharacterInvalid: false,
    inputMode: 'neutral' as const,
    narrativeStyleId: null,
    composerText: '向前走',
    contextInputBlockThresholdRatio: 0.9,
    timelineResetKey: 0,
    lastTurnId: 3,
    lastPersistedTurnId: 3,
    sending: false,
    stopping: false,
    setOptimisticTruncateFromTurn: vi.fn(),
    refreshSessionData: vi.fn().mockResolvedValue(true),
    requestConfirm: vi.fn(),
    requireRoleSelection: vi.fn(),
    showToast: vi.fn(),
    logger: createSessionRoomLogger('test'),
  }
}

describe('useSessionTimelineActions turn startup ownership', () => {
  it('allows only one action through asynchronous preflight', async () => {
    const contextPreview = deferred<{
      available: boolean
      usage: null
    }>()
    const refreshContextPreview = vi.fn(() => contextPreview.promise)
    const jumpToLatestHistoryBottom = vi.fn().mockResolvedValue(3)
    const streamLocalTurn = vi.fn().mockResolvedValue(undefined)
    const dependencies = baseDependencies()
    dependencies.logger.info = vi.fn()
    dependencies.logger.warn = vi.fn()
    dependencies.logger.error = vi.fn()

    const { result } = renderHook(
      () => useSessionTimelineActions({
        ...dependencies,
        sessionId: 'session_1',
        session: session('session_1'),
        refreshContextPreview,
        jumpToLatestHistoryBottom,
        streamLocalTurn,
      }),
      { wrapper: wrapper() },
    )

    let first!: Promise<void>
    let second!: Promise<void>
    await act(async () => {
      first = result.current.handleSend()
      second = result.current.handleQuickReply('快速回复')
      contextPreview.resolve({ available: true, usage: null })
      await Promise.all([first, second])
    })

    expect(refreshContextPreview).toHaveBeenCalledTimes(1)
    expect(jumpToLatestHistoryBottom).toHaveBeenCalledTimes(1)
    expect(streamLocalTurn).toHaveBeenCalledTimes(1)
    expect(dependencies.showToast).toHaveBeenCalledWith('当前仍在生成，请稍后再试')
  })

  it('does not allow a history deletion to race an asynchronous turn startup', async () => {
    const contextPreview = deferred<{
      available: boolean
      usage: null
    }>()
    const refreshContextPreview = vi.fn(() => contextPreview.promise)
    const dependencies = baseDependencies()
    dependencies.logger.info = vi.fn()
    dependencies.logger.warn = vi.fn()
    dependencies.logger.error = vi.fn()
    const message: SessionTimelineMessage = {
      id: 'history-31',
      messageId: 31,
      turnId: 3,
      seqInTurn: 1,
      role: SESSION_TIMELINE_ROLE.USER,
      content: '向前走',
      speaker: {
        name: '言琴',
        fallback: '言',
        tone: 'player',
      },
      canDelete: true,
    }
    const { result } = renderHook(
      () => useSessionTimelineActions({
        ...dependencies,
        sessionId: 'session_1',
        session: session('session_1'),
        refreshContextPreview,
        jumpToLatestHistoryBottom: vi.fn().mockResolvedValue(3),
        streamLocalTurn: vi.fn().mockResolvedValue(undefined),
      }),
      { wrapper: wrapper() },
    )

    let send!: Promise<void>
    await act(async () => {
      send = result.current.handleSend()
      result.current.handleDelete(message)
    })

    expect(dependencies.requestConfirm).not.toHaveBeenCalled()
    expect(dependencies.showToast).toHaveBeenCalledWith('当前仍在生成，请稍后再试')

    await act(async () => {
      contextPreview.resolve({ available: true, usage: null })
      await send
    })
  })

  it('abandons an old preflight after switching sessions', async () => {
    const firstContextPreview = deferred<{
      available: boolean
      usage: null
    }>()
    const refreshContextPreview = vi.fn()
      .mockImplementationOnce(() => firstContextPreview.promise)
      .mockResolvedValue({ available: true, usage: null })
    const jumpToLatestHistoryBottom = vi.fn().mockResolvedValue(3)
    const streamLocalTurn = vi.fn().mockResolvedValue(undefined)
    const dependencies = baseDependencies()
    dependencies.logger.info = vi.fn()
    dependencies.logger.warn = vi.fn()
    dependencies.logger.error = vi.fn()

    const { result, rerender } = renderHook(
      ({ sessionId }) => useSessionTimelineActions({
        ...dependencies,
        sessionId,
        session: session(sessionId),
        refreshContextPreview,
        jumpToLatestHistoryBottom,
        streamLocalTurn,
      }),
      {
        initialProps: { sessionId: 'session_1' },
        wrapper: wrapper(),
      },
    )

    let oldAction!: Promise<void>
    await act(async () => {
      oldAction = result.current.handleSend()
    })
    await act(async () => {
      rerender({ sessionId: 'session_2' })
    })
    await act(async () => {
      firstContextPreview.resolve({ available: true, usage: null })
      await oldAction
    })

    expect(streamLocalTurn).not.toHaveBeenCalled()

    await act(async () => {
      await result.current.handleSend()
    })

    expect(streamLocalTurn).toHaveBeenCalledTimes(1)
    expect(refreshContextPreview).toHaveBeenCalledTimes(2)
  })
})
