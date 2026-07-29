// @vitest-environment jsdom

import { act, renderHook, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import React, { type ReactNode } from 'react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { HISTORY_MESSAGE_ROLE, type HistoryPage } from '@/types/session'
import { createSessionRoomLogger } from '../sessionRoomLogger'
import { HISTORY_REFRESH_MODE } from '../sessionRoomTypes'
import { useSessionHistoryWindow } from './useSessionHistoryWindow'

const getSessionHistoryPageMock = vi.hoisted(() => vi.fn())

vi.mock('@/lib/api/sessions', () => ({
  getSessionHistoryPage: getSessionHistoryPageMock,
}))

function deferred<T>() {
  let resolve!: (value: T) => void
  const promise = new Promise<T>((settle) => {
    resolve = settle
  })
  return { promise, resolve }
}

function historyPage(turnId: number): HistoryPage {
  return {
    turns: [{
      turnId,
      messages: [{
        messageId: turnId * 10,
        turnId,
        seqInTurn: 1,
        role: HISTORY_MESSAGE_ROLE.USER,
        content: `turn ${turnId}`,
        mode: 'neutral',
        metadata: {},
      }],
    }],
    startTurnId: turnId,
    endTurnId: turnId,
    latestTurnId: turnId,
    hasBefore: false,
    hasAfter: false,
    limit: 20,
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

describe('useSessionHistoryWindow session ownership', () => {
  beforeEach(() => {
    getSessionHistoryPageMock.mockReset()
  })

  it('does not apply an old session refresh after the view switches sessions', async () => {
    const staleRefresh = deferred<HistoryPage>()
    getSessionHistoryPageMock.mockImplementation((
      sessionId: string,
      options: { beforeTurnId?: number },
    ) => {
      if (sessionId === 'session_1' && options.beforeTurnId) {
        return staleRefresh.promise
      }
      return Promise.resolve(historyPage(sessionId === 'session_1' ? 1 : 2))
    })
    const logger = createSessionRoomLogger('test')
    logger.info = vi.fn()
    logger.warn = vi.fn()
    logger.error = vi.fn()

    const { result, rerender } = renderHook(
      ({ sessionId }) => useSessionHistoryWindow({ sessionId, logger }),
      {
        initialProps: { sessionId: 'session_1' },
        wrapper: wrapper(),
      },
    )
    await waitFor(() => expect(result.current.activePage?.latestTurnId).toBe(1))

    let oldRefresh!: Promise<boolean>
    await act(async () => {
      oldRefresh = result.current.refreshHistoryWindow({
        mode: HISTORY_REFRESH_MODE.ACTIVE,
      })
    })
    await act(async () => {
      rerender({ sessionId: 'session_2' })
    })
    await waitFor(() => expect(result.current.activePage?.latestTurnId).toBe(2))

    await act(async () => {
      staleRefresh.resolve(historyPage(99))
      await oldRefresh
    })

    expect(result.current.activePage?.latestTurnId).toBe(2)
  })
})
